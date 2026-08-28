"""
data/generate_open_mode_from_live.py
=====================================
AquaVeda — Open Mode Synchronization Script

Runs the Live GEE analysis pipeline EXACTLY ONCE per watershed, saves the
results to data/live_snapshot.json, then merges only the synchronized fields
into the four Open Mode JSON files.

OPEN-ONLY FIELDS (never overwritten):
  - change_data: landuse, water.months_with_water_*, water.new_water_bodies
  - monthly_ndvi, rainfall (not computed in Live Mode)
  - Before/After imagery (Live=GEE tiles, Open=local illustrative PNGs)

Before modifying any JSON, timestamped backups are created.

Usage:
    cd watershed-monitor
    python data/generate_open_mode_from_live.py

Do NOT commit data/live_snapshot.json or data/backups/ -- both are in .gitignore.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# -- Setup project path --------------------------------------------------------
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

# -- Logging -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aquaveda.generate_open_mode")

# -- Paths ---------------------------------------------------------------------
DATA_DIR      = _SCRIPT_DIR
SNAPSHOT_PATH = os.path.join(DATA_DIR, "live_snapshot.json")
BACKUPS_DIR   = os.path.join(DATA_DIR, "backups")

CHANGE_DATA_PATH   = os.path.join(DATA_DIR, "change_data.json")
HEALTH_SCORES_PATH = os.path.join(DATA_DIR, "health_scores.json")
NDVI_TS_PATH       = os.path.join(DATA_DIR, "ndvi_timeseries.json")
WATER_TS_PATH      = os.path.join(DATA_DIR, "water_timeseries.json")
SAMPLE_WS_PATH     = os.path.join(DATA_DIR, "sample_watersheds.json")
HIWARE_BOUNDARY    = os.path.join(DATA_DIR, "watershed_boundary_hiware_bazar.geojson")


# =============================================================================
# HELPERS
# =============================================================================

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _backup_json_files(timestamp: str) -> None:
    """Create timestamped backups of all four Open Mode JSON files."""
    backup_dir = os.path.join(BACKUPS_DIR, timestamp)
    os.makedirs(backup_dir, exist_ok=True)
    files = [CHANGE_DATA_PATH, HEALTH_SCORES_PATH, NDVI_TS_PATH, WATER_TS_PATH]
    for src in files:
        if os.path.exists(src):
            basename = os.path.basename(src)
            dst = os.path.join(backup_dir, basename)
            shutil.copy2(src, dst)
            size = os.path.getsize(src)
            h    = _file_hash(src)
            logger.info(
                "BACKUP  %-35s  size=%d bytes  sha256=%s...",
                basename, size, h[:16],
            )
    logger.info("Backups written to: %s", backup_dir)


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Saved: %s", path)


# =============================================================================
# GEE INITIALISATION
# =============================================================================

def _init_gee() -> None:
    """Initialize GEE using config.initialize_gee() -- same path as Live Mode."""
    from config import initialize_gee, EE_PROJECT_ID
    logger.info("Initializing Google Earth Engine (project=%s)...", EE_PROJECT_ID)
    initialize_gee()
    from backend.gee_engine import _ee_ready
    if not _ee_ready():
        raise RuntimeError(
            "GEE initialization failed -- check EE_PROJECT_ID and credentials."
        )
    logger.info("GEE ready.")


# =============================================================================
# PER-WATERSHED LIVE ANALYSIS
# Mirrors app.py lines 463-691 exactly.
# =============================================================================

def _run_one_watershed(ws: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the Live Mode pipeline for one watershed and return a dict containing
    all synchronized metrics.  Stops immediately on failure -- never retries.
    """
    ws_id    = ws["id"]
    lat, lon = ws["lat"],  ws["lon"]
    start_yr = ws.get("start_year", 2019)
    end_yr   = 2024

    before_dates = (f"{start_yr}-01-01", f"{start_yr}-12-31")
    after_dates  = (f"{end_yr}-01-01",   f"{end_yr}-12-31")

    logger.info("=" * 60)
    logger.info("WATERSHED: %s  (%s)", ws_id, ws.get("name", ""))
    logger.info("  Before: %s -- %s", before_dates[0], before_dates[1])
    logger.info("  After : %s -- %s", after_dates[0],  after_dates[1])
    logger.info("=" * 60)

    # -- Imports (same as app.py) ----------------------------------------------
    import ee as _ee
    from backend.gee_engine import _make_geometry, create_s2_composite
    from backend.change_detection import generate_change_summary
    from backend.indices import generate_ndvi_timeseries, generate_water_timeseries
    from backend.health_score import calculate_watershed_health

    # -- AOI geometry (app.py L473-476) ----------------------------------------
    geom                   = _make_geometry(lat, lon, 10 * 1000)  # 10 km composites
    fallback_analysis_geom = _make_geometry(lat, lon,  5 * 1000)  # 5 km analysis

    # -- BEFORE composite (app.py L481-491) ------------------------------------
    logger.info("[1/5] Building BEFORE composite (%s)...", before_dates[0])
    t0 = time.perf_counter()
    before_img, before_meta = create_s2_composite(
        aoi=geom,
        start_date=before_dates[0],
        end_date=before_dates[1],
        label=f"Before {start_yr}",
    )
    if before_img is None:
        raise RuntimeError(
            f"{ws_id}: BEFORE composite returned None. "
            "Stopping to avoid overwriting data with incomplete results."
        )
    logger.info("  BEFORE composite OK (%.1f s).", time.perf_counter() - t0)

    # -- AFTER composite (app.py L496-506) -------------------------------------
    logger.info("[2/5] Building AFTER composite (%s)...", after_dates[0])
    t0 = time.perf_counter()
    after_img, after_meta = create_s2_composite(
        aoi=geom,
        start_date=after_dates[0],
        end_date=after_dates[1],
        label=f"After {end_yr}",
    )
    if after_img is None:
        raise RuntimeError(
            f"{ws_id}: AFTER composite returned None. "
            "Stopping to avoid overwriting data with incomplete results."
        )
    logger.info("  AFTER composite OK (%.1f s).", time.perf_counter() - t0)

    # -- Watershed analysis geometry (app.py L514-618) -------------------------
    if ws_id == "hiware_bazar" and os.path.exists(HIWARE_BOUNDARY):
        with open(HIWARE_BOUNDARY, "r", encoding="utf-8") as _f:
            _local_geojson = json.load(_f)
        _coords = _local_geojson["features"][0]["geometry"]["coordinates"]
        watershed_analysis_geom = _ee.Geometry.Polygon(_coords)
        logger.info("  Using verified local boundary for hiware_bazar.")
    else:
        # All other watersheds: HydroBASINS is rejected by the >20x area guard
        # (documented in app.py L557-598), so use 5 km fallback directly.
        watershed_analysis_geom = fallback_analysis_geom
        logger.info("  Using 5 km fallback analysis geometry for %s.", ws_id)

    # -- Change detection (app.py L627-637) ------------------------------------
    logger.info("[3/5] Running change detection...")
    t0 = time.perf_counter()
    change_result = generate_change_summary(
        lat,
        lon,
        {"start": before_dates[0], "end": before_dates[1]},
        {"start": after_dates[0],  "end": after_dates[1]},
        watershed_id=ws_id,
        progress_callback=None,
        before_image=before_img,
        after_image=after_img,
        geometry=watershed_analysis_geom,
    )
    logger.info("  Change detection OK (%.1f s).", time.perf_counter() - t0)

    # -- Validate required sections are GEE-derived (app.py L643-656) ----------
    _REQUIRED = ("vegetation", "water", "erosion")
    _section_sources = change_result.get("_section_sources", {})
    _failed = [s for s in _REQUIRED if _section_sources.get(s, "demo") != "gee"]
    if _failed:
        raise RuntimeError(
            f"{ws_id}: Required live sections failed GEE: {', '.join(_failed)}. "
            "Stopping immediately to avoid contaminating Open Mode JSON."
        )

    # -- NDVI timeseries (app.py L667-669) -------------------------------------
    # geometry=None -- uses default 5 km buffer internally (same as app.py).
    logger.info("[4/5] NDVI timeseries (%d-%d)...", start_yr, end_yr)
    t0 = time.perf_counter()
    ndvi_ts = generate_ndvi_timeseries(lat, lon, start_yr, end_yr)
    if not ndvi_ts:
        raise RuntimeError(
            f"{ws_id}: NDVI timeseries returned no data. "
            "Stopping to avoid overwriting data with empty results."
        )
    logger.info(
        "  NDVI timeseries OK -- %d years (%.1f s).",
        len(ndvi_ts), time.perf_counter() - t0,
    )

    # -- Water timeseries (app.py L672-674) ------------------------------------
    # geometry=None -- uses default 5 km buffer internally (same as app.py).
    logger.info("[5/5] Water timeseries (%d-%d)...", start_yr, end_yr)
    t0 = time.perf_counter()
    water_ts = generate_water_timeseries(lat, lon, start_yr, end_yr)
    if not water_ts:
        raise RuntimeError(
            f"{ws_id}: Water timeseries returned no data. "
            "Stopping to avoid overwriting data with empty results."
        )
    logger.info(
        "  Water timeseries OK -- %d years (%.1f s).",
        len(water_ts), time.perf_counter() - t0,
    )

    # -- Health score (app.py L691) --------------------------------------------
    health = calculate_watershed_health(change_result, ndvi_ts)

    veg = change_result.get("vegetation", {})
    wat = change_result.get("water", {})
    ero = change_result.get("erosion", {})

    logger.info(
        "  NDVI change=%.4f | water_change_pct=%.1f | erosion_reduction=%.1f%%",
        veg.get("change", 0),
        wat.get("change_percent", 0),
        ero.get("reduction_percent", 0),
    )
    logger.info(
        "  Health score=%d (%s)",
        health.get("total_score", 0),
        health.get("grade", "?"),
    )

    return {
        "watershed_id":   ws_id,
        "generated_at":   datetime.utcnow().isoformat() + "Z",
        "analysis_period": {
            "before": before_dates,
            "after":  after_dates,
        },
        # -- SYNCHRONIZED FIELDS -----------------------------------------------
        "change_result": {
            "vegetation": change_result.get("vegetation", {}),
            "water":      change_result.get("water", {}),
            "erosion":    change_result.get("erosion", {}),
        },
        "health_score": {
            "total_score":          health.get("total_score"),
            "grade":                health.get("grade"),
            "grade_emoji":          health.get("grade_emoji"),
            "vegetation_score":     health.get("vegetation_score"),
            "water_score":          health.get("water_score"),
            "erosion_score":        health.get("erosion_score"),
            "sustainability_score": health.get("sustainability_score"),
            "recommendations":      health.get("recommendations", []),
        },
        "ndvi_timeseries":  ndvi_ts,
        "water_timeseries": water_ts,
        # -- METADATA ----------------------------------------------------------
        "_section_sources": _section_sources,
        "_source":          change_result.get("_source", "unknown"),
        "_gee_metadata": {
            "before_scenes_raw":   before_meta.get("images_before_filter", 0),
            "before_scenes_clean": before_meta.get("images_after_filter",  0),
            "after_scenes_raw":    after_meta.get("images_before_filter",  0),
            "after_scenes_clean":  after_meta.get("images_after_filter",   0),
        },
    }


