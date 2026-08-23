"""
backend/gee_engine.py
=====================
Google Earth Engine (GEE) satellite image retrieval engine for AquaVeda.

All public functions degrade gracefully when GEE is unavailable:
- They return (None, None) or {} instead of raising exceptions.
- Callers can check the first return value for None to fall back to demo data.

Collections used:
  Sentinel-2   : COPERNICUS/S2_SR_HARMONIZED   (10-20 m, multispectral)
  Landsat-8    : LANDSAT/LC08/C02/T1_L2         (30 m, surface reflectance)
  SRTM DEM     : USGS/SRTMGL1_003              (30 m elevation)
  CHIRPS Rain  : UCSB-CHG/CHIRPS/DAILY          (daily rainfall)
"""

import hashlib
import json
import logging
import os
import pickle
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

# ── Third-party / GEE ────────────────────────────────────────────────────────
try:
    import ee
    import geemap
    _GEE_IMPORT_OK = True
except ImportError:
    ee = None
    geemap = None
    _GEE_IMPORT_OK = False

# ── Project config ────────────────────────────────────────────────────────────
try:
    from config import (
        EE_PROJECT_ID,
        NDVI_VIS, NDWI_VIS, SAVI_VIS, SLOPE_VIS,
        GEE_AVAILABLE,
    )
except ImportError:
    EE_PROJECT_ID = None
    NDVI_VIS = {"min": -0.2, "max": 0.8, "palette": ["red", "yellow", "green"]}
    NDWI_VIS = {"min": -0.5, "max": 0.5, "palette": ["brown", "white", "blue"]}
    SAVI_VIS  = {"min": -0.2, "max": 0.8, "palette": ["red", "orange", "green"]}
    SLOPE_VIS = {"min": 0,    "max": 45,  "palette": ["green", "yellow", "red"]}
    GEE_AVAILABLE = False

# ── Module-level logger ───────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


def _ee_ready() -> bool:
    """Check if Google Earth Engine is initialized and ready to execute queries.

    Returns True only when the ``ee`` package is importable **and** a credential
    object has been attached (i.e. ``ee.Initialize()`` has been called
    successfully in this process).  Safe to call at any time — never raises.
    """
    if not _GEE_IMPORT_OK or ee is None:
        return False
    try:
        # ee.data._credentials is set by Initialize(); None/missing means not ready
        return ee.data._credentials is not None
    except Exception:
        return False


# ── Fallback monthly rainfall sample (used when GEE unavailable) ──────────────
_SAMPLE_MONTHLY_RAIN = [
    {"month": 1,  "month_name": "Jan", "rainfall_mm": 4},
    {"month": 2,  "month_name": "Feb", "rainfall_mm": 6},
    {"month": 3,  "month_name": "Mar", "rainfall_mm": 10},
    {"month": 4,  "month_name": "Apr", "rainfall_mm": 15},
    {"month": 5,  "month_name": "May", "rainfall_mm": 30},
    {"month": 6,  "month_name": "Jun", "rainfall_mm": 95},
    {"month": 7,  "month_name": "Jul", "rainfall_mm": 145},
    {"month": 8,  "month_name": "Aug", "rainfall_mm": 120},
    {"month": 9,  "month_name": "Sep", "rainfall_mm": 70},
    {"month": 10, "month_name": "Oct", "rainfall_mm": 25},
    {"month": 11, "month_name": "Nov", "rainfall_mm": 8},
    {"month": 12, "month_name": "Dec", "rainfall_mm": 4},
]


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _is_gee_ready() -> bool:
    """Return True only when the GEE API is imported and initialised."""
    if not _GEE_IMPORT_OK or ee is None:
        logger.warning("earthengine-api not installed — skipping GEE call.")
        return False
    try:
        # Lightweight call to verify the session is authenticated.
        ee.Number(1).getInfo()
        return True
    except Exception as exc:
        logger.warning("GEE not initialised: %s", exc)
        return False


def _make_geometry(lat: float, lon: float, buffer_m: float) -> "ee.Geometry":
    """
    Create a buffered ee.Geometry around the given lat/lon.

    NOTE: GEE uses [lon, lat] coordinate order (GeoJSON convention).
    """
    point = ee.Geometry.Point([lon, lat])  # ← GEE order: [lon, lat]
    return point.buffer(buffer_m)


# =============================================================================
# 1. SENTINEL-2 S2CLOUDLESS PREPROCESSING PIPELINE
# =============================================================================
#
# Pipeline follows the official GEE community tutorial:
#   https://developers.google.com/earth-engine/tutorials/community/sentinel-2-s2cloudless
#
# Step A: get_s2_collection()        -- raw S2_SR_HARMONIZED, bounds+date filter
# Step B: join_cloud_probability()   -- join COPERNICUS/S2_CLOUD_PROBABILITY
# Step C: _apply_cloud_shadow_mask() -- per-image pixel-level cloud+shadow mask
# Step D: create_s2_composite()      -- full pipeline -> composite + metadata
#
# Collections used:
#   COPERNICUS/S2_SR_HARMONIZED       -- Sentinel-2 L2A surface reflectance
#   COPERNICUS/S2_CLOUD_PROBABILITY   -- s2cloudless ML cloud probability (0-100)
#
# Thresholds (defaults match GEE community tutorial):
#   _CLOUD_FILTER        = 60 (%) -- scene-level metadata pre-filter
#   _CLOUD_PROB_THRESH   = 65 (%) -- pixel is cloudy if prob > this value
#   _NIR_DARK_THRESH     = 0.15   -- NIR reflectance below this = shadow candidate
#   _CLOUD_PROJ_DIST     = 1  km  -- distance to project cloud shadows downhill
#   _BUFFER_M            = 50 m   -- dilation buffer around cloud/shadow masks
#   _MIN_VALID_IMAGES    = 1      -- minimum cloud-free scenes for a valid composite

class InsufficientImageryError(RuntimeError):
    """Raised when not enough cloud-free Sentinel-2 images are available."""

# S2cloudless pipeline constants
_S2_COLLECTION      = "COPERNICUS/S2_SR_HARMONIZED"
_S2_CLOUD_PROB_COL  = "COPERNICUS/S2_CLOUD_PROBABILITY"
_CLOUD_FILTER       = 60    # % scene-level pre-filter
_CLOUD_PROB_THRESH  = 65    # % pixel-level cloud probability threshold
_NIR_DARK_THRESH    = 0.15  # NIR reflectance threshold for shadow detection
_CLOUD_PROJ_DIST    = 1     # km distance to project cloud shadows
_BUFFER_M           = 50    # m dilation buffer around cloud/shadow masks
_MIN_VALID_IMAGES   = 1     # minimum cloud-free scenes required


