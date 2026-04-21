# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
import io
import requests
from datetime import datetime, timedelta

# =========================================================
# 1. CONFIGURACIÓN E IDENTIDAD INSTITUCIONAL
# =========================================================
st.set_page_config(page_title="Dashboard de Control DCC2", layout="wide")

# Estilos CSS para simular entorno Power BI con toques de la CGR
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { 
        background-color: #ffffff; padding: 15px; border-radius: 10px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-top: 4px solid #003366;
    }
    h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. FUNCIONES DE APOYO (NORMALIZACIÓN Y CARGA)
# =========================================================

def normalizar_texto(t):
    if pd.isna(t) or t == '': return ""
    return "".join((c for c in unicodedata.normalize('NFD', str(t).upper()) if unicodedata.category(c) != 'Mn')).strip()

def normalizar_id(v):
    if pd.isna(v): return ""
    return re.sub(r'[^A-Z0-9]', '', str(v).strip().upper().replace('.0', ''))

@st.cache_data(ttl=600)
def descargar_excel(url, nombre_debug, hoja=None):
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(resp.content), sheet_name=hoja if hoja else 0)
        return df.dropna(how='all')
    except Exception as e:
        return f"Error en {nombre_debug}: {str(e)}"

# =========================================================
# 3. CARGA DE DATOS DESDE ONEDRIVE
# =========================================================

st.markdown("<h1 style='text-align: center;'>📊 TABLERO DE CONTROL Y ALERTAS TEMPRANAS DCC2</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/b/b8/Escudo_de_la_Contralor%C3%ADa_General_de_la_Rep%C3%BAblica_de_Colombia.png", width=100)
    st.header("⚙️ Sincronización")
    if st.button("🔄 Actualizar Datos Real-Time"):
        st.cache_data.clear()
        st.rerun()
    
    st.write("---")
    st.info("Este tablero monitorea los términos legales de Mandamiento, Fuerza Ejecutoria, Medidas y Búsquedas.")

# Carga de datos usando st.secrets
datos = {}
if "links_onedrive" in st.secrets:
    links = st.secrets["links_onedrive"]
    config = {
        "FUIC": (links.get("FUIC"), "PARA ENVIAR"),
        "BIENES": (links.get("BIENES"), None),
        "PROVIDENCIAS": (links.get("PROVIDENCIAS"), None),
        "BUSQUEDA": (links.get("BUSQUEDA_BIENES"), None)
    }
    with st.spinner('Consolidando inteligencia de procesos...'):
        for clave, (url, hoja) in config.items():
            if url:
                res = descargar_excel(url, clave, hoja)
                if not isinstance(res, str): datos[clave] = res

# =========================================================
# 4. MOTOR DE ALERTAS Y LÓGICA DE NEGOCIO
# =========================================================

