"""
AquaVeda — Satellite-Based Watershed Impact Monitor
Smart India Hackathon 2026 | Team AquaVeda

Modes:
  1. Demo Mode: Uses local JSON files (instant, reliable)
  2. Live Mode: Uses Google Earth Engine for live analysis
"""

import os
import json
import time

import streamlit as st
import folium
from streamlit_folium import st_folium

# --- 1. IMPORTS & INITIALIZATION ---
from config import initialize_gee, GEE_AVAILABLE, DEMO_MODE, SAMPLE_WATERSHEDS

# Backend
from backend.gee_engine import (
    _ee_ready, get_sentinel2_image, get_all_tile_layers, get_thumbnail_url
)
from backend.indices import (
    generate_ndvi_timeseries, generate_water_timeseries, generate_monthly_ndvi
)
from backend.watershed import (
    delineate_watershed, get_drainage_network, calculate_erosion_risk
)
from backend.change_detection import generate_change_summary
from backend.health_score import calculate_watershed_health, get_demo_health_score

# Frontend / Visuals
from frontend.map_builder import build_complete_map
from frontend.charts import (
    ndvi_trend_chart, water_area_chart, health_score_gauge,
    change_comparison_chart, erosion_pie_chart, rainfall_ndvi_chart,
    landuse_sankey
)
from geo_photos.photo_handler import (
    extract_gps_from_photo, create_photo_thumbnail, save_photo_entry,
    load_all_photos
)

try:
    from backend.report_generator import generate_watershed_report
except ImportError:
    generate_watershed_report = None


# --- 2. PAGE CONFIG ---
st.set_page_config(
    page_title="AquaVeda — Watershed Monitor",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- 3. LOAD CSS ---
_CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "style.css")
if os.path.exists(_CSS_PATH):
    with open(_CSS_PATH, encoding="utf-8") as _f:
        st.markdown(f"<style>{_f.read()}</style>", unsafe_allow_html=True)


# --- 4. INITIALIZE GEE ---
if 'gee_initialized' not in st.session_state:
    gee_status = initialize_gee()
    st.session_state.gee_initialized = gee_status
    st.session_state.demo_mode = not gee_status

# Initialize some other session state vars
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'selected_watershed_id' not in st.session_state:
    st.session_state.selected_watershed_id = None


# --- 5. SHOW MODE BANNER ---
if st.session_state.demo_mode:
    st.info("📡 Running in Demo Mode with sample data. GEE not connected or disabled.", icon="ℹ️")
else:
    st.success("🛰️ Connected to Google Earth Engine — Live satellite data available", icon="✅")


# --- 6. LOAD DATA FUNCTIONS ---
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

@st.cache_data
def load_all_demo_data():
    """Load all demo data from JSON files."""
    def _load(filename):
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    return {
        "watersheds":       _load("sample_watersheds.json") or SAMPLE_WATERSHEDS,
        "change_data":      _load("change_data.json") or {},
        "health_scores":    _load("health_scores.json") or {},
        "ndvi_timeseries":  _load("ndvi_timeseries.json") or {},
        "water_timeseries": _load("water_timeseries.json") or {},
        "landuse":          _load("landuse_transition.json") or {},
        "boundary":         _load("watershed_boundary_hiware_bazar.geojson"),
        "drainage":         _load("drainage_network.geojson"),
        "monthly_ndvi":     _load("monthly_ndvi.json") or {},
        "rainfall":         _load("rainfall_data.json") or {},
    }

demo_data = load_all_demo_data()
watersheds = demo_data["watersheds"]