def get_s2_collection(
    aoi: "ee.Geometry",
    start_date: str,
    end_date: str,
    cloud_filter: int = _CLOUD_FILTER,
) -> "ee.ImageCollection":
    """
    Step A: Raw COPERNICUS/S2_SR_HARMONIZED collection filtered by AOI,
    date range, and scene-level CLOUDY_PIXEL_PERCENTAGE < cloud_filter.

    This is a metadata-level filter only. Pixel-level masking is done in
    _apply_cloud_shadow_mask() after joining the cloud probability data.

    Args:
        aoi          : ee.Geometry for spatial filtering.
        start_date   : ISO date string, e.g. "2019-01-01".
        end_date     : ISO date string, e.g. "2019-12-31".
        cloud_filter : Maximum scene cloud cover (%) to include (default 60).

    Returns:
        ee.ImageCollection filtered to AOI, date range, and cloud cover.
    """
    return (
        ee.ImageCollection(_S2_COLLECTION)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cloud_filter))
    )


def join_cloud_probability(
    s2_col: "ee.ImageCollection",
    aoi: "ee.Geometry",
    start_date: str,
    end_date: str,
) -> "ee.ImageCollection":
    """
    Step B: Join COPERNICUS/S2_CLOUD_PROBABILITY to each S2 image via
    system:index (the shared granule identifier).

    After this join, each image in the returned collection has a
    'cloud_probability' property containing its matched cloud-probability image.

    Args:
        s2_col     : ee.ImageCollection from get_s2_collection() (Step A).
        aoi        : Same AOI geometry used in Step A.
        start_date : Same start date used in Step A.
        end_date   : Same end date used in Step A.

    Returns:
        ee.ImageCollection where each image has a 'cloud_probability' property.

    Collection:
        COPERNICUS/S2_CLOUD_PROBABILITY -- 10 m cloud probability (0-100 %)
        generated by the s2cloudless ML model, matched to S2_SR_HARMONIZED
        via system:index (granule acquisition ID).
    """
    s2_cloud_prob = (
        ee.ImageCollection(_S2_CLOUD_PROB_COL)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
    )
    join = ee.Join.saveFirst("cloud_probability")
    condition = ee.Filter.equals(
        leftField="system:index",
        rightField="system:index",
    )
    return ee.ImageCollection(join.apply(s2_col, s2_cloud_prob, condition))


def _apply_cloud_shadow_mask(
    image: "ee.Image",
    cloud_prob_thresh: int = _CLOUD_PROB_THRESH,
    nir_dark_thresh: float = _NIR_DARK_THRESH,
    cloud_proj_dist: float = _CLOUD_PROJ_DIST,
    buffer_m: int = _BUFFER_M,
) -> "ee.Image":
    """
    Step C: Per-image cloud and cloud-shadow masking following s2cloudless.

    Algorithm:
      1. Cloud mask  -- pixels where cloud probability > cloud_prob_thresh.
      2. Shadow mask -- dark NIR pixels within the directional projection of
                        clouds using the scene solar azimuth angle.
      3. Dilation    -- buffer cloud+shadow masks by buffer_m metres to catch
                        edges and penumbra.
      4. UpdateMask  -- mask combined cloud+shadow pixels (they become no-data).

    Args:
        image             : ee.Image with 'cloud_probability' property (Step B).
        cloud_prob_thresh : Cloud probability threshold in % (default 65).
        nir_dark_thresh   : NIR reflectance (<) for shadow candidates (default 0.15).
        cloud_proj_dist   : Shadow projection distance in km (default 1).
        buffer_m          : Dilation buffer in metres (default 50).

    Returns:
        ee.Image with cloud+shadow pixels masked. All bands preserved.
    """
    # 1. Cloud mask from probability band
    cloud_prob = ee.Image(image.get("cloud_probability"))
    is_cloud   = cloud_prob.select("probability").gt(cloud_prob_thresh).rename("clouds")

    # 2. Shadow detection: dark NIR within cloud projection
    nir         = image.select("B8").divide(10000)
    dark_pixels = nir.lt(nir_dark_thresh).rename("dark_pixels")

    shadow_azimuth = ee.Number(90).subtract(
        ee.Number(image.get("MEAN_SOLAR_AZIMUTH_ANGLE"))
    )
    proj_distance_pixels = ee.Number(cloud_proj_dist * 1000 / 10).round()

    cloud_proj = (
        is_cloud
        .directionalDistanceTransform(shadow_azimuth, proj_distance_pixels)
        .reproject(crs=image.select("B8").projection(), scale=100)
        .select("distance")
        .mask()
        .rename("cloud_transform")
    )
    shadows = cloud_proj.And(dark_pixels).rename("shadows")

    # 3. Combine cloud + shadow
    is_cloud_or_shadow = is_cloud.Or(shadows)

    # 4. Dilate mask to capture edges (only if buffer requested)
    if buffer_m > 0:
        is_cloud_or_shadow = (
            is_cloud_or_shadow
            .focal_min(2)
            .focal_max(buffer_m * 2 / 20)
            .reproject(crs=image.select("B8").projection(), scale=20)
            .rename("cloudmask")
        )

    return image.updateMask(is_cloud_or_shadow.Not())


def create_s2_composite(
    aoi: "ee.Geometry",
    start_date: str,
    end_date: str,
    label: str = "",
    cloud_filter: int = _CLOUD_FILTER,
    cloud_prob_thresh: int = _CLOUD_PROB_THRESH,
    nir_dark_thresh: float = _NIR_DARK_THRESH,
    cloud_proj_dist: float = _CLOUD_PROJ_DIST,
    buffer_m: int = _BUFFER_M,
    min_valid_images: int = _MIN_VALID_IMAGES,
) -> Tuple[Optional["ee.Image"], dict]:
    """
    Step D: Full s2cloudless Sentinel-2 preprocessing pipeline.

    Executes Steps A (collection) -> B (cloud prob join) -> C (mask) and
    forms a median composite from the cloud-masked collection.

    Both BEFORE and AFTER composites must use this same function so that
    preprocessing is identical for both periods.

    Args:
        aoi               : ee.Geometry -- watershed area of interest.
        start_date        : ISO date string for period start.
        end_date          : ISO date string for period end.
        label             : Human-readable label, e.g. "Before 2019".
        cloud_filter      : Scene-level CLOUDY_PIXEL_PERCENTAGE threshold (%).
        cloud_prob_thresh : Pixel-level cloud probability threshold (%).
        nir_dark_thresh   : NIR dark-pixel threshold for shadow detection.
        cloud_proj_dist   : Shadow projection distance (km).
        buffer_m          : Cloud/shadow dilation buffer (m).
        min_valid_images  : Minimum cloud-free scenes required.

    Returns:
        (composite, metadata) tuple where:
          composite : ee.Image -- median composite (clipped to AOI).
          metadata  : dict -- satellite acquisition and processing info.

    Raises:
        InsufficientImageryError : if scenes are insufficient after filtering.
        Exception                : re-raises unexpected GEE errors.
    """
    meta: dict = {
        "sensor":                "Sentinel-2",
        "collection":            _S2_COLLECTION,
        "cloud_prob_collection": _S2_CLOUD_PROB_COL,
        "period":                f"{start_date} to {end_date}",
        "label":                 label,
        "cloud_mask":            "s2cloudless pixel-level cloud+shadow mask",
        "cloud_prob_threshold":  cloud_prob_thresh,
        "scene_cloud_filter":    cloud_filter,
        "processing":            "Cloud + cloud-shadow masked median composite",
        "images_before_filter":  0,
        "images_after_filter":   0,
    }

    # Step A
    s2_col   = get_s2_collection(aoi, start_date, end_date, cloud_filter)
    n_before = s2_col.size().getInfo()
    meta["images_before_filter"] = n_before
    logger.info(
        "create_s2_composite [%s]: %d scenes in AOI+date range (%s to %s)",
        label or "unlabelled", n_before, start_date, end_date,
    )

    if n_before == 0:
        raise InsufficientImageryError(
            f"No Sentinel-2 observations found for period ({start_date} to {end_date}). "
            "Check the watershed coordinates and date range."
        )

    # Step B
    s2_with_prob = join_cloud_probability(s2_col, aoi, start_date, end_date)
    n_joined = s2_with_prob.size().getInfo()
    logger.info(
        "create_s2_composite [%s]: %d scenes matched with cloud-probability.",
        label or "unlabelled", n_joined,
    )

    if n_joined == 0:
        raise InsufficientImageryError(
            f"Cloud-probability data could not be joined for period ({start_date} to {end_date}). "
            "COPERNICUS/S2_CLOUD_PROBABILITY may not cover this date range."
        )

    # Step C
    s2_masked = s2_with_prob.map(
        lambda img: _apply_cloud_shadow_mask(
            img,
            cloud_prob_thresh=cloud_prob_thresh,
            nir_dark_thresh=nir_dark_thresh,
            cloud_proj_dist=cloud_proj_dist,
            buffer_m=buffer_m,
        )
    )
    n_after = s2_masked.size().getInfo()
    meta["images_after_filter"] = n_after
    logger.info(
        "create_s2_composite [%s]: %d scenes remain after cloud+shadow masking.",
        label or "unlabelled", n_after,
    )

    if n_after < min_valid_images:
        raise InsufficientImageryError(
            f"Insufficient cloud-free Sentinel-2 imagery for period ({start_date} to {end_date}): "
            f"{n_after} usable scene(s), minimum required is {min_valid_images}. "
            "Try widening the date range or reducing the cloud filter threshold."
        )

    # Step D: Median composite
    composite = s2_masked.median().clip(aoi)
    logger.info(
        "create_s2_composite [%s]: composite created from %d cloud-free scenes.",
        label or "unlabelled", n_after,
    )
    return composite, meta


