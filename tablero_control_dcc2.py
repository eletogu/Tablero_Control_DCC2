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
# 1. CONFIGURACIÓN Y SEGURIDAD
# =========================================================
st.set_page_config(page_title="Dashboard de Control DCC2", layout="wide")

# Inicialización de estados globales
if 'password_correct' not in st.session_state:
    st.session_state['password_correct'] = False
if 'modulo_actual' not in st.session_state:
    st.session_state.modulo_actual = "🏠 Inicio"
if 'usuario_logueado' not in st.session_state:
    st.session_state.usuario_logueado = ""

def check_password():
    def password_entered():
        user_input = st.session_state["username"].strip()
        pass_input = st.session_state["password"].strip()
        creds = st.secrets.get("credentials", {})
        
        if user_input in creds and str(pass_input) == str(creds[user_input]):
            st.session_state["password_correct"] = True
            st.session_state["usuario_logueado"] = user_input
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.markdown("<h1 style='text-align: center; color: #003366;'>🔐 Acceso Restringido DCC2</h1>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input("Usuario", key="username")
            st.text_input("Contraseña", type="password", key="password")
            if st.button("Ingresar"):
                password_entered()
                st.rerun()
        return False
    return True

if not check_password():
    st.stop()

# =========================================================
# 2. ESTÉTICA PROFESIONAL Y MARCO AJUSTADO (CSS)
# =========================================================
st.markdown("""
    <style>
    /* 1. OCULTAR ELEMENTOS DE DESARROLLO */
    #MainMenu, footer, header, .stDeployButton, #stDecoration, 
    [data-testid="stStatusWidget"], .viewerBadge_container__1QSob, 
    .stAppToolbar, iframe[title="manage-app"] { visibility: hidden !important; display: none !important; }
    
    /* 2. DISEÑO DE PÁGINA */
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI Semibold', sans-serif; text-align: center; }

    /* 3. MÉTRICAS */
    .stMetric { 
        background-color: #ffffff; padding: 10px; border-radius: 10px; 
        box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-top: 4px solid #003366;
    }

    /* 4. CONTENEDOR AJUSTADO AL TAMAÑO DE LA TABLA Y CENTRADO */
    .scroll-container {
        max-height: 450px;
        overflow-y: auto;
        overflow-x: auto;
        border: 1px solid #dee2e6;
        border-radius: 4px;
        background-color: white;
        margin-bottom: 25px;
        width: fit-content;      /* AJUSTA EL MARCO AL TAMAÑO DE LA TABLA */
        max-width: 100%;         /* EVITA QUE SE SALGA DE LA PANTALLA */
        margin-left: auto;       /* CENTRA EL CONTENEDOR */
        margin-right: auto;      /* CENTRA EL CONTENEDOR */
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }

    /* 5. TABLA ESTILO EXCEL */
    .tabla-hibrida {
        width: auto !important;  /* NO FUERZA EL 100% PARA QUE EL MARCO SE AJUSTE */
        border-collapse: collapse !important;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
        font-size: 13px !important;
    }
    .tabla-hibrida thead th {
        position: sticky;
        top: 0;
        background-color: #f1f3f5 !important;
        color: #003366 !important;
        text-align: center !important;
        padding: 8px 15px !important;
        z-index: 10;
        border: 1px solid #dee2e6 !important;
        font-weight: bold;
        white-space: nowrap;
    }
    .tabla-hibrida tbody td {
        border: 1px solid #dee2e6 !important;
        height: 22px !important; 
        padding: 2px 10px !important;
        line-height: 1.1 !important;
        vertical-align: middle !important;
        text-align: center !important; /* Centro por defecto */
        white-space: nowrap;
    }
    
    /* ALINEACIÓN IZQUIERDA PARA TEXTO */
    .text-col {
        text-align: left !important;
        padding-left: 12px !important;
    }

    .tabla-hibrida tbody tr:hover { background-color: #f1f5f9; }

    /* Botones Sidebar */
    .stButton>button { width: 100%; border-radius: 5px; text-align: left; }
    </style>
    """, unsafe_allow_html=True)

# --- DICCIONARIO DE MESES ---
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

# --- FUNCIONES DE APOYO ---
def normalizar_texto(t):
    if pd.isna(t) or t == '': return ""
    texto = "".join((c for c in unicodedata.normalize('NFD', str(t).upper()) if unicodedata.category(c) != 'Mn'))
    return " ".join(texto.split()).strip()

def normalizar_id(v):
    if pd.isna(v): return ""
    return re.sub(r'[^A-Z0-9]', '', str(v).strip().upper().replace('.0', ''))

def buscar_columna_flexible(df, posibles_nombres):
    posibles_norm = [normalizar_texto(n) for n in posibles_nombres]
    for col in df.columns:
        if normalizar_texto(col) in posibles_norm: return col
    return None

def color_semaforo_html(val):
    if not isinstance(val, str): return ''
    if val in ['VENCIDO', 'PERDIDA', 'CADUCADO', 'VENCIDA', 'PENDIENTE']:
        return 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
    elif val in ['CRÍTICO', 'RIESGO ALTO', 'RENOVAR YA', 'PRÓXIMA']:
        return 'background-color: #fff3cd; color: #856404; font-weight: bold;'
    elif val == 'OK':
        return 'background-color: #d4edda; color: #155724;'
    return ''

@st.cache_data(ttl=600)
def descargar_excel(url, hoja):
    try:
        resp = requests.get(url, timeout=45)
        resp.raise_for_status()
        return pd.read_excel(io.BytesIO(resp.content), sheet_name=hoja).dropna(how='all')
    except Exception as e:
        return str(e)

# =========================================================
# 3. PROCESAMIENTO DE DATOS
# =========================================================
links = st.secrets.get("links_onedrive", {})
if not links:
    st.error("⚠️ Enlaces de datos no configurados.")
    st.stop()

with st.spinner('Sincronizando información institucional...'):
    bases = {
        "FUIC": descargar_excel(links.get("FUIC"), "PARA ENVIAR"),
        "PROVIDENCIAS": descargar_excel(links.get("PROVIDENCIAS"), "PROVIDENCIAS"),
        "BIENES": descargar_excel(links.get("BIENES"), "BIENES IDENTIFICADOS"),
        "BUSQUEDAS": descargar_excel(links.get("BUSQUEDA_BIENES"), "BUSQUEDA DE BIENES (SOLICITUDES")
    }

if any(isinstance(v, str) for v in bases.values()):
    st.error("Error al conectar con las bases de datos en OneDrive.")
    st.stop()

df_f, df_p, df_b, df_bus = bases["FUIC"], bases["PROVIDENCIAS"], bases["BIENES"], bases["BUSQUEDAS"]

for df in [df_f, df_p, df_b, df_bus]:
    cid = buscar_columna_flexible(df, ["No. Proceso", "PCC", "PROCESO"])
    if cid: df['ID_LINK'] = df[cid].astype(str).apply(normalizar_id)
    for col in df.columns:
        if any(k in col.upper() for k in ['FECHA', 'SOLICITUD', 'PRACTICA']) and "REGISTRO" not in col.upper():
            df[col] = pd.to_datetime(df[col], errors='coerce')

hoy = datetime.now()
col_f_busq = buscar_columna_flexible(df_bus, ["Fecha Solicitud"])
df_bus_latest = df_bus.groupby('ID_LINK')[col_f_busq].max().reset_index()
df_bus_latest.rename(columns={col_f_busq: 'Ultima_Busq_Real'}, inplace=True)

alertas = []
col_sust = buscar_columna_flexible(df_f, ["Sustanciador a Cargo", "Sustanciador"])
col_f_ejec = buscar_columna_flexible(df_f, ["Fecha Ejecutoria"])
col_f_not = buscar_columna_flexible(df_f, ["Fecha Not MP"])
col_estado = buscar_columna_flexible(df_f, ["Estado Proceso en el Mes que se Rinde"])
col_reg_b = buscar_columna_flexible(df_b, ["No. Registro (Matrícula Inmobiliaria/Mercantil, No. Cuenta, No. Placa, Etc)"])

cols_etapas = [c for c in df_f.columns if 'ETAPA' in c.upper()]
def get_stage(row):
    for col in reversed(cols_etapas):
        val = str(row[col]).strip() if pd.notna(row[col]) else ""
        if val: return val
    return "N/A"
df_f['ETAPA_REAL'] = df_f.apply(get_stage, axis=1)

for _, row in df_f.iterrows():
    pid = row.get('ID_LINK', '')
    if "ARCHIVADO" in str(row.get(col_estado, "")).upper(): continue
    al_mp, al_fe, al_me, al_bu = "OK", "OK", "OK", "OK"
    venc_fuerza, fb, registro_afectado = pd.NaT, pd.NaT, ""

    provs = df_p[df_p['ID_LINK'] == pid]
    cnp, cfp = buscar_columna_flexible(df_p, ["Nombre Providencia"]), buscar_columna_flexible(df_p, ["Fecha Providencia"])
    if cnp and cfp:
        ar = provs[provs[cnp].astype(str).str.contains("AVOCO", na=False, case=False)]
        fa = ar[cfp].min() if not ar.empty else pd.NaT
        if pd.notna(fa) and "PERSUASIVA" in str(row['ETAPA_REAL']).upper():
            if (hoy - fa).days >= 90: al_mp = "VENCIDO"
            elif (hoy - fa).days >= 60: al_mp = "CRÍTICO"

    fej = row.get(col_f_ejec)
    if pd.notna(fej) and pd.isna(row.get(col_f_not)):
        venc_fuerza = fej + timedelta(days=1826)
        if (hoy - fej).days / 365.25 >= 5: al_fe = "PERDIDA"
        elif (hoy - fej).days / 365.25 >= 4: al_fe = "RIESGO ALTO"

    b_pr = df_b[df_b['ID_LINK'] == pid]
    ctb, cfe_reg = buscar_columna_flexible(df_b, ["Tipo Bien Identificado"]), buscar_columna_flexible(df_b, ["Fecha Práctica, Inscripción o Registro Embargo"])
    if ctb and cfe_reg:
        inms = b_pr[b_pr[ctb].astype(str).str.contains("INMUEBLE", na=False, case=False)]
        vencimientos_m, registros_alerta = [], []
        for _, inm in inms.iterrows():
            fr = inm[cfe_reg]
            obs = str(inm.get('OBSERVACIONES', ''))
            patron = r'RENOVACION \d\s+(\d{2}/\d{2}/\d{4})'
            match = re.search(patron, normalizar_texto(obs))
            v = datetime.strptime(match.group(1), "%d/%m/%Y") + timedelta(days=1826) if match else (fr + timedelta(days=3652) if pd.notna(fr) else None)
            if v:
                vencimientos_m.append(v)
                if hoy > v or (v - hoy).days / 30 <= 6:
                    val_reg = str(inm.get(col_reg_b, "")).replace('.0', '')
                    if val_reg and val_reg != "nan": registros_alerta.append(val_reg)
        if vencimientos_m:
            fv = min(vencimientos_m)
            if hoy > fv: al_me = "CADUCADO"
            elif (fv - hoy).days / 30 <= 6: al_me = "RENOVAR YA"
            if al_me != "OK": registro_afectado = ", ".join(sorted(list(set(registros_alerta))))

    l_date_row = df_bus_latest[df_bus_latest['ID_LINK'] == pid]['Ultima_Busq_Real']
    fb = l_date_row.iloc[0] if not l_date_row.empty else pd.NaT
    if pd.isna(fb): al_bu = "PENDIENTE"
    else:
        if (hoy - fb).days >= 120: al_bu = "VENCIDA"
        elif (hoy - fb).days >= 90: al_bu = "PRÓXIMA"

    if any(x != "OK" for x in [al_mp, al_fe, al_me, al_bu]):
        alertas.append({
            "No. Proceso": row[buscar_columna_flexible(df_f, ["No. Proceso"])],
            "Sustanciador": row.get(col_sust, "N/A"),
            "Etapa Actual": row['ETAPA_REAL'], 
            "Mandamiento": al_mp, "Fuerza Ejecutoria": al_fe, "Medidas (Inm)": al_me, "Búsqueda Bienes": al_bu,
            "ID_LINK": pid, "Fecha_Ejecutoria": fej, "Vencimiento_Fuerza": venc_fuerza, 
            "No. Registro": registro_afectado, "Ultima_Busqueda": fb
        })

df_alertas = pd.DataFrame(alertas)

# =========================================================
# 4. NAVEGACIÓN Y FILTROS
# =========================================================
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.usuario_logueado}")
    st.write("---")
    st.markdown("### 🧭 Navegación")
    if st.button("🏠 Inicio"): st.session_state.modulo_actual = "🏠 Inicio"
    if st.button("📋 Inventario de Alertas"): st.session_state.modulo_actual = "📋 Inventario"
    if st.button("🚨 Riesgos de Prescripción"): st.session_state.modulo_actual = "🚨 Top 10"
    if st.button("🔎 Cronograma Búsqueda"): st.session_state.modulo_actual = "🔎 Cronograma"
    
    st.write("---")
    st.markdown("### 🔍 Filtro Maestro")
    todos_sust = sorted(df_alertas['Sustanciador'].unique()) if not df_alertas.empty else []
    sel_sust = st.multiselect("Funcionario:", todos_sust)
    
    st.write("---")
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.password_correct = False
        st.rerun()

