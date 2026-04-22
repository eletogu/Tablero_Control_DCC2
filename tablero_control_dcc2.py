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
# 1. ESTÉTICA Y CONFIGURACIÓN (COLORES INSTITUCIONALES)
# =========================================================
st.set_page_config(page_title="Dashboard de Control DCC2", layout="wide")

# Estilos CSS personalizados para simular entorno profesional CGR
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { 
        background-color: #ffffff; padding: 20px; border-radius: 15px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-top: 5px solid #003366;
    }
    h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI Semibold', sans-serif; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 600; margin-top: 5px; }
    .ficha-detalle {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 10px solid #003366; box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .status-alert { font-weight: bold; padding: 2px 6px; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZACIÓN DE ESTADO DE SESIÓN ---
if 'filtro_alerta' not in st.session_state:
    st.session_state.filtro_alerta = "TODAS"

# --- FUNCIONES DE LIMPIEZA Y EXTRACCIÓN ---
def normalizar_id(v):
    if pd.isna(v): return ""
    return re.sub(r'[^A-Z0-9]', '', str(v).strip().upper().replace('.0', ''))

def extraer_fecha_renovacion(texto, tipo):
    """
    Detecta 'Renovación X dd/mm/aaaa' en la columna Observaciones
    """
    if pd.isna(texto): return None
    patron = f"RENOVACION {tipo}\\s+(\\d{{2}}/\\d{{2}}/\\d{{4}})"
    match = re.search(patron, str(texto).upper())
    if match:
        try:
            return datetime.strptime(match.group(1), "%d/%m/%Y")
        except:
            return None
    return None

@st.cache_data(ttl=600)
def descargar_excel(url, nombre_debug, hoja):
    try:
        resp = requests.get(url, timeout=40)
        resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(resp.content), sheet_name=hoja)
        return df.dropna(how='all')
    except Exception as e:
        return f"Error en {nombre_debug} (Hoja: {hoja}): {str(e)}"

# =========================================================
# 2. CARGA Y PROCESAMIENTO DE DATOS
# =========================================================

st.markdown("<h1 style='text-align: center;'>📊 CENTRO DE CONTROL OPERATIVO DCC2</h1>", unsafe_allow_html=True)

links = st.secrets.get("links_onedrive", None)

if not links:
    st.warning("⚠️ Configure los enlaces en los 'Secrets' de Streamlit bajo la sección [links_onedrive].")
