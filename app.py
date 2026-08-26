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
import logging

logger = logging.getLogger(__name__)

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
        extract_gps_from_photo, create_photo_thumbnail,
        create_photo_image_b64,
        find_nearest_reference_observation,
        save_photo_entry, load_all_photos
    )
except Exception:
    def extract_gps_from_photo(*a, **kw): return {"has_gps": False}
    def create_photo_thumbnail(*a, **kw): return None
    def create_photo_image_b64(*a, **kw): return None
    def find_nearest_reference_observation(*a, **kw):
        return {"matched": False, "error": "photo matcher unavailable"}
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


# --- 4. INITIALIZE APPLICATION ---
# Start in Demo Mode so the UI loads immediately.
# Google Earth Engine is initialized only when Live Mode is explicitly requested.

if 'gee_initialized' not in st.session_state:
    st.session_state.gee_initialized = False

if 'demo_mode' not in st.session_state:
    st.session_state.demo_mode = True

# Initialize session state vars
for _key, _val in [
    ('analysis_results', None),
    ('analysis_error',   None),   # set on live GEE failure; cleared on new analysis
    ('selected_watershed_id', None),
    ('previous_watershed', None),
    ('_trigger_analysis', False),
]:
    if _key not in st.session_state:
        st.session_state[_key] = _val


# --- 5. MODE BANNER ---
# Use the same readiness check used by the actual live analysis pipeline.
if st.session_state.demo_mode:
    st.info(
        "Running in Demo Mode. Results are pre-computed datasets, not live satellite data.",
        icon="📁",
    )
