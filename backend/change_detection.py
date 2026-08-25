"""
backend/change_detection.py
===========================
Before/after change detection for AquaVeda watershed monitoring.

All public functions degrade gracefully when GEE is unavailable:
- They return {'success': False, ...} instead of raising exceptions.
- generate_change_summary() falls back to demo data (data/change_data.json)
  for any section that fails.

Output format of generate_change_summary() matches data/change_data.json
exactly so the dashboard can swap live and demo data transparently.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

# -- Google Earth Engine -------------------------------------------------------
try:
    import ee
    _EE_OK = True
except ImportError:
    ee = None
    _EE_OK = False

# -- Project indices module ----------------------------------------------------
try:
    from backend.indices import (
        calculate_ndvi,
        calculate_ndwi,
    )
    _INDICES_OK = True
except ImportError:
    _INDICES_OK = False

# -- Watershed erosion module --------------------------------------------------
try:
    from backend.watershed import calculate_erosion_risk
    _WATERSHED_OK = True
except ImportError:
    _WATERSHED_OK = False

# -- GEE engine ----------------------------------------------------------------
try:
    from backend.gee_engine import get_sentinel2_image, cache_gee_result, load_cached_result
    _ENGINE_OK = True
except ImportError:
    _ENGINE_OK = False

logger = logging.getLogger(__name__)

_DEMO_CHANGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "change_data.json",
)

# Pixel area image helper (lazily initialised)
_PIXEL_AREA: Optional["ee.Image"] = None


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _ee_ready() -> bool:
    if not _EE_OK or ee is None:
        return False
    try:
        return bool(ee.data.is_initialized())
    except Exception:
        return False


def _pixel_area_image() -> "ee.Image":
    global _PIXEL_AREA
    if _PIXEL_AREA is None:
        _PIXEL_AREA = ee.Image.pixelArea()
    return _PIXEL_AREA


def _area_ha(mask: "ee.Image", geometry: "ee.Geometry", scale: int = 10) -> float:
    """Return area in hectares where mask==1 over geometry."""
    result = (
        mask.multiply(_pixel_area_image())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=scale,
            maxPixels=1e9,
        )
        .getInfo()
    )
    # Key may vary depending on the band name; grab the first numeric value
    for v in result.values():
        if v is not None:
            return round(float(v) / 10_000, 2)
    return 0.0


def _mean_value(image: "ee.Image", geometry: "ee.Geometry", scale: int = 10) -> Optional[float]:
    """Return the spatial mean of image over geometry."""
    result = (
        image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=scale,
            maxPixels=1e9,
        )
        .getInfo()
    )
    for v in result.values():
        if v is not None:
            return round(float(v), 4)
    return None


def _load_demo(watershed_id: Optional[str] = None) -> Dict[str, Any]:
    """Return demo change data dict, optionally scoped to one watershed."""
    try:
        with open(_DEMO_CHANGE_PATH, "r", encoding="utf-8") as fh:
            all_data = json.load(fh)
        if watershed_id and watershed_id in all_data:
            return all_data[watershed_id]
        # Return first entry as generic fallback
        return next(iter(all_data.values())) if all_data else {}
    except Exception as exc:
        logger.error("_load_demo: could not load change_data.json -- %s", exc)
        return {}


# =============================================================================
# 1. VEGETATION CHANGE (NDVI)
# =============================================================================

def detect_vegetation_change(
    before_image: "ee.Image",
    after_image: "ee.Image",
    geometry: "ee.Geometry",
) -> Dict[str, Any]:
    """
    Detect vegetation change between two Sentinel-2 composites using NDVI.

    Computes per-pixel NDVI delta, classifies pixels into five change
    categories, and measures the area (hectares) in each category.

    Change thresholds
    -----------------
    > +0.15  : Significant improvement  (active revegetation, planting success)
    +0.05 .. +0.15 : Moderate improvement
    -0.05 .. +0.05 : No significant change
    -0.15 .. -0.05 : Moderate decline
    < -0.15 : Significant decline        (land degradation, deforestation)

    Args:
        before_image : Sentinel-2 SR ee.Image for the baseline period.
        after_image  : Sentinel-2 SR ee.Image for the current period.
        geometry     : AOI (ee.Geometry) used for statistics and area calc.

    Returns:
        dict with keys:
          ndvi_before, ndvi_after, change    : float means
          improved_area_ha, declined_area_ha,
          unchanged_area_ha                  : float hectares
          percent_improved                   : float 0-100
          change_image                       : ee.Image (1-band 'ndvi_change')
          success                            : bool
    """
    if not _ee_ready() or before_image is None or after_image is None or geometry is None:
        return {"success": False, "error": "GEE not available or missing inputs"}

    try:
        # -- Compute NDVI for both periods ------------------------------------
        ndvi_before = calculate_ndvi(before_image)
        ndvi_after  = calculate_ndvi(after_image)

        if ndvi_before is None or ndvi_after is None:
            return {"success": False, "error": "NDVI calculation failed"}

        # -- Change image -----------------------------------------------------
        change = ndvi_after.subtract(ndvi_before).rename("ndvi_change").clip(geometry)

        # -- Area per change category -----------------------------------------
        sig_improve   = change.gt(0.15)
        mod_improve   = change.gt(0.05).And(change.lte(0.15))
        no_change     = change.gte(-0.05).And(change.lte(0.05))
        mod_decline   = change.lt(-0.05).And(change.gte(-0.15))
        sig_decline   = change.lt(-0.15)

        improved = sig_improve.Or(mod_improve)
        declined = mod_decline.Or(sig_decline)
        unchanged = no_change

        area_img = ee.Image.cat([
            improved.multiply(_pixel_area_image()).rename("improved_area_m2"),
            declined.multiply(_pixel_area_image()).rename("declined_area_m2"),
            unchanged.multiply(_pixel_area_image()).rename("unchanged_area_m2")
        ])

        area_stats = area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9,
            bestEffort=True
        ).getInfo()

        improved_ha   = round(area_stats.get("improved_area_m2", 0) / 10000, 2)
        declined_ha   = round(area_stats.get("declined_area_m2", 0) / 10000, 2)
        unchanged_ha  = round(area_stats.get("unchanged_area_m2", 0) / 10000, 2)
        total_ha      = improved_ha + declined_ha + unchanged_ha

        percent_improved = (
            round(improved_ha / total_ha * 100, 1) if total_ha > 0 else 0.0
        )

        # -- Scalar means -----------------------------------------------------
        ndvi_img = ee.Image.cat([
            ndvi_before.rename("ndvi_before"),
            ndvi_after.rename("ndvi_after")
        ])

        ndvi_stats = ndvi_img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9,
            bestEffort=True
        ).getInfo()

        ndvi_before_mean = round(ndvi_stats.get("ndvi_before", 0.0), 3)
        ndvi_after_mean  = round(ndvi_stats.get("ndvi_after", 0.0), 3)
        change_mean      = round(ndvi_after_mean - ndvi_before_mean, 4)

        logger.info(
            "detect_vegetation_change: NDVI %.3f -> %.3f (delta %.3f), "
            "improved=%.1f ha, declined=%.1f ha",
            ndvi_before_mean, ndvi_after_mean, change_mean,
            improved_ha, declined_ha,
        )

        return {
            "ndvi_before":      ndvi_before_mean,
            "ndvi_after":       ndvi_after_mean,
            "change":           change_mean,
            "improved_area_ha": improved_ha,
            "declined_area_ha": declined_ha,
            "unchanged_area_ha": unchanged_ha,
            "percent_improved": percent_improved,
            "change_image":     change,       # ee.Image for map overlay
            "success":          True,
        }

    except Exception as exc:
        logger.error("detect_vegetation_change failed: %s", exc)
        return {"success": False, "error": str(exc)}


# =============================================================================
# 2. WATER BODY CHANGE (NDWI)
# =============================================================================

def detect_water_change(
    before_image: "ee.Image",
    after_image: "ee.Image",
    geometry: "ee.Geometry",
    ndwi_threshold: float = 0.0,
) -> Dict[str, Any]:
    """
    Detect water-body area change using NDWI binary masks.

    Pixels with NDWI > ndwi_threshold are classified as open water.
    New water = was dry before, wet after.
    Lost water = was wet before, dry after.

    Args:
        before_image    : Baseline Sentinel-2 SR image.
        after_image     : Current Sentinel-2 SR image.
        geometry        : AOI geometry.
        ndwi_threshold  : Detection threshold (default 0.0).

    Returns:
        dict with keys:
          area_before_ha, area_after_ha : float
          change_ha, change_percent     : float
          new_water_ha, lost_water_ha   : float
          success                       : bool
    """
    if not _ee_ready() or before_image is None or after_image is None or geometry is None:
        return {"success": False, "error": "GEE not available or missing inputs"}

    try:
        ndwi_before = calculate_ndwi(before_image)
        ndwi_after  = calculate_ndwi(after_image)

        if ndwi_before is None or ndwi_after is None:
            return {"success": False, "error": "NDWI calculation failed"}

        # Binary water masks
        water_before = ndwi_before.gt(ndwi_threshold)
        water_after  = ndwi_after.gt(ndwi_threshold)
        new_water    = water_before.Not().And(water_after)
        lost_water   = water_before.And(water_after.Not())

        water_area_img = ee.Image.cat([
            water_before.multiply(_pixel_area_image()).rename("water_before_area_m2"),
            water_after.multiply(_pixel_area_image()).rename("water_after_area_m2"),
            new_water.multiply(_pixel_area_image()).rename("new_water_area_m2"),
            lost_water.multiply(_pixel_area_image()).rename("lost_water_area_m2")
        ])

        water_stats = water_area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9,
            bestEffort=True
        ).getInfo()

        area_before_ha = round(water_stats.get("water_before_area_m2", 0) / 10000, 2)
        area_after_ha  = round(water_stats.get("water_after_area_m2", 0) / 10000, 2)
        new_water_ha   = round(water_stats.get("new_water_area_m2", 0) / 10000, 2)
        lost_water_ha  = round(water_stats.get("lost_water_area_m2", 0) / 10000, 2)

        change_ha = round(area_after_ha - area_before_ha, 2)
        change_percent = (
            round(change_ha / area_before_ha * 100, 1) if area_before_ha > 0 else 0.0
        )

        logger.info(
            "detect_water_change: %.2f ha -> %.2f ha (%.1f%%), "
            "new=%.2f ha, lost=%.2f ha",
            area_before_ha, area_after_ha, change_percent,
            new_water_ha, lost_water_ha,
        )

        return {
            "area_before_ha":  area_before_ha,
            "area_after_ha":   area_after_ha,
            "change_ha":       change_ha,
            "change_percent":  change_percent,
            "new_water_ha":    new_water_ha,
            "lost_water_ha":   lost_water_ha,
            "success":         True,
        }

    except Exception as exc:
        logger.error("detect_water_change failed: %s", exc)
        return {"success": False, "error": str(exc)}


# =============================================================================
# 3. LAND-USE CHANGE (K-Means)
# =============================================================================

def detect_landuse_change(
    before_image: "ee.Image",
    after_image: "ee.Image",
    geometry: "ee.Geometry",
    n_classes: int = 5,
) -> Dict[str, Any]:
    """
    Unsupervised land-use change detection using GEE's weka K-Means clusterer.

    Both images are classified with the SAME clusterer (trained on the before
    image) so that cluster IDs are directly comparable across time periods.

    Note: Cluster IDs (0-4) have no inherent semantic labels ('Water',
    'Vegetation', etc.) — they are spectral groupings. For a hackathon
    prototype the raw pixel counts per class show structural land-use shift
    without requiring labelled training data.

    Args:
        before_image : Baseline Sentinel-2 SR image (used to train clusterer).
        after_image  : Current Sentinel-2 SR image.
        geometry     : AOI geometry.
        n_classes    : Number of K-Means clusters (default 5).

    Returns:
        dict with keys:
          before_class_counts : {class_id: pixel_count}
          after_class_counts  : {class_id: pixel_count}
          before_classified   : ee.Image
          after_classified    : ee.Image
          clusterer_trained   : True
          success             : bool
    """
    if not _ee_ready() or before_image is None or after_image is None or geometry is None:
        return {"success": False, "error": "GEE not available or missing inputs"}

    try:
        bands = ["B2", "B3", "B4", "B8", "B11", "B12"]

        # -- Train clusterer on baseline image --------------------------------
        training = before_image.select(bands).sample(
            region=geometry, scale=10, numPixels=5000, seed=42
        )
        clusterer = ee.Clusterer.wekaKMeans(n_classes).train(training)

        # -- Classify both images ---------------------------------------------
        before_classified = (
            before_image.select(bands).cluster(clusterer).rename("class")
        )
        after_classified = (
            after_image.select(bands).cluster(clusterer).rename("class")
        )

        # -- Count pixels per class (scaled at 30 m for speed) ---------------
        def _class_counts(classified_image: "ee.Image") -> Dict[int, int]:
            counts: Dict[int, int] = {}
            for i in range(n_classes):
                mask = classified_image.eq(i)
                area = mask.multiply(_pixel_area_image()).reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=geometry,
                    scale=30,
                    maxPixels=1e9,
                ).getInfo()
                ha = 0.0
                for v in area.values():
                    if v is not None:
                        ha = round(float(v) / 10_000, 1)
                        break
                counts[i] = ha
            return counts

        before_counts = _class_counts(before_classified)
        after_counts  = _class_counts(after_classified)

        logger.info(
            "detect_landuse_change: before=%s, after=%s",
            before_counts, after_counts,
        )

        return {
            "before_class_counts": before_counts,
            "after_class_counts":  after_counts,
            "before_classified":   before_classified,
            "after_classified":    after_classified,
            "n_classes":           n_classes,
            "clusterer_trained":   True,
            "success":             True,
        }

    except Exception as exc:
        logger.error("detect_landuse_change failed: %s", exc)
        return {"success": False, "error": str(exc)}


# =============================================================================
# 4. MASTER PIPELINE
# =============================================================================

def generate_change_summary(
    lat: float,
    lon: float,
    before_dates: Dict[str, str],
    after_dates: Dict[str, str],
    buffer_km: float = 10,
    watershed_id: Optional[str] = None,
    progress_callback=None,
    before_image: Optional["ee.Image"] = None,
    after_image: Optional["ee.Image"] = None,
    geometry: Optional["ee.Geometry"] = None,
) -> Dict[str, Any]:
    import time
    _t_total = time.perf_counter()
    """
    Run the full change-detection pipeline and return a summary dict that
    matches the schema of ``data/change_data.json``.

    Any section that fails (vegetation, water, erosion, landuse) is replaced
    with the corresponding demo data so the dashboard always has something
    to display.

    When all three optional image parameters are supplied, no additional Sentinel-2
    composite fetches are performed.

    Args:
        lat, lon         : Watershed centre (decimal degrees).
        before_dates     : {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}
        after_dates      : Same format for the after period.
        buffer_km        : AOI radius in km (default 10).
        watershed_id     : Key into change_data.json used for demo fallback.
        progress_callback: Optional callable(step: int, total: int, msg: str)
                           so callers can drive an st.progress() bar.
        before_image     : Optional pre-built BEFORE Sentinel-2 composite.
        after_image      : Optional pre-built AFTER Sentinel-2 composite.
        geometry         : Optional shared AOI geometry for the supplied composites.

    Returns:
        dict matching change_data.json schema:
        {
            "vegetation": {...},
            "water":      {...},
            "erosion":    {...},
            "landuse":    {...},
            "_source":    "gee" | "demo" | "mixed",
        }
    """
    demo = _load_demo(watershed_id)
    total_steps = 5
    sources: list[str] = []

    def _progress(step: int, msg: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(step, total_steps, msg)
            except Exception:
                pass
        logger.info("[%d/%d] %s", step, total_steps, msg)

    # -------------------------------------------------------------------------
    # Early exit: GEE unavailable
    # -------------------------------------------------------------------------
    if not _ee_ready() or not _ENGINE_OK:
        logger.warning(
            "generate_change_summary: GEE not ready, returning full demo data."
        )
        demo["_source"] = "demo"
        demo["_section_sources"] = {
            "vegetation": "demo",
            "water":      "demo",
            "erosion":    "demo",
            "landuse":    "demo",
        }
        return demo

    # -------------------------------------------------------------------------
    # Step 1: Obtain Sentinel-2 images
    # -------------------------------------------------------------------------
    # Prefer pre-built composites supplied by app.py. This prevents the
    # expensive s2cloudless pipeline from running a second time.
    if before_image is not None and after_image is not None and geometry is not None:
        _progress(1, "Reusing pre-built BEFORE Sentinel-2 composite...")
        img_before = before_image
        img_after = after_image
        geom = geometry

        logger.info(
            "generate_change_summary: reusing pre-built Sentinel-2 composites "
            "and shared geometry."
        )
    else:
        _progress(1, "Fetching baseline Sentinel-2 image...")
        try:
            img_before, _fetched_geom = get_sentinel2_image(
                lat, lon,
                before_dates.get("start", "2019-01-01"),
                before_dates.get("end",   "2019-12-31"),
                buffer_km,
            )
            geom = geometry if geometry is not None else _fetched_geom
        except Exception as exc:
            logger.error(
                "generate_change_summary: before image fetch failed: %s",
                exc,
            )
            img_before, geom = None, None

        _progress(2, "Fetching current Sentinel-2 image...")
        try:
            img_after, _ = get_sentinel2_image(
                lat, lon,
                after_dates.get("start", "2024-01-01"),
                after_dates.get("end",   "2024-12-31"),
                buffer_km,
            )
        except Exception as exc:
            logger.error(
                "generate_change_summary: after image fetch failed: %s",
                exc,
            )
            img_after = None

    if img_before is None or img_after is None or geom is None:
        logger.warning(
            "generate_change_summary: image fetch failed, returning full demo data."
        )
        demo["_source"] = "demo"
        demo["_section_sources"] = {
            "vegetation": "demo",
            "water":      "demo",
            "erosion":    "demo",
            "landuse":    "demo",
        }
        return demo

    summary: Dict[str, Any] = {}
    # Per-section source tracking — maps section name to "gee" or "demo"
    section_sources: Dict[str, str] = {}

    # -------------------------------------------------------------------------
    # Step 3: Vegetation change
    # -------------------------------------------------------------------------
    _progress(3, "Detecting vegetation change (NDVI)...")
    _t0 = time.perf_counter()
    veg = detect_vegetation_change(img_before, img_after, geom)
    logger.info("CHANGE DETECTION TIMING: vegetation %.2f seconds", time.perf_counter() - _t0)
    if veg.get("success"):
        summary["vegetation"] = {
            "ndvi_before":       veg["ndvi_before"],
            "ndvi_after":        veg["ndvi_after"],
            "change":            veg["change"],
            "improved_area_ha":  veg["improved_area_ha"],
            "declined_area_ha":  veg["declined_area_ha"],
            "unchanged_area_ha": veg["unchanged_area_ha"],
            "percent_improved":  veg["percent_improved"],
        }
        sources.append("gee")
        section_sources["vegetation"] = "gee"
    else:
        logger.warning("Vegetation section failed, using demo data.")
        summary["vegetation"] = demo.get("vegetation", {})
        sources.append("demo")
        section_sources["vegetation"] = "demo"

    # -------------------------------------------------------------------------
    # Step 4: Water change
    # -------------------------------------------------------------------------
    _progress(4, "Detecting water body change (NDWI)...")
    _t0 = time.perf_counter()
    water = detect_water_change(img_before, img_after, geom)
    logger.info("CHANGE DETECTION TIMING: water %.2f seconds", time.perf_counter() - _t0)
    if water.get("success"):
        summary["water"] = {
            "area_before_ha":  water["area_before_ha"],
            "area_after_ha":   water["area_after_ha"],
            "change_ha":       water["change_ha"],
            "change_percent":  water["change_percent"],
            "new_water_bodies": 0,              # Satellite count not impl. yet
            # NOTE: months_with_water_* are patched from demo JSON (change_data.json)
            # because multi-month water persistence is not computed from GEE in this
            # version. When this live implementation is added, remove this patch and
            # update the _source logic accordingly.
            "months_with_water_before": demo.get("water", {}).get("months_with_water_before", 0),
            "months_with_water_after":  demo.get("water", {}).get("months_with_water_after",  0),
        }
        sources.append("gee")
        section_sources["water"] = "gee"
    else:
        logger.warning("Water section failed, using demo data.")
        summary["water"] = demo.get("water", {})
        sources.append("demo")
        section_sources["water"] = "demo"

    # -------------------------------------------------------------------------
    # Step 5: Erosion risk
    # -------------------------------------------------------------------------
    _progress(5, "Calculating erosion risk change...")
    erosion_section: Dict[str, Any] = {}
    if _WATERSHED_OK:
        try:
            _t0 = time.perf_counter()
            er_before = calculate_erosion_risk(geom, calculate_ndvi(img_before))
            logger.info("CHANGE DETECTION TIMING: erosion_before %.2f seconds", time.perf_counter() - _t0)
            
            _t0 = time.perf_counter()
            er_after  = calculate_erosion_risk(geom, calculate_ndvi(img_after))
            logger.info("CHANGE DETECTION TIMING: erosion_after %.2f seconds", time.perf_counter() - _t0)

            if er_before.get("success") and er_after.get("success"):
                cb = er_before["class_areas"]
                ca = er_after["class_areas"]
                high_before = cb.get("High", 0) + cb.get("Very High", 0)
                high_after  = ca.get("High", 0) + ca.get("Very High", 0)
                reduction_pct = (
                    round((high_before - high_after) / high_before * 100, 1)
                    if high_before > 0 else 0.0
                )
                erosion_section = {
                    "high_risk_before_ha": high_before,
                    "high_risk_after_ha":  high_after,
                    "reduction_percent":   reduction_pct,
                    "classes_before":      cb,
                    "classes_after":       ca,
                }
                sources.append("gee")
                section_sources["erosion"] = "gee"
            else:
                erosion_section = demo.get("erosion", {})
                sources.append("demo")
                section_sources["erosion"] = "demo"

        except Exception as exc:
            logger.error("Erosion section failed: %s", exc)
            erosion_section = demo.get("erosion", {})
            sources.append("demo")
            section_sources["erosion"] = "demo"
    else:
        erosion_section = demo.get("erosion", {})
        sources.append("demo")
        section_sources["erosion"] = "demo"

    summary["erosion"] = erosion_section

    # Land-use: always use demo data in this version.
    # K-Means land-use classification requires many additional GEE API calls
    # and is not yet implemented in the live pipeline.  This field will be
    # replaced with a live result in a future phase, at which point the
    # _source flag will need updating to account for it.
    summary["landuse"] = demo.get("landuse", {})
    section_sources["landuse"] = "demo"  # intentionally always demo in this version

    # Aggregate source tag (for logging/debugging)
    unique_sources = set(sources)
    summary["_source"] = (
        "gee"   if unique_sources == {"gee"}  else
        "demo"  if unique_sources == {"demo"} else
        "mixed"
    )
    # Per-section source map — used by app.py to validate core sections individually
    summary["_section_sources"] = section_sources

    # -------------------------------------------------------------------------
    # Cache the result for future runs
    # -------------------------------------------------------------------------
    if _ENGINE_OK:
        try:
            cache_key = (
                f"change_summary_{lat:.4f}_{lon:.4f}_"
                f"{before_dates.get('start','')}_{after_dates.get('start','')}"
            )
            # Strip non-serialisable ee.Image objects before caching
            cacheable = {}
            for k, v in summary.items():
                if _EE_OK and ee and isinstance(v, ee.Image):
                    continue
                cacheable[k] = v
            cache_gee_result(cache_key, cacheable)
        except Exception as exc:
            logger.warning("generate_change_summary: caching failed: %s", exc)

    logger.info("CHANGE DETECTION TIMING: total %.2f seconds", time.perf_counter() - _t_total)
    logger.info(
        "generate_change_summary: done (source=%s).", summary["_source"]
    )
    return summary
