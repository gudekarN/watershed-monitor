"""
AquaVeda — Satellite-Based Watershed Impact Monitor
Smart India Hackathon 2026 | Team AquaVeda
Demo Mode: Loads data from local JSON files. No GEE dependency.
Run with:  streamlit run app.py
"""

import os
import sys
import json
import subprocess

import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 1. PAGE CONFIG  (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AquaVeda — Watershed Monitor",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load custom CSS
_CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "style.css")
if os.path.exists(_CSS_PATH):
    with open(_CSS_PATH, encoding="utf-8") as _f:
        _css_content = _f.read()
    st.markdown(f"<style>{_css_content}</style>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

DATA_FILES = {
    "watersheds":       "sample_watersheds.json",
    "change_data":      "change_data.json",
    "health_scores":    "health_scores.json",
    "ndvi_timeseries":  "ndvi_timeseries.json",
    "water_timeseries": "water_timeseries.json",
    "landuse":          "landuse_transition.json",
    "photos":           "sample_photo_metadata.json",
    "boundary":         "watershed_boundary_hiware_bazar.geojson",
    "drainage":         "drainage_network.geojson",
    "erosion":          "erosion_data.json",
    "monthly_ndvi":     "monthly_ndvi.json",
    "rainfall":         "rainfall_data.json",
}

STATUS_COLORS = {
    "Functional":   "#22c55e",
    "Needs Repair": "#f59e0b",
    "Damaged":      "#ef4444",
    "Dry":          "#94a3b8",
}

TYPE_ICONS = {
    "Check Dam":        "🌊",
    "Farm Pond":        "💧",
    "Contour Trench":   "🏔️",
    "Percolation Tank": "🔵",
    "Gabion Structure": "🪨",
}

LANDUSE_COLORS = {
    "Water":             "#3b82f6",
    "Dense Vegetation":  "#16a34a",
    "Sparse Vegetation": "#86efac",
    "Barren":            "#d97706",
    "Built-up":          "#6b7280",
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. LOAD DEMO DATA
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(filename: str):
    """Load a JSON / GeoJSON file from DATA_DIR."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_demo_data() -> dict:
    """
    Load all 12 demo JSON files into st.session_state.demo_data.
    If any file is missing, run generate_demo_data.py first.
    Returns the full data dictionary.
    """
    if "demo_data" in st.session_state:
        return st.session_state.demo_data

    missing = [
        fname for fname in DATA_FILES.values()
        if not os.path.exists(os.path.join(DATA_DIR, fname))
    ]
    if missing:
        gen_script = os.path.join(DATA_DIR, "generate_demo_data.py")
        if os.path.exists(gen_script):
            with st.spinner("Generating demo data files…"):
                subprocess.run([sys.executable, gen_script], check=False)
        else:
            st.warning(f"Missing data files and generate_demo_data.py not found: {missing}")

    data = {key: _load_json(fname) for key, fname in DATA_FILES.items()}
    st.session_state.demo_data = data
    return data


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_watershed_by_id(watersheds: list, wid: str) -> dict:
    for ws in watersheds:
        if ws["id"] == wid:
            return ws
    return watersheds[0] if watersheds else {}


def ws_label(ws: dict) -> str:
    return f"{ws['name']}, {ws['state']}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. DEMO-MODE BANNER  (very top)
# ─────────────────────────────────────────────────────────────────────────────
st.info(
    "ℹ️ Running in **Demo Mode** with sample data. "
    "Connect GEE for live satellite analysis.",
    icon="📡",
)

# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
data = load_all_demo_data()
watersheds: list = data.get("watersheds") or []

# ─────────────────────────────────────────────────────────────────────────────
# 3. SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 🌊 AquaVeda")
    st.markdown("### Satellite Watershed Monitor")
    st.divider()

    ws_names = [ws_label(ws) for ws in watersheds]
    ws_ids   = [ws["id"] for ws in watersheds]

    if "selected_watershed_id" not in st.session_state:
        st.session_state.selected_watershed_id = ws_ids[0] if ws_ids else None

    sel_idx = ws_ids.index(st.session_state.selected_watershed_id) \
        if st.session_state.selected_watershed_id in ws_ids else 0

    chosen_name = st.selectbox(
        "Select Watershed",
        options=ws_names,
        index=sel_idx,
        key="ws_selectbox",
    )
    chosen_id = ws_ids[ws_names.index(chosen_name)]
    st.session_state.selected_watershed_id = chosen_id

    selected_ws = get_watershed_by_id(watersheds, chosen_id)

    # Watershed info panel
    st.markdown("#### 📍 Watershed Info")
    structs = selected_ws.get("structures", {})
    st.markdown(
        f"**State:** {selected_ws.get('state', '—')}  \n"
        f"**District:** {selected_ws.get('district', '—')}  \n"
        f"**Area:** {selected_ws.get('area_sq_km', '—')} sq km  \n"
        f"**Rainfall:** {selected_ws.get('annual_rainfall_mm', '—')} mm/year  \n"
        f"**Project Started:** {selected_ws.get('start_year', '—')}"
    )
    if structs:
        st.markdown("**Structures:**")
        for k, v in structs.items():
            st.markdown(f"&nbsp;&nbsp;• {v} {k.replace('_', ' ').title()}")

    st.divider()

    # Map layer checkboxes
    st.markdown("#### 🗺️ Map Layers")
    show_ndvi     = st.checkbox("Show NDVI Layer",         value=True,  key="show_ndvi")
    show_water    = st.checkbox("Show Water Bodies",        value=True,  key="show_water")
    show_boundary = st.checkbox("Show Watershed Boundary", value=True,  key="show_boundary")
    show_photos   = st.checkbox("Show Field Photos",        value=True,  key="show_photos")
    show_drainage = st.checkbox("Show Drainage Network",    value=False, key="show_drainage")

    st.divider()

    if st.button("📄 Generate Report", use_container_width=True):
        st.info(
            "Report generation is coming soon! "
            "This will export a PDF with all metrics and maps.",
            icon="📋",
        )

# ─────────────────────────────────────────────────────────────────────────────
# 4. HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🌊 Satellite-Based Watershed Impact Monitor")
st.markdown("*Using Remote Sensing & GEE for Watershed Development Monitoring*")

# ─────────────────────────────────────────────────────────────────────────────
# 5. METRIC CARDS
# ─────────────────────────────────────────────────────────────────────────────
change_data_all: dict = data.get("change_data") or {}
cd = change_data_all.get(chosen_id, {})
veg     = cd.get("vegetation", {})
water   = cd.get("water", {})
erosion = cd.get("erosion", {})

health_all: dict = data.get("health_scores") or {}
hs = health_all.get(chosen_id, {})

ndvi_change = veg.get("change", 0)
ndvi_before = veg.get("ndvi_before", 0.01)
ndvi_pct    = round(ndvi_change / max(ndvi_before, 0.01) * 100, 1)
water_after = water.get("area_after_ha", 0)
water_chpct = water.get("change_percent", 0)
ero_red     = erosion.get("reduction_percent", 0)
score       = hs.get("total_score", 0)
grade       = hs.get("grade", "—")

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("🌿 NDVI Change",  f"+{ndvi_change:.2f}", delta=f"+{ndvi_pct}%")
with m2:
    st.metric("💧 Water Area",   f"{water_after} ha",   delta=f"+{water_chpct:.1f}%")
with m3:
    st.metric("🏜️ Erosion Risk", f"-{ero_red:.1f}%",    delta=f"-{ero_red:.1f}%",
              delta_color="inverse")
with m4:
    st.metric("🎯 Health Score", f"{score}/100",         delta=grade)

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# 6. MAIN TWO-COLUMN LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

# ────────────────────────────  LEFT (60%)  ───────────────────────────────────
with col_left:
    tab_map, tab_ba, tab_fp = st.tabs(["🗺️ Map", "📸 Before/After", "📷 Field Photos"])

    # ── Map tab ──────────────────────────────────────────────────────────────
    with tab_map:
        lat = selected_ws.get("lat", 19.35)
        lon = selected_ws.get("lon", 74.55)

        m = folium.Map(location=[lat, lon], zoom_start=13, tiles=None)

        folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
        folium.TileLayer(
            tiles=(
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ),
            attr="Esri",
            name="Esri Satellite",
        ).add_to(m)

        # Watershed boundary
        boundary_geojson = data.get("boundary")
        if show_boundary:
            if boundary_geojson and chosen_id == "hiware_bazar":
                folium.GeoJson(
                    boundary_geojson,
                    name="Watershed Boundary",
                    style_function=lambda _: {
                        "color": "#3b82f6",
                        "weight": 3,
                        "dashArray": "8 4",
                        "fillOpacity": 0.05,
                        "fillColor": "#3b82f6",
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=["name", "area_sq_km"],
                        aliases=["Watershed:", "Area (sq km):"],
                    ),
                ).add_to(m)
            else:
                folium.Circle(
                    location=[lat, lon],
                    radius=selected_ws.get("area_sq_km", 10) * 180,
                    color="#3b82f6",
                    weight=3,
                    dash_array="8 4",
                    fill=True,
                    fill_opacity=0.05,
                    tooltip=f"{selected_ws.get('name')} Watershed Boundary (approximate)",
                ).add_to(m)

        # Drainage network
        drainage_geojson = data.get("drainage")
        if show_drainage and drainage_geojson and chosen_id == "hiware_bazar":
            folium.GeoJson(
                drainage_geojson,
                name="Drainage Network",
                style_function=lambda _: {
                    "color": "#7dd3fc",
                    "weight": 2,
                    "opacity": 0.9,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["name", "stream_order", "length_km"],
                    aliases=["Stream:", "Order:", "Length (km):"],
                ),
            ).add_to(m)

        # Photo markers
        photos_all: list = data.get("photos") or []
        ws_photos = [p for p in photos_all if p.get("watershed_id") == chosen_id]
        if show_photos:
            color_map = {
                "Functional":   "green",
                "Needs Repair": "orange",
                "Damaged":      "red",
                "Dry":          "gray",
            }
            for photo in ws_photos:
                status    = photo.get("status", "Unknown")
                pin_color = color_map.get(status, "blue")
                icon_char = TYPE_ICONS.get(photo.get("type", ""), "📍")
                popup_html = (
                    f"<div style='font-family:sans-serif;min-width:200px'>"
                    f"<b>{icon_char} {photo.get('type','')}</b><br>"
                    f"<span style='color:{STATUS_COLORS.get(status,'#888')}'>● {status}</span><br>"
                    f"<small>{photo.get('description','')}</small><br>"
                    f"<small>📅 {photo.get('date','')}</small><br>"
                    f"<small>💧 Water level: {photo.get('water_level','')}</small>"
                    f"</div>"
                )
                folium.Marker(
                    location=[photo["lat"], photo["lon"]],
                    popup=folium.Popup(popup_html, max_width=260),
                    tooltip=f"{photo.get('type')} — {status}",
                    icon=folium.Icon(color=pin_color, icon="camera", prefix="fa"),
                ).add_to(m)

        folium.LayerControl(collapsed=False).add_to(m)
        st_folium(m, width=700, height=500, returned_objects=[])

    # ── Before / After tab ───────────────────────────────────────────────────
    with tab_ba:
        ndvi_bef = veg.get("ndvi_before", 0.28)
        ndvi_aft = veg.get("ndvi_after",  0.58)
        start_yr = selected_ws.get("start_year", 2019)

        ba1, ba2 = st.columns(2)
        with ba1:
            st.markdown(f"### 📷 Before ({start_yr})")
            st.info(
                f"**NDVI: {ndvi_bef:.2f}** | Dry, sparse vegetation\n\n"
                f"🌾 Vegetation: sparse  \n"
                f"💧 Water bodies: {water.get('area_before_ha','—')} ha  \n"
                f"🏜️ Barren land: high risk",
                icon="🔴",
            )
        with ba2:
            st.markdown("### 🌿 After (2024)")
            st.success(
                f"**NDVI: {ndvi_aft:.2f}** | Green, healthy crops\n\n"
                f"🌾 Vegetation: dense  \n"
                f"💧 Water bodies: {water.get('area_after_ha','—')} ha  \n"
                f"✅ Erosion risk reduced",
                icon="✅",
            )

        st.markdown("---")
        improved_ha  = veg.get("improved_area_ha", 0)
        pct_improved = veg.get("percent_improved", 0)
        st.markdown(
            f"**📊 Change Summary**  \n"
            f"- Vegetation improved across **{improved_ha} ha** "
            f"({pct_improved:.1f}% of watershed)  \n"
            f"- NDVI increased by **+{ndvi_change:.2f}** (+{ndvi_pct:.1f}%)  \n"
            f"- Water area grew by **{water.get('change_ha', 0)} ha** "
            f"({water.get('change_percent', 0):.0f}% increase)  \n"
            f"- Erosion risk reduced by **{ero_red:.1f}%**  \n"
            f"- Water availability: "
            f"**{water.get('months_with_water_before','—')} → "
            f"{water.get('months_with_water_after','—')} months/year**"
        )

    # ── Field Photos tab ─────────────────────────────────────────────────────
    with tab_fp:
        if ws_photos:
            st.markdown(f"**{len(ws_photos)} field records** for {chosen_name}")
            fp_cols = st.columns(3)
            for i, photo in enumerate(ws_photos):
                status    = photo.get("status", "Unknown")
                bg_color  = STATUS_COLORS.get(status, "#94a3b8")
                icon_char = TYPE_ICONS.get(photo.get("type", ""), "📍")
                with fp_cols[i % 3]:
                    st.markdown(
                        f"""
                        <div style="border:1px solid {bg_color};border-radius:10px;
                                    padding:12px;margin-bottom:10px;background:rgba(0,0,0,0.03)">
                          <div style="font-size:1.4rem">{icon_char}</div>
                          <b>{photo.get('type','')}</b><br>
                          <span style="background:{bg_color};color:white;
                                       border-radius:4px;padding:2px 8px;
                                       font-size:0.75rem">{status}</span><br>
                          <small>📍 {photo.get('lat',0):.4f}, {photo.get('lon',0):.4f}</small><br>
                          <small>📅 {photo.get('date','')}</small><br>
                          <small style="color:#555">{photo.get('description','')}</small>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.info(f"No field photos recorded for **{chosen_name}** yet.")

        st.markdown("---")
        st.markdown("#### 📤 Upload Field Photo")
        st.file_uploader(
            "Upload geotagged photo (JPG/PNG)",
            type=["jpg", "jpeg", "png"],
            disabled=True,
            help="Photo upload will be enabled in the next release.",
        )
        st.caption("📡 Photo upload requires GEE integration — coming soon.")


# ───────────────────────────  RIGHT (40%)  ───────────────────────────────────
with col_right:
    tab_trends, tab_health, tab_lu = st.tabs(["📊 Trends", "🎯 Health", "📈 Land Use"])

    # ── Trends tab ───────────────────────────────────────────────────────────
    with tab_trends:
        ndvi_ts_all: dict = data.get("ndvi_timeseries") or {}
        ndvi_ts: list     = ndvi_ts_all.get(chosen_id, [])

        if ndvi_ts:
            df_ndvi = pd.DataFrame(ndvi_ts)
            fig_ndvi = go.Figure()
            fig_ndvi.add_trace(go.Scatter(
                x=df_ndvi["year"], y=df_ndvi["ndvi_mean"],
                mode="lines+markers", name="NDVI Mean",
                line=dict(color="#22c55e", width=2.5),
                marker=dict(size=7, color="#16a34a"),
            ))
            if "ndvi_max" in df_ndvi.columns:
                years_fwd = df_ndvi["year"].tolist()
                years_rev = years_fwd[::-1]
                ymax = df_ndvi["ndvi_max"].tolist()
                ymin = df_ndvi["ndvi_min"].tolist()[::-1]
                fig_ndvi.add_trace(go.Scatter(
                    x=years_fwd + years_rev,
                    y=ymax + ymin,
                    fill="toself",
                    fillcolor="rgba(34,197,94,0.12)",
                    line=dict(color="rgba(0,0,0,0)"),
                    name="NDVI Range", showlegend=False,
                ))
            fig_ndvi.add_hline(
                y=0.4, line_dash="dash", line_color="red",
                annotation_text="Threshold 0.4",
                annotation_position="top left",
            )
            start_year = selected_ws.get("start_year", 2019)
            yr_min = df_ndvi["year"].min()
            yr_max = df_ndvi["year"].max()
            if yr_min <= start_year <= yr_max:
                fig_ndvi.add_vline(
                    x=start_year, line_dash="dot", line_color="#f59e0b",
                    annotation_text="Project Started",
                    annotation_position="top right",
                )
            fig_ndvi.update_layout(
                template="plotly_dark",
                margin=dict(l=60, r=30, t=60, b=60),
                title=dict(
                    text="Vegetation Health Trend (NDVI)",
                    font=dict(size=15, color="#e2e8f0"),
                    x=0.02, xanchor="left", pad=dict(b=15)
                ),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)
                ),
                xaxis=dict(title=dict(font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                yaxis=dict(title=dict(font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_ndvi, use_container_width=True)
        else:
            st.info("No NDVI timeseries data for this watershed.")

        water_ts_all: dict = data.get("water_timeseries") or {}
        water_ts: list     = water_ts_all.get(chosen_id, [])
        if water_ts:
            df_water = pd.DataFrame(water_ts)
            fig_water = go.Figure(go.Bar(
                x=df_water["year"], y=df_water["water_area_ha"],
                marker_color="#3b82f6", name="Water Area (ha)",
            ))
            fig_water.update_layout(
                template="plotly_dark",
                margin=dict(l=60, r=30, t=60, b=60),
                title=dict(
                    text="Water Body Area Over Time",
                    font=dict(size=15, color="#e2e8f0"),
                    x=0.02, xanchor="left", pad=dict(b=15)
                ),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)
                ),
                xaxis=dict(title=dict(font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                yaxis=dict(title=dict(font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_water, use_container_width=True)
        else:
            st.info("No water timeseries data for this watershed.")

    # ── Health tab ───────────────────────────────────────────────────────────
    with tab_health:
        total_score = hs.get("total_score", 0)
        grade_label = hs.get("grade", "—")
        grade_emoji = hs.get("grade_emoji", "")
        veg_score   = hs.get("vegetation_score", 0)
        wat_score   = hs.get("water_score", 0)
        ero_score   = hs.get("erosion_score", 0)
        sus_score   = hs.get("sustainability_score", 0)

        bar_color = "#22c55e"
        if total_score < 40:
            bar_color = "#ef4444"
        elif total_score < 60:
            bar_color = "#f59e0b"
        elif total_score < 80:
            bar_color = "#facc15"

        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=total_score,
            number=dict(font=dict(size=48, color="#e2e8f0")),
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#94a3b8", 'tickfont': dict(size=10)},
                'bar': {'color': bar_color, 'thickness': 0.7},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 39], 'color': 'rgba(239,68,68,0.35)'},
                    {'range': [40, 59], 'color': 'rgba(245,158,11,0.35)'},
                    {'range': [60, 79], 'color': 'rgba(250,204,21,0.35)'},
                    {'range': [80, 100], 'color': 'rgba(34,197,94,0.35)'}
                ]
            }
        ))
        fig_gauge.update_layout(
            height=350, margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.markdown(f"<h3 style='text-align:center;margin-top:-20px;color:#e2e8f0;'>Grade: {grade_label} {grade_emoji}</h3>", unsafe_allow_html=True)

        st.markdown("**Score Breakdown**")
        st.markdown(f"🌿 Vegetation: **{veg_score}/35**")
        st.progress(min(veg_score / 35, 1.0))
        st.markdown(f"💧 Water: **{wat_score}/35**")
        st.progress(min(wat_score / 35, 1.0))
        st.markdown(f"🏜️ Erosion: **{ero_score}/20**")
        st.progress(min(ero_score / 20, 1.0))
        st.markdown(f"♻️ Sustainability: **{sus_score}/10**")
        st.progress(min(sus_score / 10, 1.0))

        recommendations = hs.get("recommendations", [])
        if recommendations:
            st.subheader("📋 Recommendations")
            for rec in recommendations:
                if "URGENT" in rec.upper() or "damage" in rec.lower():
                    st.warning(rec, icon="⚠️")
                else:
                    st.info(rec, icon="💡")

    # ── Land Use tab ─────────────────────────────────────────────────────────
    with tab_lu:
        lu_all: dict = data.get("landuse") or {}
        lu = lu_all.get(chosen_id, {})
        labels       = lu.get("labels", [])
        before_areas = lu.get("before_areas_ha", [])
        after_areas  = lu.get("after_areas_ha", [])

        if labels and before_areas and after_areas:
            bar_colors = [LANDUSE_COLORS.get(lbl, "#888888") for lbl in labels]
            fig_lu = go.Figure()
            fig_lu.add_trace(go.Bar(
                name="Before (2019)", x=labels, y=before_areas,
                marker_color="#9ca3af", opacity=0.8,
            ))
            fig_lu.add_trace(go.Bar(
                name="After (2024)", x=labels, y=after_areas,
                marker_color=bar_colors, opacity=0.9,
            ))
            fig_lu.update_layout(
                template="plotly_dark",
                barmode="group",
                bargap=0.25,
                margin=dict(l=60, r=30, t=60, b=100),
                title=dict(
                    text="Land Use Change (Before vs After)",
                    font=dict(size=15, color="#e2e8f0"),
                    x=0.02, xanchor="left", pad=dict(b=15)
                ),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)
                ),
                xaxis=dict(title=dict(text="Land Use Class", font=dict(size=12), standoff=15), tickfont=dict(size=10), tickangle=-30, automargin=True),
                yaxis=dict(title=dict(text="Area (ha)", font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_lu, use_container_width=True)

            flows = lu.get("flows", [])
            if flows:
                st.markdown("**Transition Flows**")
                df_flows = pd.DataFrame(flows)
                df_flows.columns = ["From", "To", "Area (ha)"]
                st.dataframe(df_flows, use_container_width=True, hide_index=True)
        else:
            st.info("No land use data available for this watershed.")


# ─────────────────────────────────────────────────────────────────────────────
# 7. BOTTOM — Detailed Analysis expander
# ─────────────────────────────────────────────────────────────────────────────
st.divider()

with st.expander("📋 Detailed Analysis", expanded=False):
    det1, det2 = st.columns(2)

    with det1:
        st.markdown("#### 🏜️ Erosion Risk Classes")
        ero_before = erosion.get("classes_before", {})
        ero_after  = erosion.get("classes_after", {})
        if ero_before and ero_after:
            classes = list(ero_before.keys())
            df_ero = pd.DataFrame({
                "Class":       classes,
                "Before (ha)": [ero_before.get(c, 0) for c in classes],
                "After (ha)":  [ero_after.get(c, 0) for c in classes],
                "Change (ha)": [ero_after.get(c, 0) - ero_before.get(c, 0) for c in classes],
            })
            st.dataframe(df_ero, use_container_width=True, hide_index=True)
        else:
            st.info("No erosion class data available.")

    with det2:
        monthly_all: dict = data.get("monthly_ndvi") or {}
        monthly_ws: list  = monthly_all.get(chosen_id, [])
        if monthly_ws:
            st.markdown("#### 🌿 Monthly NDVI Pattern")
            df_m = pd.DataFrame(monthly_ws)
            xcol = next(
                (c for c in ["month_name", "month"] if c in df_m.columns),
                df_m.columns[0],
            )
            ycol = next(
                (c for c in ["ndvi_mean", "ndvi"] if c in df_m.columns),
                df_m.columns[1],
            )
            fig_m = px.line(
                df_m, x=xcol, y=ycol, markers=True,
                title="Monthly NDVI (Latest Year)",
                color_discrete_sequence=["#22c55e"],
            )
            fig_m.update_layout(
                template="plotly_dark",
                margin=dict(l=60, r=30, t=60, b=60),
                title=dict(
                    text="Monthly NDVI (Latest Year)",
                    font=dict(size=15, color="#e2e8f0"),
                    x=0.02, xanchor="left", pad=dict(b=15)
                ),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)
                ),
                xaxis=dict(title=dict(text=xcol, font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                yaxis=dict(title=dict(text=ycol, font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_m, use_container_width=True)

        rainfall_all: dict = data.get("rainfall") or {}
        rainfall_ws: list  = rainfall_all.get(chosen_id, [])
        if rainfall_ws and ndvi_ts:
            st.markdown("#### 🌧️ Rainfall vs NDVI Correlation")
            df_rain  = pd.DataFrame(rainfall_ws)
            df_ndvi2 = pd.DataFrame(ndvi_ts)
            rain_col = next(
                (c for c in ["annual_rainfall_mm", "rainfall_mm"] if c in df_rain.columns),
                df_rain.columns[-1],
            )
            if "year" in df_rain.columns and "year" in df_ndvi2.columns:
                df_merged = pd.merge(
                    df_rain[["year", rain_col]],
                    df_ndvi2[["year", "ndvi_mean"]],
                    on="year", how="inner",
                )
                if not df_merged.empty:
                    fig_corr = px.scatter(
                        df_merged, x=rain_col, y="ndvi_mean", text="year",
                        trendline="ols", title="Rainfall vs NDVI",
                        color_discrete_sequence=["#3b82f6"],
                    )
                    fig_corr.update_layout(
                        template="plotly_dark",
                        margin=dict(l=60, r=30, t=60, b=60),
                        title=dict(
                            text="Rainfall vs NDVI",
                            font=dict(size=15, color="#e2e8f0"),
                            x=0.02, xanchor="left", pad=dict(b=15)
                        ),
                        legend=dict(
                            orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1, font=dict(size=11)
                        ),
                        xaxis=dict(title=dict(text=rain_col, font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                        yaxis=dict(title=dict(text="NDVI Mean", font=dict(size=12), standoff=15), tickfont=dict(size=10), automargin=True),
                        height=320,
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig_corr, use_container_width=True)

st.caption(
    "Built for Smart India Hackathon 2026 | Team AquaVeda | "
    "Powered by GEE + ISRO"
)
