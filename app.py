import streamlit as st
import datetime
import math
import pandas as pd
import plotly.graph_objects as go
from garminconnect import Garmin

st.set_page_config(page_title="Garmin PMC", page_icon="📈", layout="centered")

st.title("📈 Mi PMC Diario")

st.sidebar.header("Configuración")
email = st.sidebar.text_input("Email Garmin")
password = st.sidebar.text_input("Contraseña Garmin", type="password")

ftp_usuario = st.sidebar.number_input("Tu FTP (W)", value=250)
fc_max = st.sidebar.number_input("FC Máxima", value=185)
fc_reposo = st.sidebar.number_input("FC Reposo", value=50)
dias_historial = st.sidebar.slider("Días de historial", 30, 180, 90)

def calcular_tss(act):
    duracion_seg = act.get('duration', 0)
    if duracion_seg <= 0: return 0.0
    duracion_horas = duracion_seg / 3600.0
    
    np = act.get('weightedAveragePower') or act.get('averagePower')
    if np and ftp_usuario > 0:
        if_val = np / ftp_usuario
        return round((duracion_seg * np * if_val) / (ftp_usuario * 3600.0) * 100.0, 1)
        
    avg_hr = act.get('averageHR')
    if avg_hr and fc_max > fc_reposo:
        hrr = max(0.0, min(1.0, (avg_hr - fc_reposo) / (fc_max - fc_reposo)))
        return round(duracion_horas * (hrr ** 2) * 100.0, 1)
        
    return round(duracion_horas * (0.6 ** 2) * 100.0, 1)

if st.button("Sincronizar con Garmin"):
    if not email or not password:
        st.error("Por favor introduce tu email y contraseña de Garmin.")
    else:
        with st.spinner("Conectando con Garmin Connect..."):
            try:
                client = Garmin(email, password)
                client.login()
                
                fecha_fin = datetime.date.today()
                fecha_inicio = fecha_fin - datetime.timedelta(days=dias_historial)
                
                actividades = client.get_activities_by_date(fecha_inicio.isoformat(), fecha_fin.isoformat())
                
                registros = []
                for act in actividades:
                    st_time = act.get('startTimeLocal', '')
                    if st_time:
                        f = datetime.datetime.strptime(st_time, "%Y-%m-%d %H:%M:%S").date()
                        registros.append({'fecha': f, 'tss': calcular_tss(act)})
                
                df = pd.DataFrame(registros)
                tss_diario = df.groupby('fecha')['tss'].sum() if not df.empty else pd.Series(dtype=float)
                
                rango = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')
                pmc = pd.DataFrame(index=rango.date)
                pmc['tss'] = tss_diario
                pmc['tss'] = pmc['tss'].fillna(0.0)
                
                k_ctl = 1 - math.exp(-1 / 42.0)
                k_atl = 1 - math.exp(-1 / 7.0)
                
                ctl, atl = 0.0, 0.0
                ctl_l, atl_l, tsb_l = [], [], []
                
                for tss in pmc['tss']:
                    tsb_l.append(round(ctl - atl, 1))
                    ctl += (tss - ctl) * k_ctl
                    atl += (tss - atl) * k_atl
                    ctl_l.append(round(ctl, 1))
                    atl_l.append(round(atl, 1))
                    
                pmc['CTL'] = ctl_l
                pmc['ATL'] = atl_l
                pmc['TSB'] = tsb_l
                
                hoy = pmc.iloc[-1]
                col1, col2, col3 = st.columns(3)
                col1.metric("Forma (CTL)", hoy['CTL'])
                col2.metric("Fatiga (ATL)", hoy['ATL'])
                col3.metric("Frescura (TSB)", hoy['TSB'])
                
                fig = go.Figure()
                
                colores = ['green' if x >= 0 else 'red' for x in pmc['TSB']]
                fig.add_trace(go.Bar(x=pmc.index, y=pmc['TSB'], name='TSB (Frescura)', marker_color=colores))
                
                fig.add_trace(go.Scatter(x=pmc.index, y=pmc['CTL'], name='CTL (Forma)', line=dict(color='blue', width=3)))
                fig.add_trace(go.Scatter(x=pmc.index, y=pmc['ATL'], name='ATL (Fatiga)', line=dict(color='magenta', width=2)))
                
                fig.update_layout(
                    title="Performance Management Chart",
                    xaxis_title="Fecha",
                    yaxis_title="Puntos",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=10, r=10, t=40, b=10)
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Error durante la sincronización: {e}")
