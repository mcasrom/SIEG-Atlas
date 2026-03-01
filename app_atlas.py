"""
S.I.E.G. ATLAS - Geopolitical Infrastructure Dashboard V1.0
Ejes: Petroleo | Maritimo | Cables | MarChina | Espacio | Ciber
"""

import json
import logging
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------------
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_LIVE    = os.path.join(BASE_DIR, "data", "live")
HISTORY_CSV  = os.path.join(DATA_LIVE, "history_atlas.csv")

APP_VERSION  = "V1.0"
BUILD_DATE   = "2026"

MODULOS = ["Petroleo", "Maritimo", "Cables", "MarChina", "Espacio", "Ciber"]

MODULO_DISPLAY = {
    "Petroleo":  "🛢 Petroleo & Gas",
    "Maritimo":  "⚓ Rutas Maritimas",
    "Cables":    "🔌 Cables Submarinos",
    "MarChina":  "🌊 Mar de China",
    "Espacio":   "🛰 Espacio",
    "Ciber":     "💻 Cibergeopolitica",
}

MODULO_DESC = {
    "Petroleo":  "Precios, rutas de suministro, OPEC, embargos y ataques a infraestructura energetica.",
    "Maritimo":  "Estrechos criticos (Hormuz, Suez, Malacca), incidentes navales y bloqueos.",
    "Cables":    "Incidentes en cables submarinos de fibra optica e infraestructura de internet.",
    "MarChina":  "Disputas territoriales, incidentes navales y tension en el Indo-Pacifico.",
    "Espacio":   "Lanzamientos militares, tests ASAT, debris orbital y carrera espacial.",
    "Ciber":     "Alertas APT, ataques a infraestructura critica y actores estatales.",
}

# Coordenadas para mapa de incidentes por modulo
MODULO_COORDS = {
    "Petroleo":  [(26.0,  56.0, "Golfo Persico"),
                  (25.0,  37.0, "Mar Rojo"),
                  (29.0,  48.0, "Kuwait/Iraq"),
                  (56.0,  44.0, "Rusia/Gas"),
                  (4.0,    6.0, "Nigeria/Delta")],
    "Maritimo":  [(26.5,  56.3, "Estrecho de Hormuz"),
                  (12.5,  43.5, "Bab el-Mandeb"),
                  (30.5,  32.3, "Canal de Suez"),
                  (1.3,  103.8, "Estrecho de Malacca"),
                  (22.3, 114.1, "Mar de China Meridional")],
    "Cables":    [(37.0,  25.0, "Mediterraneo"),
                  (51.5,  -0.1, "Atlantico Norte"),
                  (35.0, 139.0, "Pacifico"),
                  (1.3,  103.8, "SE Asia Hub"),
                  (-34.0,-18.0, "Atlantico Sur")],
    "MarChina":  [(15.0, 114.0, "Mar de China Meridional"),
                  (24.5, 122.0, "Estrecho de Taiwan"),
                  (10.0, 109.0, "Islas Spratly"),
                  (16.5, 112.3, "Islas Paracel"),
                  (20.0, 121.0, "Luzon Strait")],
    "Espacio":   [(28.5, -80.6, "Cabo Canaveral"),
                  (45.6,  63.3, "Baikonur"),
                  (19.6, 110.9, "Wenchang"),
                  (5.2,  -52.8, "Kourou"),
                  (30.4, 130.9, "Tanegashima")],
    "Ciber":     [(38.9, -77.0, "CISA/EEUU"),
                  (52.5,  13.4, "BSI/Alemania"),
                  (51.5,  -0.1, "NCSC/UK"),
                  (55.7,  37.6, "APT/Rusia"),
                  (39.9, 116.4, "APT/China")],
}

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
ATLAS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

