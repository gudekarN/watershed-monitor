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
try:
    from backend.gee_engine import (
        _ee_ready, get_sentinel2_image, get_all_tile_layers, get_thumbnail_url,
        create_s2_composite, InsufficientImageryError,
        _make_geometry,
    )
except Exception as _gee_err:
    def _ee_ready(): return False
    def get_sentinel2_image(*a, **kw): return None, None
    def get_all_tile_layers(*a, **kw): return None
    def get_thumbnail_url(*a, **kw): return None
    def create_s2_composite(*a, **kw): return None, {}
    def _make_geometry(*a, **kw): return None
    class InsufficientImageryError(RuntimeError): pass

try:
    from backend.indices import (
        generate_ndvi_timeseries, generate_water_timeseries, generate_monthly_ndvi
    )
except Exception:
    def generate_ndvi_timeseries(*a, **kw): return []
    def generate_water_timeseries(*a, **kw): return []
    def generate_monthly_ndvi(*a, **kw): return []

try:
    from backend.watershed import (
        delineate_watershed, get_drainage_network, calculate_erosion_risk
    )
except Exception:
    def delineate_watershed(*a, **kw): return None
    def get_drainage_network(*a, **kw): return None
    def calculate_erosion_risk(*a, **kw): return {}

try:
    from backend.change_detection import generate_change_summary
except Exception:
    def generate_change_summary(*a, **kw): return {}

try:
    from backend.health_score import calculate_watershed_health, get_demo_health_score
except Exception:
    def calculate_watershed_health(*a, **kw): return {}
    def get_demo_health_score(*a, **kw): return {}

# Frontend / Visuals
try:
    from frontend.map_builder import build_complete_map
except Exception:
    def build_complete_map(*a, **kw): return None

try:
    from frontend.charts import (
        ndvi_trend_chart, water_area_chart, health_score_gauge,
        change_comparison_chart, erosion_pie_chart, rainfall_ndvi_chart,
        landuse_sankey
    )
except Exception:
    def ndvi_trend_chart(*a, **kw): return None
    def water_area_chart(*a, **kw): return None
    def health_score_gauge(*a, **kw): return None
    def change_comparison_chart(*a, **kw): return None
    def erosion_pie_chart(*a, **kw): return None
    def rainfall_ndvi_chart(*a, **kw): return None
    def landuse_sankey(*a, **kw): return None

try:
    from geo_photos.photo_handler import (
        extract_gps_from_photo, create_photo_thumbnail, save_photo_entry,
        load_all_photos
    )
except Exception:
    def extract_gps_from_photo(*a, **kw): return {"has_gps": False}
    def create_photo_thumbnail(*a, **kw): return None
    def save_photo_entry(*a, **kw): return {}
    def load_all_photos(*a, **kw): return []

try:
    from backend.report_generator import generate_watershed_report