if "FUIC" in datos:
    df_f = datos["FUIC"]
    df_p = datos.get("PROVIDENCIAS", pd.DataFrame())
    df_b = datos.get("BIENES", pd.DataFrame())
    df_bus = datos.get("BUSQUEDA", pd.DataFrame())

    def buscar_col(df, terminos):
        for c in df.columns:
            if any(t in normalizar_texto(c) for t in terminos): return c
        return None

    # Columnas Clave
    c_pcc = buscar_col(df_f, ["PROCESO", "PCC"])
    c_sust = buscar_col(df_f, ["SUSTANCIADOR"])
    c_f_ejec = buscar_col(df_f, ["FECHA EJECUTORIA"])
    c_f_not_mp = buscar_col(df_f, ["FECHA NOT MP", "NOTIFICACION MANDAMIENTO"])
    c_etapa = buscar_col(df_f, ["ETAPA ACTUAL"])

    # Normalización
    for df in [df_f, df_p, df_b, df_bus]:
        cid = buscar_col(df, ["PROCESO", "PCC"])
        if cid: df['ID_B'] = df[cid].apply(normalizar_id)
        for col in df.columns:
            if 'FECHA' in col.upper():
                df[col] = pd.to_datetime(df[col], errors='coerce')

    hoy = datetime.now()
    alertas_lista = []

    for idx, row in df_f.iterrows():
        pid = row['ID_B']
        etapa = str(row.get(c_etapa, "")).upper()
        sustanciador = row.get(c_sust, "SIN ASIGNAR")
        
        # --- BUSCAR FECHA AVOCO (Base para Mandamiento) ---
        provs_proc = df_p[df_p['ID_B'] == pid] if not df_p.empty else pd.DataFrame()
        c_f_prov = buscar_col(df_p, ["FECHA", "FECHA PROVIDENCIA"])
        c_desc_prov = buscar_col(df_p, ["PROVIDENCIA", "AUTO"])
        
        avoco_row = provs_proc[provs_proc[c_desc_prov].str.contains("AVOCO", na=False, case=False)] if c_desc_prov else pd.DataFrame()
        fecha_avoco = avoco_row[c_f_prov].min() if not avoco_row.empty else pd.NA
        
        # 1. TRANSICIÓN A MANDAMIENTO (3 MESES DESDE AVOCO)
        status_mp = "OK"
        if pd.notna(fecha_avoco) and "PERSUASIVA" in etapa:
            meses_desde_avoco = (hoy.year - fecha_avoco.year) * 12 + (hoy.month - fecha_avoco.month)
            if meses_desde_avoco >= 3: status_mp = "VENCIDO"
            elif meses_desde_avoco >= 2: status_mp = "CRITICO"

        # 2. FUERZA EJECUTORIA (5 AÑOS)
        f_ejecutoria = row.get(c_f_ejec)
        f_not_mp = row.get(c_f_not_mp)
        status_fuerza = "OK"
        if pd.notna(f_ejecutoria) and pd.isna(f_not_mp):
            anios_ejec = (hoy - f_ejecutoria).days / 365.25
            if anios_ejec >= 5: status_fuerza = "PERDIDA"
            elif anios_ejec >= 4: status_fuerza = "RIESGO ALTO"

        # 3. MEDIDAS CAUTELARES (10 AÑOS - INMUEBLES)
        bienes_proc = df_b[df_b['ID_B'] == pid] if not df_b.empty else pd.DataFrame()
        c_tipo_b = buscar_col(df_b, ["TIPO BIEN"])
        c_f_emb = buscar_col(df_b, ["FECHA PRACTICA", "INSCRIPCION", "REGISTRO"])
        
        inmuebles = bienes_proc[bienes_proc[c_tipo_b].str.contains("INMUEBLE", na=False, case=False)] if c_tipo_b else pd.DataFrame()
        status_medida = "OK"
        if not inmuebles.empty and c_f_emb:
            fecha_embargo = inmuebles[c_f_emb].min()
            if pd.notna(fecha_embargo):
                anios_emb = (hoy - fecha_embargo).days / 365.25
                if anios_emb >= 10: status_medida = "CADUCADO"
                elif anios_emb >= 9.5: status_medida = "RENOVAR YA"

        # 4. BÚSQUEDA DE BIENES (4 MESES)
        busquedas_proc = df_bus[df_bus['ID_B'] == pid] if not df_bus.empty else pd.DataFrame()
        c_f_busq = buscar_col(df_bus, ["FECHA"])
        ultima_busq = busquedas_proc[c_f_busq].max() if not busquedas_proc.empty and c_f_busq else pd.NA
        
        status_busq = "OK"
        if pd.isna(ultima_busq): status_busq = "PENDIENTE"
        else:
            meses_busq = (hoy.year - ultima_busq.year) * 12 + (hoy.month - ultima_busq.month)
            if meses_busq >= 4: status_busq = "VENCIDA"
            elif meses_busq >= 3: status_busq = "PROXIMA"

        alertas_lista.append({
            "PCC": row.get(c_pcc),
            "Sustanciador": sustanciador,
            "Etapa": etapa,
            "Mandamiento": status_mp,
            "Fuerza Ejecutoria": status_fuerza,
            "Medidas Cautelares": status_medida,
            "Búsqueda Bienes": status_busq
        })

    df_alertas = pd.DataFrame(alertas_lista)

    # =========================================================
    # 5. VISUALIZACIÓN DEL DASHBOARD
    # =========================================================

    with st.sidebar:
        st.write("---")
        st.subheader("🔍 Filtros de Control")
        sel_sust = st.multiselect("Sustanciador:", sorted(df_alertas['Sustanciador'].unique()))
        sel_etapa = st.multiselect("Etapa Procesal:", sorted(df_alertas['Etapa'].unique()))
        
        df_filtrado = df_alertas.copy()
        if sel_sust: df_filtrado = df_filtrado[df_filtrado['Sustanciador'].isin(sel_sust)]
        if sel_etapa: df_filtrado = df_filtrado[df_filtrado['Etapa'].isin(sel_etapa)]

    # --- KPI GENERALES ---
    c1, c2, c3 = st.columns(3)
    with c1:
        riesgo_fuerza = len(df_filtrado[df_filtrado['Fuerza Ejecutoria'] != "OK"])
        st.metric("Riesgo Fuerza Ejecutoria", riesgo_fuerza, delta="Crítico", delta_color="inverse")
    with c2:
        renovar = len(df_filtrado[df_filtrado['Medidas Cautelares'] != "OK"])
        st.metric("Medidas por Renovar", renovar, delta="Urgente", delta_color="inverse")
    with c3:
        busq_pend = len(df_filtrado[df_filtrado['Búsqueda Bienes'].isin(["PENDIENTE", "VENCIDA"])])
        st.metric("Búsquedas Pendientes", busq_pend, delta="Retraso")

    # --- PANEL DE ALERTAS CRÍTICAS ---
    st.write("---")
    st.subheader("🚨 Panel de Alertas Críticas")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.write("**⚖️ Términos de Mandamiento y Fuerza**")
        criticos = df_filtrado[(df_filtrado['Mandamiento'] != "OK") | (df_filtrado['Fuerza Ejecutoria'] != "OK")]
        if not criticos.empty:
            st.dataframe(criticos[['PCC', 'Sustanciador', 'Etapa', 'Mandamiento', 'Fuerza Ejecutoria']], hide_index=True)
        else:
            st.success("Términos de ley al día en esta selección.")

    with col_b:
        st.write("**🏠 Garantías y Búsqueda de Bienes**")
        riesgo_bienes = df_filtrado[(df_filtrado['Medidas Cautelares'] != "OK") | (df_filtrado['Búsqueda Bienes'].isin(["PENDIENTE", "VENCIDA"]))]
        if not riesgo_bienes.empty:
            st.dataframe(riesgo_bienes[['PCC', 'Sustanciador', 'Medidas Cautelares', 'Búsqueda Bienes']], hide_index=True)
        else:
            st.success("Investigación patrimonial al día.")

    # --- ESTADÍSTICAS ---
    st.write("---")
    st.subheader("📈 Alertas por Sustanciador")
    stats_sust = df_filtrado.groupby('Sustanciador').agg({
        'Mandamiento': lambda x: (x == 'VENCIDO').sum(),
        'Fuerza Ejecutoria': lambda x: (x != 'OK').sum(),
        'Búsqueda Bienes': lambda x: (x == 'VENCIDA').sum()
    }).rename(columns={'Mandamiento': 'Mandamiento Vencido', 'Fuerza Ejecutoria': 'Riesgo Fuerza', 'Búsqueda Bienes': 'Búsquedas Vencidas'})
    st.bar_chart(stats_sust)

    with st.expander("📄 Ver Inventario Completo"):
        st.dataframe(df_filtrado, use_container_width=True)

else:
    st.error("❌ No se detectaron las fuentes de datos. Verifique los links en Secrets.")