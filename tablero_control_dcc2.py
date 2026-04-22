# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
import io
import requests
from datetime import datetime

# =========================================================
# 1. ESTÉTICA Y CONFIGURACIÓN (COLORES CGR)
# =========================================================
st.set_page_config(page_title="Dashboard de Control DCC2", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f4f7f9; }
    .stMetric { 
        background-color: #ffffff; padding: 20px; border-radius: 15px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-top: 5px solid #003366;
    }
    h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI Semibold', sans-serif; }
    .stAlert { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES DE LIMPIEZA ---
def normalizar_id(v):
    if pd.isna(v): return ""
    return re.sub(r'[^A-Z0-9]', '', str(v).strip().upper().replace('.0', ''))

@st.cache_data(ttl=600)
def descargar_excel(url, nombre_debug, hoja):
    try:
        resp = requests.get(url, timeout=35)
        resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(resp.content), sheet_name=hoja)
        return df.dropna(how='all')
    except Exception as e:
        return f"Error en {nombre_debug} (Hoja: {hoja}): {str(e)}"

# =========================================================
# 2. CARGA DE DATOS (ESTRUCTURA EXACTA DCC2)
# =========================================================

st.markdown("<h1 style='text-align: center;'>📊 TABLERO DE CONTROL ESTRATÉGICO DCC2</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/b/b8/Escudo_de_la_Contralor%C3%ADa_General_de_la_Rep%C3%BAblica_de_Colombia.png", width=120)
    st.header("⚙️ Gestión de Datos")
    if st.button("🔄 Sincronizar Bases"):
        st.cache_data.clear()
        st.rerun()
    st.write("---")

links = st.secrets.get("links_onedrive", None)

if not links:
    st.warning("⚠️ Configure 'links_onedrive' en los Secrets de Streamlit.")
