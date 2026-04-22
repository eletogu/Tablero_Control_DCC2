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
    .error-diag { padding: 15px; background-color: #f8d7da; color: #721c24; border-radius: 10px; border: 1px solid #f5c6cb; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

if 'filtro_alerta' not in st.session_state:
    st.session_state.filtro_alerta = "TODAS"

# --- FUNCIONES DE LIMPIEZA Y NORMALIZACIÓN ---
def normalizar_texto(t):
    if pd.isna(t) or t == '': return ""
    texto = "".join((c for c in unicodedata.normalize('NFD', str(t).upper()) if unicodedata.category(c) != 'Mn'))
    texto = re.sub(r'[\r\n\t]+', ' ', texto)
    return " ".join(texto.split()).strip()

def normalizar_id(v):
    if pd.isna(v): return ""
    return re.sub(r'[^A-Z0-9]', '', str(v).strip().upper().replace('.0', ''))

def buscar_columna_flexible(df, posibles_nombres):
    """Busca una columna comparando nombres normalizados."""
    posibles_norm = [normalizar_texto(n) for n in posibles_nombres]
    for col in df.columns:
        if normalizar_texto(col) in posibles_norm:
            return col
    return None

def extraer_fecha_renovacion(texto, tipo):
    if pd.isna(texto): return None
    obs_norm = normalizar_texto(texto)
    patron = f"RENOVACION {tipo}\\s+(\\d{{2}}/\\d{{2}}/\\d{{4}})"
    match = re.search(patron, obs_norm)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d/%m/%Y")
        except:
            return None
    return None

# --- LÓGICA DE COLOR PARA LAS TABLAS ---
def color_semaforo(val):
    """Asigna colores de fondo según el texto de la alerta."""
    color = ''
    if val in ['VENCIDO', 'PERDIDA', 'CADUCADO', 'VENCIDA', 'PENDIENTE']:
        color = 'background-color: #f8d7da; color: #721c24; font-weight: bold;' # Rojo
    elif val in ['CRÍTICO', 'RIESGO ALTO', 'RENOVAR YA', 'PRÓXIMA']:
        color = 'background-color: #fff3cd; color: #856404; font-weight: bold;' # Amarillo
    elif val == 'OK':
        color = 'background-color: #d4edda; color: #155724;' # Verde
    return color

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
    st.warning("⚠️ Configure los enlaces en los 'Secrets' de Streamlit.")
else:
    with st.spinner('Sincronizando archivos con la nube...'):
        bases = {
            "FUIC": descargar_excel(links.get("FUIC"), "FUIC", "PARA ENVIAR"),
            "PROVIDENCIAS": descargar_excel(links.get("PROVIDENCIAS"), "PROVIDENCIAS", "PROVIDENCIAS"),
            "BIENES": descargar_excel(links.get("BIENES"), "BIENES IDENTIFICADOS", "BIENES IDENTIFICADOS"),
            "BUSQUEDAS": descargar_excel(links.get("BUSQUEDA_BIENES"), "BUSQUEDA DE BIENES", "BUSQUEDA DE BIENES (SOLICITUDES")
        }

    errores_carga = [v for v in bases.values() if isinstance(v, str)]
    if errores_carga:
        for err in errores_carga: st.error(err)
    else:
        df_f, df_p, df_b, df_bus = bases["FUIC"], bases["PROVIDENCIAS"], bases["BIENES"], bases["BUSQUEDAS"]
        
        nombres_id = ["No. Proceso", "No Proceso", "PCC", "PROCESO"]
        col_id_f = buscar_columna_flexible(df_f, nombres_id)
        col_id_p = buscar_columna_flexible(df_p, nombres_id)
        col_id_b = buscar_columna_flexible(df_b, nombres_id)
        col_id_bus = buscar_columna_flexible(df_bus, nombres_id)

        if not all([col_id_f, col_id_p, col_id_b, col_id_bus]):
            st.markdown('<div class="error-diag"><h3>❌ Error de Estructura Detectado</h3><p>No se encontró la columna <b>"No. Proceso"</b> en uno o más archivos.</p></div>', unsafe_allow_html=True)
            st.stop()

        for df in [df_f, df_p, df_b, df_bus]:
            c_id = buscar_columna_flexible(df, nombres_id)
            df['ID_LINK'] = df[c_id].astype(str).apply(normalizar_id)
            for col in df.columns:
                col_upper = col.upper()
                if "NO. REGISTRO" in col_upper:
                    continue
                if any(k in col_upper for k in ['FECHA', 'SOLICITUD', 'PRACTICA']):
                    df[col] = pd.to_datetime(df[col], errors='coerce')

        cols_etapas = [c for c in df_f.columns if 'ETAPA' in c.upper()]
        def get_current_stage(row):
            for col in reversed(cols_etapas):
                val = str(row[col]).strip() if pd.notna(row[col]) else ""
                if val: return val
            return "NO REGISTRA"
        df_f['ETAPA_REAL'] = df_f.apply(get_current_stage, axis=1)

        # --- MOTOR DE AUDITORÍA ---
        hoy = datetime.now()
        alertas = []
        col_sust = buscar_columna_flexible(df_f, ["Sustanciador a Cargo", "Sustanciador"])
        col_f_ejec = buscar_columna_flexible(df_f, ["Fecha Ejecutoria"])
        col_f_not = buscar_columna_flexible(df_f, ["Fecha Not MP"])

        for _, row in df_f.iterrows():
            pid = row['ID_LINK']
            etapa = str(row['ETAPA_REAL']).upper()
            
            alerta_mp = "OK"
            provs = df_p[df_p['ID_LINK'] == pid]
            col_nom_p = buscar_columna_flexible(df_p, ["Nombre Providencia", "Providencia"])
            col_f_p = buscar_columna_flexible(df_p, ["Fecha Providencia", "Fecha"])
            
            if col_nom_p and col_f_p:
                avoco_row = provs[provs[col_nom_p].astype(str).str.contains("AVOCO", na=False, case=False)]
                f_avoco = avoco_row[col_f_p].min() if not avoco_row.empty else pd.NaT
                if pd.notna(f_avoco) and hasattr(f_avoco, 'year') and "PERSUASIVA" in etapa:
                    meses = (hoy.year - f_avoco.year) * 12 + (hoy.month - f_avoco.month)
                    if meses >= 3: alerta_mp = "VENCIDO"
                    elif meses >= 2: alerta_mp = "CRÍTICO"

            alerta_fuerza = "OK"
            val_f_ejec = row.get(col_f_ejec) if col_f_ejec else None
            val_f_not = row.get(col_f_not) if col_f_not else None
            if pd.notna(val_f_ejec) and pd.isna(val_f_not) and hasattr(val_f_ejec, 'year'):
                anios_trans = (hoy - val_f_ejec).days / 365.25
                if anios_trans >= 5: alerta_fuerza = "PERDIDA"
                elif anios_trans >= 4: alerta_fuerza = "RIESGO ALTO"

            alerta_medida = "OK"
            b_proc = df_b[df_b['ID_LINK'] == pid]
            col_tipo_b = buscar_columna_flexible(df_b, ["Tipo Bien Identificado (Inmueble, Vehículo, Mueble, Cuenta Bancaría, Otros)", "Tipo Bien"])
            col_f_emb = buscar_columna_flexible(df_b, ["Fecha Práctica, Inscripción o Registro Embargo", "Fecha Registro"])
            
            if col_tipo_b and col_f_emb:
                inms = b_proc[b_proc[col_tipo_b].astype(str).str.contains("INMUEBLE", na=False, case=False)]
                vencimientos = []
                for _, inmueble in inms.iterrows():
                    f_reg = inmueble[col_f_emb]
                    obs = inmueble.get('OBSERVACIONES', '')
                    f_r2 = extraer_fecha_renovacion(obs, "2")
                    f_r1 = extraer_fecha_renovacion(obs, "1")
                    if pd.notna(f_r2): venc = f_r2 + timedelta(days=5*365.25)
                    elif pd.notna(f_r1): venc = f_r1 + timedelta(days=5*365.25)
                    elif pd.notna(f_reg) and hasattr(f_reg, 'year'): venc = f_reg + timedelta(days=10*365.25)
                    else: continue
                    vencimientos.append(venc)
                if vencimientos:
                    f_venc_final = min(vencimientos)
                    if hoy > f_venc_final: alerta_medida = "CADUCADO"
                    elif (f_venc_final - hoy).days / 365.25 <= 0.5: alerta_medida = "RENOVAR YA"

            alerta_busq = "OK"
            bus_proc = df_bus[df_bus['ID_LINK'] == pid]
            col_f_sol = buscar_columna_flexible(df_bus, ["Fecha Solicitud", "Fecha"])
            f_ult_bus = bus_proc[col_f_sol].max() if (not bus_proc.empty and col_f_sol) else pd.NaT
            if pd.isna(f_ult_bus): alerta_busq = "PENDIENTE"
            elif hasattr(f_ult_bus, 'year'):
                m_bus = (hoy.year - f_ult_bus.year) * 12 + (hoy.month - f_ult_bus.month)
                if m_bus >= 4: alerta_busq = "VENCIDA"
                elif m_bus >= 3: alerta_busq = "PRÓXIMA"

            alertas.append({
                "No. Proceso": row[col_id_f],
                "Sustanciador": row.get(col_sust, "N/A"),
                "Etapa Actual": etapa,
                "Mandamiento": alerta_mp,
                "Fuerza Ejecutoria": alerta_fuerza,
                "Medidas (Inm)": alerta_medida,
                "Búsqueda Bienes": alerta_busq,
                "ID_LINK": pid
            })

        df_alertas = pd.DataFrame(alertas)

        # =========================================================
        # 3. INTERFAZ DE USUARIO
        # =========================================================
        with st.sidebar:
            st.header("🔍 Filtros de Gestión")
            sel_sust = st.multiselect("Filtrar por Sustanciador:", sorted(df_alertas['Sustanciador'].unique()))
            if st.button("Limpiar Filtros"):
                st.session_state.filtro_alerta = "TODAS"
                st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            cnt = len(df_alertas[df_alertas['Fuerza Ejecutoria'] != "OK"])
            st.metric("Riesgo Fuerza", cnt)
            if st.button(f"Ver {cnt} procesos", key="k1"): st.session_state.filtro_alerta = "FUERZA"
        with c2:
            cnt = len(df_alertas[df_alertas['Medidas (Inm)'] != "OK"])
            st.metric("Medidas x Renovar", cnt)
            if st.button(f"Ver {cnt} procesos", key="k2"): st.session_state.filtro_alerta = "MEDIDAS"
        with c3:
            cnt = len(df_alertas[df_alertas['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])])
            st.metric("Búsquedas Vencidas", cnt)
            if st.button(f"Ver {cnt} procesos", key="k3"): st.session_state.filtro_alerta = "BUSQUEDA"
        with c4:
            cnt = len(df_alertas[df_alertas['Mandamiento'] != "OK"])
            st.metric("Términos MP", cnt)
            if st.button(f"Ver {cnt} procesos", key="k4"): st.session_state.filtro_alerta = "MP"

        st.write("---")
        df_disp = df_alertas.copy()
        if sel_sust: df_disp = df_disp[df_disp['Sustanciador'].isin(sel_sust)]
        
        if st.session_state.filtro_alerta == "FUERZA": df_disp = df_disp[df_disp['Fuerza Ejecutoria'] != "OK"]
        elif st.session_state.filtro_alerta == "MEDIDAS": df_disp = df_disp[df_disp['Medidas (Inm)'] != "OK"]
        elif st.session_state.filtro_alerta == "BUSQUEDA": df_disp = df_disp[df_disp['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])]
        elif st.session_state.filtro_alerta == "MP": df_disp = df_disp[df_disp['Mandamiento'] != "OK"]

        # --- APLICACIÓN DE COLORES A LA TABLA PRINCIPAL ---
        cols_alerta = ["Mandamiento", "Fuerza Ejecutoria", "Medidas (Inm)", "Búsqueda Bienes"]
        df_styled = df_disp.drop(columns=['ID_LINK']).style.applymap(color_semaforo, subset=cols_alerta)
        
        st.dataframe(df_styled, use_container_width=True, hide_index=True)

        # =========================================================
        # 4. FICHA DE DETALLE
        # =========================================================
        st.write("---")
        st.subheader("🧐 Consulta Detallada de Expediente")
        exp_sel = st.selectbox("Seleccione un proceso:", ["-- Seleccione --"] + sorted(df_disp['No. Proceso'].unique().tolist()))

        if exp_sel != "-- Seleccione --":
            p_id_sel = normalizar_id(exp_sel)
            info_f = df_f[df_f['ID_LINK'] == p_id_sel].iloc[0]
            info_b = df_b[df_b['ID_LINK'] == p_id_sel]
            info_p = df_p[df_p['ID_LINK'] == p_id_sel]
            
            st.markdown(f'<div class="ficha-detalle"><h3>EXPEDIENTE: {exp_sel}</h3><p><b>Sustanciador:</b> {info_f.get(col_sust)}</p></div>', unsafe_allow_html=True)
            
            c_i1, c_i2 = st.columns(2)
            with c_i1:
                st.write("### 🏠 Bienes")
                if not info_b.empty:
                    col_ejec_b = buscar_columna_flexible(df_b, ["Ejecutado"])
                    col_tipo_b = buscar_columna_flexible(df_b, ["Tipo Bien Identificado (Inmueble, Vehículo, Mueble, Cuenta Bancaría, Otros)"])
                    col_esp_b = buscar_columna_flexible(df_b, ["Especifico (Casa, Apto, Oficina, Auto, Motocicleta, Ahorros, Corriente, Etc…)"])
                    col_reg_b = buscar_columna_flexible(df_b, ["No. Registro (Matrícula Inmobiliaria/Mercantil, No. Cuenta, No. Placa, Etc)"])
                    
                    df_b_detail = info_b.copy()
                    if col_reg_b:
                        df_b_detail[col_reg_b] = df_b_detail[col_reg_b].astype(str).replace(r'\.0$', '', regex=True)
                    
                    cols_final = [c for c in [col_ejec_b, col_tipo_b, col_esp_b, col_reg_b] if c and c in df_b_detail.columns]
                    st.dataframe(df_b_detail[cols_final], hide_index=True)
                else: 
                    st.info("Sin bienes registrados.")
            
            with c_i2:
                st.write("### ⚖️ Providencias")
                if not info_p.empty:
                    cols_p_avail = []
                    if col_f_p and col_f_p in info_p.columns: cols_p_avail.append(col_f_p)
                    if col_nom_p and col_nom_p in info_p.columns: cols_p_avail.append(col_nom_p)
                    
                    if cols_p_avail:
                        df_p_show = info_p[cols_p_avail].copy()
                        if col_f_p in df_p_show.columns:
                            df_p_show = df_p_show.sort_values(col_f_p, ascending=False)
                            df_p_show[col_f_p] = df_p_show[col_f_p].dt.strftime('%d/%m/%Y')
                        
                        st.dataframe(df_p_show, hide_index=True)
                    else:
                        st.warning("⚠️ No se pudieron identificar las columnas de fecha o nombre en Providencias.")
                else: st.info("Sin providencias.")