else:
    try:
        _banner_gee_ready = bool(_ee_ready())
    except Exception:
        _banner_gee_ready = False

    if _banner_gee_ready:
        st.info(
            "Google Earth Engine ready. Click **📊 Analyze Watershed** to run live analysis.",
            icon="🛰️",
        )
    else:
        st.warning(
            "Google Earth Engine is not ready. Live analysis cannot run. "
            "Switch to Demo Mode or refresh the connection.",
            icon="⚠️",
        )


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
    force_demo = st.checkbox(
        "Open Mode",
        value=st.session_state.demo_mode
    )

    if force_demo != st.session_state.demo_mode:

        if force_demo:
            # Switching to Demo Mode
            st.session_state.demo_mode = True
            st.session_state.analysis_results = None
            st.session_state.analysis_error = None
            st.rerun()

        else:
            # Switching to Live Mode
            with st.spinner("Connecting to Google Earth Engine..."):
                try:
                    st.session_state.gee_initialized = initialize_gee()
                except Exception:
                    st.session_state.gee_initialized = False

            if st.session_state.gee_initialized:
                st.session_state.demo_mode = False
                st.session_state.analysis_results = None
                st.session_state.analysis_error = None
            else:
                st.session_state.demo_mode = True
                st.warning(
                    "Google Earth Engine could not be initialized. "
                    "Open Mode remains active."
                )

            st.rerun()

    mode_str = "Open (Pre-computed Data)" if st.session_state.demo_mode else "Live (Google Earth Engine)"
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
        # Main analytical layers
        "NDVI (After)":       st.checkbox("Show NDVI Layer",         value=True),
        "Water Mask (After)": st.checkbox("Show Water Bodies",       value=True),

        # Spatial context / field evidence
        "Watershed Boundary": st.checkbox("Show Watershed Boundary", value=True),
        "Field Photos":       st.checkbox("Show Field Photos",       value=True),
        "Structures":         st.checkbox("Show Structures",         value=True),
        "Drainage Network":   st.checkbox("Show Drainage Network",   value=False),
        "NDVI Legend":        st.checkbox("Show NDVI Legend",        value=True),

        # Comparison-only / optional analytical layers.
        # Explicitly disabled here so build_complete_map() does not add them
        # automatically. They remain available in res["tile_layers"] for
        # future comparison/analysis features.
        "NDVI (Before)":      False,
        "Slope":              False,
        "before_satellite":   False,
        "after_satellite":    False,
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
if analyze_btn or st.session_state.pop("_trigger_analysis", False):
    # Always clear previous results before starting a new analysis.
    # This ensures no stale data from a previous watershed or mode is shown.
    st.session_state.analysis_results = None
    st.session_state.analysis_error   = None

    if st.session_state.demo_mode:
        # ── DEMO MODE ──────────────────────────────────────────────────────────
        with st.spinner("Loading pre-computed analysis data..."):
            try:
                st.session_state.analysis_results = load_from_demo_files(chosen_id)
            except Exception as e:
                st.session_state.analysis_error = f"Failed to load demo data: {e}"
    elif not _ee_ready():
        # ── LIVE GEE MODE (NOT READY) ──────────────────────────────────────────
        st.session_state.analysis_results = None
        st.session_state.analysis_error = (
            "Google Earth Engine is not ready. "
            "Live analysis was not executed and demo data was not substituted."
        )
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
                # Smaller fallback for change-detection when no verified boundary
                # is available (non-Hiware). Reduces GEE compute cost significantly.
                fallback_analysis_geom = _make_geometry(lat, lon, 5 * 1000)

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

                # Watershed boundary is optional visualization data.
                # Never substitute the 10 km analysis AOI for a real watershed
                # boundary because that would be geographically misleading.
                _LOCAL_BOUNDARIES = {
                    "hiware_bazar": demo_data.get("boundary"),  # already loaded FeatureCollection
                }
                _local_geojson = _LOCAL_BOUNDARIES.get(chosen_id)

                if _local_geojson:
                    # Convert local GeoJSON polygon to ee.Geometry for GEE analysis
                    import ee as _ee
                    _coords = _local_geojson["features"][0]["geometry"]["coordinates"]
                    watershed_analysis_geom = _ee.Geometry.Polygon(_coords)
                    # Use local pre-known area — avoids a blocking GEE round-trip.
                    # The GEE .area().getInfo() call was removed because it stalled
                    # the analysis pipeline before any timeseries work started.
                    _area_known = selected_ws.get("area_sq_km") or 0.0
                    # Synthetic watershed_geom dict so map display + slider work correctly
                    watershed_geom = {
                        "success":    True,
                        "geojson":    _local_geojson["features"][0]["geometry"],
                        "geometry":   watershed_analysis_geom,
                        "area_sq_km": _area_known,
                        "basin_id":   chosen_id,
                    }
                    logger.info("LIVE ANALYSIS: using verified local boundary for %s",
                                chosen_id)
                else:
                    # Fall back to HydroBASINS for watersheds without a local boundary.
                    #
                    # SCALE-MISMATCH GUARD
                    # HydroBASINS Level 7 basins are macro-hydrological units that can be
                    # 50–350× larger than small project watersheds (verified across all 5
                    # watersheds in this dataset). Using such a polygon for reduceRegion()
                    # at scale=10 m would make GEE process thousands of km² — causing
                    # multi-minute stalls or quota exhaustion.
                    #
                    # Rule: if hydrobasins_area / expected_project_area > MAX_RATIO, the
                    # polygon is classified as a project-basin mismatch and MUST NOT be
                    # used for computational analysis or displayed as the project boundary.
                    # The 10 km analysis AOI (geom) is used as the computational fallback.
                    #
                    # Threshold: 20× — all four non-Hiware HydroBASINS polygons exceeded
                    # 54× in testing; 20× provides a clear safety margin while allowing
                    # genuine HydroBASINS matches (e.g. larger basins that happen to match
                    # the project scale) to pass through.
                    _HYDROBASINS_MAX_AREA_RATIO = 20.0

                    watershed_geom = delineate_watershed(lat, lon)
                    watershed_analysis_geom = None

                    if (
                        isinstance(watershed_geom, dict)
                        and watershed_geom.get("success") is True
                        and watershed_geom.get("geometry") is not None
                    ):
                        _hydro_area     = watershed_geom.get("area_sq_km") or 0.0
                        _expected_area  = selected_ws.get("area_sq_km") or 0.0
                        _area_ratio     = (
                            _hydro_area / _expected_area
                            if _expected_area > 0 else float("inf")
                        )

                        if _area_ratio > _HYDROBASINS_MAX_AREA_RATIO:
                            # HydroBASINS polygon is clearly a macro-basin, not the
                            # project watershed. Reject it for both computation AND display.
                            logger.warning(
                                "LIVE ANALYSIS: HydroBASINS basin_id=%s area=%.1f km² "
                                "is %.0fx the expected project area (%.1f km²) — "
                                "exceeds %.0fx threshold. Using 5 km AOI as fallback.",
                                watershed_geom.get("basin_id"),
                                _hydro_area,
                                _area_ratio,
                                _expected_area,
                                _HYDROBASINS_MAX_AREA_RATIO,
                            )
                            # Use the 5 km fallback AOI for computation only.
                            watershed_analysis_geom = fallback_analysis_geom
                            # Clear watershed_geom so the UI does NOT draw the oversized
                            # HydroBASINS polygon as the project boundary.
                            watershed_geom = {
                                "success":    False,
                                "geojson":    None,
                                "geometry":   None,
                                "area_sq_km": None,
                                "basin_id":   None,
                                "error":      "HydroBASINS basin too large for project scale",
                            }
                            status_text.text(
                                "Project boundary unavailable — "
                                "Live analysis using the 5 km analysis AOI."
                            )
                        else:
                            # HydroBASINS polygon is plausibly project-scale — use it.
                            watershed_analysis_geom = watershed_geom["geometry"]
                            logger.info(
                                "LIVE ANALYSIS: HydroBASINS basin_id=%s area=%.2f km² "
                                "(ratio=%.1fx — within threshold).",
                                watershed_geom.get("basin_id"),
                                _hydro_area,
                                _area_ratio,
                            )
                    else:
                        status_text.text(
                            "Project boundary unavailable — "
                            "Live analysis using the 5 km analysis AOI."
                        )
                        watershed_analysis_geom = fallback_analysis_geom

                # NOTE: watershed_geom is preserved exactly as returned from delineate_watershed
                # (whether None or a failed dict) so the UI knows NOT to draw it as a real boundary.
                # Do NOT overwrite watershed_geom with geom.


                status_text.text("Running change detection analysis...")
                progress.progress(60)
                change_result = generate_change_summary(
                    lat,
                    lon,
                    {"start": before_dates[0], "end": before_dates[1]},
                    {"start": after_dates[0], "end": after_dates[1]},
                    watershed_id=chosen_id,
                    progress_callback=lambda *a: None,
                    before_image=before_img,
                    after_image=after_img,
                    geometry=watershed_analysis_geom,
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

                # ── Timeseries — use default 5 km buffer geometry ──────────────
                # The watershed polygon is kept for change detection (above) where
                # spatial accuracy matters. The timeseries use a fixed-radius AOI
                # so that year-over-year comparisons remain consistent across all
                # watersheds regardless of polygon availability.
                # Do NOT pass geometry=watershed_analysis_geom here.
                status_text.text("Calculating NDVI timeseries (years " +
                                 str(start_yr) + "–" + str(end_yr) + ")...")
                progress.progress(80)
                ndvi_ts  = generate_ndvi_timeseries(
                    lat, lon, start_yr, end_yr
                )
                status_text.text("NDVI timeseries complete. Calculating water timeseries...")
                progress.progress(85)
                water_ts = generate_water_timeseries(
                    lat, lon, start_yr, end_yr
                )
                status_text.text("Water timeseries complete. Calculating health score...")
                progress.progress(90)

                # Require at least minimal GEE timeseries results
                if not ndvi_ts:
                    raise RuntimeError(
                        "NDVI timeseries returned no data from GEE. "
                        "Live analysis aborted."
                    )

                if not water_ts:
                    raise RuntimeError(
                        "Water timeseries returned no data from GEE. "
                        "Live analysis aborted."
                    )

                health = calculate_watershed_health(change_result, ndvi_ts)

                status_text.text("Generating map tile layers...")
                progress.progress(95)
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
                    # Real delineated watershed geometry only.
                    # None means boundary visualization is unavailable.
                    "watershed_geom": watershed_geom,

                    # Drainage is optional and expensive. Only request it
                    # when the user explicitly enabled the layer and a real
                    # watershed geometry is available.
                    "drainage_geom": (
                        get_drainage_network(
                            watershed_geom.get("geometry")
                        )
                        if (
                            show_layers.get("Drainage Network", False)
                            and isinstance(watershed_geom, dict)
                            and watershed_geom.get("success") is True
                            and watershed_geom.get("geometry") is not None
                        )
                        else None
                    ),

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
        if st.button("📁 Switch to Open Mode", use_container_width=True):
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
        "📁 Open Analysis · Pre-computed Data"
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
        # Trigger the same analysis handler used by the sidebar button.
        # Do not duplicate the analysis pipeline here.
        st.session_state["_trigger_analysis"] = True
        st.rerun()

    # ── Mode Guide — centered card between Analyze button and Overview ─────────
    _mg_col_l, _mg_col_c, _mg_col_r = st.columns([1, 3, 1])
    with _mg_col_c:
        st.markdown(
            """
            <div style="
                background: rgba(255,255,255,0.05);
                border-left: 3px solid #4a9eff;
                border-radius: 6px;
                padding: 11px 14px;
                margin: 14px 0 4px 0;
                font-size: 0.82rem;
                line-height: 1.5;
                color: #c9d1d9;
            ">
            <span style="font-weight:600; color:#4a9eff;">ℹ️ Mode Guide</span><br>
            <b>Live Mode:</b> Use for real-time satellite analysis when Google Earth Engine
            and internet access are available.<br>
            <b>Open Mode:</b> Use the pre-computed dataset when internet/API access is
            unavailable or Live Mode cannot be used.
            </div>
            """,
            unsafe_allow_html=True,
        )
    # ── End Mode Guide ─────────────────────────────────────────────────────────

    # ── Analysis Overview — visible only before analysis runs ─────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "<h4 style='text-align:center; color:#7ca8d4; margin-bottom:4px;'>"
        "Analysis Overview</h4>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center; color:#8b9bb4; font-size:0.83rem; margin-bottom:14px;'>"
        "What this tool analyses for the selected watershed</p>",
        unsafe_allow_html=True,
    )

    _card_style = (
        "background: rgba(255,255,255,0.04);"
        "border: 1px solid rgba(74,158,255,0.18);"
        "border-radius: 8px;"
        "padding: 16px 14px 14px 14px;"
        "min-height: 130px;"
        "color: #c9d1d9;"
        "font-size: 0.82rem;"
        "line-height: 1.5;"
    )
    _icon_style = "font-size:1.4rem; display:block; margin-bottom:6px;"
    _title_style = "font-weight:600; font-size:0.88rem; color:#4a9eff; display:block; margin-bottom:4px;"

    _ov_c1, _ov_c2, _ov_c3 = st.columns(3, gap="medium")

    with _ov_c1:
        st.markdown(
            f"""<div style="{_card_style}">
            <span style="{_icon_style}">🛰️</span>
            <span style="{_title_style}">Satellite Analysis</span>
            Analyze Sentinel-2 satellite imagery to evaluate watershed conditions
            and changes over time.
            </div>""",
            unsafe_allow_html=True,
        )

    with _ov_c2:
        st.markdown(
            f"""<div style="{_card_style}">
            <span style="{_icon_style}">📊</span>
            <span style="{_title_style}">Environmental Indicators</span>
            Track vegetation health, water availability, erosion risk, and
            watershed health.
            </div>""",
            unsafe_allow_html=True,
        )

    with _ov_c3:
        st.markdown(
            f"""<div style="{_card_style}">
            <span style="{_icon_style}">📍</span>
            <span style="{_title_style}">Field Verification</span>
            Review field observations and supporting photo evidence for
            ground-level validation.
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<p style='"
        "text-align:center; color:#5a6a7a; font-size:0.76rem;"
        "margin-top:14px; letter-spacing:0.02em;"
        "'>"
        "Select a watershed &nbsp;→&nbsp; Choose Live / Open Mode "
        "&nbsp;→&nbsp; Analyze &nbsp;→&nbsp; Explore results"
        "</p>",
        unsafe_allow_html=True,
    )
    # ── End Analysis Overview ──────────────────────────────────────────────────

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
        f"Live Satellite Analysis · Sentinel-2 · Google Earth Engine{_period_str}",
        icon="🛰️",
    )
else:
    st.info(
        "Open Mode Analysis · Pre-computed Local Dataset · data/*.json",
        icon="📁",
    )

# ── Analysis Mode explanation panel ───────────────────────────────────────────
with st.expander("ℹ️ Analysis Mode", expanded=False):
    st.markdown(
        """
**🛰️ Live Mode** — Live satellite analysis using Google Earth Engine.
Recommended when internet / API access is available.

**📁 Open Mode** — Pre-computed local analysis for demonstrations and use
when Live Mode is unavailable.
        """
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

if _is_demo and chosen_id != "hiware_bazar":
    st.info(
        "ℹ️ Detailed watershed boundary data is available for Hiware Bazar in "
        "this pre-computed local dataset. Other watershed locations are shown using verified "
        "center coordinates and field observations."
    )

with st.container(border=True):
    try:
        with st.spinner("Loading map..."):
            photos       = load_all_photos(watershed_id=chosen_id)
            _watershed_result = res.get("watershed_geom")
            if (
                isinstance(_watershed_result, dict)
                and _watershed_result.get("success") is True
            ):
                b_geo = _watershed_result.get("geojson")
            else:
                b_geo = None

            # Demo boundary data is currently available only for Hiware Bazar.
            # Never reuse it for another watershed.
            if (
                not b_geo
                and _is_demo
                and chosen_id == "hiware_bazar"
            ):
                b_geo = demo_data.get("boundary")

            _drainage_result = res.get("drainage_geom")
            if (
                isinstance(_drainage_result, dict)
                and _drainage_result.get("success") is True
            ):
                d_geo = _drainage_result.get("geojson")
            else:
                d_geo = None

            # Demo drainage data is also currently available only for Hiware Bazar.
            if (
                not d_geo
                and _is_demo
                and chosen_id == "hiware_bazar"
            ):
                d_geo = demo_data.get("drainage")

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
            st.markdown("**Health Index Breakdown**")

            veg_s = health.get("vegetation_score", 0) or 0
            wat_s = health.get("water_score", 0) or 0
            ero_s = health.get("erosion_score", 0) or 0
            sust_s = health.get("sustainability_score", 0) or 0

            st.progress(
                min(veg_s / 35, 1.0),
                text=f"🌿 Vegetation Recovery — {veg_s}/35"
            )
            st.progress(
                min(wat_s / 35, 1.0),
                text=f"💧 Water Retention — {wat_s}/35"
            )
            st.progress(
                min(ero_s / 20, 1.0),
                text=f"🏜️ Erosion Reduction — {ero_s}/20"
            )
            st.progress(
                min(sust_s / 10, 1.0),
                text=f"📈 Sustainability Trend — {sust_s}/10"
            )

            st.caption(
                f"Total: {health.get('total_score', 0)}/100"
            )

        except Exception as e:
            st.warning(f"Health score breakdown could not be rendered: {e}")

        # Explain the scoring method without duplicating scoring logic.
        _score_explanation = health.get("score_explanation", {})
        _weights = health.get("weights", {})

        with st.expander("ℹ️ How is the Health Score calculated?"):
            st.markdown(
                "**Watershed Health Index = 100 points**"
            )

            if _weights:
                st.markdown(
                    f"- 🌿 Vegetation Recovery: **{_weights.get('vegetation', 35)} points**\n"
                    f"- 💧 Water Retention: **{_weights.get('water', 35)} points**\n"
                    f"- 🏜️ Erosion Reduction: **{_weights.get('erosion', 20)} points**\n"
                    f"- 📈 Sustainability Trend: **{_weights.get('sustainability', 10)} points**"
                )

            if _score_explanation:
                st.markdown("**Reference ranges used by the prototype:**")

                if _score_explanation.get("vegetation_reference"):
                    st.caption(
                        f"🌿 {_score_explanation['vegetation_reference']}"
                    )

                if _score_explanation.get("water_reference"):
                    st.caption(
                        f"💧 {_score_explanation['water_reference']}"
                    )

                if _score_explanation.get("erosion_reference"):
                    st.caption(
                        f"🏜️ {_score_explanation['erosion_reference']}"
                    )

                if _score_explanation.get("sustainability"):
                    st.caption(
                        f"📈 {_score_explanation['sustainability']}"
                    )

                if _score_explanation.get("validation_status"):
                    st.info(
                        _score_explanation["validation_status"],
                        icon="ℹ️"
                    )

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
        st.caption("📁 The following supplemental charts use pre-computed local data.")
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
        _live_compare = (_data_source == "live")
        _tile_layers = res.get("tile_layers") or {}

        st.markdown("### 🛰️ Satellite Change Comparison")
        st.caption(
            "Drag the divider to compare watershed conditions before and after "
            "the intervention."
        )

        if _live_compare:
            _before_tile = _tile_layers.get("before_satellite")
            _after_tile = _tile_layers.get("after_satellite")

            if not _before_tile or not _after_tile:
                st.warning(
                    "Before/After satellite imagery is unavailable for this live analysis."
                )
            else:
                # Use one Leaflet map and two GEE tile layers.
                # This avoids rendering two independent maps and keeps both
                # years perfectly aligned.
                _before_url = _before_tile.get("tile_url")
                _after_url = _after_tile.get("tile_url")

                if not _before_url or not _after_url:
                    st.warning(
                        "Satellite tile URLs are unavailable for this comparison."
                    )
                else:
                    import json
                    _lat = ws_info.get("lat", 20.0)
                    _lon = ws_info.get("lon", 76.0)

                    _ws_geom = res.get("watershed_geom")
                    if isinstance(_ws_geom, dict) and _ws_geom.get("geojson"):
                        _ws_geom_json = json.dumps(_ws_geom["geojson"])
                    else:
                        _ws_geom_json = "null"

                    # Load the Leaflet side-by-side plugin only inside the
                    # comparison component. No project dependency is added.
                    _slider_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">

<link
  rel="stylesheet"
  href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
/>

<style>
html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
}}

#map {{
    width: 100%;
    height: 520px;
}}

.compare-title {{
    position: absolute;
    top: 12px;
    z-index: 1000;
    padding: 6px 12px;
    border-radius: 6px;
    background: rgba(15, 23, 42, 0.85);
    color: white;
    font-family: Arial, sans-serif;
    font-size: 14px;
    font-weight: 700;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    pointer-events: none;
}}

.before-title {{
    left: 12px;
}}

.after-title {{
    right: 12px;
}}

.compare-help {{
    position: absolute;
    bottom: 14px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1000;
    padding: 8px 16px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.9);
    color: white;
    font-family: Arial, sans-serif;
    font-size: 13px;
    font-weight: 600;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    pointer-events: none;
}}
</style>
</head>

<body>

<div id="map"></div>

<div class="compare-title before-title">
    🔴 BEFORE · 2019
</div>

<div class="compare-title after-title">
    🟢 AFTER · 2024
</div>

<div class="compare-help">
    ← 2019 baseline &nbsp;|&nbsp; 2024 post-intervention →
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
(function() {{
    const map = L.map("map", {{
        center: [{_lat}, {_lon}],
        zoom: 12,
        zoomControl: true,
        attributionControl: true
    }});

    const reference = L.tileLayer(
        "https://{{s}}.basemaps.cartocdn.com/light_nolabels/{{z}}/{{x}}/{{y}}{{r}}.png",
        {{
            attribution: "© OpenStreetMap © CARTO",
            maxZoom: 19
        }}
    ).addTo(map);

    const beforeLayer = L.tileLayer(
        {_before_url!r},
        {{
            opacity: 1.0,
            maxZoom: 20,
            attribution: "Sentinel-2 / Google Earth Engine"
        }}
    );

    const afterLayer = L.tileLayer(
        {_after_url!r},
        {{
            opacity: 1.0,
            maxZoom: 20,
            attribution: "Sentinel-2 / Google Earth Engine"
        }}
    );

    afterLayer.addTo(map);

    // Create a clipping pane for the AFTER imagery.
    const afterPane = map.createPane("afterPane");
    afterPane.style.zIndex = 401;
    afterPane.style.clipPath = "inset(0 0 0 50%)";

    // Recreate AFTER layer using the clipping pane.
    map.removeLayer(afterLayer);

    const clippedAfterLayer = L.tileLayer(
        {_after_url!r},
        {{
            pane: "afterPane",
            opacity: 1.0,
            maxZoom: 20,
            attribution: "Sentinel-2 / Google Earth Engine"
        }}
    ).addTo(map);

    // BEFORE remains underneath.
    beforeLayer.addTo(map);

    // Overlay the watershed boundary (if available) on top of satellites
    const wsGeom = {_ws_geom_json};
    if (wsGeom) {{
        L.geoJSON(wsGeom, {{
            style: {{
                color: "#ffeb3b",
                weight: 3,
                fillOpacity: 0,
                opacity: 1
            }},
            interactive: false
        }}).addTo(map);
    }}

    let split = 50;
    let dragging = false;

    function applySplit() {{
        const pane = document.getElementById("map");
        const width = pane.clientWidth;
        const splitPx = Math.round(width * split / 100);

        afterPane.style.clipPath =
            `inset(0 0 0 ${{splitPx}}px)`;

        divider.style.left = `${{splitPx}}px`;
    }}

    const divider = document.createElement("div");
    divider.style.position = "absolute";
    divider.style.top = "0";
    divider.style.bottom = "0";
    divider.style.width = "4px";
    divider.style.background = "#ffffff";
    divider.style.boxShadow = "0 0 12px rgba(0,0,0,0.8)";
    divider.style.zIndex = "1001";
    divider.style.left = "50%";
    divider.style.cursor = "ew-resize";
    divider.style.pointerEvents = "auto";
    divider.style.touchAction = "none";

    const handle = document.createElement("div");
    handle.innerHTML = "↔";
    handle.style.position = "absolute";
    handle.style.left = "50%";
    handle.style.top = "50%";
    handle.style.transform = "translate(-50%, -50%)";
    handle.style.width = "42px";
    handle.style.height = "42px";
    handle.style.border = "2px solid #ffffff";
    handle.style.borderRadius = "50%";
    handle.style.background = "white";
    handle.style.color = "#0f172a";
    handle.style.display = "flex";
    handle.style.alignItems = "center";
    handle.style.justifyContent = "center";
    handle.style.fontSize = "18px";
    handle.style.fontWeight = "700";
    handle.style.boxShadow = "0 4px 12px rgba(0,0,0,0.6)";
    handle.style.pointerEvents = "none";

    divider.appendChild(handle);

    document.getElementById("map").appendChild(divider);

    function setSplit(clientX) {{
        const rect = document
            .getElementById("map")
            .getBoundingClientRect();

        split = Math.max(
            0,
            Math.min(100, ((clientX - rect.left) / rect.width) * 100)
        );

        applySplit();
    }}

    // Prevent Leaflet from interpreting divider interaction as map dragging.
    function stopLeafletInteraction(event) {{
        event.preventDefault();
        event.stopPropagation();
    }}

    divider.addEventListener("mousedown", function(event) {{
        stopLeafletInteraction(event);
        dragging = true;
    }});

    divider.addEventListener("mousemove", function(event) {{
        if (dragging) {{
            event.preventDefault();
            event.stopPropagation();
            setSplit(event.clientX);
        }}
    }});

    document.addEventListener("mouseup", function() {{
        dragging = false;
    }});

    divider.addEventListener("touchstart", function(event) {{
        event.preventDefault();
        event.stopPropagation();
        dragging = true;

        if (event.touches.length) {{
            setSplit(event.touches[0].clientX);
        }}
    }}, {{ passive: false }});

    document.addEventListener("touchend", function() {{
        dragging = false;
    }});

    document.addEventListener("touchmove", function(event) {{
        if (dragging && event.touches.length) {{
            event.preventDefault();
            event.stopPropagation();
            setSplit(event.touches[0].clientX);
        }}
    }}, {{ passive: false }});

    // Also support modern pointer events for reliable mouse/touch dragging.
    divider.addEventListener("pointerdown", function(event) {{
        event.preventDefault();
        event.stopPropagation();
        dragging = true;

        if (event.clientX !== undefined) {{
            setSplit(event.clientX);
        }}

        try {{
            divider.setPointerCapture(event.pointerId);
        }} catch (e) {{}}
    }});

    document.addEventListener("pointermove", function(event) {{
        if (dragging) {{
            event.preventDefault();
            event.stopPropagation();
            setSplit(event.clientX);
        }}
    }}, {{ passive: false }});

    document.addEventListener("pointerup", function() {{
        dragging = false;
    }});

    document.addEventListener("pointercancel", function() {{
        dragging = false;
    }});

    window.addEventListener("resize", applySplit);

    // Keep the map fitted at the same location for both years.
    map.setView([{_lat}, {_lon}], 12);

    setTimeout(applySplit, 200);
}})();
</script>

</body>
</html>
"""

                    st.components.v1.html(
                        _slider_html,
                        height=540,
                        scrolling=False
                    )

                st.markdown("")

                c1, c2, c3 = st.columns(3)

                with c1:
                    st.metric(
                        "2019 NDVI",
                        f"{veg.get('ndvi_before', 0):.2f}"
                    )

                with c2:
                    st.metric(
                        "2024 NDVI",
                        f"{veg.get('ndvi_after', 0):.2f}"
                    )

                with c3:
                    _ndvi_delta = veg.get("change", 0) or 0
                    st.metric(
                        "NDVI Change",
                        f"{'+' if _ndvi_delta > 0 else ''}{_ndvi_delta:.2f}"
                    )

                c4, c5, c6 = st.columns(3)

                with c4:
                    st.metric(
                        "2019 Water Area",
                        f"{wat.get('area_before_ha', 0):.1f} ha"
                    )

                with c5:
                    st.metric(
                        "2024 Water Area",
                        f"{wat.get('area_after_ha', 0):.1f} ha"
                    )

                with c6:
                    _water_delta = wat.get("change_percent", 0) or 0
                    st.metric(
                        "Water Change",
                        f"{'+' if _water_delta > 0 else ''}{_water_delta:.1f}%"
                    )

                st.caption(
                    "🛰️ Sentinel-2 SR Harmonized · Cloud-masked composite · "
                    "Google Earth Engine"
                )

        else:
            # ── DEMO MODE: image-based draggable split comparison ──────────────
            import base64

            _assets_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "assets"
            )

            # ── Per-watershed image lookup ─────────────────────────────────────
            # Primary: assets/before_after/<watershed_id>/before.png|after.png
            # Fallback (Hiware Bazar only): legacy assets/demo_before.png / demo_after.png
            _ba_dir = os.path.join(_assets_dir, "before_after", chosen_id)
            _demo_before_path = os.path.join(_ba_dir, "before.png")
            _demo_after_path  = os.path.join(_ba_dir, "after.png")

            # Fallback for Hiware Bazar when new structure not yet populated
            if not os.path.exists(_demo_before_path) and chosen_id == "hiware_bazar":
                _demo_before_path = os.path.join(_assets_dir, "demo_before.png")
            if not os.path.exists(_demo_after_path) and chosen_id == "hiware_bazar":
                _demo_after_path = os.path.join(_assets_dir, "demo_after.png")

            _before_missing = not os.path.exists(_demo_before_path)
            _after_missing  = not os.path.exists(_demo_after_path)

            if _before_missing or _after_missing:
                st.info(
                    f"Before/After imagery is not available for "
                    f"{ws_info.get('name', chosen_id)} yet.",
                    icon="🛰️",
                )
            else:
                with open(_demo_before_path, "rb") as _bf:
                    _before_b64 = base64.b64encode(_bf.read()).decode()
                with open(_demo_after_path, "rb") as _af:
                    _after_b64 = base64.b64encode(_af.read()).decode()

                _before_data_uri = f"data:image/png;base64,{_before_b64}"
                _after_data_uri  = f"data:image/png;base64,{_after_b64}"

                _demo_slider_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #0f172a;
}}

