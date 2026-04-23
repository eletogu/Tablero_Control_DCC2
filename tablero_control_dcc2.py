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
# 1. CONFIGURACIÓN Y SEGURIDAD (LOGIN ROBUSTO)
# =========================================================
st.set_page_config(page_title="Dashboard de Control DCC2", layout="wide")

def check_password():
    """Verifica credenciales contra los Secrets de Streamlit."""
    def password_entered():
        """Valida usuario y contraseña."""
        user_input = st.session_state["username"].strip()
        pass_input = st.session_state["password"].strip()
        
        try:
            creds = st.secrets["credentials"]
        except:
            creds = {}
        
        if user_input in creds and str(pass_input) == str(creds[user_input]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("<h1 style='text-align: center; color: #003366;'>🔐 Acceso Restringido DCC2</h1>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input("Usuario", key="username")
            st.text_input("Contraseña", type="password", key="password")
            if st.button("Ingresar"):
                password_entered()
                if st.session_state.get("password_correct"):
                    st.rerun()
                else:
                    st.error("😕 Usuario o contraseña incorrectos")
        return False
    elif not st.session_state["password_correct"]:
        st.error("😕 Usuario o contraseña incorrectos")
        return False
    return True

if not check_password():
    st.stop()

# =========================================================
# 2. ESTÉTICA Y NORMALIZACIÓN
# =========================================================
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { 
        background-color: #ffffff; padding: 20px; border-radius: 15px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-top: 5px solid #003366;
    }
    h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI Semibold', sans-serif; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 600; margin-top: 5px; }
    .panel-priorizacion {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 10px solid #d9534f; box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    [data-testid="stDataFrame"] td { text-align: center !important; }
    [data-testid="stTable"] td { text-align: center !important; }
    [data-testid="stTable"] th { text-align: center !important; }
    </style>
    """, unsafe_allow_html=True)

if 'filtro_alerta' not in st.session_state:
    st.session_state.filtro_alerta = "TODAS"

def normalizar_texto(t):
    if pd.isna(t) or t == '': return ""
    texto = "".join((c for c in unicodedata.normalize('NFD', str(t).upper()) if unicodedata.category(c) != 'Mn'))
    texto = re.sub(r'[\r\n\t]+', ' ', texto) 
    return " ".join(texto.split()).strip()

def normalizar_id(v):
    if pd.isna(v): return ""
    return re.sub(r'[^A-Z0-9]', '', str(v).strip().upper().replace('.0', ''))

def buscar_columna_flexible(df, posibles_nombres):
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
        try: return datetime.strptime(match.group(1), "%d/%m/%Y")
        except: return None
    return None

def color_semaforo(val):
    if not isinstance(val, str): return 'text-align: center;'
    if val in ['VENCIDO', 'PERDIDA', 'CADUCADO', 'VENCIDA', 'PENDIENTE']:
        return 'background-color: #f8d7da; color: #721c24; font-weight: bold; text-align: center;'
    elif val in ['CRÍTICO', 'RIESGO ALTO', 'RENOVAR YA', 'PRÓXIMA']:
        return 'background-color: #fff3cd; color: #856404; font-weight: bold; text-align: center;'
    elif val == 'OK':
        return 'background-color: #d4edda; color: #155724; text-align: center;'
    return 'text-align: center;'

@st.cache_data(ttl=600)
def descargar_excel(url, nombre_debug, hoja):
    try:
        resp = requests.get(url, timeout=45)
        resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(resp.content), sheet_name=hoja)
        return df.dropna(how='all')
    except Exception as e:
        return f"Error en {nombre_debug} (Hoja: {hoja}): {str(e)}"

# =========================================================
# 3. PROCESAMIENTO DE DATOS
# =========================================================
st.markdown("<h1 style='text-align: center;'>📊 TABLERO ESTRATÉGICO DCC2</h1>", unsafe_allow_html=True)
links = st.secrets.get("links_onedrive", None)

if not links:
    st.error("⚠️ Enlaces de datos no configurados.")
else:
    with st.spinner('Actualizando información operativa...'):
        bases = {
            "FUIC": descargar_excel(links.get("FUIC"), "FUIC", "PARA ENVIAR"),
            "PROVIDENCIAS": descargar_excel(links.get("PROVIDENCIAS"), "PROVIDENCIAS", "PROVIDENCIAS"),
            "BIENES": descargar_excel(links.get("BIENES"), "BIENES IDENTIFICADOS", "BIENES IDENTIFICADOS"),
            "BUSQUEDAS": descargar_excel(links.get("BUSQUEDA_BIENES"), "BUSQUEDA", "BUSQUEDA DE BIENES (SOLICITUDES")
        }

    errores = [v for v in bases.values() if isinstance(v, str)]
    if errores:
        for err in errores: st.error(err)
    else:
        df_f, df_p, df_b, df_bus = bases["FUIC"], bases["PROVIDENCIAS"], bases["BIENES"], bases["BUSQUEDAS"]
        
        for df in [df_f, df_p, df_b, df_bus]:
            cid = buscar_columna_flexible(df, ["No. Proceso", "PCC", "PROCESO"])
            if cid:
                df['ID_LINK'] = df[cid].astype(str).apply(normalizar_id)
            for col in df.columns:
                if "NO. REGISTRO" in col.upper(): continue
                if any(k in col.upper() for k in ['FECHA', 'SOLICITUD', 'PRACTICA']):
                    df[col] = pd.to_datetime(df[col], errors='coerce')

        cols_etapas = [c for c in df_f.columns if 'ETAPA' in c.upper()]
        def get_stage(row):
            for col in reversed(cols_etapas):
                val = str(row[col]).strip() if pd.notna(row[col]) else ""
                if val: return val
            return "N/A"
        df_f['ETAPA_REAL'] = df_f.apply(get_stage, axis=1)

        hoy = datetime.now()
        alertas = []
        col_sust = buscar_columna_flexible(df_f, ["Sustanciador a Cargo", "Sustanciador"])
        col_f_ejec = buscar_columna_flexible(df_f, ["Fecha Ejecutoria"])
        col_f_not = buscar_columna_flexible(df_f, ["Fecha Not MP"])
        col_estado = buscar_columna_flexible(df_f, ["Estado Proceso en el Mes que se Rinde"])

        for _, row in df_f.iterrows():
            pid = row.get('ID_LINK', '')
            etapa = str(row['ETAPA_REAL']).upper()
            est_proc = str(row.get(col_estado, "")).upper() if col_estado else ""
            venc_fuerza = pd.NaT

            # 1. Mandamiento
            al_mp = "OK"
            provs = df_p[df_p['ID_LINK'] == pid]
            cnp = buscar_columna_flexible(df_p, ["Nombre Providencia"])
            cfp = buscar_columna_flexible(df_p, ["Fecha Providencia"])
            if cnp and cfp:
                ar = provs[provs[cnp].astype(str).str.contains("AVOCO", na=False, case=False)]
                fa = ar[cfp].min() if not ar.empty else pd.NaT
                if pd.notna(fa) and "PERSUASIVA" in etapa:
                    dias_mp = (hoy - fa).days
                    if dias_mp >= 90: al_mp = "VENCIDO"
                    elif dias_mp >= 60: al_mp = "CRÍTICO"

            # 2. Fuerza Ejecutoria
            al_fe = "OK"
            fej = row.get(col_f_ejec)
            if pd.notna(fej) and pd.isna(row.get(col_f_not)) and hasattr(fej, 'year'):
                venc_fuerza = fej + timedelta(days=1826)
                anios_trans = (hoy - fej).days / 365.25
                if anios_trans >= 5: al_fe = "PERDIDA"
                elif anios_trans >= 4: al_fe = "RIESGO ALTO"

            # 3. Medidas
            al_me = "OK"
            b_pr = df_b[df_b['ID_LINK'] == pid]
            ctb = buscar_columna_flexible(df_b, ["Tipo Bien Identificado (Inmueble, Vehículo, Mueble, Cuenta Bancaría, Otros)"])
            cfe_reg = buscar_columna_flexible(df_b, ["Fecha Práctica, Inscripción o Registro Embargo"])
            if ctb and cfe_reg:
                inms = b_pr[b_pr[ctb].astype(str).str.contains("INMUEBLE", na=False, case=False)]
                vencimientos_m = []
                for _, inm in inms.iterrows():
                    fr = inm[cfe_reg]
                    obs = str(inm.get('OBSERVACIONES', ''))
                    fr2, fr1 = extraer_fecha_renovacion(obs, "2"), extraer_fecha_renovacion(obs, "1")
                    if pd.notna(fr2): v = fr2 + timedelta(days=5*365.25)
                    elif pd.notna(fr1): v = fr1 + timedelta(days=5*365.25)
                    elif pd.notna(fr): v = fr + timedelta(days=10*365.25)
                    else: continue
                    vencimientos_m.append(v)
                if vencimientos_m:
                    fv = min(vencimientos_m)
                    if hoy > fv: al_me = "CADUCADO"
                    elif (fv - hoy).days / 30 <= 6: al_me = "RENOVAR YA"

            # 4. Búsqueda
            al_bu = "OK"
            if "ARCHIVADO" not in est_proc:
                b_bus_df = df_bus[df_bus['ID_LINK'] == pid]
                cfs_bus = buscar_columna_flexible(df_bus, ["Fecha Solicitud"])
                fb = b_bus_df[cfs_bus].max() if (not b_bus_df.empty and cfs_bus) else pd.NaT
                if pd.isna(fb): 
                    al_bu = "PENDIENTE"
                else:
                    dias_bus = (hoy - fb).days
                    if dias_bus >= 120: al_bu = "VENCIDA"
                    elif dias_bus >= 90: al_bu = "PRÓXIMA"

            if any(x != "OK" for x in [al_mp, al_fe, al_me, al_bu]):
                alertas.append({
                    "No. Proceso": row[buscar_columna_flexible(df_f, ["No. Proceso"])],
                    "Sustanciador": row.get(col_sust, "N/A"),
                    "Etapa Actual": etapa,
                    "Mandamiento": al_mp,
                    "Fuerza Ejecutoria": al_fe,
                    "Medidas (Inm)": al_me,
                    "Búsqueda Bienes": al_bu,
                    "ID_LINK": pid,
                    "Fecha_Ejecutoria": fej,
                    "Vencimiento_Fuerza": venc_fuerza
                })

        df_alertas = pd.DataFrame(alertas)

        # =========================================================
        # 4. INTERFAZ DE USUARIO (KPIs CON BOTONES)
        # =========================================================
        with st.sidebar:
            st.header("🔍 Gestión")
            sel_sust = st.multiselect("Filtrar Sustanciador:", sorted(df_alertas['Sustanciador'].unique()))
            if st.button("Limpiar todos los filtros"):
                st.session_state.filtro_alerta = "TODAS"
                st.rerun()
            st.write("---")
            if st.button("Cerrar Sesión"):
                st.session_state.password_correct = False
                st.rerun()

        # Fila de métricas con sus respectivos botones de filtrado
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            count_fe = len(df_alertas[df_alertas['Fuerza Ejecutoria'] != "OK"])
            st.metric("Riesgo Fuerza", count_fe)
            if st.button(f"Ver {count_fe} casos", key="btn_fe"):
                st.session_state.filtro_alerta = "FUERZA"

        with c2:
            count_me = len(df_alertas[df_alertas['Medidas (Inm)'] != "OK"])
            st.metric("Medidas x Renovar", count_me)
            if st.button(f"Ver {count_me} casos", key="btn_me"):
                st.session_state.filtro_alerta = "MEDIDAS"

        with c3:
            count_bu = len(df_alertas[df_alertas['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])])
            st.metric("Búsquedas Vencidas", count_bu)
            if st.button(f"Ver {count_bu} casos", key="btn_bu"):
                st.session_state.filtro_alerta = "BUSQUEDA"

        with c4:
            count_mp = len(df_alertas[df_alertas['Mandamiento'] != "OK"])
            st.metric("Términos MP", count_mp)
            if st.button(f"Ver {count_mp} casos", key="btn_mp"):
                st.session_state.filtro_alerta = "MP"

        st.write("---")
        
        # Lógica de Filtrado de la Tabla Principal
        df_disp = df_alertas.copy()
        
        # Aplicar filtro de sustanciador primero
        if sel_sust:
            df_disp = df_disp[df_disp['Sustanciador'].isin(sel_sust)]
        
        # Aplicar filtro de alerta por botón
        titulo_tabla = "📋 Inventario de Alertas Activas"
        if st.session_state.filtro_alerta == "FUERZA":
            df_disp = df_disp[df_disp['Fuerza Ejecutoria'] != "OK"]
            titulo_tabla = "🚨 Procesos con Riesgo de Fuerza Ejecutoria"
        elif st.session_state.filtro_alerta == "MEDIDAS":
            df_disp = df_disp[df_disp['Medidas (Inm)'] != "OK"]
            titulo_tabla = "🏠 Procesos con Medidas por Renovar"
        elif st.session_state.filtro_alerta == "BUSQUEDA":
            df_disp = df_disp[df_disp['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])]
            titulo_tabla = "🔎 Procesos con Búsqueda de Bienes Vencida/Pendiente"
        elif st.session_state.filtro_alerta == "MP":
            df_disp = df_disp[df_disp['Mandamiento'] != "OK"]
            titulo_tabla = "⚖️ Procesos con Términos de Mandamiento Vencidos"

        # Mostrar Tabla Principal
        cols_al = ["Mandamiento", "Fuerza Ejecutoria", "Medidas (Inm)", "Búsqueda Bienes"]
        df_main_show = df_disp.drop(columns=['ID_LINK', 'Fecha_Ejecutoria', 'Vencimiento_Fuerza'])
        
        df_styled = df_main_show.style.map(color_semaforo, subset=cols_al)\
                                       .set_properties(**{'text-align': 'center'})\
                                       .set_table_styles([{'selector': 'th', 'props': [('text-align', 'center')]}])
        
        st.subheader(titulo_tabla)
        st.dataframe(df_styled, use_container_width=True, hide_index=True)

        # =========================================================
        # 5. MÓDULO PRIORITARIO: TOP 10 FUERZA EJECUTORIA
        # =========================================================
        st.write("---")
        st.subheader("🚨 Top 10: Procesos con Riesgo Crítico de Fuerza Ejecutoria")
        st.markdown("_Listado priorizado de expedientes próximos a prescribir (5 años desde la ejecutoria)._")
        
        df_prio_fe = df_alertas[df_alertas['Vencimiento_Fuerza'].notna()].sort_values(by="Vencimiento_Fuerza", ascending=True).head(10).copy()
        
        if not df_prio_fe.empty:
            df_prio_fe['Días para Prescribir'] = df_prio_fe['Vencimiento_Fuerza'].apply(
                lambda x: f"{(x - hoy).days} d" if (x - hoy).days >= 0 else f"PRESCRITO ({(hoy - x).days} d)"
            )
            df_prio_fe['Fecha Ejecutoria'] = df_prio_fe['Fecha_Ejecutoria'].dt.strftime('%d/%m/%Y')
            df_prio_fe['Vencimiento Fuerza'] = df_prio_fe['Vencimiento_Fuerza'].dt.strftime('%d/%m/%Y')
            
            st.markdown('<div class="panel-priorizacion">', unsafe_allow_html=True)
            cols_f_show = ["No. Proceso", "Sustanciador", "Fecha Ejecutoria", "Vencimiento Fuerza", "Días para Prescribir"]
            st.table(df_prio_fe[cols_f_show].style.set_properties(**{'text-align': 'center'}))
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.success("✅ No se detectan procesos con riesgo inminente de pérdida de fuerza ejecutoria.")