def get_sentinel2_image(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    buffer_km: float = 10,
) -> Tuple[Optional["ee.Image"], Optional["ee.Geometry"]]:
    """
    Retrieve a cloud-masked Sentinel-2 SR Harmonized composite for the AOI.

    Backward-compatible public API. Internally calls create_s2_composite()
    (the full s2cloudless pipeline) instead of the old CLOUDY_PIXEL_PERCENTAGE
    metadata filter.

    Args:
        lat, lon       : Centre of the area of interest (decimal degrees).
        start_date     : ISO date string, e.g. "2024-01-01".
        end_date       : ISO date string, e.g. "2024-12-31".
        buffer_km      : Radius of the buffered AOI in kilometres (default 10).

    Returns:
        (ee.Image, ee.Geometry) on success, or (None, None) on failure.

    Collection:
        COPERNICUS/S2_SR_HARMONIZED with pixel-level cloud+shadow masking via
        COPERNICUS/S2_CLOUD_PROBABILITY (s2cloudless approach).
    """
    if not _is_gee_ready():
        return None, None

    try:
        geometry  = _make_geometry(lat, lon, buffer_km * 1000)
        composite, meta = create_s2_composite(
            aoi=geometry,
            start_date=start_date,
            end_date=end_date,
            label=f"lat={lat:.4f},lon={lon:.4f}",
        )
        logger.info(
            "get_sentinel2_image: ready (before=%d, after=%d, %s to %s).",
            meta.get("images_before_filter", 0),
            meta.get("images_after_filter",  0),
            start_date, end_date,
        )
        return composite, geometry

    except InsufficientImageryError as exc:
        logger.warning("get_sentinel2_image: %s", exc)
        return None, None

    except Exception as exc:
        logger.error("get_sentinel2_image failed: %s", exc)
        return None, None




# =============================================================================
# 2. LANDSAT-8 IMAGE
# =============================================================================

def get_landsat8_image(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    buffer_km: float = 10,
) -> Tuple[Optional["ee.Image"], Optional["ee.Geometry"]]:
    """
    Retrieve a cloud-masked, scale-corrected Landsat-8 median composite.

    Args:
        lat, lon       : Centre of the area of interest (decimal degrees).
        start_date     : ISO date string, e.g. "2024-01-01".
        end_date       : ISO date string, e.g. "2024-12-31".
        buffer_km      : Radius of the buffered AOI in kilometres (default 10).

    Returns:
        (ee.Image, ee.Geometry) on success, or (None, None) on failure.

    Collection:
        LANDSAT/LC08/C02/T1_L2 — Collection 2 Tier-1 Level-2 surface reflectance.
        Band mapping:
          SR_B2=Blue, SR_B3=Green, SR_B4=Red, SR_B5=NIR,
          SR_B6=SWIR1, SR_B7=SWIR2
        QA_PIXEL bit 3 = cloud flag.
    """
    if not _is_gee_ready():
        return None, None

    try:
        geometry = _make_geometry(lat, lon, buffer_km * 1000)

        # ── Scale factor correction ──────────────────────────────────────────
        def apply_scale(image: "ee.Image") -> "ee.Image":
            """Apply Collection-2 SR scale factor: DN * 0.0000275 - 0.2."""
            optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
            return image.addBands(optical, overwrite=True)

        # ── Cloud mask using QA_PIXEL ────────────────────────────────────────
        def mask_clouds(image: "ee.Image") -> "ee.Image":
            """Mask pixels where QA_PIXEL bit 3 (cloud) is set."""
            qa = image.select("QA_PIXEL")
            cloud_mask = qa.bitwiseAnd(1 << 3).eq(0)   # bit 3 = cloud
            return image.updateMask(cloud_mask)

        collection = (
            ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
            .filterBounds(geometry)
            .filterDate(start_date, end_date)
            .map(mask_clouds)
            .map(apply_scale)
        )

        count = collection.size().getInfo()
        if count == 0:
            logger.warning(
                "Landsat-8: no images found for (%s, %s) between %s and %s",
                lat, lon, start_date, end_date,
            )
            return None, None

        image = collection.median().clip(geometry)
        logger.info(
            "Landsat-8 composite created from %d images (lat=%.4f, lon=%.4f)",
            count, lat, lon,
        )
        return image, geometry

    except Exception as exc:
        logger.error("get_landsat8_image failed: %s", exc)
        return None, None


# =============================================================================
# 3. ELEVATION / DEM
# =============================================================================

