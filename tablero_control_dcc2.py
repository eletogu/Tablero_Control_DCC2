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
# 1. ESTÉTICA Y CONFIGURACIÓN INSTITUCIONAL
# =========================================================
st.set_page_config(page_title="Dashboard de Control DCC2", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f4f7f9; }
    .stMetric { 
        background-color: #ffffff; padding: 20px; border-radius: 15px; 
        box-shadow: 0 4px 10px rgba(0,0,0,0.08); border-top: 5px solid #003366;
    }
    h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI', sans-serif; }
    .card-alerta { 
        padding: 20px; background-color: #fff3cd; color: #856404; 
        border: 1px solid #ffeeba; border-radius: 10px; margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES TÉCNICAS DE NORMALIZACIÓN ---
def normalizar_texto(t):
    if pd.isna(t) or t == '': return ""
    return "".join((c for c in unicodedata.normalize('NFD', str(t).upper()) if unicodedata.category(c) != 'Mn')).strip()

def normalizar_id(v):
    if pd.isna(v): return ""
    # Limpieza profunda de IDs para evitar fallos en el cruce
    return re.sub(r'[^A-Z0-9]', '', str(v).strip().upper().replace('.0', ''))

@st.cache_data(ttl=600)
def descargar_excel(url, nombre_debug, hoja=None):
    try:
        if not url or not isinstance(url, str) or not url.startswith("http"):
            return f"URL inválida para {nombre_debug}"
        resp = requests.get(url, timeout=35)
        resp.raise_for_status()
        # Intentamos leer la hoja específica si se proporciona
        try:
            df = pd.read_excel(io.BytesIO(resp.content), sheet_name=hoja)
        except:
            df = pd.read_excel(io.BytesIO(resp.content), sheet_name=0)
        return df.dropna(how='all')
    except Exception as e:
        return f"Error en {nombre_debug}: {str(e)}"

# =========================================================
# 2. GESTIÓN DE DATOS Y SEGURIDAD DE ENLACES
# =========================================================

st.markdown("<h1 style='text-align: center;'>📊 TABLERO DE CONTROL ESTRATÉGICO DCC2</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/b/b8/Escudo_de_la_Contralor%C3%ADa_General_de_la_Rep%C3%BAblica_de_Colombia.png", width=120)
    st.header("⚙️ Operaciones")
    if st.button("🔄 Sincronizar con la Nube"):
        st.cache_data.clear()
        st.rerun()
    st.write("---")

# Protección contra KeyError: links_onedrive
links = st.secrets.get("links_onedrive", None)

if not links:
    st.markdown("""
        <div class="card-alerta">
            <h3>⚠️ Configuración Requerida</h3>
            <p>Los enlaces de OneDrive no están configurados correctamente en los secretos de la aplicación.</p>
            <p>Por favor, asegúrese de tener la sección <b>[links_onedrive]</b> definida en los 'Secrets' de Streamlit Cloud.</p>
        </div>
    """, unsafe_allow_html=True)
else:
    config_descarga = {
        "FUIC": (links.get("FUIC"), "PARA ENVIAR"),
        "BIENES": (links.get("BIENES"), None),
        "PROVIDENCIAS": (links.get("PROVIDENCIAS"), None),
        "BUSQUEDA": (links.get("BUSQUEDA_BIENES"), None)
    }
    
    bases_datos = {}
    with st.spinner('Consolidando expedientes de la Dirección...'):
        for clave, (url, hoja) in config_descarga.items():
            if url:
                res = descargar_excel(url, clave, hoja)
                if not isinstance(res, str): 
                    bases_datos[clave] = res
                else:
                    st.sidebar.warning(f"Aviso en {clave}: {res}")

    # =========================================================
    # 3. LÓGICA DE AUDITORÍA (TIEMPOS Y CADUCIDADES)
    # =========================================================
    if "FUIC" in bases_datos:
        df_f = bases_datos["FUIC"]
        df_p = bases_datos.get("PROVIDENCIAS", pd.DataFrame())
        df_b = bases_datos.get("BIENES", pd.DataFrame())
        df_bus = bases_datos.get("BUSQUEDA", pd.DataFrame())

        def buscar_col(df, terminos):
            for c in df.columns:
                if any(t in normalizar_texto(c) for t in terminos): return c
            return None

        # Identificación de columnas con validación de existencia
        c_pcc = buscar_col(df_f, ["PROCESO", "PCC"])
        c_sust = buscar_col(df_f, ["SUSTANCIADOR"])
        c_f_ejec = buscar_col(df_f, ["FECHA EJECUTORIA"])
        c_f_not_mp = buscar_col(df_f, ["FECHA NOT MP", "NOTIFICACION MANDAMIENTO"])
        c_etapa = buscar_col(df_f, ["ETAPA ACTUAL"])

        # Validación de columnas críticas antes de procesar
        columnas_faltantes = []
        if not c_pcc: columnas_faltantes.append("PCC/Proceso")
        if not c_etapa: columnas_faltantes.append("Etapa Actual")

        if columnas_faltantes:
            st.error(f"❌ Error de Estructura: No se encontraron las columnas: {', '.join(columnas_faltantes)} en el archivo FUIC.")
        else:
            # Normalización y preparación
            for d in [df_f, df_p, df_b, df_bus]:
                if not d.empty:
                    cid = buscar_col(d, ["PROCESO", "PCC"])
                    if cid: d['ID_B'] = d[cid].apply(normalizar_id)
                    for col in d.columns:
                        if 'FECHA' in col.upper():
                            d[col] = pd.to_datetime(d[col], errors='coerce')

            hoy = datetime.now()
            data_alertas = []

            for _, row in df_f.iterrows():
                p_id = row.get('ID_B')
                if not p_id: continue
                
                # Acceso seguro a columnas dinámicas
                etapa = str(row.get(c_etapa, "N/A")).upper()
                responsable = row.get(c_sust, "POR ASIGNAR") if c_sust else "N/A"
                
                # --- Fecha Avoco ---
                f_avoco = pd.NA
                if not df_p.empty:
                    c_f_p = buscar_col(df_p, ["FECHA", "FECHA PROVIDENCIA"])
                    c_desc_p = buscar_col(df_p, ["PROVIDENCIA", "AUTO"])
                    if c_desc_p and c_f_p:
                        provs = df_p[df_p['ID_B'] == p_id]
                        av_row = provs[provs[c_desc_p].str.contains("AVOCO", na=False, case=False)]
                        f_avoco = av_row[c_f_p].min() if not av_row.empty else pd.NA
                
                # 1. Alerta Mandamiento
                status_mp = "OK"
                if pd.notna(f_avoco) and "PERSUASIVA" in etapa:
                    meses_trans = (hoy.year - f_avoco.year) * 12 + (hoy.month - f_avoco.month)
                    if meses_trans >= 3: status_mp = "VENCIDO"
                    elif meses_trans >= 2: status_mp = "PRÓXIMO"

                # 2. Fuerza Ejecutoria
                status_fuerza = "OK"
                f_ejec = row.get(c_f_ejec) if c_f_ejec else None
                f_not_mp = row.get(c_f_not_mp) if c_f_not_mp else None
                if pd.notna(f_ejec) and pd.isna(f_not_mp):
                    anios_trans = (hoy - f_ejec).days / 365.25
                    if anios_trans >= 5: status_fuerza = "PERDIDA"
                    elif anios_trans >= 4: status_fuerza = "RIESGO ALTO"

                # 3. Medidas Cautelares
                status_medida = "OK"
                if not df_b.empty:
                    c_tipo_b = buscar_col(df_b, ["TIPO BIEN"])
                    c_f_reg = buscar_col(df_b, ["FECHA PRACTICA", "INSCRIPCION", "REGISTRO"])
                    if c_tipo_b and c_f_reg:
                        b_proc = df_b[df_b['ID_B'] == p_id]
                        inms = b_proc[b_proc[c_tipo_b].str.contains("INMUEBLE", na=False, case=False)]
                        if not inms.empty:
                            f_emb = inms[c_f_reg].min()
                            if pd.notna(f_emb):
                                anios_emb = (hoy - f_emb).days / 365.25
                                if anios_emb >= 10: status_medida = "CADUCADO"
                                elif anios_emb >= 9.5: status_medida = "RENOVAR YA"

                # 4. Búsqueda de Bienes
                status_busq = "OK"
                if not df_bus.empty:
                    c_f_b = buscar_col(df_bus, ["FECHA"])
                    if c_f_b:
                        h_bus = df_bus[df_bus['ID_B'] == p_id]
                        u_b = h_bus[c_f_b].max() if not h_bus.empty else pd.NA
                        if pd.isna(u_b): status_busq = "PENDIENTE"
                        else:
                            m_bus = (hoy.year - u_b.year) * 12 + (hoy.month - u_b.month)
                            if m_bus >= 4: status_busq = "VENCIDA"
                            elif m_bus >= 3: status_busq = "PRÓXIMA"

                data_alertas.append({
                    "PCC": row.get(c_pcc),
                    "Sustanciador": responsable,
                    "Etapa": etapa,
                    "Mandamiento": status_mp,
                    "Fuerza Ejecutoria": status_fuerza,
                    "Medidas Cautelares": status_medida,
                    "Búsqueda Bienes": status_busq
                })

            df_alertas = pd.DataFrame(data_alertas)

            # =========================================================
            # 4. INTERFAZ VISUAL DEL DASHBOARD
            # =========================================================
            with st.sidebar:
                st.subheader("🔍 Filtros de Visualización")
                list_sust = sorted(df_alertas['Sustanciador'].unique())
                sel_sust = st.multiselect("Sustanciador:", list_sust)
                list_etapa = sorted(df_alertas['Etapa'].unique())
                sel_etapa = st.multiselect("Etapa Procesal:", list_etapa)
                
                df_final = df_alertas.copy()
                if sel_sust: df_final = df_final[df_final['Sustanciador'].isin(sel_sust)]
                if sel_etapa: df_final = df_final[df_final['Etapa'].isin(sel_etapa)]

            # Fila Superior de KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Pérdida de Fuerza", len(df_final[df_final['Fuerza Ejecutoria'] != "OK"]))
            c2.metric("Medidas x Renovar", len(df_final[df_final['Medidas Cautelares'] != "OK"]))
            c3.metric("Búsquedas Vencidas", len(df_final[df_final['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])]))
            c4.metric("Términos MP Vencidos", len(df_final[df_final['Mandamiento'] == "VENCIDO"]))

            st.write("---")
            
            # Paneles Detallados
            tab_alertas, tab_gestores = st.tabs(["🚨 Alertas de Acción Inmediata", "👨‍⚖️ Gestión por Sustanciador"])
            
            with tab_alertas:
                mask_critico = (df_final['Mandamiento'] != "OK") | \
                               (df_final['Fuerza Ejecutoria'] != "OK") | \
                               (df_final['Medidas Cautelares'] != "OK") | \
                               (df_final['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"]))
                
                df_crit = df_final[mask_critico]
                if not df_crit.empty:
                    st.dataframe(df_crit, use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Todos los procesos están dentro de los términos legales.")

            with tab_gestores:
                stats = df_final.groupby('Sustanciador').agg({
                    'Fuerza Ejecutoria': lambda x: (x != 'OK').sum(),
                    'Medidas Cautelares': lambda x: (x != 'OK').sum(),
                    'Búsqueda Bienes': lambda x: (x.isin(['VENCIDA', 'PENDIENTE'])).sum()
                }).rename(columns={'Fuerza Ejecutoria': 'Fuerza', 'Medidas Cautelares': 'Medidas', 'Búsqueda Bienes': 'Búsquedas'})
                st.bar_chart(stats)
    else:
        st.error("Error Crítico: No se pudo cargar el archivo FUIC. Verifique los enlaces.")