#compare-container {{
    position: relative;
    width: 100%;
    height: 520px;
    overflow: hidden;
    user-select: none;
    -webkit-user-select: none;
}}

.compare-img {{
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    pointer-events: none;
}}

#img-after {{
    clip-path: inset(0 0 0 50%);
}}

.compare-title {{
    position: absolute;
    top: 12px;
    z-index: 1000;
    padding: 6px 12px;
    border-radius: 6px;
    background: rgba(15, 23, 42, 0.85);
    color: white;
    font-family: Arial, sans-serif;
    font-size: 14px;
    font-weight: 700;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    pointer-events: none;
}}

.before-title {{ left: 12px; }}
.after-title  {{ right: 12px; }}

.compare-help {{
    position: absolute;
    bottom: 14px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1000;
    padding: 8px 16px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.9);
    color: white;
    font-family: Arial, sans-serif;
    font-size: 13px;
    font-weight: 600;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    pointer-events: none;
    white-space: nowrap;
}}

#divider {{
    position: absolute;
    top: 0;
    bottom: 0;
    width: 4px;
    left: 50%;
    background: #ffffff;
    box-shadow: 0 0 12px rgba(0,0,0,0.8);
    z-index: 1001;
    cursor: ew-resize;
    pointer-events: auto;
    touch-action: none;
}}