def get_elevation(
    lat: float,
    lon: float,
    buffer_km: float = 10,
) -> Tuple[Optional["ee.Image"], Optional["ee.Geometry"]]:
    """
    Return a clipped SRTM 30-m elevation image and its AOI geometry.

    Args:
        lat, lon  : Centre coordinates (decimal degrees).
        buffer_km : AOI radius in km (default 10).

    Returns:
        (ee.Image, ee.Geometry) — the clipped DEM and the buffered geometry.
        Returns (None, None) if GEE is unavailable or an error occurs.

    Dataset:
        USGS/SRTMGL1_003 — NASA SRTM 1 arc-second (~30 m) global DEM.
        Single band "elevation" in metres.
    """
    if not _is_gee_ready():
        return None, None

    try:
        geometry = _make_geometry(lat, lon, buffer_km * 1000)
        dem = ee.Image("USGS/SRTMGL1_003").clip(geometry)
        logger.info("SRTM DEM clipped for (lat=%.4f, lon=%.4f)", lat, lon)
        return dem, geometry

    except Exception as exc:
        logger.error("get_elevation failed: %s", exc)
        return None, None


def get_slope(lat: float, lon: float, buffer_km: float = 10) -> Tuple[Optional["ee.Image"], Optional["ee.Geometry"]]:
    """
    Get slope image derived from SRTM DEM.
    Returns: (slope_ee_image, geometry) or (None, None) on failure.
    """
    if not _is_gee_ready():
        return None, None

    try:
        dem, geometry = get_elevation(lat, lon, buffer_km=buffer_km)
        if dem is None or geometry is None:
            return None, None
        slope = ee.Terrain.slope(dem).rename('slope').clip(geometry)
        return slope, geometry
    except Exception as exc:
        logger.error("get_slope failed: %s", exc)
        return None, None


# =============================================================================
# 4. RAINFALL DATA  (CHIRPS)
# =============================================================================

def get_rainfall_data(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> dict:
    """
    Compute total and monthly rainfall for the given point from CHIRPS daily data.

    Args:
        lat, lon    : Coordinates of the point of interest.
        start_date  : ISO date string, e.g. "2024-01-01".
        end_date    : ISO date string, e.g. "2024-12-31".

    Returns:
        dict with keys:
          "total_mm"  : float  — total rainfall over the period.
          "monthly"   : list of {"month": int, "month_name": str, "rainfall_mm": float}
          "source"    : "GEE" or "sample" (indicates data origin).

    Fallback:
        Returns sample data (labelled "source": "sample") if GEE is unavailable
        or if any error occurs during the API call.

    Dataset:
        UCSB-CHG/CHIRPS/DAILY — Climate Hazards Group InfraRed Precipitation
        with Stations (CHIRPS). ~5.5 km spatial resolution, daily since 1981.
        Band "precipitation" is in mm/day.
    """
    if not _is_gee_ready():
        return _fallback_rainfall()

    try:
        point = ee.Geometry.Point([lon, lat])  # GEE: [lon, lat]
        _start = datetime.strptime(start_date, "%Y-%m-%d")
        _end   = datetime.strptime(end_date,   "%Y-%m-%d")

        # ── Total rainfall ───────────────────────────────────────────────────
        collection = (
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterBounds(point)
            .filterDate(start_date, end_date)
        )

        total_image = collection.sum()
        total_mm = float(
            total_image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=5000,
                maxPixels=1e9,
            ).get("precipitation").getInfo() or 0
        )

        # ── Monthly breakdown ────────────────────────────────────────────────
        _MONTH_NAMES = [
            "Jan","Feb","Mar","Apr","May","Jun",
            "Jul","Aug","Sep","Oct","Nov","Dec",
        ]
        monthly = []
        year = _start.year
        end_year = _end.year

        for yr in range(year, end_year + 1):
            month_start = 1 if yr > year else _start.month
            month_end   = 12 if yr < end_year else _end.month

            for mo in range(month_start, month_end + 1):
                mo_start = f"{yr}-{mo:02d}-01"
                # last day of the month
                if mo == 12:
                    mo_end = f"{yr + 1}-01-01"
                else:
                    mo_end = f"{yr}-{mo + 1:02d}-01"

                try:
                    mo_col   = collection.filterDate(mo_start, mo_end)
                    mo_total = mo_col.sum()
                    mo_mm = float(
                        mo_total.reduceRegion(
                            reducer=ee.Reducer.mean(),
                            geometry=point,
                            scale=5000,
                            maxPixels=1e9,
                        ).get("precipitation").getInfo() or 0
                    )
                except Exception:
                    mo_mm = 0.0

                monthly.append({
                    "month":        mo,
                    "month_name":   _MONTH_NAMES[mo - 1],
                    "rainfall_mm":  round(mo_mm, 1),
                })

        logger.info(
            "CHIRPS rainfall computed: total=%.1f mm for (%s → %s)",
            total_mm, start_date, end_date,
        )
        return {
            "total_mm": round(total_mm, 1),
            "monthly":  monthly,
            "source":   "GEE",
        }

    except Exception as exc:
        logger.error("get_rainfall_data failed: %s", exc)
        return _fallback_rainfall()


def _fallback_rainfall() -> dict:
    """Return sample rainfall data when GEE is unavailable."""
    total = sum(m["rainfall_mm"] for m in _SAMPLE_MONTHLY_RAIN)
    return {
        "total_mm": total,
        "monthly":  _SAMPLE_MONTHLY_RAIN,
        "source":   "sample",
    }


# =============================================================================
# 5. THUMBNAIL URL
# =============================================================================

def get_thumbnail_url(
    ee_image: "ee.Image",
    geometry: "ee.Geometry",
    vis_params: dict,
    dimensions: int = 512,
) -> Optional[str]:
    """
    Generate a public thumbnail PNG URL for display in Streamlit.

    Args:
        ee_image   : An ee.Image to visualise.
        geometry   : The AOI used to clip the thumbnail region.
        vis_params : Visualisation parameters dict, e.g.:
                     {"bands": ["B4","B3","B2"], "min": 0, "max": 3000}
        dimensions : Output image size in pixels on the longest edge (default 512).

    Returns:
        URL string (str) on success, or None on failure.

    Notes:
        - Thumbnail URLs are signed and expire after ~3 hours.
        - Maximum resolution supported by getThumbURL is 2048 pixels.
        - For larger exports, use ee.batch.Export.image.toDrive() instead.
    """
    if not _is_gee_ready():
        return None

    if ee_image is None or geometry is None:
        logger.warning("get_thumbnail_url: received None image or geometry.")
        return None

    try:
        url = ee_image.getThumbURL({
            "region":     geometry,
            "dimensions": dimensions,
            "format":     "png",
            **vis_params,
        })
        logger.info("Thumbnail URL generated (dimensions=%d).", dimensions)
        return url

    except Exception as exc:
        logger.error("get_thumbnail_url failed: %s", exc)
        return None


# =============================================================================
# 6. CONVENIENCE: RGB COMPOSITE URLS
# =============================================================================

def get_s2_rgb_url(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    buffer_km: float = 10,
    dimensions: int = 512,
) -> Optional[str]:
    """
    Convenience wrapper: Sentinel-2 true-colour (B4/B3/B2) thumbnail URL.

    Returns a PNG URL or None if GEE is unavailable.
    """
    image, geometry = get_sentinel2_image(lat, lon, start_date, end_date, buffer_km)
    if image is None:
        return None
    vis = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.4}
    return get_thumbnail_url(image, geometry, vis, dimensions)