# =========================================================
# 5. RENDERIZADO (MARCO AJUSTADO Y CENTRADO)
# =========================================================
st.markdown("<h1>📊 TABLERO ESTRATÉGICO DCC2</h1>", unsafe_allow_html=True)
df_disp = df_alertas.copy()
if sel_sust: df_disp = df_disp[df_disp['Sustanciador'].isin(sel_sust)]

if st.session_state.modulo_actual == "🏠 Inicio":
    st.markdown("### Resumen Ejecutivo")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Riesgo Fuerza", len(df_alertas[df_alertas['Fuerza Ejecutoria'] != "OK"]))
    with c2: st.metric("Medidas x Renovar", len(df_alertas[df_alertas['Medidas (Inm)'] != "OK"]))
    with c3: st.metric("Búsquedas Vencidas", len(df_alertas[df_alertas['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])]))
    with c4: st.metric("Términos MP", len(df_alertas[df_alertas['Mandamiento'] != "OK"]))
    st.write("---")
    st.info("Utilice el menú lateral para acceder a los detalles.")

elif st.session_state.modulo_actual == "📋 Inventario":
    st.markdown("### 📋 Inventario de Alertas Activas")
    cols_v = ["No. Proceso", "Sustanciador", "Etapa Actual", "Mandamiento", "Fuerza Ejecutoria", "Medidas (Inm)", "Búsqueda Bienes"]
    if not df_disp.empty:
        styled_df = df_disp[cols_v].style.map(color_semaforo_html, subset=["Mandamiento", "Fuerza Ejecutoria", "Medidas (Inm)", "Búsqueda Bienes"])
        html_table = styled_df.to_html(classes='tabla-hibrida', index=False, escape=False)
        html_table = html_table.replace('<td>', '<td class="text-col">', 3 * len(df_disp))
        st.markdown(f'<div class="scroll-container">{html_table}</div>', unsafe_allow_html=True)
    else:
        st.success("✅ Todo al día.")

elif st.session_state.modulo_actual == "🚨 Top 10":
    st.markdown("### 🚨 Prioridad: Riesgo Fuerza Ejecutoria")
    df_p_fe = df_alertas[df_alertas['Vencimiento_Fuerza'].notna()].sort_values(by="Vencimiento_Fuerza")
    if sel_sust: df_p_fe = df_p_fe[df_p_fe['Sustanciador'].isin(sel_sust)]
    df_p_fe = df_p_fe.head(10).copy()
    if not df_p_fe.empty:
        df_p_fe['Días'] = df_p_fe['Vencimiento_Fuerza'].apply(lambda x: f"{(x-hoy).days} d" if (x-hoy).days >=0 else "PRESCRITO")
        df_p_fe['Vencimiento'], df_p_fe['Ejecutoria'] = df_p_fe['Vencimiento_Fuerza'].dt.strftime('%d/%m/%Y'), df_p_fe['Fecha_Ejecutoria'].dt.strftime('%d/%m/%Y')
        html_t10 = df_p_fe[["No. Proceso", "Sustanciador", "Ejecutoria", "Vencimiento", "Días"]].to_html(classes='tabla-hibrida', index=False)
        html_t10 = html_t10.replace('<td>', '<td class="text-col">', 2 * len(df_p_fe))
        st.markdown(f'<div class="scroll-container">{html_t10}</div>', unsafe_allow_html=True)
    else:
        st.success("✅ Sin riesgos.")

elif st.session_state.modulo_actual == "🔎 Cronograma":
    st.markdown("### 🔎 Cronograma de Gestión: Búsqueda de Bienes")
    df_act = df_f[~df_f[col_estado].astype(str).str.upper().str.contains("ARCHIVADO", na=False)].copy()
    cron_list = []
    for _, r in df_act.iterrows():
        u_f = df_bus_latest[df_bus_latest['ID_LINK'] == r['ID_LINK']]['Ultima_Busq_Real'].iloc[0] if not df_bus_latest[df_bus_latest['ID_LINK'] == r['ID_LINK']].empty else pd.NaT
        p_f, es_o = (hoy, True) if pd.isna(u_f) else (u_f + timedelta(days=120), False)
        cron_list.append({"No. Proceso": r.get(buscar_columna_flexible(df_f, ["No. Proceso", "PROCESO"])), "Sustanciador": r.get(col_sust, "N/A"), "Fecha_F": p_f, "Es_Omision": es_o})
    df_cron = pd.DataFrame(cron_list).sort_values(by="Fecha_F")
    if sel_sust: df_cron = df_cron[df_cron['Sustanciador'].isin(sel_sust)]
    if not df_cron.empty:
        mask_o = df_cron["Es_Omision"].values
        df_cv = df_cron[["No. Proceso", "Sustanciador"]].copy()
        df_cv['Mes Próxima BB'] = df_cron['Fecha_F'].apply(lambda x: MESES_ES.get(x.month, ""))
        def style_red(df):
            stls = pd.DataFrame('', index=df.index, columns=df.columns)
            for i, o in enumerate(mask_o):
                if o: stls.iloc[i, 2] = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
            return stls
        html_cron = df_cv.reset_index(drop=True).style.apply(style_red, axis=None).to_html(classes='tabla-hibrida', index=False)
        html_cron = html_cron.replace('<td>', '<td class="text-col">', 2 * len(df_cv))
        st.markdown(f'<div class="scroll-container">{html_cron}</div>', unsafe_allow_html=True)
        st.caption("Nota: Meses en rojo indican omisión de búsquedas previas.")