# =============================================================================
# MERGE INTO OPEN MODE JSON
# =============================================================================

def _merge_into_open_mode(
    ws_id:      str,
    live:       Dict[str, Any],
    change_all: Dict[str, Any],
    health_all: Dict[str, Any],
    ndvi_all:   Dict[str, Any],
    water_all:  Dict[str, Any],
) -> None:
    """
    Merge only SYNCHRONIZED fields from `live` into the four Open Mode
    JSON dicts (in-place).  OPEN-ONLY fields are preserved exactly.
    """
    live_veg = live["change_result"]["vegetation"]
    live_wat = live["change_result"]["water"]
    live_ero = live["change_result"]["erosion"]
    live_hs  = live["health_score"]

    # -- change_data.json ------------------------------------------------------
    existing_cd = change_all.get(ws_id, {})

    # SYNCHRONIZED: vegetation
    existing_cd["vegetation"] = {
        "ndvi_before":       live_veg.get("ndvi_before"),
        "ndvi_after":        live_veg.get("ndvi_after"),
        "change":            live_veg.get("change"),
        "improved_area_ha":  live_veg.get("improved_area_ha"),
        "declined_area_ha":  live_veg.get("declined_area_ha"),
        "unchanged_area_ha": live_veg.get("unchanged_area_ha"),
        "percent_improved":  live_veg.get("percent_improved"),
    }

    # SYNCHRONIZED: water core fields; OPEN-ONLY fields preserved
    existing_wat = existing_cd.get("water", {})
    existing_cd["water"] = {
        "area_before_ha":  live_wat.get("area_before_ha"),
        "area_after_ha":   live_wat.get("area_after_ha"),
        "change_ha":       live_wat.get("change_ha"),
        "change_percent":  live_wat.get("change_percent"),
        # OPEN-ONLY -- not computed by Live Mode; preserved from existing JSON
        "new_water_bodies":         existing_wat.get("new_water_bodies", 0),
        "months_with_water_before": existing_wat.get("months_with_water_before", 0),
        "months_with_water_after":  existing_wat.get("months_with_water_after",  0),
    }

    # SYNCHRONIZED: erosion
    existing_cd["erosion"] = {
        "high_risk_before_ha": live_ero.get("high_risk_before_ha"),
        "high_risk_after_ha":  live_ero.get("high_risk_after_ha"),
        "reduction_percent":   live_ero.get("reduction_percent"),
        "classes_before":      live_ero.get("classes_before", {}),
        "classes_after":       live_ero.get("classes_after", {}),
    }

    # OPEN-ONLY: landuse key is untouched
    change_all[ws_id] = existing_cd

    # -- health_scores.json ----------------------------------------------------
    health_all[ws_id] = {
        "total_score":          live_hs["total_score"],
        "grade":                live_hs["grade"],
        "grade_emoji":          live_hs["grade_emoji"],
        "vegetation_score":     live_hs["vegetation_score"],
        "water_score":          live_hs["water_score"],
        "erosion_score":        live_hs["erosion_score"],
        "sustainability_score": live_hs["sustainability_score"],
        "recommendations":      live_hs["recommendations"],
    }

    # -- ndvi_timeseries.json --------------------------------------------------
    ndvi_all[ws_id] = live["ndvi_timeseries"]

    # -- water_timeseries.json -------------------------------------------------
    water_all[ws_id] = live["water_timeseries"]


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    t_total = time.perf_counter()

    # -- GEE init --------------------------------------------------------------
    _init_gee()

    # -- Load watershed list ---------------------------------------------------
    watersheds: List[Dict[str, Any]] = _load_json(SAMPLE_WS_PATH)
    logger.info("Loaded %d watersheds from sample_watersheds.json.", len(watersheds))

    # -- Load existing Open Mode JSON files ------------------------------------
    change_all  = _load_json(CHANGE_DATA_PATH)
    health_all  = _load_json(HEALTH_SCORES_PATH)
    ndvi_all    = _load_json(NDVI_TS_PATH)
    water_all   = _load_json(WATER_TS_PATH)

    # -- Create timestamped backups BEFORE any modification --------------------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("Creating backups (timestamp=%s)...", ts)
    _backup_json_files(ts)

    # -- Run Live pipeline -- one execution per watershed, stop on any failure -
    snapshot: Dict[str, Any] = {
        "_meta": {
            "generated_at":   datetime.utcnow().isoformat() + "Z",
            "script":         "data/generate_open_mode_from_live.py",
            "note": (
                "Validation artifact only. Not required at runtime. "
                "Added to .gitignore."
            ),
        }
    }

    for ws in watersheds:
        ws_id = ws["id"]
        logger.info("\n>>> Starting watershed: %s\n", ws_id)
        t_ws = time.perf_counter()
        try:
            live_result = _run_one_watershed(ws)
        except Exception as exc:
            logger.error(
                "FATAL: Watershed %s failed: %s\n"
                "Stopping immediately. No JSON files have been modified yet.",
                ws_id, exc,
            )
            sys.exit(1)

        snapshot[ws_id] = live_result
        logger.info(
            "<<< Watershed %s done in %.1f s.\n",
            ws_id, time.perf_counter() - t_ws,
        )

    # -- Save snapshot first -- before touching any Open Mode JSON -------------
    logger.info("Saving live_snapshot.json...")
    _save_json(SNAPSHOT_PATH, snapshot)
    logger.info("Snapshot saved: %s", SNAPSHOT_PATH)

    # -- Merge into Open Mode JSON files ---------------------------------------
    logger.info("\nMerging synchronized fields into Open Mode JSON files...")
    for ws in watersheds:
        ws_id = ws["id"]
        _merge_into_open_mode(
            ws_id, snapshot[ws_id],
            change_all, health_all, ndvi_all, water_all,
        )
        logger.info("  Merged: %s", ws_id)

    _save_json(CHANGE_DATA_PATH,   change_all)
    _save_json(HEALTH_SCORES_PATH, health_all)
    _save_json(NDVI_TS_PATH,       ndvi_all)
    _save_json(WATER_TS_PATH,      water_all)

    # -- Summary table ---------------------------------------------------------
    print()
    print("=" * 72)
    print(f"{'SYNCHRONIZATION COMPLETE':^72}")
    print("=" * 72)
    print(
        f"{'Watershed':<20} {'NDVI delta':>10} "
        f"{'Water%':>8} {'Erosion%':>10} {'Score':>6} {'Grade':<10}"
    )
    print("-" * 72)
    for ws in watersheds:
        ws_id = ws["id"]
        r  = snapshot[ws_id]
        vg = r["change_result"]["vegetation"]
        wt = r["change_result"]["water"]
        er = r["change_result"]["erosion"]
        hs = r["health_score"]
        print(
            f"{ws_id:<20} "
            f"{vg.get('change', 0):>+10.4f} "
            f"{wt.get('change_percent', 0):>+8.1f} "
            f"{er.get('reduction_percent', 0):>10.1f} "
            f"{hs.get('total_score', 0):>6} "
            f"{hs.get('grade', '?'):<10}"
        )
    print("=" * 72)
    print(f"\nTotal wall-clock time: {time.perf_counter() - t_total:.1f} s")
    print(f"Snapshot : {SNAPSHOT_PATH}")
    print(f"Backups  : {os.path.join(BACKUPS_DIR, ts)}")
    print("\nRun local validator next (no GEE calls):")
    print("  python data/validate_open_vs_live.py")


if __name__ == "__main__":
    main()