def get_s2_ndvi_url(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    buffer_km: float = 10,
    dimensions: int = 512,
) -> Optional[str]:
    """
    Convenience wrapper: Sentinel-2 NDVI thumbnail URL.

    NDVI = (B8 - B4) / (B8 + B4). Returns a PNG URL or None.
    """
    image, geometry = get_sentinel2_image(lat, lon, start_date, end_date, buffer_km)
    if image is None:
        return None
    try:
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
        return get_thumbnail_url(ndvi, geometry, NDVI_VIS, dimensions)
    except Exception as exc:
        logger.error("get_s2_ndvi_url failed: %s", exc)
        return None


def get_l8_rgb_url(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    buffer_km: float = 10,
    dimensions: int = 512,
) -> Optional[str]:
    """
    Convenience wrapper: Landsat-8 true-colour (SR_B4/SR_B3/SR_B2) thumbnail URL.

    Returns a PNG URL or None if GEE is unavailable.
    """
    image, geometry = get_landsat8_image(lat, lon, start_date, end_date, buffer_km)
    if image is None:
        return None
    vis = {"bands": ["SR_B4", "SR_B3", "SR_B2"], "min": 0.0, "max": 0.3, "gamma": 1.4}
    return get_thumbnail_url(image, geometry, vis, dimensions)


# =============================================================================
# 7. FOLIUM BRIDGE — GEE tile layers for the interactive map
# =============================================================================

# Folium is imported lazily here so gee_engine can be used without it.
try:
    import folium
    _FOLIUM_OK = True
except ImportError:
    folium = None
    _FOLIUM_OK = False

# Canonical vis-params used by get_all_tile_layers.
# Hex palette strings (no leading #) are required by the GEE tile API.
_TILE_NDVI_VIS = {
    "min": -0.2,
    "max": 0.8,
    "palette": ["d73027", "fee08b", "1a9850"],
}
_TILE_NDWI_VIS = {
    "min": -0.5,
    "max": 0.5,
    "palette": ["8B4513", "FFFFFF", "0000FF"],
}
_TILE_TRUE_COLOR_VIS = {
    "bands": ["B4", "B3", "B2"],
    "min": 0,
    "max": 3000,
    "gamma": 1.4,
}
_TILE_SLOPE_VIS = {
    "min": 0,
    "max": 45,
    "palette": ["00FF00", "FFFF00", "FF0000"],
}


def ee_image_to_folium_tile(
    ee_image: "ee.Image",
    vis_params: dict,
    name: str = "Layer",
) -> Optional[dict]:
    """
    Convert an ee.Image into a Folium-compatible tile URL dictionary.

    This is the bridge between GEE and Folium. Without this, satellite data
    cannot be displayed on the interactive Folium map in the dashboard.

    Args:
        ee_image   : An ee.Image object to visualise.
        vis_params : Visualisation parameters, e.g.:
                     {'min': 0, 'max': 1, 'palette': ['red', 'green']}
                     or {'bands': ['B4','B3','B2'], 'min': 0, 'max': 3000}
        name       : Display name shown in the Folium LayerControl widget.

    Returns:
        dict with keys:
          'tile_url'    : XYZ tile URL string for Folium.TileLayer.
          'name'        : Layer display name.
          'attribution' : Attribution string.
        Returns None if GEE is unavailable or an error occurs.

    Notes:
        - Tile URLs are signed and valid for ~3 hours per GEE session.
        - The returned dict is consumed by add_ee_layer_to_folium().
    """
    if not _is_gee_ready():
        return None
    if ee_image is None:
        logger.warning("ee_image_to_folium_tile: received None image for layer '%s'.", name)
        return None

    try:
        map_id_dict = ee.Image(ee_image).getMapId(vis_params)
        tile_url = map_id_dict["tile_fetcher"].url_format
        logger.info("Tile URL created for layer '%s'.", name)
        return {
            "tile_url":    tile_url,
            "name":        name,
            "attribution": "Google Earth Engine",
        }
    except Exception as exc:
        logger.error("ee_image_to_folium_tile failed for layer '%s': %s", name, exc)
        return None


def add_ee_layer_to_folium(
    folium_map: "folium.Map",
    tile_dict: Optional[dict],
    opacity: float = 0.7,
) -> "folium.Map":
    """
    Add a GEE tile layer (from ee_image_to_folium_tile) to a Folium map.

    Args:
        folium_map : folium.Map object to add the layer to.
        tile_dict  : dict returned by ee_image_to_folium_tile(), or None.
        opacity    : Layer transparency between 0 (invisible) and 1 (opaque).

    Returns:
        The same folium.Map object (modified in-place), or the original map
        unchanged if tile_dict is None or folium is not installed.

    Usage:
        m = folium.Map(location=[lat, lon], zoom_start=12)
        tile = ee_image_to_folium_tile(ndvi_image, NDVI_VIS, "NDVI")
        m = add_ee_layer_to_folium(m, tile, opacity=0.75)
    """
    if tile_dict is None:
        return folium_map
    if not _FOLIUM_OK or folium is None:
        logger.warning("add_ee_layer_to_folium: folium not installed.")
        return folium_map

    try:
        folium.raster_layers.TileLayer(
            tiles=tile_dict["tile_url"],
            attr=tile_dict["attribution"],
            name=tile_dict["name"],
            overlay=True,
            control=True,
            opacity=opacity,
        ).add_to(folium_map)
        logger.info("Added tile layer '%s' to Folium map.", tile_dict["name"])
    except Exception as exc:
        logger.error(
            "add_ee_layer_to_folium failed for layer '%s': %s",
            tile_dict.get("name", "?"), exc,
        )

    return folium_map