#handle {{
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 42px;
    height: 42px;
    border: 2px solid #ffffff;
    border-radius: 50%;
    background: white;
    color: #0f172a;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(0,0,0,0.6);
    pointer-events: none;
}}
</style>
</head>
<body>

<div id="compare-container">
    <img id="img-before" class="compare-img"
         src="{_before_data_uri}" alt="Before 2019">
    <img id="img-after" class="compare-img"
         src="{_after_data_uri}" alt="After 2024">

    <div class="compare-title before-title">🔴 BEFORE &bull; 2019</div>
    <div class="compare-title after-title">🟢 AFTER &bull; 2024</div>

    <div class="compare-help">
        &larr; 2019 baseline &nbsp;|&nbsp; 2024 post-intervention &rarr;
    </div>

    <div id="divider">
        <div id="handle">&#8596;</div>
    </div>
</div>

<script>
(function() {{
    const container = document.getElementById("compare-container");
    const imgAfter  = document.getElementById("img-after");
    const divider   = document.getElementById("divider");

    let split    = 50;
    let dragging = false;

    function applySplit() {{
        const w = container.clientWidth;
        const px = Math.round(w * split / 100);
        imgAfter.style.clipPath = "inset(0 0 0 " + px + "px)";
        divider.style.left      = px + "px";
    }}

    function setSplit(clientX) {{
        const rect = container.getBoundingClientRect();
        split = Math.max(0, Math.min(100,
            ((clientX - rect.left) / rect.width) * 100
        ));
        applySplit();
    }}

    // Mouse
    divider.addEventListener("mousedown", function(e) {{
        e.preventDefault(); e.stopPropagation(); dragging = true;
    }});
    document.addEventListener("mousemove", function(e) {{
        if (dragging) {{ e.preventDefault(); setSplit(e.clientX); }}
    }});
    document.addEventListener("mouseup", function() {{ dragging = false; }});

    // Touch
    divider.addEventListener("touchstart", function(e) {{
        e.preventDefault(); e.stopPropagation(); dragging = true;
        if (e.touches.length) setSplit(e.touches[0].clientX);
    }}, {{ passive: false }});
    document.addEventListener("touchmove", function(e) {{
        if (dragging && e.touches.length) {{
            e.preventDefault(); setSplit(e.touches[0].clientX);
        }}
    }}, {{ passive: false }});
    document.addEventListener("touchend", function() {{ dragging = false; }});

    // Pointer (covers both mouse & touch uniformly)
    divider.addEventListener("pointerdown", function(e) {{
        e.preventDefault(); e.stopPropagation(); dragging = true;
        try {{ divider.setPointerCapture(e.pointerId); }} catch(ex) {{}}
        setSplit(e.clientX);
    }});
    document.addEventListener("pointermove", function(e) {{
        if (dragging) {{ e.preventDefault(); setSplit(e.clientX); }}
    }}, {{ passive: false }});
    document.addEventListener("pointerup",     function() {{ dragging = false; }});
    document.addEventListener("pointercancel", function() {{ dragging = false; }});

    window.addEventListener("resize", applySplit);
    setTimeout(applySplit, 100);
}})();
</script>