def load_from_demo_files(watershed_id: str):
    """Bundle demo data for a specific watershed into an analysis_results dict."""
    change = demo_data["change_data"].get(watershed_id, {})
    health = demo_data["health_scores"].get(watershed_id, {})
    ndvi_ts = demo_data["ndvi_timeseries"].get(watershed_id, [])
    water_ts = demo_data["water_timeseries"].get(watershed_id, [])
    monthly = demo_data["monthly_ndvi"].get(watershed_id, [])
    rainfall = demo_data["rainfall"].get(watershed_id, [])
    landuse = demo_data["landuse"].get(watershed_id, {})
    
    ws_data = next((w for w in watersheds if w["id"] == watershed_id), watersheds[0])
    
    # Try to load geometry if we are the default hiware bazar
    geom = None
    if watershed_id == "hiware_bazar":
        geom = demo_data["boundary"]

    return {
        "change_data": change,
        "health_score": health,
        "ndvi_ts": ndvi_ts,
        "water_ts": water_ts,
        "monthly_ndvi": monthly,
        "rainfall": rainfall,
        "landuse": landuse,
        "watershed_geom": geom,
        "drainage_geom": demo_data["drainage"] if watershed_id == "hiware_bazar" else None,
        "tile_layers": None,
        "is_demo": True,
        "ws_data": ws_data
    }


# --- 7. SIDEBAR ---
with st.sidebar:
    st.markdown("# 🌊 AquaVeda")
    st.markdown("### Satellite Watershed Monitor")
    st.divider()

    # Data Source controls
    st.markdown("#### 🛰️ Data Source")
    force_demo = st.checkbox("Force Demo Mode", value=st.session_state.demo_mode)
    if force_demo != st.session_state.demo_mode:
        st.session_state.demo_mode = force_demo
        st.session_state.analysis_results = None
        st.rerun()
        
    mode_str = "Demo (Local JSON)" if st.session_state.demo_mode else "Live (Google Earth Engine)"
    st.caption(f"Current: **{mode_str}**")
    
    if st.button("🔄 Refresh Connection"):
        st.cache_data.clear()
        st.session_state.gee_initialized = initialize_gee()
        st.session_state.demo_mode = not st.session_state.gee_initialized
        st.rerun()

    st.divider()

    # Watershed selection
    ws_names = [f"{w['name']}, {w['state']}" for w in watersheds]
    ws_ids = [w['id'] for w in watersheds]
    
    sel_idx = ws_ids.index(st.session_state.selected_watershed_id) if st.session_state.selected_watershed_id in ws_ids else 0
    
    chosen_name = st.selectbox("Select Watershed", options=ws_names, index=sel_idx)
    chosen_id = ws_ids[ws_names.index(chosen_name)]
    
    # Reset analysis if watershed changed
    if chosen_id != st.session_state.selected_watershed_id:
        st.session_state.selected_watershed_id = chosen_id
        st.session_state.analysis_results = None

    selected_ws = next((w for w in watersheds if w["id"] == chosen_id), watersheds[0])

    # Map layer toggles
    st.markdown("#### 🗺️ Map Layers")
    show_layers = {
        "NDVI (After)": st.checkbox("Show NDVI Layer", value=True),
        "Water Mask (After)": st.checkbox("Show Water Bodies", value=True),
        "Watershed Boundary": st.checkbox("Show Watershed Boundary", value=True),
        "Field Photos": st.checkbox("Show Field Photos", value=True),
        "Structures": st.checkbox("Show Structures", value=True),
        "Drainage Network": st.checkbox("Show Drainage Network", value=False),
        "NDVI Legend": st.checkbox("Show NDVI Legend", value=True),
    }

    st.divider()
    analyze_btn = st.button("📊 Analyze Watershed", use_container_width=True, type="primary")

    if st.button("📄 Generate Report", use_container_width=True):
        if not st.session_state.analysis_results:
            st.warning("Please run Analysis first.")
        elif generate_watershed_report:
            with st.spinner("Generating PDF..."):
                pdf_bytes = generate_watershed_report(st.session_state.analysis_results)
                st.download_button(
                    "📥 Download PDF Report", 
                    pdf_bytes, 
                    f"watershed_report_{chosen_id}.pdf",
                    mime="application/pdf"
                )
        else:
            st.info("Report generation coming soon!", icon="📋")