except Exception:
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
    try:
        with open(_CSS_PATH, encoding="utf-8") as _f:
            st.markdown(f"<style>{_f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass


# --- 4. INITIALIZE GEE ---
if 'gee_initialized' not in st.session_state:
    try:
        gee_status = initialize_gee()
    except Exception:
        gee_status = False
    st.session_state.gee_initialized = gee_status
    st.session_state.demo_mode = not gee_status

# Initialize session state vars
for _key, _val in [
    ('analysis_results', None),
    ('analysis_error',   None),   # set on live GEE failure; cleared on new analysis
    ('selected_watershed_id', None),
    ('previous_watershed', None),
]:
    if _key not in st.session_state:
        st.session_state[_key] = _val


# --- 5. MODE BANNER ---
# A compact per-session mode indicator is shown here; the per-analysis
# source badge is rendered inline under the dashboard title after analysis runs.
if st.session_state.demo_mode:
    st.info("📁 Running in Demo Mode. Results are pre-computed datasets, not live satellite data.", icon="📁")
else:
    # Only claim GEE is ready if the session was actually initialized successfully.
    if st.session_state.gee_initialized:
        st.info("🛰️ Google Earth Engine connected. Click **📊 Analyze Watershed** to run live analysis.", icon="🛰️")
    else:
        st.warning("⚠️ Google Earth Engine not connected. Analysis will fail unless you refresh the connection.", icon="⚠️")


# --- 6. LOAD DATA FUNCTIONS ---
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

@st.cache_data
def load_all_demo_data():
    """Load all demo data from JSON files with safe fallbacks."""
    def _load(filename, fallback=None):
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return fallback

    return {
        "watersheds":       _load("sample_watersheds.json") or SAMPLE_WATERSHEDS,
        "change_data":      _load("change_data.json", {}),
        "health_scores":    _load("health_scores.json", {}),
        "ndvi_timeseries":  _load("ndvi_timeseries.json", {}),
        "water_timeseries": _load("water_timeseries.json", {}),
        "landuse":          _load("landuse_transition.json", {}),
        "boundary":         _load("watershed_boundary_hiware_bazar.geojson"),
        "drainage":         _load("drainage_network.geojson"),
        "monthly_ndvi":     _load("monthly_ndvi.json", {}),
        "rainfall":         _load("rainfall_data.json", {}),
    }

try:
    demo_data = load_all_demo_data()
    watersheds = demo_data["watersheds"] or SAMPLE_WATERSHEDS
except Exception:
    demo_data = {k: {} for k in ["change_data","health_scores","ndvi_timeseries",
                                  "water_timeseries","landuse","monthly_ndvi","rainfall"]}
    demo_data.update({"boundary": None, "drainage": None})
    watersheds = SAMPLE_WATERSHEDS

# Guard: ensure we always have at least one watershed
if not watersheds:
    watersheds = SAMPLE_WATERSHEDS


def load_from_demo_files(watershed_id: str) -> dict:
    """Bundle demo data for a specific watershed into an analysis_results dict.

    Returns a result dict with data_source='demo'.  is_demo is always derived
    from data_source so there is a single source of truth.
    """
    try:
        change  = demo_data["change_data"].get(watershed_id, {})
        health  = demo_data["health_scores"].get(watershed_id, {})
        ndvi_ts = demo_data["ndvi_timeseries"].get(watershed_id, [])
        water_ts= demo_data["water_timeseries"].get(watershed_id, [])
        monthly = demo_data["monthly_ndvi"].get(watershed_id, [])
        rainfall= demo_data["rainfall"].get(watershed_id, [])
        landuse = demo_data["landuse"].get(watershed_id, {})
        ws_data = next((w for w in watersheds if w["id"] == watershed_id), watersheds[0])
        geom    = demo_data["boundary"] if watershed_id == "hiware_bazar" else None

        result = {
            # Authoritative source identifier — single source of truth
            "data_source":    "demo",
            # Derived convenience flag — always consistent with data_source
            "is_demo":        True,
            "change_data":    change,
            "health_score":   health,
            "ndvi_ts":        ndvi_ts,
            "water_ts":       water_ts,
            # Demo-only metrics (included in demo mode, hidden in live mode)
            "monthly_ndvi":   monthly,
            "rainfall":       rainfall,
            "landuse":        landuse,
            "watershed_geom": geom,
            "drainage_geom":  demo_data["drainage"] if watershed_id == "hiware_bazar" else None,
            "tile_layers":    None,
            "ws_data":        ws_data,
            "watershed_info": ws_data,
        }
        return result
    except Exception as e:
        st.warning(f"Could not load demo data: {e}")
        return {
            "data_source": "demo",
            "is_demo":     True,
            "ws_data":     {},
            "watershed_info": {},
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
        # Clear results AND error so no stale state from the previous mode persists
        st.session_state.analysis_results = None
        st.session_state.analysis_error   = None
        st.rerun()

    mode_str = "Demo (Local JSON)" if st.session_state.demo_mode else "Live (Google Earth Engine)"
    st.caption(f"Current: **{mode_str}**")

    if st.button("🔄 Refresh Connection"):
        st.cache_data.clear()
        try:
            st.session_state.gee_initialized = initialize_gee()
        except Exception:
            st.session_state.gee_initialized = False
        st.session_state.demo_mode = not st.session_state.gee_initialized
        # Clear results AND error on connection refresh
        st.session_state.analysis_results = None
        st.session_state.analysis_error   = None
        st.rerun()

    st.divider()

    # Watershed selection
    ws_names = [f"{w['name']}, {w['state']}" for w in watersheds]
    ws_ids   = [w['id'] for w in watersheds]

    # Fallback: if stored id gone, reset to first
    stored_id = st.session_state.selected_watershed_id
    if stored_id not in ws_ids:
        stored_id = ws_ids[0]
        st.session_state.selected_watershed_id = stored_id

    sel_idx = ws_ids.index(stored_id)
    chosen_name = st.selectbox("Select Watershed", options=ws_names, index=sel_idx)
    chosen_id   = ws_ids[ws_names.index(chosen_name)]

    # SESSION STATE CLEANUP when watershed changes
    if st.session_state.get('previous_watershed') != chosen_id:
        # Clear both results and any error from the previous watershed
        st.session_state.pop('analysis_results', None)
        st.session_state.analysis_error   = None
        st.session_state.previous_watershed = chosen_id
        st.session_state.selected_watershed_id = chosen_id

    # Safe fallback if chosen_id somehow doesn't match
    selected_ws = next((w for w in watersheds if w["id"] == chosen_id), watersheds[0])

    # Map layer toggles
    st.markdown("#### 🗺️ Map Layers")
    show_layers = {
        "NDVI (After)":       st.checkbox("Show NDVI Layer",         value=True),
        "Water Mask (After)": st.checkbox("Show Water Bodies",        value=True),
        "Watershed Boundary": st.checkbox("Show Watershed Boundary",  value=True),
        "Field Photos":       st.checkbox("Show Field Photos",        value=True),
        "Structures":         st.checkbox("Show Structures",          value=True),
        "Drainage Network":   st.checkbox("Show Drainage Network",    value=False),
        "NDVI Legend":        st.checkbox("Show NDVI Legend",         value=True),
    }

    st.divider()
    analyze_btn = st.button("📊 Analyze Watershed", use_container_width=True, type="primary")

    # Generate Report button
    if st.button("📄 Generate Report", use_container_width=True):
        if not st.session_state.get('analysis_results'):
            st.warning("Please run Analysis first.")
        elif generate_watershed_report:
            with st.spinner("Generating PDF report..."):
                try:
                    res = st.session_state.analysis_results
                    watershed_info  = res.get('watershed_info', res.get('ws_data', selected_ws))
                    change_data     = res.get('change_data', {})
                    health_score    = res.get('health_score', {})
                    timeseries_data = {
                        'ndvi_ts':  res.get('ndvi_ts', []),
                        'water_ts': res.get('water_ts', []),
                        'landuse':  res.get('landuse', {}),
                    }
                    photos_data = res.get('photos_data', res.get('photos', []))

                    pdf_bytes = generate_watershed_report(
                        watershed_info, change_data, health_score,
                        timeseries_data, photos_data
                    )
                    st.download_button(
                        "📥 Download PDF Report",
                        pdf_bytes,
                        f"watershed_report_{chosen_id}.pdf",
                        mime="application/pdf"
                    )
                except Exception as _rpt_err:
                    st.error(f"Report generation failed: {_rpt_err}")
        else:
            st.info("Report generation module unavailable.", icon="📋")

    st.divider()

    # 5. ABOUT SECTION
    with st.expander("ℹ️ About AquaVeda"):
        st.markdown("""
**AquaVeda** monitors watershed development projects using satellite data.

**Data Sources:**
- Sentinel-2 (ESA Copernicus) — 10m resolution
- SRTM DEM (NASA/USGS) — 30m elevation
- CHIRPS — Rainfall data
- HydroBASINS (WWF) — Watershed boundaries

**Indices Used:**
- NDVI: Vegetation health
- NDWI: Water body detection
- SAVI: Arid vegetation
- BSI: Bare soil/erosion

Built for Smart India Hackathon 2026
        """)


# --- 8. ANALYZE BUTTON HANDLER ---
if analyze_btn:
    # Always clear previous results before starting a new analysis.
    # This ensures no stale data from a previous watershed or mode is shown.
    st.session_state.analysis_results = None
    st.session_state.analysis_error   = None

    if st.session_state.demo_mode or not _ee_ready():
        # ── DEMO MODE ──────────────────────────────────────────────────────────
        with st.spinner("Loading demo analysis data..."):
            time.sleep(0.8)
            try:
                st.session_state.analysis_results = load_from_demo_files(chosen_id)
            except Exception as e:
                st.session_state.analysis_error = f"Failed to load demo data: {e}"
    else:
        # ── LIVE GEE MODE ──────────────────────────────────────────────────────
        with st.spinner("🛰️ Fetching satellite data from GEE..."):
            progress    = st.progress(0)
            status_text = st.empty()

            try:
                lat, lon = selected_ws["lat"], selected_ws["lon"]
                start_yr = selected_ws.get("start_year", 2019)
                end_yr   = 2024

                before_dates = (f"{start_yr}-01-01", f"{start_yr}-12-31")
                after_dates  = (f"{end_yr}-01-01",   f"{end_yr}-12-31")

                # Shared AOI geometry — both composites use the same AOI
                # so that preprocessing (cloud masking, clipping) is identical.
                geom = _make_geometry(lat, lon, 10 * 1000)

                # ── BEFORE composite (s2cloudless pipeline) ───────────────────
                status_text.text("Building cloud-masked BEFORE composite (2019)...")
                progress.progress(10)
                before_img, before_meta = create_s2_composite(
                    aoi=geom,
                    start_date=before_dates[0],
                    end_date=before_dates[1],
                    label=f"Before {start_yr}",
                )
                if before_img is None:
                    raise RuntimeError(
                        f"BEFORE composite ({before_dates[0]} to {before_dates[1]}) "
                        "returned no image from GEE. Live analysis aborted."
                    )

                # ── AFTER composite (same s2cloudless pipeline) ───────────────
                status_text.text("Building cloud-masked AFTER composite (2024)...")
                progress.progress(25)
                after_img, after_meta = create_s2_composite(
                    aoi=geom,
                    start_date=after_dates[0],
                    end_date=after_dates[1],
                    label=f"After {end_yr}",
                )
                if after_img is None:
                    raise RuntimeError(
                        f"AFTER composite ({after_dates[0]} to {after_dates[1]}) "
                        "returned no image from GEE. Live analysis aborted."
                    )

                status_text.text("Delineating watershed boundary...")
                progress.progress(40)
                watershed_geom = delineate_watershed(lat, lon)
                if watershed_geom is None:
                    watershed_geom = geom  # fallback to image geometry

                status_text.text("Running change detection analysis...")
                progress.progress(60)
                change_result = generate_change_summary(
                    lat, lon,
                    {"start": before_dates[0], "end": before_dates[1]},
                    {"start": after_dates[0],  "end": after_dates[1]},
                    watershed_id=chosen_id,
                    progress_callback=lambda *a: None,
                )

                # ── Core-section source validation ─────────────────────────────
                # Only the three required core sections must be GEE-derived.
                # landuse and months_with_water are intentionally deferred to
                # demo JSON in this version and must NOT trigger an abort.
                _REQUIRED_LIVE_SECTIONS = ("vegetation", "water", "erosion")
                _section_sources = change_result.get("_section_sources", {})

                _failed_core = [
                    sec for sec in _REQUIRED_LIVE_SECTIONS
                    if _section_sources.get(sec, "demo") != "gee"
                ]
                if _failed_core:
                    raise RuntimeError(
                        f"Required live sections failed GEE processing: "
                        f"{', '.join(_failed_core)}. "
                        "Live analysis aborted to prevent showing demo values "
                        "as live satellite results."
                    )

                status_text.text("Calculating timeseries & health score...")
                progress.progress(80)
                ndvi_ts  = generate_ndvi_timeseries(lat, lon, start_yr, end_yr)
                water_ts = generate_water_timeseries(lat, lon, start_yr, end_yr)

                # Require at least minimal GEE timeseries results
                if not ndvi_ts:
                    raise RuntimeError(
                        "NDVI timeseries returned no data from GEE. "
                        "Live analysis aborted."
                    )

                health = calculate_watershed_health(change_result, ndvi_ts)

                status_text.text("Generating map tile layers...")
                progress.progress(90)
                tiles = get_all_tile_layers(
                    lat, lon,
                    # BUG-1 fix: before_dates/after_dates must be dicts for .get() calls.
                    # before_dates is a tuple; convert to dict inline.
                    {"start": before_dates[0], "end": before_dates[1]},
                    {"start": after_dates[0],  "end": after_dates[1]},
                    # BUG-2 fix: do NOT pass watershed_geom as buffer_km.
                    # Use the default buffer_km=10 (same as the composites above).
                    # BUG-3 fix: supply already-built composites so the pipeline
                    # is NOT called a second time inside get_all_tile_layers().
                    before_img=before_img,
                    after_img=after_img,
                )

                progress.progress(100)
                status_text.text("✅ Live analysis complete!")
                time.sleep(0.5)
                status_text.empty()
                progress.empty()

                # ── Store LIVE result ──────────────────────────────────────────
                # Only GEE-derived fields are included.
                # monthly_ndvi, rainfall, and landuse are intentionally OMITTED
                # in live mode — they are demo-only fields that will be added
                # when live implementations are available in a later phase.
                st.session_state.analysis_results = {
                    # Authoritative source identifier
                    "data_source":    "live",
                    # Derived convenience flag — always consistent with data_source
                    "is_demo":        False,
                    # Live GEE metrics
                    "change_data":    change_result,
                    "health_score":   health,
                    "ndvi_ts":        ndvi_ts,
                    "water_ts":       water_ts if water_ts else [],
                    # monthly_ndvi, rainfall, landuse intentionally omitted in live mode
                    "watershed_geom": watershed_geom,
                    "drainage_geom":  get_drainage_network(lat, lon),
                    "tile_layers":    tiles,
                    "ws_data":        selected_ws,
                    "watershed_info": selected_ws,
                    "before_img":     before_img,
                    "after_img":      after_img,
                    "geom":           geom,
                    # Analysis period metadata
                    "analysis_period": {
                        "before": before_dates,
                        "after":  after_dates,
                    },
                    # Satellite acquisition and processing metadata
                    # These are real values from create_s2_composite(), not fabricated.
                    "satellite_metadata": {
                        "sensor":              "Sentinel-2",
                        "collection":          "COPERNICUS/S2_SR_HARMONIZED",
                        "cloud_mask":          "COPERNICUS/S2_CLOUD_PROBABILITY (s2cloudless)",
                        "processing":          "Cloud + cloud-shadow masked median composite",
                        "before_period":       f"{before_dates[0]} to {before_dates[1]}",
                        "after_period":        f"{after_dates[0]} to {after_dates[1]}",
                        "before_scenes_raw":   before_meta.get("images_before_filter", 0),
                        "before_scenes_clean": before_meta.get("images_after_filter",  0),
                        "after_scenes_raw":    after_meta.get("images_before_filter",  0),
                        "after_scenes_clean":  after_meta.get("images_after_filter",   0),
                        "cloud_prob_threshold": before_meta.get("cloud_prob_threshold", 65),
                        "scene_cloud_filter":   before_meta.get("scene_cloud_filter", 60),
                    },
                }
                st.session_state.analysis_error = None

            except Exception as e:
                # ── LIVE ANALYSIS FAILED ───────────────────────────────────────
                # Do NOT fall back to demo data silently.
                # Clear any previous results and surface the error explicitly.
                progress.empty()
                status_text.empty()
                st.session_state.analysis_results = None
                st.session_state.analysis_error   = str(e)


# --- 9. MAIN CONTENT LAYOUT ---

# ── ERROR STATE — live analysis failed ────────────────────────────────────────
if st.session_state.get('analysis_error') and not st.session_state.get('analysis_results'):
    st.title("🌊 AquaVeda Dashboard")
    st.markdown(f"### {selected_ws.get('name', chosen_id)}, {selected_ws.get('state', '')}")
    st.error(
        "**Live satellite analysis failed.** "
        "No demo data has been substituted to avoid presenting inaccurate results.",
        icon="🚨",
    )
    with st.expander("Error details", expanded=False):
        st.code(str(st.session_state.analysis_error))
    _err_c1, _err_c2, _err_c3 = st.columns([1, 1, 2])
    with _err_c1:
        if st.button("🔄 Retry Analysis", use_container_width=True):
            st.session_state.analysis_error = None
            st.rerun()
    with _err_c2:
        if st.button("📁 Switch to Demo Mode", use_container_width=True):
            st.session_state.demo_mode     = True
            st.session_state.analysis_error = None
            st.session_state.analysis_results = None
            st.rerun()
    st.stop()

# ── EMPTY STATE — watershed selected but no analysis yet ──────────────────────
if not st.session_state.get('analysis_results'):
    st.title("🌊 AquaVeda Dashboard")
    st.markdown(f"### {selected_ws.get('name', chosen_id)}, {selected_ws.get('state', '')}")
    _mode_label = (
        "📁 Demo Analysis · Pre-computed Dataset"
        if st.session_state.demo_mode
        else "🛰️ Ready for Live Satellite Analysis · Google Earth Engine"
    )
    st.caption(_mode_label)
    st.markdown("---")
    st.info("Ready for satellite analysis. Press the button below to begin.", icon="🛰️")
    # Provide an Analyze button directly in the main area as well as the sidebar
    if st.button(
        "📊 Analyze Watershed",
        use_container_width=False,
        type="primary",
        key="main_analyze_btn",
    ):
        # Delegate to the sidebar button's logic by triggering a rerun;
        # the sidebar button sets analyze_btn which the handler above picks up.
        # We replicate the handler inline here for the main-area button.
        st.session_state.analysis_results = None
        st.session_state.analysis_error   = None

        if st.session_state.demo_mode or not _ee_ready():
            with st.spinner("Loading demo analysis data..."):
                time.sleep(0.8)
                try:
                    st.session_state.analysis_results = load_from_demo_files(chosen_id)
                except Exception as _e:
                    st.session_state.analysis_error = f"Failed to load demo data: {_e}"
        else:
            st.info("Use the **📊 Analyze Watershed** button in the sidebar to start live analysis.", icon="🛰️")
        st.rerun()
    st.stop()

# Extract analysis results
res    = st.session_state.analysis_results
change = res.get("change_data", {})
health = res.get("health_score", {})
veg    = change.get("vegetation", {})
wat    = change.get("water", {})
ero    = change.get("erosion", {})

# Authoritative data source — single source of truth
_data_source = res.get("data_source", "demo")   # "live" | "demo" | "error"
# Derived convenience flag — always derived from data_source, never set independently
_is_demo = (_data_source != "live")

ws_info = res.get("ws_data") or res.get("watershed_info") or selected_ws

st.title(f"🌊 {ws_info.get('name', chosen_id)} Watershed")
st.markdown(f"*{ws_info.get('district', '')}, {ws_info.get('state', '')}*")

# ── Compact source badge ───────────────────────────────────────────────────────
if _data_source == "live":
    _period = res.get("analysis_period", {})
    _before_yr = (_period.get("before") or [""])[0][:4]
    _after_yr  = (_period.get("after")  or [""])[0][:4]
    _period_str = f" · {_before_yr}–{_after_yr}" if _before_yr and _after_yr else ""
    st.success(
        f"🛰️ Live Satellite Analysis · Sentinel-2 · Google Earth Engine{_period_str}",
        icon="🛰️",
    )
else:
    st.info(
        "📁 Demo Analysis · Pre-computed Dataset · data/*.json",
        icon="📁",
    )

# ── Metric cards ──────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
try:
    with m1:
        nv   = veg.get("change", 0) or 0
        npct = veg.get("percent_improved", 0) or 0
        st.metric("🌿 NDVI Change", f"{'+' if nv>0 else ''}{nv:.2f}", f"{'+' if npct>0 else ''}{npct:.1f}% Area")
except Exception:
    with m1: st.metric("🌿 NDVI Change", "-")

try:
    with m2:
        wa   = wat.get("area_after_ha", 0) or 0
        wpct = wat.get("change_percent", 0) or 0
        st.metric("💧 Water Area", f"{wa:.1f} ha", f"{'+' if wpct>0 else ''}{wpct:.1f}%")
except Exception:
    with m2: st.metric("💧 Water Area", "-")

try:
    with m3:
        er = ero.get("reduction_percent", 0) or 0
        st.metric("🏜️ Erosion Risk", f"-{er:.1f}%", f"-{er:.1f}%", delta_color="inverse")
except Exception:
    with m3: st.metric("🏜️ Erosion Risk", "-")

try:
    with m4:
        sc = health.get("total_score", 0) or 0
        gr = health.get("grade", "-")
        st.metric("🎯 Health Score", f"{sc}/100", gr)
except Exception:
    with m4: st.metric("🎯 Health Score", "-")

st.markdown("---")

# ── FULL-WIDTH MAP ─────────────────────────────────────────────────────────────
st.markdown("### 🗺️ Interactive Satellite Map")
with st.container(border=True):
    try:
        with st.spinner("Loading map..."):
            photos       = load_all_photos(watershed_id=chosen_id)
            b_geo        = res.get("watershed_geom") or demo_data.get("boundary")
            d_geo        = res.get("drainage_geom")  or demo_data.get("drainage")

            folium_map = build_complete_map(
                watershed_data    = ws_info,
                photos            = photos,
                tile_layers       = res.get("tile_layers"),
                show_layers       = show_layers,
                drainage_geojson  = d_geo,
                watershed_geojson = b_geo,
            )
        if folium_map:
            st_folium(folium_map, use_container_width=True, height=550, returned_objects=[])
        else:
            st.warning("Map could not be rendered. Check your data files.", icon="🗺️")
    except Exception as e:
        st.warning(f"Map could not be rendered: {e}", icon="🗺️")

st.markdown("---")

# ── FULL-WIDTH ANALYSIS TABS ───────────────────────────────────────────────────
st.markdown("### 📊 Watershed Analysis & Ground Truth")

tab_health, tab_trends, tab_compare, tab_landuse, tab_photos = st.tabs([
    "🎯 Health Score & Recommendations",
    "📈 Vegetation & Water Trends",
    "📸 Before vs After",
    "🌍 Land Use & Erosion",
    "📷 Field Verification",
])

# ── TAB 1: HEALTH ─────────────────────────────────────────────────────────────
with tab_health:
    h_left, h_right = st.columns([1, 1])

    with h_left:
        try:
            f_g = health_score_gauge(
                health.get("total_score", 0),
                health.get("grade", "-"),
                health.get("grade_emoji", "")
            )
            if f_g:
                st.plotly_chart(f_g, use_container_width=True)
        except Exception as e:
            st.warning(f"Health gauge could not be rendered: {e}")

        try:
            st.markdown("**Sub-Scores:**")
            veg_s = health.get("vegetation_score", 0) or 0
            wat_s = health.get("water_score", 0) or 0
            ero_s = health.get("erosion_score", 0) or 0
            st.progress(min(veg_s / 35, 1.0), text=f"🌿 Vegetation ({veg_s}/35)")
            st.progress(min(wat_s / 35, 1.0), text=f"💧 Water ({wat_s}/35)")
            st.progress(min(ero_s / 20, 1.0), text=f"🏜️ Erosion ({ero_s}/20)")
        except Exception as e:
            st.warning(f"Sub-scores could not be rendered: {e}")

    with h_right:
        try:
            recs = health.get("recommendations", [])
            if recs:
                st.subheader("📋 Recommendations")
                for r in recs:
                    st.info(r)
            else:
                st.info("No recommendations available yet. Run analysis first.", icon="💡")
        except Exception as e:
            st.warning(f"Recommendations could not be displayed: {e}")

# ── TAB 2: TRENDS ─────────────────────────────────────────────────────────────
with tab_trends:
    t_left, t_right = st.columns([1, 1])

    with t_left:
        ts_ndvi = res.get("ndvi_ts", [])
        if ts_ndvi:
            try:
                f1 = ndvi_trend_chart(ts_ndvi, ws_info.get("start_year"))
                if f1:
                    st.plotly_chart(f1, use_container_width=True)
            except Exception as e:
                st.warning(f"NDVI trend chart could not be rendered: {e}")
        else:
            st.info("Click Analyze to generate NDVI trend data.", icon="🌿")

        if change:
            try:
                f3 = change_comparison_chart(change)
                if f3:
                    st.plotly_chart(f3, use_container_width=True)
            except Exception as e:
                st.warning(f"Change comparison chart could not be rendered: {e}")

    with t_right:
        ts_wat = res.get("water_ts", [])
        if ts_wat:
            try:
                f2 = water_area_chart(ts_wat)
                if f2:
                    st.plotly_chart(f2, use_container_width=True)
            except Exception as e:
                st.warning(f"Water area chart could not be rendered: {e}")
        else:
            st.info("Click Analyze to generate water area trend data.", icon="💧")

    # ── Demo-only supplemental charts (monthly NDVI + rainfall) ───────────────
    # These fields only exist in demo results; they are intentionally omitted
    # from live results until live implementations are available.
    _monthly = res.get("monthly_ndvi")
    _rainfall = res.get("rainfall")
    if _is_demo and (_monthly or _rainfall):
        st.markdown("---")
        st.caption("📁 The following supplemental charts use pre-computed demo data.")
        try:
            if _monthly and rainfall_ndvi_chart:
                f_rn = rainfall_ndvi_chart(_monthly, _rainfall or [])
                if f_rn:
                    st.plotly_chart(f_rn, use_container_width=True)
        except Exception as e:
            st.warning(f"Monthly NDVI/rainfall chart could not be rendered: {e}")
    elif not _is_demo and not _monthly:
        # Live mode — these metrics not yet implemented for live GEE
        pass  # Charts simply absent; no misleading placeholder shown

# ── TAB 3: BEFORE/AFTER ───────────────────────────────────────────────────────
with tab_compare:
    try:
        # Authoritative data source
        _live_compare = (_data_source == "live")
        b1, b2 = st.columns(2)

        # Extract the already-generated GEE tile layers.
        # These were created from the same BEFORE/AFTER composites used
        # throughout the live analysis, so no additional GEE processing occurs.
        _tile_layers = res.get("tile_layers") or {}

        with b1:
            st.markdown("### 🔴 BEFORE · 2019")
            if _live_compare:
                _before_tile = _tile_layers.get("before_satellite")

                if _before_tile:
                    try:
                        # Render the existing GEE tile layer on a dedicated
                        # Folium map so the BEFORE view uses actual Sentinel-2
                        # imagery without creating another thumbnail request.
                        _before_map = folium.Map(
                            location=[
                                ws_info.get("lat", 20.0),
                                ws_info.get("lon", 76.0)
                            ],
                            zoom_start=12,
                            control_scale=True,
                            tiles=None,
                        )

                        folium.TileLayer(
                            tiles="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
                            attr="© OpenStreetMap © CARTO",
                            name="Reference",
                            overlay=False,
                            control=False,
                        ).add_to(_before_map)

                        if res.get("watershed_geom"):
                            try:
                                from frontend.map_builder import add_watershed_boundary
                                add_watershed_boundary(
                                    _before_map,
                                    res.get("watershed_geom"),
                                    name="Watershed Boundary"
                                )
                            except Exception:
                                pass

                        from backend.gee_engine import add_ee_layer_to_folium
                        add_ee_layer_to_folium(
                            _before_map,
                            _before_tile,
                            opacity=1.0
                        )

                        st_folium(
                            _before_map,
                            use_container_width=True,
                            height=400,
                            returned_objects=[]
                        )
                    except Exception as _before_map_err:
                        st.warning(
                            f"BEFORE satellite imagery unavailable: {_before_map_err}"
                        )
                else:
                    st.warning("BEFORE satellite imagery unavailable.")
            else:
                st.info(
                    "📁 Demo Mode\n\n"
                    "Pre-computed demo satellite visualization is not available "
                    "for this comparison.",
                    icon="📁"
                )

            st.info(
                f"**NDVI**: {veg.get('ndvi_before', 0):.2f}\n\n"
                f"**Water**: {wat.get('area_before_ha', 0):.1f} ha",
                icon="🔴"
            )

        with b2:
            st.markdown("### 🟢 AFTER · 2024")
            if _live_compare:
                _after_tile = _tile_layers.get("after_satellite")

                if _after_tile:
                    try:
                        _after_map = folium.Map(
                            location=[
                                ws_info.get("lat", 20.0),
                                ws_info.get("lon", 76.0)
                            ],
                            zoom_start=12,
                            control_scale=True,
                            tiles=None,
                        )

                        folium.TileLayer(
                            tiles="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
                            attr="© OpenStreetMap © CARTO",
                            name="Reference",
                            overlay=False,
                            control=False,
                        ).add_to(_after_map)

                        if res.get("watershed_geom"):
                            try:
                                from frontend.map_builder import add_watershed_boundary
                                add_watershed_boundary(
                                    _after_map,
                                    res.get("watershed_geom"),
                                    name="Watershed Boundary"
                                )
                            except Exception:
                                pass

                        from backend.gee_engine import add_ee_layer_to_folium
                        add_ee_layer_to_folium(
                            _after_map,
                            _after_tile,
                            opacity=1.0
                        )

                        st_folium(
                            _after_map,
                            use_container_width=True,
                            height=400,
                            returned_objects=[]
                        )
                    except Exception as _after_map_err:
                        st.warning(
                            f"AFTER satellite imagery unavailable: {_after_map_err}"
                        )
                else:
                    st.warning("AFTER satellite imagery unavailable.")
            else:
                st.info(
                    "📁 Demo Mode\n\n"
                    "Pre-computed demo satellite visualization is not available "
                    "for this comparison.",
                    icon="📁"
                )

            st.success(
                f"**NDVI**: {veg.get('ndvi_after', 0):.2f}\n\n"
                f"**Water**: {wat.get('area_after_ha', 0):.1f} ha",
                icon="🟢"
            )

        _src_label = (
            "🛰️ Sentinel-2 SR Harmonized · Cloud-masked composite · Google Earth Engine"
            if _live_compare
            else "📁 Demo Analysis · Pre-computed Dataset"
        )
        st.caption(f"**Data source:** {_src_label}")

    except Exception as e:
        st.warning(f"Before/After comparison could not be rendered: {e}")

# ── TAB 4: LAND USE & EROSION ─────────────────────────────────────────────────
with tab_landuse:
    lu_left, lu_right = st.columns([1, 1])

    with lu_left:
        lu_data = res.get("landuse", {})
        if _is_demo and lu_data.get("flows"):
            # Land use transition is a demo-only metric in this phase.
            # It is intentionally excluded from live results.
            try:
                f_s = landuse_sankey(lu_data)
                if f_s:
                    st.plotly_chart(f_s, use_container_width=True)
            except Exception as e:
                st.warning(f"Land use chart could not be rendered: {e}")
        elif not _is_demo:
            st.info(
                "Land use transition analysis is not yet available in Live mode. "
                "This metric will be added in a future phase.",
                icon="📈",
            )
        else:
            st.info("Land use transition data not available for this watershed.", icon="📈")

    with lu_right:
        ero_cls = ero.get("classes_after", {})
        if ero_cls:
            try:
                f_e = erosion_pie_chart(ero_cls)
                if f_e:
                    st.plotly_chart(f_e, use_container_width=True)
            except Exception as e:
                st.warning(f"Erosion chart could not be rendered: {e}")
        else:
            st.info("Erosion class data not available for this watershed.", icon="🏜️")

# ── TAB 5: FIELD VERIFICATION ─────────────────────────────────────────────────
with tab_photos:
    try:
        st.markdown("#### 📤 Upload Field Photo")
        uploaded_files = st.file_uploader(
            "📸 Upload Geo-Tagged Photos from Field",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            help="Photos taken with GPS-enabled phones will auto-detect location"
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    col1, col2 = st.columns([1, 2])

                    with col1:
                        try:
                            st.image(uploaded_file, width=200)
                        except Exception:
                            st.warning("Could not preview image.")

                    with col2:
                        try:
                            gps_data = extract_gps_from_photo(uploaded_file)
                        except Exception:
                            gps_data = {"has_gps": False}

                        if gps_data.get('has_gps'):
                            st.success(f"📍 GPS Found: {gps_data['lat']:.4f}, {gps_data['lon']:.4f}")
                            lat_input = gps_data['lat']
                            lon_input = gps_data['lon']
                        else:
                            st.warning("No GPS data found. Please enter coordinates manually.")
                            lat_input = st.number_input(
                                "Latitude", value=float(ws_info.get('lat', 0.0)),
                                format="%.4f", key=f"lat_{uploaded_file.name}"
                            )
                            lon_input = st.number_input(
                                "Longitude", value=float(ws_info.get('lon', 0.0)),
                                format="%.4f", key=f"lon_{uploaded_file.name}"
                            )

                        structure_type = st.selectbox(
                            "Structure Type",
                            ["Check Dam", "Farm Pond", "Contour Trench",
                             "Percolation Tank", "Gabion Structure", "Nala Bund", "Other"],
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

                        if st.button("💾 Save Photo Entry", key=f"save_{uploaded_file.name}"):
                            try:
                                from datetime import datetime
                                save_photo_entry({
                                    'lat': lat_input, 'lon': lon_input,
                                    'type': structure_type, 'status': status,
                                    'water_level': f"{water_level}%",
                                    'description': notes,
                                    'date': datetime.now().strftime('%Y-%m-%d'),
                                    'watershed_id': chosen_id,
                                }, chosen_id)
                                st.success("Photo saved! Marker added to map.")
                                st.rerun()
                            except Exception as _save_err:
                                st.error(f"Could not save photo: {_save_err}")
                except Exception as _photo_err:
                    st.warning(f"Error processing {uploaded_file.name}: {_photo_err}")

    except Exception as e:
        st.warning(f"Photo uploader error: {e}")

    st.markdown("---")
    st.subheader("📋 Field Verification Log")
    try:
        all_photos = load_all_photos(chosen_id)
        if all_photos:
            p_cols = st.columns(3)
            for i, photo in enumerate(all_photos):
                with p_cols[i % 3]:
                    status_color = {
                        'Functional': '#22c55e', 'Needs Repair': '#f59e0b',
                        'Damaged': '#ef4444', 'Dry': '#64748b'
                    }.get(photo.get('status', ''), '#3b82f6')

                    st.markdown(f"""
                    <div style="border:1px solid #334155; border-radius:10px; padding:12px;
                                margin:6px 0; border-left:4px solid {status_color};
                                background:rgba(30,41,59,0.6);">
                        <strong style="color:#f8fafc">{photo.get('type', 'Photo')}</strong>
                        <br><span style="color:#94a3b8; font-size:12px;">
                        📍 {photo.get('lat', 0):.4f}, {photo.get('lon', 0):.4f}</span>
                        <br><span style="color:#94a3b8; font-size:12px;">📅 {photo.get('date', '')}</span>
                        <br><span style="background:{status_color}; color:white;
                                  padding:2px 8px; border-radius:8px; font-size:11px; font-weight:600;">
                        {photo.get('status', '')}</span>
                        <br><span style="font-size:12px; color:#cbd5e1">{photo.get('description', '')[:60]}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No field photos recorded for this watershed yet.")
    except Exception as e:
        st.warning(f"Could not load field photos: {e}")

st.divider()
st.caption("Built for Smart India Hackathon 2026 | Team AquaVeda")