.stApp { background-color: #080a10; color: #00ccff; }
.block-container { max-width: 98% !important; padding-top: 3.5rem; }

h1, h2, h3 { color: #00ccff !important; font-family: 'Share Tech Mono', monospace; }

.stTabs [data-baseweb="tab-list"] { background-color: #0a0f1a; border-bottom: 1px solid #00ccff; }
.stTabs [data-baseweb="tab"] { color: #0077aa; font-family: monospace; }
.stTabs [aria-selected="true"] { color: #00ccff !important; border-bottom: 2px solid #00ccff !important; }

.atlas-hero {
    border: 1px solid #00ccff; border-top: 3px solid #00ccff;
    background: linear-gradient(180deg, #080f1a 0%, #080a10 100%);
    padding: 16px 22px; border-radius: 6px; margin-bottom: 18px;
    font-family: 'Share Tech Mono', monospace;
}
.atlas-version { color: #00ccff; font-size: 0.72em; letter-spacing: 0.15em; opacity: 0.7; margin-bottom: 5px; }
.atlas-timestamp { color: #0099cc; font-size: 1.0em; font-weight: bold; margin-bottom: 8px; }
.atlas-desc { color: #aaccff; font-size: 0.80em; line-height: 1.8;
    border-top: 1px solid #0a2a3a; padding-top: 8px; }
.atlas-desc span { color: #00ccff; font-weight: bold; }

.alert-box {
    background: #0a1020; border-left: 3px solid #ff4400;
    padding: 8px 14px; margin: 4px 0; border-radius: 3px;
    font-family: monospace; font-size: 0.82em; color: #ffaa88;
}
.module-card {
    background: #0a0f1a; border: 1px solid #0a2a3a;
    border-radius: 6px; padding: 12px; margin-bottom: 8px;
    font-family: monospace;
}
</style>
"""

# ---------------------------------------------------------------------------
# PRECIO PETROLEO — API publica gratuita
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def fetch_oil_price() -> dict:
    """Obtiene precio Brent y WTI via API publica."""
    try:
        # Alpha Vantage free tier — commodity prices
        url = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=5d"
        r = requests.get(url, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        prev  = data["chart"]["result"][0]["meta"]["chartPreviousClose"]
        delta = price - prev
        return {"brent": round(price, 2), "delta": round(delta, 2), "ok": True}
    except Exception:
        pass
    try:
        url2 = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1d&range=5d"
        r = requests.get(url2, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        prev  = data["chart"]["result"][0]["meta"]["chartPreviousClose"]
        return {"wti": round(price, 2), "delta": round(price - prev, 2), "ok": True}
    except Exception:
        return {"ok": False}

# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------

@st.cache_data(ttl=180)
def load_modulo(modulo: str) -> dict:
    path = os.path.join(DATA_LIVE, f"atlas_{modulo.lower()}.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"modulo": modulo, "score": 0, "alertas": [],
                "noticias": 0, "timestamp": 0, "version": "?"}


@st.cache_data(ttl=180)
def load_all_modulos() -> list:
    result = []
    for m in MODULOS:
        d = load_modulo(m)
        result.append({
            "key":       m,
            "display":   MODULO_DISPLAY.get(m, m),
            "score":     float(d.get("score", 0)),
            "alertas":   d.get("alertas", []),
            "noticias":  int(d.get("noticias", 0)),
            "timestamp": float(d.get("timestamp", 0)),
        })
    return sorted(result, key=lambda x: x["score"], reverse=True)


@st.cache_data(ttl=180)
def load_history() -> pd.DataFrame:
    if not os.path.exists(HISTORY_CSV):
        return pd.DataFrame(columns=["timestamp", "modulo", "score", "dt"])
    try:
        df = pd.read_csv(HISTORY_CSV, header=None,
                         names=["timestamp", "modulo", "score"])
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df["score"]  = pd.to_numeric(df["score"], errors="coerce").fillna(0)
        df["modulo"] = df["modulo"].str.strip()
        df["dt"]     = pd.to_datetime(df["timestamp"], unit="s")
        return df.sort_values("dt")
    except Exception as e:
        logger.error("Error cargando historico: %s", e)
        return pd.DataFrame(columns=["timestamp", "modulo", "score", "dt"])

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def score_color_atlas(score: float) -> str:
    if score >= 70: return "#ff2222"
    if score >= 50: return "#ff8800"
    if score >= 30: return "#ffdd00"
    return "#00ccff"

def score_label_atlas(score: float) -> str:
    if score >= 70: return "CRITICO"
    if score >= 50: return "ALTO"
    if score >= 30: return "MEDIO"
    return "NORMAL"

def compute_trends(df: pd.DataFrame, modulos: list) -> dict:
    trends = {}
    for m in modulos:
        s = df[df["modulo"] == m["key"]].sort_values("timestamp", ascending=False)["score"]
        trends[m["key"]] = float(s.iloc[0]) - float(s.iloc[1]) if len(s) >= 2 else 0.0
    return trends

# ---------------------------------------------------------------------------
# COMPONENTES UI
# ---------------------------------------------------------------------------

def render_hero(modulos: list, df: pd.DataFrame) -> None:
    now_str    = datetime.now().strftime("%d-%m-%Y %H:%M:%S UTC")
    ts_vals    = [m["timestamp"] for m in modulos if m["timestamp"] > 0]
    signal_str = datetime.fromtimestamp(max(ts_vals)).strftime("%d-%m-%Y %H:%M:%S") if ts_vals else "SIN SENAL"
    records    = len(df)
    n_alertas  = sum(len(m["alertas"]) for m in modulos)

    st.markdown(f"""
    <div class='atlas-hero'>
        <div class='atlas-version'>
            S.I.E.G. ATLAS {APP_VERSION} &nbsp;|&nbsp;
            6 Ejes Geopoliticos &nbsp;|&nbsp;
            Ciclo: 60 min &nbsp;|&nbsp;
            Nodo: Odroid-C2 / DietPi
        </div>
        <div class='atlas-timestamp'>
            📡 ULTIMA SENAL: {signal_str} &nbsp;|&nbsp;
            📊 REGISTROS: {records:,} &nbsp;|&nbsp;
            🚨 ALERTAS ACTIVAS: {n_alertas} &nbsp;|&nbsp;
            🕐 {now_str}
        </div>
        <div class='atlas-desc'>
            <span>[ MISION ]</span>
            Monitorizacion de infraestructura critica global: energia, rutas maritimas,
            cables submarinos, espacio y ciberespacio.<br>
            <span>[ EJES ]</span>
            Petroleo & Gas · Rutas Maritimas · Cables Submarinos ·
            Mar de China · Espacio · Cibergeopolitica.<br>
            <span>[ METODOLOGIA ]</span>
            OSINT multi-fuente · Scoring por vocabulario especializado ·
            Alertas automaticas por titulares de alta severidad.
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_gauge_grid(modulos: list, trends: dict) -> None:
    cols = st.columns(3)
    for i, m in enumerate(modulos):
        with cols[i % 3]:
            delta  = trends.get(m["key"], 0.0)
            color  = score_color_atlas(m["score"])
            nivel  = score_label_atlas(m["score"])
            arrow  = f"+{delta:.0f}" if delta > 0 else f"{delta:.0f}"

            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=m["score"],
                gauge={
                    "axis": {"range": [0, 100],
                             "tickcolor": "#00ccff",
                             "tickfont": {"color": "#00ccff", "size": 8}},
                    "bar":  {"color": color},
                    "bgcolor": "#0a0f1a",
                    "bordercolor": "#0a2a3a",
                    "steps": [
                        {"range": [0,  30], "color": "#080a10"},
                        {"range": [30, 50], "color": "#0a1410"},
                        {"range": [50, 70], "color": "#1a1000"},
                        {"range": [70,100], "color": "#1a0000"},
                    ],
                },
                number={"font": {"color": "#00ccff", "size": 30}, "suffix": "%"},
                title={"text": m["display"],
                       "font": {"color": "#aaccff", "size": 11}},
            ))
            fig.update_layout(
                height=190,
                margin=dict(t=50, b=10, l=10, r=10),
                paper_bgcolor="#080a10",
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})

            st.markdown(
                f"<div style='text-align:center;font-family:monospace;"
                f"font-size:0.75em;color:#aaccff'>"
                f"{arrow:>5} &nbsp; <b>{nivel}</b> &nbsp; "
                f"{m['noticias']} fuentes</div>",
                unsafe_allow_html=True,
            )

            # Alertas activas bajo el gauge
            for alerta in m["alertas"][:2]:
                st.markdown(
                    f"<div class='alert-box'>↳ {alerta[:90]}</div>",
                    unsafe_allow_html=True,
                )


def render_oil_panel() -> None:
    st.subheader("🛢 Precio del Petroleo — Tiempo Real")
    oil = fetch_oil_price()

    c1, c2, c3 = st.columns(3)
    if oil.get("ok"):
        brent = oil.get("brent") or oil.get("wti", 0)
        delta = oil.get("delta", 0)
        label = "Brent" if "brent" in oil else "WTI"
        color = "normal" if abs(delta) < 2 else ("inverse" if delta < 0 else "normal")
        c1.metric(f"{label} (USD/barril)", f"${brent}", f"{delta:+.2f}")
        c2.metric("Tendencia", "📈 ALZA" if delta > 0 else "📉 BAJA",
                  f"{abs(delta):.2f} vs cierre anterior")
        c3.metric("Nivel de alerta energetica",
                  "⚠ ELEVADO" if brent > 90 else "✅ NORMAL",
                  f"Umbral: $90/barril")
    else:
        st.warning("API de precio no disponible. Verificar conectividad.")

    st.caption("Fuente: Yahoo Finance (datos diferidos ~15 min)")


def render_incident_map(modulos: list, selected_mod: str) -> None:
    """Mapa de puntos calientes por modulo seleccionado."""
    coords = MODULO_COORDS.get(selected_mod, [])
    if not coords:
        st.info("Sin coordenadas para este modulo.")
        return

    mod_data = next((m for m in modulos if m["key"] == selected_mod), None)
    base_score = mod_data["score"] if mod_data else 30

    rows = []
    for lat, lon, nombre in coords:
        rows.append({
            "lat": lat, "lon": lon,
            "nombre": nombre,
            "score": base_score,
            "size": max(base_score * 0.6, 8),
        })

    df_map = pd.DataFrame(rows)
    fig = px.scatter_geo(
        df_map,
        lat="lat", lon="lon",
        size="size",
        color="score",
        color_continuous_scale=[
            [0.0, "#00ccff"],
            [0.5, "#ff8800"],
            [1.0, "#ff0000"],
        ],
        range_color=[0, 100],
        hover_name="nombre",
        hover_data={"score": True, "lat": False, "lon": False, "size": False},
        projection="natural earth",
    )
    fig.update_layout(
        paper_bgcolor="#080a10",
        geo=dict(
            bgcolor="#080a10",
            landcolor="#0a0f1a",
            oceancolor="#05080f",
            showocean=True, showland=True,
            showcountries=True,
            countrycolor="#0a2a3a",
            coastlinecolor="#0a2a3a",
            framecolor="#00ccff",
        ),
        coloraxis_colorbar=dict(
            tickfont={"color": "#00ccff"},
            title=dict(text="Score", font={"color": "#00ccff"}),
        ),
        margin=dict(t=10, b=10, l=0, r=0),
        height=380,
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


def render_cyber_timeline(df: pd.DataFrame) -> None:
    """Timeline de actividad de ciberataques."""
    df_c = df[df["modulo"] == "Ciber"].sort_values("dt")
    if df_c.empty:
        st.info("Sin datos historicos de Ciber.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_c["dt"], y=df_c["score"],
        mode="lines+markers",
        fill="tozeroy",
        fillcolor="rgba(0,100,255,0.08)",
        line=dict(color="#00ccff", width=2),
        marker=dict(size=5, color="#00ccff"),
        name="Score Ciber",
        hovertemplate="%{x}<br>Score: %{y}%<extra></extra>",
    ))
    fig.add_hline(y=70, line_dash="dot", line_color="#ff2222",
                  annotation_text="CRITICO", annotation_font_color="#ff2222")
    fig.add_hline(y=50, line_dash="dot", line_color="#ff8800",
                  annotation_text="ALTO", annotation_font_color="#ff8800")
    fig.update_layout(
        paper_bgcolor="#080a10", plot_bgcolor="#080a10",
        font_color="#00ccff",
        xaxis=dict(gridcolor="#0a2a3a", tickfont={"color": "#aaccff"}),
        yaxis=dict(range=[0, 105], gridcolor="#0a2a3a",
                   tickfont={"color": "#aaccff"}),
        margin=dict(t=20, b=20, l=10, r=10),
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


def render_maritime_alerts(modulos: list) -> None:
    """Panel de alertas maritimas activas."""
    mar = next((m for m in modulos if m["key"] == "Maritimo"), None)
    if not mar:
        return

    col1, col2 = st.columns([1, 2])
    with col1:
        nivel = score_label_atlas(mar["score"])
        color = score_color_atlas(mar["score"])
        st.markdown(f"""
        <div style='background:#0a0f1a;border:1px solid {color};border-radius:6px;
                    padding:20px;text-align:center;font-family:monospace;'>
            <div style='color:#aaccff;font-size:0.8em;margin-bottom:8px'>
                NIVEL DE RIESGO MARITIMO
            </div>
            <div style='color:{color};font-size:2.5em;font-weight:bold'>
                {mar["score"]}%
            </div>
            <div style='color:{color};font-size:1em;margin-top:5px'>
                {nivel}
            </div>
            <div style='color:#aaccff;font-size:0.75em;margin-top:10px'>
                {mar["noticias"]} fuentes monitorizadas
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("**Estrechos criticos monitorizados:**")
        estrechos = [
            ("🔴 Estrecho de Hormuz", "20% trafico mundial de petroleo"),
            ("🟡 Bab el-Mandeb",      "Acceso al Canal de Suez / Mar Rojo"),
            ("🟢 Canal de Suez",      "12% comercio maritimo global"),
            ("🟢 Estrecho de Malacca","Ruta Asia-Europa / energia"),
            ("🟡 Mar de China Sur",   "Disputa territorial activa"),
        ]
        for nombre, desc in estrechos:
            st.markdown(f"**{nombre}** — {desc}")

        if mar["alertas"]:
            st.divider()
            st.markdown("**Alertas activas:**")
            for a in mar["alertas"]:
                st.markdown(
                    f"<div class='alert-box'>⚠ {a[:110]}</div>",
                    unsafe_allow_html=True,
                )


def render_comparative(df: pd.DataFrame) -> None:
    if df.empty:
        return
    palette = ["#00ccff","#ff8800","#00ff41","#ff2222",
               "#ffdd00","#ff44aa"]
    fig = go.Figure()
    for idx, m in enumerate(MODULOS):
        df_m = df[df["modulo"] == m].sort_values("dt")
        if df_m.empty:
            continue
        fig.add_trace(go.Scatter(
            x=df_m["dt"], y=df_m["score"],
            mode="lines",
            name=MODULO_DISPLAY.get(m, m),
            line=dict(color=palette[idx % len(palette)], width=2),
            hovertemplate="%{fullData.name}<br>%{x}<br>%{y}%<extra></extra>",
        ))
    fig.add_hline(y=70, line_dash="dot", line_color="#ff2222",
                  annotation_text="CRITICO", annotation_font_color="#ff2222",
                  annotation_font_size=9)
    fig.add_hline(y=50, line_dash="dot", line_color="#ff8800",
                  annotation_text="ALTO", annotation_font_color="#ff8800",
                  annotation_font_size=9)
    fig.update_layout(
        paper_bgcolor="#080a10", plot_bgcolor="#080a10",
        font_color="#00ccff",
        xaxis=dict(gridcolor="#0a2a3a", tickfont={"color":"#aaccff"}),
        yaxis=dict(range=[0,105], gridcolor="#0a2a3a",
                   tickfont={"color":"#aaccff"}),
        legend=dict(bgcolor="#0a0f1a", bordercolor="#0a2a3a",
                    font={"color":"#aaccff","size":10}),
        margin=dict(t=20, b=20, l=10, r=10),
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


def render_module_detail(modulo: dict, df: pd.DataFrame) -> None:
    key = modulo["key"]
    st.markdown(f"*{MODULO_DESC.get(key, '')}*")
    st.divider()

    c1, c2, c3 = st.columns(3)
    c1.metric("Score actual", f"{modulo['score']}%")
    c2.metric("Nivel", score_label_atlas(modulo["score"]))
    c3.metric("Fuentes procesadas", modulo["noticias"])

    df_m = df[df["modulo"] == key].sort_values("dt")
    if not df_m.empty:
        fig = go.Figure(go.Scatter(
            x=df_m["dt"], y=df_m["score"],
            mode="lines+markers",
            fill="tozeroy",
            fillcolor="rgba(0,150,255,0.06)",
            line=dict(color="#00ccff", width=2),
            marker=dict(size=4),
        ))
        fig.add_hline(y=70, line_dash="dot", line_color="#ff2222")
        fig.add_hline(y=50, line_dash="dot", line_color="#ff8800")
        fig.update_layout(
            paper_bgcolor="#080a10", plot_bgcolor="#080a10",
            font_color="#00ccff",
            xaxis=dict(gridcolor="#0a2a3a", tickfont={"color":"#aaccff"}),
            yaxis=dict(range=[0,105], gridcolor="#0a2a3a",
                       tickfont={"color":"#aaccff"}),
            margin=dict(t=10, b=10, l=10, r=10),
            height=260,
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
        st.caption(
            f"Min: {df_m['score'].min():.0f}% · "
            f"Max: {df_m['score'].max():.0f}% · "
            f"Media: {df_m['score'].mean():.1f}% · "
            f"Registros: {len(df_m)}"
        )

    if modulo["alertas"]:
        st.subheader("Alertas activas")
        for a in modulo["alertas"]:
            st.markdown(
                f"<div class='alert-box'>🚨 {a}</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="S.I.E.G. ATLAS",
        page_icon="🌐",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(ATLAS_CSS, unsafe_allow_html=True)

    modulos    = load_all_modulos()
    df_history = load_history()
    trends     = compute_trends(df_history, modulos)

    # Sidebar minimo
    with st.sidebar:
        st.header("🌐 S.I.E.G. ATLAS")
        st.caption(f"Version: {APP_VERSION}")
        st.divider()
        st.markdown("**Modulos activos:**")
        for m in modulos:
            color = score_color_atlas(m["score"])
            st.markdown(
                f"<span style='color:{color}'>■</span> "
                f"{m['display']} — **{m['score']}%**",
                unsafe_allow_html=True,
            )
        st.divider()
        st.markdown("**Proyecto relacionado:**")
        st.markdown("[S.I.E.G. Core →](https://sieg-core.streamlit.app)")
        st.code("mybloggingnotes@gmail.com", language=None)

    # Cabecera
    st.title("🌐 S.I.E.G. ATLAS — INFRASTRUCTURE INTELLIGENCE")
    render_hero(modulos, df_history)

    # Tabs principales
    tab_overview, tab_oil, tab_maritime, tab_cyber, tab_map, tab_comparative, tab_detail = st.tabs([
        "📊 Overview",
        "🛢 Petroleo",
        "⚓ Maritimo",
        "💻 Ciber Timeline",
        "🗺 Mapa",
        "📈 Comparativa",
        "🔍 Por Modulo",
    ])

    with tab_overview:
        st.subheader("Estado Actual — 6 Ejes Geopoliticos")
        render_gauge_grid(modulos, trends)

        st.divider()
        # Tabla resumen
        rows = [{
            "Modulo":    m["display"],
            "Score %":   int(m["score"]),
            "Nivel":     score_label_atlas(m["score"]),
            "Alertas":   len(m["alertas"]),
            "Fuentes":   m["noticias"],
        } for m in modulos]
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Score %": st.column_config.ProgressColumn(
                    "Score %", min_value=0, max_value=100, format="%d%%"
                ),
            },
        )

    with tab_oil:
        render_oil_panel()
        st.divider()
        st.subheader("Evolucion Historica — Tension Energetica")
        df_pet = df_history[df_history["modulo"] == "Petroleo"].sort_values("dt")
        if not df_pet.empty:
            fig = go.Figure(go.Scatter(
                x=df_pet["dt"], y=df_pet["score"],
                mode="lines+markers",
                fill="tozeroy",
                fillcolor="rgba(255,150,0,0.08)",
                line=dict(color="#ff8800", width=2),
                marker=dict(size=4, color="#ff8800"),
            ))
            fig.update_layout(
                paper_bgcolor="#080a10", plot_bgcolor="#080a10",
                font_color="#00ccff",
                xaxis=dict(gridcolor="#0a2a3a", tickfont={"color":"#aaccff"}),
                yaxis=dict(range=[0,105], gridcolor="#0a2a3a",
                           tickfont={"color":"#aaccff"}),
                margin=dict(t=10, b=10, l=10, r=10),
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})

    with tab_maritime:
        st.subheader("Alertas de Incidentes Maritimos en Vivo")
        render_maritime_alerts(modulos)

    with tab_cyber:
        st.subheader("Timeline de Actividad Cibergeopolitica")
        render_cyber_timeline(df_history)
        st.divider()
        ciber = next((m for m in modulos if m["key"] == "Ciber"), None)
        if ciber and ciber["alertas"]:
            st.subheader("Alertas activas")
            for a in ciber["alertas"]:
                st.markdown(
                    f"<div class='alert-box'>🚨 {a}</div>",
                    unsafe_allow_html=True,
                )

    with tab_map:
        st.subheader("Mapa de Puntos Calientes por Eje")
        sel_mod = st.radio(
            "Seleccionar eje:",
            MODULOS,
            format_func=lambda x: MODULO_DISPLAY.get(x, x),
            horizontal=True,
        )
        render_incident_map(modulos, sel_mod)

    with tab_comparative:
        st.subheader("Evolucion Comparativa — Todos los Ejes")
        render_comparative(df_history)

    with tab_detail:
        st.subheader("Detalle por Modulo")
        sel = st.selectbox(
            "Seleccionar modulo:",
            [m["display"] for m in modulos],
        )
        sel_mod = next(m for m in modulos if m["display"] == sel)
        render_module_detail(sel_mod, df_history)

    st.divider()
    st.caption(
        f"S.I.E.G. ATLAS {APP_VERSION} · "
        f"Infraestructura Critica Global · {BUILD_DATE}"
    )


if __name__ == "__main__":
    main()