def get_all_tile_layers(
    lat: float,
    lon: float,
    before_dates: dict,
    after_dates: dict,
    buffer_km: float = 10,
    *,
    before_img: Optional["ee.Image"] = None,
    after_img: Optional["ee.Image"] = None,
) -> dict:
    """
    Master function: fetch all GEE satellite tile layers needed for the dashboard.

    Retrieves before/after Sentinel-2 composites and the SRTM DEM, then
    creates Folium tile dicts for every visualisation layer. Each layer is
    created inside its own try-except so a failure in one never prevents the
    others from loading.

    Results are cached in ``st.session_state`` under the key
    ``"gee_tiles_{lat}_{lon}_{before_start}_{after_start}"`` so repeated
    Streamlit reruns do not re-fetch from GEE.

    Args:
        lat, lon      : Centre of the watershed (decimal degrees).
        before_dates  : dict with 'start' and 'end' ISO strings, e.g.:
                        {"start": "2019-01-01", "end": "2019-12-31"}
        after_dates   : Same format for the "after" period.
        buffer_km     : AOI radius in km (default 10).

    Optional keyword-only args:
        before_img : Pre-built BEFORE ee.Image composite (from create_s2_composite).
                     When supplied, create_s2_composite() is NOT called for the BEFORE
                     period — tiles are generated directly from this image.
                     Pass None (default) to let this function build the composite itself.
        after_img  : Same as before_img, for the AFTER period.

    Returns:
        dict keyed by layer name, each value is either a tile_dict
        (from ee_image_to_folium_tile) or None if that layer failed:

        {
            "NDVI (Before)":       {...} or None,
            "NDVI (After)":        {...} or None,
            "NDWI (After)":        {...} or None,
            "True Color (Before)": {...} or None,
            "True Color (After)":  {...} or None,
            "Slope":               {...} or None,
            "before_satellite":    {...} or None,
            "after_satellite":     {...} or None,
        }

    Example — standalone (no pre-built composites):
        tiles = get_all_tile_layers(
            lat, lon,
            {"start": "2019-01-01", "end": "2019-12-31"},
            {"start": "2024-01-01", "end": "2024-12-31"},
        )

    Example — with pre-built composites (avoids duplicate pipeline calls):
        before_img, before_meta = create_s2_composite(aoi, "2019-01-01", "2019-12-31")
        after_img,  after_meta  = create_s2_composite(aoi, "2024-01-01", "2024-12-31")
        tiles = get_all_tile_layers(
            lat, lon,
            {"start": "2019-01-01", "end": "2019-12-31"},
            {"start": "2024-01-01", "end": "2024-12-31"},
            before_img=before_img,
            after_img=after_img,
        )
    """
    if not _is_gee_ready():
        logger.warning("get_all_tile_layers: GEE not ready — returning empty dict.")
        return {}

    # ── Session-state cache key ───────────────────────────────────────────────
    cache_key = (
        f"gee_tiles_{lat:.4f}_{lon:.4f}_"
        f"{before_dates.get('start','')}_{after_dates.get('start','')}"
    )
    try:
        import streamlit as st
        if cache_key in st.session_state:
            logger.info("get_all_tile_layers: returning cached tiles (%s).", cache_key)
            return st.session_state[cache_key]
    except ImportError:
        pass  # Streamlit not in scope (e.g. running from a script)

    result: dict = {}

    # ── Shared AOI geometry ───────────────────────────────────────────────────
    aoi = _make_geometry(lat, lon, buffer_km * 1000)

    # ── BEFORE composite ─────────────────────────────────────────────────────
    # If a pre-built composite is supplied by the caller (BUG-3 fix), reuse it
    # directly and skip create_s2_composite() to avoid a duplicate pipeline run.
    # Otherwise build it here for standalone/direct calls.
    before_start = before_dates.get("start", "2019-01-01")
    before_end   = before_dates.get("end",   "2019-12-31")
    if before_img is not None:
        logger.info(
            "get_all_tile_layers: using pre-built BEFORE composite (skipping create_s2_composite)."
        )
        img_before = before_img
    else:
        img_before = None
        logger.info("get_all_tile_layers: building BEFORE composite (%s to %s).",
                    before_start, before_end)
        try:
            img_before, _before_meta = create_s2_composite(
                aoi=aoi,
                start_date=before_start,
                end_date=before_end,
                label=f"Before {before_start[:4]}",
            )
        except InsufficientImageryError as exc:
            logger.warning("get_all_tile_layers: BEFORE composite failed: %s", exc)
        except Exception as exc:
            logger.error("get_all_tile_layers: BEFORE composite error: %s", exc)

    # ── AFTER composite ──────────────────────────────────────────────────────
    after_start = after_dates.get("start", "2024-01-01")
    after_end   = after_dates.get("end",   "2024-12-31")
    if after_img is not None:
        logger.info(
            "get_all_tile_layers: using pre-built AFTER composite (skipping create_s2_composite)."
        )
        img_after = after_img
    else:
        img_after = None
        logger.info("get_all_tile_layers: building AFTER composite (%s to %s).",
                    after_start, after_end)
        try:
            img_after, _after_meta = create_s2_composite(
                aoi=aoi,
                start_date=after_start,
                end_date=after_end,
                label=f"After {after_start[:4]}",
            )
        except InsufficientImageryError as exc:
            logger.warning("get_all_tile_layers: AFTER composite failed: %s", exc)
        except Exception as exc:
            logger.error("get_all_tile_layers: AFTER composite error: %s", exc)

    logger.info("get_all_tile_layers: fetching SRTM DEM.")
    dem, geom_dem = get_elevation(lat, lon, buffer_km)


    # ── Layer 1: NDVI (Before) ────────────────────────────────────────────────
    try:
        if img_before is not None:
            ndvi_before = img_before.normalizedDifference(["B8", "B4"]).rename("NDVI")
            result["NDVI (Before)"] = ee_image_to_folium_tile(
                ndvi_before, _TILE_NDVI_VIS, "NDVI (Before)"
            )
        else:
            result["NDVI (Before)"] = None
    except Exception as exc:
        logger.error("Layer 'NDVI (Before)' failed: %s", exc)
        result["NDVI (Before)"] = None

    # ── Layer 2: NDVI (After) ─────────────────────────────────────────────────
    try:
        if img_after is not None:
            ndvi_after = img_after.normalizedDifference(["B8", "B4"]).rename("NDVI")
            result["NDVI (After)"] = ee_image_to_folium_tile(
                ndvi_after, _TILE_NDVI_VIS, "NDVI (After)"
            )
        else:
            result["NDVI (After)"] = None
    except Exception as exc:
        logger.error("Layer 'NDVI (After)' failed: %s", exc)
        result["NDVI (After)"] = None

    # ── Layer 3: NDWI (After) — water detection ───────────────────────────────
    try:
        if img_after is not None:
            # Sentinel-2 NDWI = (B3 Green - B8 NIR) / (B3 + B8)
            ndwi_after = img_after.normalizedDifference(["B3", "B8"]).rename("NDWI")
            result["NDWI (After)"] = ee_image_to_folium_tile(
                ndwi_after, _TILE_NDWI_VIS, "NDWI (After)"
            )
        else:
            result["NDWI (After)"] = None
    except Exception as exc:
        logger.error("Layer 'NDWI (After)' failed: %s", exc)
        result["NDWI (After)"] = None

    # ── Layer 4: True Color (Before) ──────────────────────────────────────────
    try:
        if img_before is not None:
            result["True Color (Before)"] = ee_image_to_folium_tile(
                img_before, _TILE_TRUE_COLOR_VIS, "True Color (Before)"
            )
        else:
            result["True Color (Before)"] = None
    except Exception as exc:
        logger.error("Layer 'True Color (Before)' failed: %s", exc)
        result["True Color (Before)"] = None

    # ── Layer 5: True Color (After) ───────────────────────────────────────────
    try:
        if img_after is not None:
            result["True Color (After)"] = ee_image_to_folium_tile(
                img_after, _TILE_TRUE_COLOR_VIS, "True Color (After)"
            )
        else:
            result["True Color (After)"] = None
    except Exception as exc:
        logger.error("Layer 'True Color (After)' failed: %s", exc)
        result["True Color (After)"] = None

    # ── Layer 6: Slope (from DEM) ─────────────────────────────────────────────
    try:
        if dem is not None and geom_dem is not None:
            slope = ee.Terrain.slope(dem)
            result["Slope"] = ee_image_to_folium_tile(
                slope, _TILE_SLOPE_VIS, "Slope"
            )
        else:
            result["Slope"] = None
    except Exception as exc:
        logger.error("Layer 'Slope' failed: %s", exc)
        result["Slope"] = None

    # ── Layer 7: Before Satellite (RGB composite for Before/After comparison) ──
    # Alias of True Color (Before) under a stable key consumed by the
    # Before/After comparison panel and the satellite_metadata dict in app.py.
    try:
        if img_before is not None:
            result["before_satellite"] = ee_image_to_folium_tile(
                img_before, _TILE_TRUE_COLOR_VIS, "Satellite (Before)"
            )
        else:
            result["before_satellite"] = None
    except Exception as exc:
        logger.error("Layer 'before_satellite' failed: %s", exc)
        result["before_satellite"] = None

    # ── Layer 8: After Satellite (RGB composite for Before/After comparison) ───
    # Alias of True Color (After) under a stable key.
    try:
        if img_after is not None:
            result["after_satellite"] = ee_image_to_folium_tile(
                img_after, _TILE_TRUE_COLOR_VIS, "Satellite (After)"
            )
        else:
            result["after_satellite"] = None
    except Exception as exc:
        logger.error("Layer 'after_satellite' failed: %s", exc)
        result["after_satellite"] = None


    # ── Cache in session_state ────────────────────────────────────────────────
    try:
        import streamlit as st
        st.session_state[cache_key] = result
        logger.info(
            "get_all_tile_layers: cached %d layers under key '%s'.",
            len(result), cache_key,
        )
    except ImportError:
        pass

    success = sum(1 for v in result.values() if v is not None)
    logger.info(
        "get_all_tile_layers: %d/%d layers created successfully.",
        success, len(result),
    )
    return result