# --- 8. ANALYZE BUTTON HANDLER ---
if analyze_btn:
    st.session_state.analysis_results = None  # clear old
    
    if st.session_state.demo_mode or not _ee_ready():
        with st.spinner("Loading demo analysis data..."):
            time.sleep(1.0)
            st.session_state.analysis_results = load_from_demo_files(chosen_id)
    else:
        # LIVE GEE MODE
        with st.spinner("🛰️ Fetching satellite data from GEE..."):
            progress = st.progress(0)
            status_text = st.empty()
            
            try:
                lat, lon = selected_ws["lat"], selected_ws["lon"]
                start_yr = selected_ws.get("start_year", 2019)
                end_yr = 2024
                
                # Setup dates
                before_dates = (f"{start_yr}-01-01", f"{start_yr}-12-31")
                after_dates = (f"{end_yr}-01-01", f"{end_yr}-12-31")
                
                status_text.text("Fetching satellite baseline (Before)...")
                progress.progress(10)
                before_img, geom = get_sentinel2_image(lat, lon, before_dates[0], before_dates[1])
                
                status_text.text("Fetching satellite baseline (After)...")
                progress.progress(25)
                after_img, _ = get_sentinel2_image(lat, lon, after_dates[0], after_dates[1])
                
                status_text.text("Delineating watershed boundary...")
                progress.progress(40)
                watershed_geom = delineate_watershed(lat, lon)
                if watershed_geom is None:
                    watershed_geom = geom # fallback
                
                status_text.text("Running change detection analysis...")
                progress.progress(60)
                def _prog(s, t, msg):
                    pass # could hook to progress bar, but let's keep it simple
                change_result = generate_change_summary(
                    lat, lon, before_dates, after_dates, progress_callback=_prog
                )
                
                status_text.text("Calculating timeseries & health score...")
                progress.progress(80)
                ndvi_ts = generate_ndvi_timeseries(lat, lon, start_yr, end_yr)
                water_ts = generate_water_timeseries(lat, lon, start_yr, end_yr)
                health = calculate_watershed_health(change_result, ndvi_ts)
                
                status_text.text("Generating map tile layers...")
                progress.progress(90)
                tiles = get_all_tile_layers(lat, lon, before_dates, after_dates, watershed_geom)
                
                progress.progress(100)
                status_text.text("✅ Analysis complete!")
                time.sleep(0.5)
                status_text.empty()
                progress.empty()
                
                st.session_state.analysis_results = {
                    "change_data": change_result,
                    "health_score": health,
                    "ndvi_ts": ndvi_ts,
                    "water_ts": water_ts,
                    "monthly_ndvi": demo_data["monthly_ndvi"].get(chosen_id, []), # Demo fallback for speed
                    "rainfall": demo_data["rainfall"].get(chosen_id, []),
                    "landuse": demo_data["landuse"].get(chosen_id, {}),
                    "watershed_geom": watershed_geom,
                    "drainage_geom": get_drainage_network(lat, lon),
                    "tile_layers": tiles,
                    "is_demo": False,
                    "ws_data": selected_ws,
                    "before_img": before_img,
                    "after_img": after_img,
                    "geom": geom
                }
            except Exception as e:
                st.error(f"Live analysis failed: {e}")
                st.warning("Falling back to demo data.")
                st.session_state.analysis_results = load_from_demo_files(chosen_id)


# --- 9. MAIN CONTENT LAYOUT ---
if not st.session_state.analysis_results:
    st.title("🌊 AquaVeda Dashboard")
    st.info("👈 Please select a watershed and click **Analyze Watershed** to begin.")
    st.stop()

# Extract analysis results
res = st.session_state.analysis_results
change = res.get("change_data", {})
health = res.get("health_score", {})
veg = change.get("vegetation", {})
wat = change.get("water", {})
ero = change.get("erosion", {})

st.title(f"🌊 {selected_ws['name']} Watershed")
st.markdown(f"*{selected_ws['district']}, {selected_ws['state']}*")

# Metric cards
m1, m2, m3, m4 = st.columns(4)
with m1:
    nv = veg.get("change", 0)
    npct = veg.get("percent_improved", 0)
    st.metric("🌿 NDVI Change", f"{'+' if nv>0 else ''}{nv:.2f}", f"{'+' if npct>0 else ''}{npct:.1f}% Area")
with m2:
    wa = wat.get("area_after_ha", 0)
    wpct = wat.get("change_percent", 0)
    st.metric("💧 Water Area", f"{wa:.1f} ha", f"{'+' if wpct>0 else ''}{wpct:.1f}%")