else:
    with st.spinner('Actualizando inteligencia de procesos...'):
        bases = {
            "FUIC": descargar_excel(links.get("FUIC"), "FUIC", "PARA ENVIAR"),
            "PROVIDENCIAS": descargar_excel(links.get("PROVIDENCIAS"), "PROVIDENCIAS", "PROVIDENCIAS"),
            "BIENES": descargar_excel(links.get("BIENES"), "BIENES IDENTIFICADOS", "BIENES IDENTIFICADOS"),
            # Corregido: Nombre exacto de la hoja sin el paréntesis de cierre
            "BUSQUEDAS": descargar_excel(links.get("BUSQUEDA_BIENES"), "BUSQUEDA DE BIENES", "BUSQUEDA DE BIENES (SOLICITUDES")
        }

    if all(not isinstance(v, str) for v in bases.values()):
        df_f, df_p, df_b, df_bus = bases["FUIC"], bases["PROVIDENCIAS"], bases["BIENES"], bases["BUSQUEDAS"]
        
        # Unificación de Identificadores y Fechas
        for df in [df_f, df_p, df_b, df_bus]:
            # Evitar error si hay columnas duplicadas en Excel (toma la primera)
            if 'No. Proceso' in df.columns:
                df['ID_LINK'] = df['No. Proceso'].iloc[:, 0].apply(normalizar_id) if isinstance(df['No. Proceso'], pd.DataFrame) else df['No. Proceso'].apply(normalizar_id)
            
            for col in df.columns:
                if any(k in col.upper() for k in ['FECHA', 'SOLICITUD', 'REGISTRO', 'PRACTICA']):
                    df[col] = pd.to_datetime(df[col], errors='coerce')

        # Lógica de Etapa Actual Dinámica
        cols_etapas = [c for c in df_f.columns if 'ETAPA' in c.upper()]
        def get_current_stage(row):
            for col in reversed(cols_etapas):
                val = str(row[col]).strip() if pd.notna(row[col]) else ""
                if val: return val
            return "NO REGISTRA"
        df_f['ETAPA_REAL'] = df_f.apply(get_current_stage, axis=1)

        # --- MOTOR DE AUDITORÍA JURÍDICA ---
        hoy = datetime.now()
        alertas = []

        for _, row in df_f.iterrows():
            pid = row['ID_LINK']
            etapa = str(row['ETAPA_REAL']).upper()
            
            # 1. Alerta Mandamiento (3 meses desde Avoco en Persuasiva)
            alerta_mp = "OK"
            provs = df_p[df_p['ID_LINK'] == pid]
            col_nom_prov = 'Nombre Providencia'
            if col_nom_prov in provs.columns:
                nombres = provs[col_nom_prov].iloc[:, 0] if isinstance(provs[col_nom_prov], pd.DataFrame) else provs[col_nom_prov]
                avoco_mask = nombres.str.contains("AVOCO", na=False, case=False)
                avoco_row = provs[avoco_mask]
                
                col_fecha_prov = 'Fecha Providencia'
                fechas_p = avoco_row[col_fecha_prov].iloc[:, 0] if isinstance(avoco_row[col_fecha_prov], pd.DataFrame) else avoco_row[col_fecha_prov]
                f_avoco = fechas_p.min() if not avoco_row.empty else pd.NaT
                
                if pd.notna(f_avoco) and hasattr(f_avoco, 'year') and "PERSUASIVA" in etapa:
                    meses = (hoy.year - f_avoco.year) * 12 + (hoy.month - f_avoco.month)
                    if meses >= 3: alerta_mp = "VENCIDO"
                    elif meses >= 2: alerta_mp = "CRÍTICO"

            # 2. Fuerza Ejecutoria (5 años)
            alerta_fuerza = "OK"
            f_ejec = row['Fecha Ejecutoria'].iloc[0] if isinstance(row.get('Fecha Ejecutoria'), pd.Series) else row.get('Fecha Ejecutoria')
            f_not_mp = row['Fecha Not MP'].iloc[0] if isinstance(row.get('Fecha Not MP'), pd.Series) else row.get('Fecha Not MP')
            
            if pd.notna(f_ejec) and pd.isna(f_not_mp) and hasattr(f_ejec, 'year'):
                anios_trans = (hoy - f_ejec).days / 365.25
                if anios_trans >= 5: alerta_fuerza = "PERDIDA"
                elif anios_trans >= 4: alerta_fuerza = "RIESGO ALTO"

            # 3. Medidas Cautelares (Lógica Multi-Bien e Inmuebles)
            alerta_medida = "OK"
            b_proc = df_b[df_b['ID_LINK'] == pid]
            col_t_b = 'Tipo Bien Identificado (Inmueble, Vehículo, Mueble, Cuenta Bancaría, Otros)'
            tipos_b = b_proc[col_t_b].iloc[:, 0] if isinstance(b_proc[col_t_b], pd.DataFrame) else b_proc[col_t_b]
            inms = b_proc[tipos_b.str.contains("INMUEBLE", na=False, case=False)]
            
            if not inms.empty:
                vencimientos_inm = []
                col_f_reg = 'Fecha Práctica, Inscripción o Registro Embargo'
                for _, inmueble in inms.iterrows():
                    f_reg = inmueble[col_f_reg].iloc[0] if isinstance(inmueble.get(col_f_reg), pd.Series) else inmueble.get(col_f_reg)
                    obs = inmueble.get('OBSERVACIONES', '')
                    
                    f_renov2 = extraer_fecha_renovacion(obs, "2")
                    f_renov1 = extraer_fecha_renovacion(obs, "1")
                    
                    if pd.notna(f_renov2):
                        vencimiento = f_renov2 + timedelta(days=5*365.25)
                    elif pd.notna(f_renov1):
                        vencimiento = f_renov1 + timedelta(days=5*365.25)
                    elif pd.notna(f_reg) and hasattr(f_reg, 'year'):
                        vencimiento = f_reg + timedelta(days=10*365.25)
                    else:
                        continue
                    vencimientos_inm.append(vencimiento)
                
                if vencimientos_inm:
                    f_venc_final = min(vencimientos_inm)
                    anios_rest = (f_venc_final - hoy).days / 365.25
                    if hoy > f_venc_final: alerta_medida = "CADUCADO"
                    elif anios_rest <= 0.5: alerta_medida = "RENOVAR YA"

            # 4. Búsqueda de Bienes (4 meses)
            alerta_busq = "OK"
            bus_proc = df_bus[df_bus['ID_LINK'] == pid]
            col_f_bus = 'Fecha Solicitud'
            f_bus_series = bus_proc[col_f_bus].iloc[:, 0] if isinstance(bus_proc.get(col_f_bus), pd.DataFrame) else bus_proc.get(col_f_bus)
            f_ult_bus = f_bus_series.max() if not bus_proc.empty else pd.NaT
            
            if pd.isna(f_ult_bus): alerta_busq = "PENDIENTE"
            elif hasattr(f_ult_bus, 'year'):
                m_bus = (hoy.year - f_ult_bus.year) * 12 + (hoy.month - f_ult_bus.month)
                if m_bus >= 4: alerta_busq = "VENCIDA"
                elif m_bus >= 3: alerta_busq = "PRÓXIMA"

            alertas.append({
                "No. Proceso": row['No. Proceso'].iloc[0] if isinstance(row['No. Proceso'], pd.Series) else row['No. Proceso'],
                "Sustanciador": responsable if isinstance((responsable := row.get('Sustanciador a Cargo')), str) else (responsable.iloc[0] if isinstance(responsable, pd.Series) else "N/A"),
                "Etapa Actual": etapa,
                "Mandamiento": alerta_mp,
                "Fuerza Ejecutoria": alerta_fuerza,
                "Medidas (Inm)": alerta_medida,
                "Búsqueda Bienes": alerta_busq,
                "ID_LINK": pid
            })

        df_alertas = pd.DataFrame(alertas)

        # =========================================================
        # 3. INTERFAZ DE USUARIO INTERACTIVA
        # =========================================================
        with st.sidebar:
            st.header("🔍 Filtros de Gestión")
            sel_sust = st.multiselect("Filtrar por Sustanciador:", sorted(df_alertas['Sustanciador'].unique()))
            if st.button("Limpiar Filtros"):
                st.session_state.filtro_alerta = "TODAS"
                st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            count = len(df_alertas[df_alertas['Fuerza Ejecutoria'] != "OK"])
            st.metric("Riesgo Fuerza", count)
            if st.button(f"Ver {count} procesos", key="btn_fuerza"): st.session_state.filtro_alerta = "FUERZA"
        with c2:
            count = len(df_alertas[df_alertas['Medidas (Inm)'] != "OK"])
            st.metric("Medidas x Renovar", count)
            if st.button(f"Ver {count} procesos", key="btn_medidas"): st.session_state.filtro_alerta = "MEDIDAS"
        with c3:
            count = len(df_alertas[df_alertas['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])])
            st.metric("Búsquedas Vencidas", count)
            if st.button(f"Ver {count} procesos", key="btn_busq"): st.session_state.filtro_alerta = "BUSQUEDA"
        with c4:
            count = len(df_alertas[df_alertas['Mandamiento'] != "OK"])
            st.metric("Términos MP", count)
            if st.button(f"Ver {count} procesos", key="btn_mp"): st.session_state.filtro_alerta = "MP"

        st.write("---")
        df_display = df_alertas.copy()
        if sel_sust: df_display = df_display[df_display['Sustanciador'].isin(sel_sust)]
        
        if st.session_state.filtro_alerta == "FUERZA": df_display = df_display[df_display['Fuerza Ejecutoria'] != "OK"]
        elif st.session_state.filtro_alerta == "MEDIDAS": df_display = df_display[df_display['Medidas (Inm)'] != "OK"]
        elif st.session_state.filtro_alerta == "BUSQUEDA": df_display = df_display[df_display['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])]
        elif st.session_state.filtro_alerta == "MP": df_display = df_display[df_display['Mandamiento'] != "OK"]

        st.dataframe(df_display.drop(columns=['ID_LINK']), use_container_width=True, hide_index=True)

        # =========================================================
        # 4. FICHA DE DETALLE
        # =========================================================
        st.write("---")
        st.subheader("🧐 Consulta Detallada de Expediente")
        exp_sel = st.selectbox("Seleccione un proceso:", ["-- Seleccione --"] + sorted(df_display['No. Proceso'].unique().tolist()))

        if exp_sel != "-- Seleccione --":
            p_id_sel = normalizar_id(exp_sel)
            info_f = df_f[df_f['ID_LINK'] == p_id_sel].iloc[0]
            info_b = df_b[df_b['ID_LINK'] == p_id_sel]
            info_p = df_p[df_p['ID_LINK'] == p_id_sel]
            
            st.markdown(f"""
            <div class="ficha-detalle">
                <h3>EXPEDIENTE: {exp_sel}</h3>
                <p><b>Sustanciador:</b> {df_alertas[df_alertas['ID_LINK']==p_id_sel]['Sustanciador'].values[0]}</p>
            </div>""", unsafe_allow_html=True)
            
            c_inf1, c_inf2 = st.columns(2)
            with c_inf1:
                st.write("### 🏠 Bienes")
                if not info_b.empty: st.table(info_b[[col_t_b, 'OBSERVACIONES']])
                else: st.info("Sin bienes registrados.")
            with c_inf2:
                st.write("### ⚖️ Providencias")
                if not info_p.empty: st.dataframe(info_p[['Fecha Providencia', 'Nombre Providencia']].sort_values('Fecha Providencia', ascending=False), hide_index=True)
                else: st.info("Sin providencias.")
    else:
        st.error("Error al cargar las hojas. Verifique los nombres en Excel.")