# =============================================================================
# 8. CACHING LAYER — disk-backed cache for GEE results
# =============================================================================
# Strategy
# --------
# JSON is used for plain Python objects (dicts, lists, numbers, strings).
# Pickle is used as a fallback for anything that is not JSON-serialisable
# (e.g. numpy arrays, complex nested objects).
#
# Cache file layout inside cache_dir/:
#   <key>.json     — JSON payload + metadata wrapper
#   <key>.pkl      — Pickle payload (used when JSON fails)
#   <key>.meta.json— Metadata sidecar (timestamp, source, key) for .pkl files
#
# The cache key is sanitised (alphanumeric + underscores/hyphens only) before
# being used as a filename to avoid path traversal or OS-level issues.

_DEFAULT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache",
)


def _sanitise_key(key: str) -> str:
    """
    Return a filesystem-safe version of *key*.

    Replaces any character that is not alphanumeric, a hyphen, or an
    underscore with an underscore. If the sanitised key exceeds 200
    characters it is truncated and a short hash suffix is appended to
    preserve uniqueness.
    """
    import re
    safe = re.sub(r"[^\w\-]", "_", key)
    if len(safe) > 200:
        suffix = hashlib.md5(key.encode()).hexdigest()[:8]
        safe = safe[:192] + "_" + suffix
    return safe


def cache_gee_result(
    key: str,
    data: Any,
    cache_dir: str = _DEFAULT_CACHE_DIR,
) -> bool:
    """
    Persist *data* to disk under a descriptive *key*.

    Strategy
    --------
    First attempts to serialise *data* as JSON (human-readable, easy to
    inspect). If that fails (e.g. the object contains numpy arrays or
    ee objects), falls back to pickle.

    A metadata envelope is always written so that load_cached_result()
    can verify freshness without reading the whole payload.

    Args:
        key       : Descriptive cache key, e.g. ``"ndvi_hiware_bazar_2024"``.
                    Must be unique per logical result.
        data      : The Python object to cache (dict, list, scalar, …).
        cache_dir : Directory where cache files are stored.
                    Created automatically if it does not exist.

    Returns:
        True on success, False if writing failed (error is logged but
        never re-raised so callers never crash because of the cache).
    """
    try:
        os.makedirs(cache_dir, exist_ok=True)
        safe_key  = _sanitise_key(key)
        timestamp = datetime.utcnow().isoformat()

        # ── Try JSON first ────────────────────────────────────────────────────
        try:
            payload = {
                "_meta": {
                    "key":       key,
                    "saved_at":  timestamp,
                    "format":    "json",
                },
                "data": data,
            }
            json_path = os.path.join(cache_dir, f"{safe_key}.json")
            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str)
            logger.info("cache_gee_result: saved JSON cache '%s'.", json_path)
            return True

        except (TypeError, ValueError):
            # Data is not JSON-serialisable → fall back to pickle
            pass

        # ── Pickle fallback ───────────────────────────────────────────────────
        pkl_path  = os.path.join(cache_dir, f"{safe_key}.pkl")
        meta_path = os.path.join(cache_dir, f"{safe_key}.meta.json")

        with open(pkl_path, "wb") as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)

        meta = {"key": key, "saved_at": timestamp, "format": "pickle"}
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

        logger.info("cache_gee_result: saved Pickle cache '%s'.", pkl_path)
        return True

    except Exception as exc:
        logger.error("cache_gee_result failed for key '%s': %s", key, exc)
        return False


def load_cached_result(
    key: str,
    cache_dir: str = _DEFAULT_CACHE_DIR,
    max_age_hours: float = 24.0,
) -> Optional[Any]:
    """
    Load a previously cached result if it exists and is still fresh.

    Checks for both JSON and pickle cache files. Uses the ``saved_at``
    timestamp embedded in the cache metadata to decide freshness.

    Args:
        key            : The same key that was passed to cache_gee_result().
        cache_dir      : Directory to look in (must match the write location).
        max_age_hours  : Maximum age of a valid cache entry in hours.
                         Default is 24 h. Pass ``float('inf')`` to disable
                         expiry (useful for archived reference data).

    Returns:
        The cached Python object if the cache is valid and fresh.
        ``None`` if the cache is missing, expired, or corrupted.
    """
    try:
        safe_key  = _sanitise_key(key)
        now       = datetime.utcnow()
        cutoff    = timedelta(hours=max_age_hours)

        # ── Check JSON cache ──────────────────────────────────────────────────
        json_path = os.path.join(cache_dir, f"{safe_key}.json")
        if os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)

            saved_at = datetime.fromisoformat(payload["_meta"]["saved_at"])
            age = now - saved_at
            if age <= cutoff:
                logger.info(
                    "load_cached_result: JSON cache HIT for '%s' (age=%s).",
                    key, age,
                )
                return payload["data"]
            else:
                logger.info(
                    "load_cached_result: JSON cache EXPIRED for '%s' (age=%s > %sh).",
                    key, age, max_age_hours,
                )
                return None

        # ── Check pickle cache ────────────────────────────────────────────────
        pkl_path  = os.path.join(cache_dir, f"{safe_key}.pkl")
        meta_path = os.path.join(cache_dir, f"{safe_key}.meta.json")

        if os.path.isfile(pkl_path) and os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)

            saved_at = datetime.fromisoformat(meta["saved_at"])
            age = now - saved_at
            if age <= cutoff:
                with open(pkl_path, "rb") as fh:
                    data = pickle.load(fh)
                logger.info(
                    "load_cached_result: Pickle cache HIT for '%s' (age=%s).",
                    key, age,
                )
                return data
            else:
                logger.info(
                    "load_cached_result: Pickle cache EXPIRED for '%s' (age=%s > %sh).",
                    key, age, max_age_hours,
                )
                return None

        # ── Cache miss ────────────────────────────────────────────────────────
        logger.info("load_cached_result: cache MISS for '%s'.", key)
        return None

    except Exception as exc:
        logger.error("load_cached_result failed for key '%s': %s", key, exc)
        return None