else:
    # Carga dirigida según especificaciones del usuario
    bases = {
        "FUIC": descargar_excel(links.get("FUIC"), "FUIC", "PARA ENVIAR"),
        "PROVIDENCIAS": descargar_excel(links.get("PROVIDENCIAS"), "PROVIDENCIAS", "PROVIDENCIAS"),
        "BIENES": descargar_excel(links.get("BIENES"), "BIENES IDENTIFICADOS", "BIENES IDENTIFICADOS"),
        "BUSQUEDAS": descargar_excel(links.get("BUSQUEDA_BIENES"), "BUSQUEDA DE BIENES", "BUSQUEDA DE BIENES (SOLICITUDES")
    }

    if all(not isinstance(v, str) for v in bases.values()):
        # --- PREPARACIÓN DE DATAFRAMES ---
        df_f, df_p, df_b, df_bus = bases["FUIC"], bases["PROVIDENCIAS"], bases["BIENES"], bases["BUSQUEDAS"]
        
        # Normalización de IDs (No. Proceso)
        for df in [df_f, df_p, df_b, df_bus]:
            df['ID_LINK'] = df['No. Proceso'].apply(normalizar_id)
            for col in df.columns:
                if 'FECHA' in col.upper() or 'SOLICITUD' in col.upper():
                    df[col] = pd.to_datetime(df[col], errors='coerce')

        # Lógica de Etapa Actual (Buscamos la última columna que empiece por 'Etapa')
        cols_etapas = [c for c in df_f.columns if 'ETAPA' in c.upper()]
        def get_current_stage(row):
            for col in reversed(cols_etapas):
                val = str(row[col]).strip() if pd.notna(row[col]) else ""
                if val: return val
            return "DESCONOCIDA"
        
        df_f['ETAPA_REAL'] = df_f.apply(get_current_stage, axis=1)

        # =========================================================
        # 3. MOTOR DE AUDITORÍA JURÍDICA
        # =========================================================
        hoy = datetime.now()
        alertas = []

        for _, row in df_f.iterrows():
            pid = row['ID_LINK']
            sust = row.get('Sustanciador a Cargo', 'SIN ASIGNAR')
            etapa = row['ETAPA_REAL'].upper()
            
            # --- 1. Alerta Mandamiento (3 meses desde Avoco) ---
            alerta_mp = "OK"
            provs = df_p[df_p['ID_LINK'] == pid]
            avoco_row = provs[provs['Nombre Providencia'].str.contains("AVOCO", na=False, case=False)]
            f_avoco = avoco_row['Fecha Providencia'].min() if not avoco_row.empty else pd.NA
            
            if pd.notna(f_avoco) and "PERSUASIVA" in etapa:
                meses = (hoy.year - f_avoco.year) * 12 + (hoy.month - f_avoco.month)
                if meses >= 3: alerta_mp = "VENCIDO"
                elif meses >= 2: alerta_mp = "CRÍTICO"

            # --- 2. Fuerza Ejecutoria (5 años) ---
            alerta_fuerza = "OK"
            f_ejec = row.get('Fecha Ejecutoria')
            f_not_mp = row.get('Fecha Not MP')
            if pd.notna(f_ejec) and pd.isna(f_not_mp):
                anios = (hoy - f_ejec).days / 365.25
                if anios >= 5: alerta_fuerza = "PERDIDA"
                elif anios >= 4: alerta_fuerza = "RIESGO ALTO"

            # --- 3. Medidas Cautelares (10 años - Inmuebles) ---
            alerta_medida = "OK"
            b_proc = df_b[df_b['ID_LINK'] == pid]
            col_t_b = 'Tipo Bien Identificado (Inmueble, Vehículo, Mueble, Cuenta Bancaría, Otros)'
            inms = b_proc[b_proc[col_t_b].str.contains("INMUEBLE", na=False, case=False)]
            if not inms.empty:
                f_emb = inms['Fecha Práctica, Inscripción o Registro Embargo'].min()
                if pd.notna(f_emb):
                    anios_emb = (hoy - f_emb).days / 365.25
                    if anios_emb >= 10: alerta_medida = "CADUCADO"
                    elif anios_emb >= 9.5: alerta_medida = "RENOVAR YA"

            # --- 4. Búsqueda de Bienes (4 meses) ---
            alerta_busq = "OK"
            bus_proc = df_bus[df_bus['ID_LINK'] == pid]
            f_ult_bus = bus_proc['Fecha Solicitud'].max() if not bus_proc.empty else pd.NA
            if pd.isna(f_ult_bus): alerta_busq = "PENDIENTE"
            else:
                m_bus = (hoy.year - f_ult_bus.year) * 12 + (hoy.month - f_ult_bus.month)
                if m_bus >= 4: alerta_busq = "VENCIDA"
                elif m_bus >= 3: alerta_busq = "PRÓXIMA"

            alertas.append({
                "No. Proceso": row['No. Proceso'],
                "Sustanciador": sust,
                "Etapa Actual": etapa,
                "Mandamiento": alerta_mp,
                "Fuerza Ejecutoria": alerta_fuerza,
                "Medidas (Inm)": alerta_medida,
                "Búsqueda Bienes": alerta_busq
            })

        df_alertas = pd.DataFrame(alertas)

        # =========================================================
        # 4. DASHBOARD VISUAL
        # =========================================================
        with st.sidebar:
            st.subheader("🔍 Filtros Operativos")
            sel_sust = st.multiselect("Sustanciador:", sorted(df_alertas['Sustanciador'].unique()))
            df_final = df_alertas[df_alertas['Sustanciador'].isin(sel_sust)] if sel_sust else df_alertas

        # KPIs superiores
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Riesgo Fuerza", len(df_final[df_final['Fuerza Ejecutoria'] != "OK"]))
        c2.metric("Medidas x Renovar", len(df_final[df_final['Medidas (Inm)'] != "OK"]))
        c3.metric("Búsquedas Vencidas", len(df_final[df_final['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])]))
        c4.metric("Términos MP", len(df_final[df_final['Mandamiento'] != "OK"]))

        st.write("---")
        t1, t2 = st.tabs(["🚨 Alertas Críticas", "📊 Carga por Funcionario"])
        
        with t1:
            st.subheader("Expedientes con términos próximos a vencer o vencidos")
            mask = (df_final['Mandamiento'] != "OK") | (df_final['Fuerza Ejecutoria'] != "OK") | \
                   (df_final['Medidas (Inm)'] != "OK") | (df_final['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"]))
            st.dataframe(df_final[mask], use_container_width=True, hide_index=True)

        with t2:
            st.subheader("Distribución de Alertas")
            stats = df_final.groupby('Sustanciador').agg({
                'Fuerza Ejecutoria': lambda x: (x != 'OK').sum(),
                'Búsqueda Bienes': lambda x: (x.isin(['VENCIDA', 'PENDIENTE'])).sum()
            }).rename(columns={'Fuerza Ejecutoria': 'Fuerza', 'Búsqueda Bienes': 'Búsquedas'})
            st.bar_chart(stats)
    else:
        st.error("Error al cargar las hojas. Verifique los nombres: 'PARA ENVIAR', 'PROVIDENCIAS', 'BIENES IDENTIFICADOS', 'BUSQUEDA DE BIENES (SOLICITUDES'.")