</body>
</html>
"""
                st.components.v1.html(
                    _demo_slider_html,
                    height=540,
                    scrolling=False,
                )

            # ── Demo metric cards (always visible regardless of images) ────────
            st.markdown("")
            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric(
                    "2019 NDVI",
                    f"{veg.get('ndvi_before', 0):.2f}"
                )

            with c2:
                st.metric(
                    "2024 NDVI",
                    f"{veg.get('ndvi_after', 0):.2f}"
                )

            with c3:
                st.metric(
                    "NDVI Change",
                    f"{veg.get('change', 0) or 0:.2f}"
                )

            c4, c5, c6 = st.columns(3)

            with c4:
                st.metric(
                    "2019 Water Area",
                    f"{wat.get('area_before_ha', 0):.1f} ha"
                )

            with c5:
                st.metric(
                    "2024 Water Area",
                    f"{wat.get('area_after_ha', 0):.1f} ha"
                )

            with c6:
                st.metric(
                    "Water Change",
                    f"{wat.get('change_percent', 0) or 0:.1f}%"
                )

            st.caption("📁 Open Analysis · Pre-computed Data")

    except Exception as e:
        st.warning(
            f"Before/After comparison could not be rendered: {e}"
        )

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


# ─────────────────────────────────────────────────────────────────────────────
# Field Verification image dialog — defined at module scope so Streamlit can
# register it once per script run.  Image source and caption are passed via
# session state so the correct per-card image is always shown.
# ─────────────────────────────────────────────────────────────────────────────
@st.dialog("📷 Field Image Viewer")
def _field_image_dialog():
    """Display the field image stored in st.session_state['_fv_img_src']."""
    img_src = st.session_state.get("_fv_img_src")
    caption  = st.session_state.get("_fv_img_caption", "Field Photo")
    source   = st.session_state.get("_fv_img_source", "local")
    if img_src:
        st.image(img_src, use_container_width=True)
        if source == "uploaded":
            st.caption(f"📤 Uploaded Field Photo — {caption}")
        else:
            st.caption(f"🛰️ Representative imagery — {caption}")
    else:
        st.info("Image could not be loaded.")


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

                                # -------------------------------------------------
                                # 1. Generate thumbnail and display image
                                # -------------------------------------------------
                                photo_thumbnail = create_photo_thumbnail(uploaded_file)
                                photo_display = create_photo_image_b64(uploaded_file)

                                # -------------------------------------------------
                                # 2. Match GPS against the sample field
                                #    observations for this watershed.
                                # -------------------------------------------------
                                match_result = {
                                    "matched": False,
                                    "distance_m": None,
                                    "reference": None,
                                    "match_type": None,
                                }

                                if gps_data.get("has_gps"):
                                    match_result = find_nearest_reference_observation(
                                        lat_input,
                                        lon_input,
                                        chosen_id,
                                        max_distance_m=500.0,
                                    )

                                reference = match_result.get("reference") or {}

                                # A proximity match alone is not enough to call
                                # the field observation verified. Require the
                                # selected structure type to match too.
                                type_matches = (
                                    bool(reference)
                                    and str(reference.get("type", "")).strip().lower()
                                    == str(structure_type).strip().lower()
                                )

                                if match_result.get("matched") and type_matches:
                                    verification_status = "reference_match"
                                    reference_observation_id = reference.get("id")
                                    reference_distance_m = match_result.get("distance_m")

                                    st.success(
                                        f"📍 GPS reference match: "
                                        f"{reference.get('type', 'Observation')} "
                                        f"#{reference.get('id', 'N/A')} "
                                        f"at {reference_distance_m:.1f} m",
                                        icon="✅",
                                    )
                                    st.caption(
                                        "Prototype reference match only. "
                                        "This does not automatically verify the field report."
                                    )

                                elif match_result.get("matched") and not type_matches:
                                    verification_status = "reference_type_mismatch"
                                    reference_observation_id = reference.get("id")
                                    reference_distance_m = match_result.get("distance_m")

                                    st.warning(
                                        f"📍 Nearest reference is "
                                        f"{reference.get('type', 'Unknown')} "
                                        f"(not {structure_type}) "
                                        f"at {reference_distance_m:.1f} m.",
                                        icon="⚠️",
                                    )

                                elif gps_data.get("has_gps"):
                                    verification_status = "no_reference_match"
                                    reference_observation_id = None
                                    reference_distance_m = match_result.get("distance_m")

                                    st.info(
                                        "📍 No matching reference observation found "
                                        "within 500 m.",
                                        icon="ℹ️",
                                    )

                                else:
                                    verification_status = "gps_unavailable"
                                    reference_observation_id = None
                                    reference_distance_m = None

                                    st.warning(
                                        "GPS unavailable — photo saved without "
                                        "reference matching.",
                                        icon="⚠️",
                                    )

                                # -------------------------------------------------
                                # 3. Persist photo + reference-match metadata.
                                #    verified remains False unless explicitly
                                #    provided by the caller.
                                # -------------------------------------------------
                                save_photo_entry(
                                    {
                                        "lat": lat_input,
                                        "lon": lon_input,
                                        "type": structure_type,
                                        "status": status,
                                        "water_level": f"{water_level}%",
                                        "description": notes,
                                        "date": datetime.now().strftime("%Y-%m-%d"),
                                        "watershed_id": chosen_id,
                                        "verified": False,
                                        "verification_status": verification_status,
                                        "reference_observation_id": reference_observation_id,
                                        "reference_distance_m": reference_distance_m,
                                        "reference_match_type": (
                                            "sample_field_observation"
                                            if reference
                                            else None
                                        ),
                                    },
                                    chosen_id,
                                    photo_base64=photo_thumbnail,
                                    photo_image_b64=photo_display,
                                )

                                st.success(
                                    "Photo saved successfully.",
                                    icon="💾",
                                )
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

        if _is_demo and all_photos:
            for p in all_photos:
                if p.get("verification_status") and p.get("verification_status") != "not_matched":
                    continue
                
                lat = p.get("lat")
                lon = p.get("lon")
                ws_id = p.get("watershed_id", chosen_id)
                struct_type = p.get("type", "")
                
                if lat is not None and lon is not None:
                    try:
                        lat_f = float(lat)
                        lon_f = float(lon)
                        match_result = find_nearest_reference_observation(
                            lat_f, lon_f, ws_id, max_distance_m=500.0
                        )
                        ref = match_result.get("reference") or {}
                        
                        type_matches = (
                            bool(ref)
                            and str(ref.get("type", "")).strip().lower()
                            == str(struct_type).strip().lower()
                        )
                        
                        if match_result.get("matched") and type_matches:
                            p["verification_status"] = "reference_match"
                        elif match_result.get("matched") and not type_matches:
                            p["verification_status"] = "reference_type_mismatch"
                        else:
                            p["verification_status"] = "no_reference_match"
                            
                        p["reference_observation_id"] = ref.get("id")
                        p["reference_distance_m"] = match_result.get("distance_m")
                        p["reference_match_type"] = "sample_field_observation" if ref else None

                    except (ValueError, TypeError):
                        p["verification_status"] = "gps_unavailable"
                else:
                    p["verification_status"] = "gps_unavailable"

        st.markdown("### 📋 Field Evidence Status")
        st.caption(
            "GPS reference matching compares the uploaded photo location with sample "
            "field observations. A reference match is not automatic proof of field truth."
        )

        if all_photos:
            total_obs = len(all_photos)
            ref_matches = sum(1 for p in all_photos if p.get("verification_status") == "reference_match")
            type_mismatches = sum(1 for p in all_photos if p.get("verification_status") == "reference_type_mismatch")
            unmatched = sum(1 for p in all_photos if p.get("verification_status") in ("no_reference_match", "gps_unavailable", "not_matched"))
            
            st.markdown(
                f"**Total observations:** {total_obs} | "
                f"**✅ Reference matches:** {ref_matches} | "
                f"**⚠️ Type mismatches:** {type_mismatches} | "
                f"**ℹ️ Unmatched / GPS unavailable:** {unmatched}"
            )

            # ── Helper: resolve local field photo path for a sample observation
            _field_photos_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "assets", "field_photos"
            )

            def _resolve_field_image(photo_entry: dict):
                """Return absolute path to a local field image, or None if absent."""
                placeholder = photo_entry.get("image_placeholder")
                ws = photo_entry.get("watershed_id", "")
                if not placeholder or not ws:
                    return None
                ws_dir = os.path.join(_field_photos_dir, ws)
                for ext in (".jpg", ".jpeg", ".png", ".webp"):
                    candidate = os.path.join(ws_dir, placeholder + ext)
                    if os.path.exists(candidate):
                        return candidate
                return None

            # ── CSS: dark background for field-verification card containers ──
            # Targets bordered stVerticalBlock wrappers in this section only
            # (scoped by page position; does not affect other tabs).
            st.markdown(
                """
                <style>
                div[data-testid="stVerticalBlockBorderWrapper"] {
                    background: rgba(30, 41, 59, 0.55) !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            p_cols = st.columns(3)
            for i, photo in enumerate(all_photos):
                with p_cols[i % 3]:
                    status_color = {
                        'Functional': '#22c55e', 'Needs Repair': '#f59e0b',
                        'Damaged':    '#ef4444', 'Dry':          '#64748b'
                    }.get(photo.get('status', ''), '#3b82f6')

                    v_status = photo.get("verification_status", "not_matched")
                    if v_status == "reference_match":
                        v_label, v_color, v_bg = "✅ GPS Reference Match",      "#166534", "#dcfce7"
                    elif v_status == "reference_type_mismatch":
                        v_label, v_color, v_bg = "⚠️ Reference Type Mismatch", "#92400e", "#fef3c7"
                    elif v_status == "no_reference_match":
                        v_label, v_color, v_bg = "ℹ️ No Reference Match",      "#475569", "#f1f5f9"
                    elif v_status == "gps_unavailable":
                        v_label, v_color, v_bg = "⚠️ GPS Unavailable",         "#475569", "#f1f5f9"
                    else:
                        v_label, v_color, v_bg = "ℹ️ Verification Pending",    "#475569", "#f1f5f9"

                    ref_dist = photo.get("reference_distance_m")
                    ref_id   = photo.get("reference_observation_id")

                    _ref_parts = []
                    if ref_dist is not None:
                        try:
                            _ref_parts.append(
                                f"<div style='margin-top:4px;'>"
                                f"📏 Reference distance: {float(ref_dist):.1f} m</div>"
                            )
                        except (TypeError, ValueError):
                            pass
                    if ref_id is not None:
                        _ref_parts.append(
                            f"<div style='margin-top:4px;'>"
                            f"🔎 Reference observation: #{ref_id}</div>"
                        )
                    ref_html = "".join(_ref_parts)

                    manually_verified_html = (
                        "<div style='margin-top:6px; font-size:11px; "
                        "color:#166534; font-weight:600;'>✓ Manually Verified</div>"
                        if photo.get("verified") else ""
                    )

                    verification_html = (
                        f"<div style='margin-top:8px; padding:8px; border-radius:7px; "
                        f"background:{v_bg}; color:{v_color}; font-size:11px; font-weight:600;'>"
                        f"{v_label}{ref_html}</div>"
                    )

                    # ── Resolve image source ──────────────────────────────────
                    _display_b64 = photo.get("photo_image_b64")
                    _thumb_b64   = photo.get("thumbnail_b64")
                    _local_img   = _resolve_field_image(photo)

                    _has_image   = False
                    _img_src_fv  = None
                    _img_caption = photo.get("type", "Field Photo")
                    _img_source  = "local"

                    if _display_b64 or _thumb_b64:
                        _best_b64 = _display_b64 or _thumb_b64
                        _img_src_fv = (
                            _best_b64
                            if _best_b64.startswith("data:")
                            else f"data:image/jpeg;base64,{_best_b64}"
                        )
                        _has_image  = True
                        _img_source = "uploaded"
                    elif _local_img:
                        _img_src_fv = _local_img
                        _has_image  = True
                        _img_source = "local"

                    # ── Safe coordinate formatting ────────────────────────────
                    try:
                        _lat_str = f"{float(photo.get('lat', 0)):.4f}"
                        _lon_str = f"{float(photo.get('lon', 0)):.4f}"
                    except (TypeError, ValueError):
                        _lat_str = _lon_str = "N/A"

                    # ── Card as native Streamlit container ────────────────────
                    # Fixed height keeps every Field Verification card aligned.
                    # The image button remains inside the card.
                    with st.container(
                        border=True,
                        height=270,
                        key=f"fv_card_{chosen_id}_{i}",
                    ):
                        # Header: type, coordinates, date with coloured accent bar
                        st.markdown(
                            f'<div style="border-left:4px solid {status_color};'
                            f' padding-left:8px; margin-bottom:6px;">'
                            f'<strong style="color:#f8fafc;">'
                            f'{photo.get("type", "Photo")}</strong><br>'
                            f'<span style="color:#94a3b8; font-size:12px;">'
                            f'\U0001f4cd {_lat_str}, {_lon_str}</span><br>'
                            f'<span style="color:#94a3b8; font-size:12px;">'
                            f'\U0001f4c5 {photo.get("date", "")}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # ── Image action — identical height on every card ─────
                        # Active button for cards with an image; disabled button
                        # (same pixel dimensions) for cards without an image.
                        _btn_key = f"fv_img_btn_{chosen_id}_{i}"
                        if _has_image:
                            if st.button(
                                "\U0001f4f7 Click to view image",
                                key=_btn_key,
                                use_container_width=True,
                                help="Open field image viewer",
                            ):
                                st.session_state["_fv_img_src"]     = _img_src_fv
                                st.session_state["_fv_img_caption"] = _img_caption
                                st.session_state["_fv_img_source"]  = _img_source
                                _field_image_dialog()
                        else:
                            st.button(
                                "\U0001f4f7 Field image not available",
                                key=_btn_key,
                                use_container_width=True,
                                disabled=True,
                                help="No field image available for this observation",
                            )

                        # ── Status / verification / description footer ─────────
                        st.markdown(
                            f'<span style="background:{status_color}; color:white;'
                            f' padding:2px 8px; border-radius:8px; font-size:11px;'
                            f' font-weight:600;">{photo.get("status", "")}</span>'
                            f'{verification_html}'
                            f'{manually_verified_html}'
                            f'<div style="margin-top:6px; font-size:12px; color:#cbd5e1;">'
                            f'{photo.get("description", "")[:80]}</div>',
                            unsafe_allow_html=True,
                        )


        else:
            st.info("No field photos recorded for this watershed yet.")
    except Exception as e:
        st.warning(f"Could not load field photos: {e}")

st.divider()
st.caption("Built for Smart India Hackathon 2026 | Team AquaVeda")