def get_or_fetch(
    key: str,
    fetch_function: Callable,
    *args: Any,
    cache_dir: str = _DEFAULT_CACHE_DIR,
    max_age_hours: float = 24.0,
    **kwargs: Any,
) -> Any:
    """
    Cache-aside wrapper: return cached data when available, otherwise call
    *fetch_function* and cache its result automatically.

    This is the recommended way to wrap **any** GEE function call so that:
    - The first run fetches from GEE (slow — may take 10-30 s).
    - Subsequent runs within *max_age_hours* return instantly from disk.

    The cache key should be deterministic and descriptive, e.g.:
    ``"ndvi_hiware_bazar_2019-01-01_2019-12-31"``.

    Args:
        key            : Unique, descriptive cache key string.
        fetch_function : Any callable. Called as
                         ``fetch_function(*args, **kwargs)`` on a cache miss.
        *args          : Positional arguments forwarded to *fetch_function*.
        cache_dir      : Directory for cache storage.
        max_age_hours  : Maximum age of a valid cache entry in hours.
        **kwargs       : Keyword arguments forwarded to *fetch_function*.
                         ``cache_dir`` and ``max_age_hours`` are consumed here
                         and are NOT forwarded to *fetch_function*.

    Returns:
        The cached or freshly fetched result.
        If *fetch_function* raises an exception, it is logged and re-raised
        so the caller can decide how to handle the failure.

    Example::

        # Wrap get_rainfall_data with automatic caching:
        rain = get_or_fetch(
            key="rainfall_hiware_bazar_2024",
            fetch_function=get_rainfall_data,
            19.35, 74.55,
            "2024-01-01", "2024-12-31",
            max_age_hours=48,
        )

        # Wrap a lambda that calls multiple GEE functions:
        ndvi_data = get_or_fetch(
            key="ndvi_ts_arvari_river",
            fetch_function=lambda: compute_ndvi_timeseries(lat, lon),
            max_age_hours=72,
        )
    """
    # ── 1. Try cache ──────────────────────────────────────────────────────────
    cached = load_cached_result(key, cache_dir=cache_dir, max_age_hours=max_age_hours)
    if cached is not None:
        logger.info("get_or_fetch: returning cached result for '%s'.", key)
        return cached

    # ── 2. Fetch from source ──────────────────────────────────────────────────
    logger.info("get_or_fetch: cache miss — calling '%s' for key '%s'.",
                getattr(fetch_function, "__name__", repr(fetch_function)), key)
    try:
        result = fetch_function(*args, **kwargs)
    except Exception as exc:
        logger.error(
            "get_or_fetch: fetch_function failed for key '%s': %s", key, exc
        )
        raise

    # ── 3. Persist to cache ───────────────────────────────────────────────────
    if result is not None:
        cache_gee_result(key, result, cache_dir=cache_dir)
    else:
        logger.info(
            "get_or_fetch: fetch returned None for key '%s' — not caching.", key
        )

    return result


def clear_cache(
    key: Optional[str] = None,
    cache_dir: str = _DEFAULT_CACHE_DIR,
) -> int:
    """
    Delete cache entries.

    Args:
        key       : If provided, delete only the files for this specific key.
                    If None, delete ALL cache files in *cache_dir*.
        cache_dir : Cache directory.

    Returns:
        Number of files deleted.
    """
    deleted = 0
    if not os.path.isdir(cache_dir):
        return 0

    try:
        if key is not None:
            safe_key = _sanitise_key(key)
            candidates = [
                os.path.join(cache_dir, f"{safe_key}.json"),
                os.path.join(cache_dir, f"{safe_key}.pkl"),
                os.path.join(cache_dir, f"{safe_key}.meta.json"),
            ]
            for path in candidates:
                if os.path.isfile(path):
                    os.remove(path)
                    deleted += 1
                    logger.info("clear_cache: deleted '%s'.", path)
        else:
            for fname in os.listdir(cache_dir):
                if fname.endswith((".json", ".pkl")):
                    path = os.path.join(cache_dir, fname)
                    os.remove(path)
                    deleted += 1
            logger.info("clear_cache: deleted %d files from '%s'.", deleted, cache_dir)
    except Exception as exc:
        logger.error("clear_cache failed: %s", exc)

    return deleted


def cache_stats(cache_dir: str = _DEFAULT_CACHE_DIR) -> Dict[str, Any]:
    """
    Return a summary of the current cache contents.

    Useful for displaying cache status in the Streamlit dashboard sidebar
    or for debugging.

    Returns:
        dict with keys:
          'total_files'  : int   — number of cache files present.
          'total_size_kb': float — total size in kilobytes.
          'entries'      : list  — one dict per logical entry with
                           'key', 'format', 'saved_at', 'age_hours', 'size_kb'.
    """
    if not os.path.isdir(cache_dir):
        return {"total_files": 0, "total_size_kb": 0.0, "entries": []}

    entries = []
    total_size = 0
    now = datetime.utcnow()

    try:
        for fname in sorted(os.listdir(cache_dir)):
            fpath = os.path.join(cache_dir, fname)
            if not os.path.isfile(fpath):
                continue

            size_kb = os.path.getsize(fpath) / 1024
            total_size += size_kb

            if fname.endswith(".json") and not fname.endswith(".meta.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        payload = json.load(fh)
                    meta     = payload.get("_meta", {})
                    saved_at = meta.get("saved_at", "")
                    age_h    = (
                        (now - datetime.fromisoformat(saved_at)).total_seconds() / 3600
                        if saved_at else -1
                    )
                    entries.append({
                        "key":       meta.get("key", fname),
                        "format":    "json",
                        "saved_at":  saved_at,
                        "age_hours": round(age_h, 2),
                        "size_kb":   round(size_kb, 2),
                    })
                except Exception:
                    entries.append({"key": fname, "format": "json",
                                    "saved_at": "?", "age_hours": -1,
                                    "size_kb": round(size_kb, 2)})

            elif fname.endswith(".meta.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        meta = json.load(fh)
                    saved_at = meta.get("saved_at", "")
                    age_h    = (
                        (now - datetime.fromisoformat(saved_at)).total_seconds() / 3600
                        if saved_at else -1
                    )
                    pkl_size = os.path.getsize(
                        fpath.replace(".meta.json", ".pkl")
                    ) / 1024 if os.path.isfile(fpath.replace(".meta.json", ".pkl")) else 0
                    entries.append({
                        "key":       meta.get("key", fname),
                        "format":    "pickle",
                        "saved_at":  saved_at,
                        "age_hours": round(age_h, 2),
                        "size_kb":   round(pkl_size, 2),
                    })
                except Exception:
                    pass

    except Exception as exc:
        logger.error("cache_stats failed: %s", exc)

    return {
        "total_files":   len([f for f in os.listdir(cache_dir)
                              if os.path.isfile(os.path.join(cache_dir, f))]),
        "total_size_kb": round(total_size, 2),
        "entries":       entries,
    }