with m3:
    er = ero.get("reduction_percent", 0)
    st.metric("🏜️ Erosion Risk", f"-{er:.1f}%", f"-{er:.1f}%", delta_color="inverse")
with m4:
    sc = health.get("total_score", 0)
    gr = health.get("grade", "—")
    st.metric("🎯 Health Score", f"{sc}/100", gr)

st.markdown("---")

col_left, col_right = st.columns([3, 2])

# ── LEFT COLUMN ──
with col_left:
    tab_map, tab_ba, tab_fp = st.tabs(["🗺️ Map", "📸 Before/After", "📷 Field Photos"])
    
    with tab_map:
        photos = load_all_photos(watershed_id=chosen_id)
        
        # Determine geojson to use
        b_geo = res.get("watershed_geom") or demo_data["boundary"]
        d_geo = res.get("drainage_geom") or demo_data["drainage"]
        
        m = build_complete_map(
            watershed_data=selected_ws,
            photos=photos,
            tile_layers=res.get("tile_layers"),
            show_layers=show_layers,
            drainage_geojson=d_geo,
            watershed_geojson=b_geo
        )
        if m:
            st_folium(m, use_container_width=True, height=500, returned_objects=[])
        else:
            st.error("Could not build map.")

    with tab_ba:
        # If live, we can show actual thumbnails. If demo, show stats
        is_live = not res.get("is_demo")
        
        b1, b2 = st.columns(2)
        with b1:
            st.markdown("### 📷 Before")
            if is_live and res.get("before_img") and res.get("geom"):
                url = get_thumbnail_url(res["before_img"], res["geom"], {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"]})
                if url: st.image(url, use_container_width=True)
            st.info(f"**NDVI**: {veg.get('ndvi_before', 0):.2f}\n\n**Water**: {wat.get('area_before_ha',0):.1f} ha", icon="🔴")
            
        with b2:
            st.markdown("### 🌿 After")
            if is_live and res.get("after_img") and res.get("geom"):
                url = get_thumbnail_url(res["after_img"], res["geom"], {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"]})
                if url: st.image(url, use_container_width=True)
            st.success(f"**NDVI**: {veg.get('ndvi_after', 0):.2f}\n\n**Water**: {wat.get('area_after_ha',0):.1f} ha", icon="✅")
            
        st.markdown(f"**Source**: {'Live GEE Data' if is_live else 'Pre-computed Demo Data'}")

    with tab_fp:
        st.markdown("#### 📤 Upload Field Photo")
        uploaded_files = st.file_uploader(
            "📸 Upload Geo-Tagged Photos from Field",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            help="Photos taken with GPS-enabled phones will auto-detect location"
        )
        
        if uploaded_files:
            for uploaded_file in uploaded_files:
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.image(uploaded_file, width=200)
                
                with col2:
                    gps_data = extract_gps_from_photo(uploaded_file)
                    
                    if gps_data.get('has_gps'):
                        st.success(f"📍 GPS Found: {gps_data['lat']:.4f}, {gps_data['lon']:.4f}")
                        lat_input = gps_data['lat']
                        lon_input = gps_data['lon']
                    else:
                        st.warning("⚠️ No GPS data found. Please enter coordinates manually.")
                        lat_input = st.number_input("Latitude", value=selected_ws.get('lat', 0.0), 
                                                    format="%.4f", key=f"lat_{uploaded_file.name}")
                        lon_input = st.number_input("Longitude", value=selected_ws.get('lon', 0.0), 
                                                    format="%.4f", key=f"lon_{uploaded_file.name}")
                    
                    structure_type = st.selectbox(
                        "Structure Type",
                        ["Check Dam", "Farm Pond", "Contour Trench", "Percolation Tank", 
                         "Gabion Structure", "Nala Bund", "Other"],
                        key=f"type_{uploaded_file.name}"
                    )
                    
                    status = st.selectbox(
                        "Status",
                        ["Functional", "Needs Repair", "Damaged", "Dry", "Under Construction"],
                        key=f"status_{uploaded_file.name}"
                    )
                    
                    water_level = st.slider("Water Level %", 0, 100, 50, 
                                            key=f"wl_{uploaded_file.name}")
                    
                    notes = st.text_area("Notes", key=f"notes_{uploaded_file.name}")
                    
                    if st.button("💾 Save", key=f"save_{uploaded_file.name}"):
                        from datetime import datetime
                        entry = save_photo_entry({
                            'lat': lat_input, 'lon': lon_input,
                            'type': structure_type, 'status': status,
                            'water_level': f"{water_level}%",
                            'description': notes,
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'watershed_id': chosen_id
                        }, chosen_id)
                        st.success(f"✅ Photo saved! Marker added to map.")
                        st.rerun()

        st.markdown("---")
        st.subheader("📋 Field Verification Log")
        all_photos = load_all_photos(chosen_id)
        
        if all_photos:
            cols = st.columns(3)
            for i, photo in enumerate(all_photos):
                with cols[i % 3]:
                    status_color = {
                        'Functional': '#28a745', 'Needs Repair': '#ffc107',
                        'Damaged': '#dc3545', 'Dry': '#6c757d'
                    }.get(photo.get('status', ''), '#17a2b8')
                    
                    st.markdown(f"""
                    <div style="border:1px solid #ddd; border-radius:8px; padding:10px; margin:5px 0;
                                border-left:4px solid {status_color}; background:rgba(0,0,0,0.03);">
                        <strong>{photo.get('type', 'Photo')}</strong>
                        <br><span style="color:gray; font-size:12px;">
                        📍 {photo.get('lat', 0):.4f}, {photo.get('lon', 0):.4f}</span>
                        <br><span style="color:gray; font-size:12px;">📅 {photo.get('date', '')}</span>
                        <br><span style="background:{status_color}; color:white; 
                                  padding:1px 6px; border-radius:8px; font-size:11px;">
                        {photo.get('status', '')}</span>
                        <br><span style="font-size:12px; color:#555">{photo.get('description', '')[:60]}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No field photos recorded for this watershed yet.")


# ── RIGHT COLUMN ──
with col_right:
    tab_trends, tab_health, tab_lu = st.tabs(["📊 Trends", "🎯 Health", "📈 Land Use"])
    
    with tab_trends:
        ts_ndvi = res.get("ndvi_ts", [])
        if ts_ndvi:
            f1 = ndvi_trend_chart(ts_ndvi, selected_ws.get("start_year"))
            st.plotly_chart(f1, use_container_width=True)
            
        ts_wat = res.get("water_ts", [])
        if ts_wat:
            f2 = water_area_chart(ts_wat)
            st.plotly_chart(f2, use_container_width=True)
            
        f3 = change_comparison_chart(change)
        st.plotly_chart(f3, use_container_width=True)
            
    with tab_health:
        f_g = health_score_gauge(
            health.get("total_score", 0),
            health.get("grade", "—"),
            health.get("grade_emoji", "")
        )
        st.plotly_chart(f_g, use_container_width=True)
        
        st.markdown("**Sub-Scores:**")
        st.progress(min(health.get("vegetation_score", 0)/35, 1.0), text=f"Vegetation ({health.get('vegetation_score',0)}/35)")
        st.progress(min(health.get("water_score", 0)/35, 1.0), text=f"Water ({health.get('water_score',0)}/35)")
        st.progress(min(health.get("erosion_score", 0)/20, 1.0), text=f"Erosion ({health.get('erosion_score',0)}/20)")
        
        recs = health.get("recommendations", [])
        if recs:
            st.subheader("📋 Recommendations")
            for r in recs:
                st.info(r)
                
    with tab_lu:
        lu_data = res.get("landuse", {})
        if lu_data.get("flows"):
            f_s = landuse_sankey(lu_data)
            st.plotly_chart(f_s, use_container_width=True)
            
        ero_cls = ero.get("classes_after", {})
        if ero_cls:
            f_e = erosion_pie_chart(ero_cls)
            st.plotly_chart(f_e, use_container_width=True)
            
st.divider()
st.caption("Built for Smart India Hackathon 2026 | Team AquaVeda")
