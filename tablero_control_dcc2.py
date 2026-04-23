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

def check_password():
    """Verifica credenciales contra los Secrets de Streamlit."""
    def password_entered():
        user_input = st.session_state["username"].strip()
        pass_input = st.session_state["password"].strip()
        creds = st.secrets.get("credentials", {})
        
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
    return True

if not check_password():
    st.stop()

# =========================================================
# 2. ESTÉTICA INSTITUCIONAL
# =========================================================
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { 
        background-color: #ffffff; padding: 15px; border-radius: 15px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-top: 5px solid #003366;
    }
    h1, h2, h3 { color: #003366 !important; font-family: 'Segoe UI Semibold', sans-serif; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 600; }
    
    .panel-priorizacion, .panel-busqueda {
        background-color: #ffffff; padding: 20px; border-radius: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 20px;
        border-left: 10px solid #003366;
    }
    .panel-priorizacion { border-left-color: #d9534f; }
    .panel-busqueda { border-left-color: #0056b3; }

    /* Centrado para st.table */
    .stTable td, .stTable th { text-align: center !important; }
    </style>
    """, unsafe_allow_html=True)

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

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

def color_semaforo(val):
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
st.markdown("<h1 style='text-align: center;'>📊 TABLERO ESTRATÉGICO DCC2</h1>", unsafe_allow_html=True)
links = st.secrets.get("links_onedrive", {})

if not links:
    st.error("⚠️ Enlaces de datos no configurados.")
else:
    with st.spinner('Sincronizando información operativa...'):
        bases = {
            "FUIC": descargar_excel(links.get("FUIC"), "PARA ENVIAR"),
            "PROVIDENCIAS": descargar_excel(links.get("PROVIDENCIAS"), "PROVIDENCIAS"),
            "BIENES": descargar_excel(links.get("BIENES"), "BIENES IDENTIFICADOS"),
            "BUSQUEDAS": descargar_excel(links.get("BUSQUEDA_BIENES"), "BUSQUEDA DE BIENES (SOLICITUDES")
        }

    if any(isinstance(v, str) for v in bases.values()):
        for v in bases.values(): 
            if isinstance(v, str): st.error(f"Error de conexión: {v}")
    else:
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
            est_proc = str(row.get(col_estado, "")).upper()
            if "ARCHIVADO" in est_proc: continue

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
                    v = None
                    if match:
                        try: v = datetime.strptime(match.group(1), "%d/%m/%Y") + timedelta(days=1826)
                        except: pass
                    if not v and pd.notna(fr): v = fr + timedelta(days=3652)
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

            last_date_match = df_bus_latest[df_bus_latest['ID_LINK'] == pid]['Ultima_Busq_Real']
            fb = last_date_match.iloc[0] if not last_date_match.empty else pd.NaT
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
        # 4. INTERFAZ: KPIs Y TABLA PRINCIPAL
        # =========================================================
        if 'filtro_alerta' not in st.session_state: st.session_state.filtro_alerta = "TODAS"

        with st.sidebar:
            st.header("🔍 Gestión")
            todos_sustanciadores = sorted(df_alertas['Sustanciador'].unique()) if not df_alertas.empty else []
            sel_sust = st.multiselect("Filtrar Sustanciador:", todos_sustanciadores)
            if st.button("Limpiar todos los filtros"):
                st.session_state.filtro_alerta = "TODAS"
                st.rerun()
            st.write("---")
            if st.button("Cerrar Sesión"):
                st.session_state.password_correct = False
                st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            cnt = len(df_alertas[df_alertas['Fuerza Ejecutoria'] != "OK"])
            st.metric("Riesgo Fuerza", cnt); st.button(f"Ver {cnt} casos", key="b1", on_click=lambda: setattr(st.session_state, 'filtro_alerta', 'FUERZA'))
        with c2:
            cnt = len(df_alertas[df_alertas['Medidas (Inm)'] != "OK"])
            st.metric("Medidas x Renovar", cnt); st.button(f"Ver {cnt} casos", key="b2", on_click=lambda: setattr(st.session_state, 'filtro_alerta', 'MEDIDAS'))
        with c3:
            cnt = len(df_alertas[df_alertas['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])])
            st.metric("Búsquedas Vencidas", cnt); st.button(f"Ver {cnt} casos", key="b3", on_click=lambda: setattr(st.session_state, 'filtro_alerta', 'BUSQUEDA'))
        with c4:
            cnt = len(df_alertas[df_alertas['Mandamiento'] != "OK"])
            st.metric("Términos MP", cnt); st.button(f"Ver {cnt} casos", key="b4", on_click=lambda: setattr(st.session_state, 'filtro_alerta', 'MP'))

        st.write("---")
        
        # --- Lógica de filtrado maestro por Sustanciador ---
        df_disp = df_alertas.copy()
        if sel_sust:
            df_disp = df_disp[df_disp['Sustanciador'].isin(sel_sust)]
        
        titulo, cols_b = "📋 Inventario de Alertas Activas", ["No. Proceso", "Sustanciador", "Etapa Actual", "Mandamiento", "Fuerza Ejecutoria", "Medidas (Inm)", "Búsqueda Bienes"]
        
        if st.session_state.filtro_alerta == "FUERZA":
            df_disp, titulo = df_disp[df_disp['Fuerza Ejecutoria'] != "OK"], "🚨 Riesgo Fuerza Ejecutoria"
        elif st.session_state.filtro_alerta == "MEDIDAS":
            df_disp, titulo = df_disp[df_disp['Medidas (Inm)'] != "OK"], "🏠 Medidas por Renovar"
            cols_b.insert(3, "No. Registro")
        elif st.session_state.filtro_alerta == "BUSQUEDA":
            df_disp, titulo = df_disp[df_disp['Búsqueda Bienes'].isin(["VENCIDA", "PENDIENTE"])], "🔎 Búsqueda de Bienes Vencida"
            if not df_disp.empty:
                df_disp['Última Búsqueda'] = df_disp['Ultima_Busqueda'].dt.strftime('%d/%m/%Y').fillna("SIN REGISTRO")
            cols_b.append("Última Búsqueda")
        elif st.session_state.filtro_alerta == "MP":
            df_disp, titulo = df_disp[df_disp['Mandamiento'] != "OK"], "⚖️ Términos Mandamiento"

        st.subheader(titulo)
        
        if not df_disp.empty:
            conf_main = {c: st.column_config.Column(alignment="center") for c in cols_b}
            styled_main = df_disp[cols_b].style.map(color_semaforo, subset=["Mandamiento", "Fuerza Ejecutoria", "Medidas (Inm)", "Búsqueda Bienes"])
            st.dataframe(styled_main, use_container_width=True, height=450, hide_index=True, column_config=conf_main)
        else:
            st.info("💡 No hay alertas relevantes para el sustanciador seleccionado en esta categoría.")

        # =========================================================
        # 5. MÓDULOS INFERIORES: TOP 10 Y CRONOGRAMA BB
        # =========================================================
        st.write("---")
        st.subheader("🚨 Top 10: Riesgo Fuerza Ejecutoria")
        
        # Filtro maestro aplicado al Top 10
        df_p_fe = df_alertas[df_alertas['Vencimiento_Fuerza'].notna()].sort_values(by="Vencimiento_Fuerza")
        if sel_sust:
            df_p_fe = df_p_fe[df_p_fe['Sustanciador'].isin(sel_sust)]
        df_p_fe = df_p_fe.head(10).copy()

        if not df_p_fe.empty:
            df_p_fe['Días para Prescribir'] = df_p_fe['Vencimiento_Fuerza'].apply(lambda x: f"{(x-hoy).days} d" if (x-hoy).days >=0 else f"PRESCRITO ({(hoy-x).days} d)")
            df_p_fe['Vencimiento Fuerza'], df_p_fe['Fecha Ejecutoria'] = df_p_fe['Vencimiento_Fuerza'].dt.strftime('%d/%m/%Y'), df_p_fe['Fecha_Ejecutoria'].dt.strftime('%d/%m/%Y')
            st.markdown('<div class="panel-priorizacion">', unsafe_allow_html=True)
            st.table(df_p_fe[["No. Proceso", "Sustanciador", "Fecha Ejecutoria", "Vencimiento Fuerza", "Días para Prescribir"]].style.set_properties(**{'text-align': 'center'}))
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("✅ No hay procesos con riesgo de fuerza ejecutoria para el sustanciador seleccionado.")

        st.write("---")
        st.subheader("🔎 Cronograma de Gestión: Seguimiento de Búsqueda de Bienes")
        
        # Cálculo de Cronograma
        df_activos = df_f[~df_f[col_estado].astype(str).str.upper().str.contains("ARCHIVADO", na=False)].copy()
        cron_list = []
        for _, r in df_activos.iterrows():
            pid = r['ID_LINK']
            l_m = df_bus_latest[df_bus_latest['ID_LINK'] == pid]['Ultima_Busq_Real']
            u_f = l_m.iloc[0] if not l_m.empty else pd.NaT
            p_f, es_o = (hoy, True) if pd.isna(u_f) else (u_f + timedelta(days=120), False)
            cron_list.append({
                "No. Proceso": r.get(buscar_columna_flexible(df_f, ["No. Proceso", "PROCESO"])), 
                "Sustanciador": r.get(col_sust, "N/A"), 
                "Fecha_F": p_f, 
                "Es_Omision": es_o
            })
        
        df_cron = pd.DataFrame(cron_list).sort_values(by="Fecha_F")
        
        # Filtro maestro aplicado al Cronograma
        if sel_sust:
            df_cron = df_cron[df_cron['Sustanciador'].isin(sel_sust)]
        
        if not df_cron.empty:
            st.markdown('<div class="panel-busqueda">', unsafe_allow_html=True)
            mask_o = df_cron["Es_Omision"].values
            df_cr_final = df_cron[["No. Proceso", "Sustanciador"]].copy()
            df_cr_final['Fecha Próxima BB'] = df_cron['Fecha_F'].apply(lambda x: MESES_ES.get(x.month, ""))
            df_cr_final = df_cr_final.reset_index(drop=True)

            def style_red_only_month(df):
                stls = pd.DataFrame('', index=df.index, columns=df.columns)
                for i, is_new in enumerate(mask_o):
                    if is_new:
                        stls.iloc[i, stls.columns.get_loc("Fecha Próxima BB")] = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                return stls

            conf_cron = {c: st.column_config.Column(alignment="center") for c in df_cr_final.columns}
            st.dataframe(df_cr_final.style.apply(style_red_only_month, axis=None), 
                         use_container_width=True, height=400, hide_index=True, column_config=conf_cron)
            st.markdown('</div>', unsafe_allow_html=True)
            st.caption("Nota: Los meses resaltados en rojo corresponden a procesos que NO registran búsquedas previas.")
        else:
            st.info("🔎 No hay gestiones de búsqueda programadas para el sustanciador seleccionado.")
