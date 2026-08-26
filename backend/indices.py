"""
backend/indices.py
==================
Spectral index calculations for AquaVeda watershed monitoring.

All compute functions accept a Sentinel-2 SR ee.Image and return an ee.Image.
Input image must have been fetched via gee_engine.get_sentinel2_image()
(COPERNICUS/S2_SR_HARMONIZED). Expected bands:
  B2  = Blue   (490 nm)
  B3  = Green  (560 nm)
  B4  = Red    (665 nm)
  B8  = NIR    (842 nm)
  B11 = SWIR1  (1610 nm)

All functions degrade gracefully when GEE is unavailable (return None).

Indices implemented
-------------------
  NDVI  Normalized Difference Vegetation Index  (B8-B4)/(B8+B4)
  NDWI  Normalized Difference Water Index       (B3-B8)/(B3+B8)
  SAVI  Soil Adjusted Vegetation Index          (B8-B4)/(B8+B4+L)*(1+L)
  NDBI  Normalized Difference Built-up Index    (B11-B8)/(B11+B8)
  BSI   Bare Soil Index   ((B11+B4)-(B8+B2))/((B11+B4)+(B8+B2))
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

# -- Google Earth Engine -------------------------------------------------------
try:
    import ee
    _EE_OK = True
except ImportError:
    ee = None
    _EE_OK = False

logger = logging.getLogger(__name__)


# =============================================================================
# INTERNAL HELPER
# =============================================================================

def _ee_ready() -> bool:
    """Return True only when ee is imported and the session is authenticated."""
    if not _EE_OK or ee is None:
        logger.warning("indices: earthengine-api not installed.")
        return False
    try:
        return bool(ee.data.is_initialized())
    except Exception:
        return False


# =============================================================================
# 1. NDVI -- Normalized Difference Vegetation Index
# =============================================================================

def calculate_ndvi(image: "ee.Image") -> Optional["ee.Image"]:
    """
    Compute NDVI from a Sentinel-2 SR image.

    Formula:  NDVI = (NIR - Red) / (NIR + Red)
                   = (B8  - B4 ) / (B8  + B4 )

    Range     : -1 to 1
    Threshold : > 0.4  -> healthy vegetation
                0.2-0.4 -> moderate vegetation
                < 0.2  -> sparse / no vegetation

    Args:
        image : ee.Image with Sentinel-2 SR bands.

    Returns:
        ee.Image with a single float band named 'NDVI', or None on failure.
    """
    if not _ee_ready() or image is None:
        return None
    try:
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
        logger.debug("calculate_ndvi: OK")
        return ndvi
    except Exception as exc:
        logger.error("calculate_ndvi failed: %s", exc)
        return None


# =============================================================================
# 2. NDWI -- Normalized Difference Water Index
# =============================================================================

def calculate_ndwi(image: "ee.Image") -> Optional["ee.Image"]:
    """
    Compute NDWI from a Sentinel-2 SR image (McFeeters 1996).

    Formula:  NDWI = (Green - NIR) / (Green + NIR)
                   = (B3   - B8 ) / (B3   + B8 )

    Range     : -1 to 1
    Threshold : > 0.0 -> open water body detected
                < 0.0 -> land / vegetation

    Args:
        image : ee.Image with Sentinel-2 SR bands.

    Returns:
        ee.Image with a single float band named 'NDWI', or None on failure.
    """
    if not _ee_ready() or image is None:
        return None
    try:
        ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
        logger.debug("calculate_ndwi: OK")
        return ndwi
    except Exception as exc:
        logger.error("calculate_ndwi failed: %s", exc)
        return None


# =============================================================================
# 3. SAVI -- Soil Adjusted Vegetation Index
# =============================================================================

def calculate_savi(image: "ee.Image", L: float = 0.5) -> Optional["ee.Image"]:
    """
    Compute SAVI from a Sentinel-2 SR image (Huete 1988).

    Formula:  SAVI = ((NIR - Red) / (NIR + Red + L)) * (1 + L)

    Soil brightness correction factor L:
      L = 1.0  -> areas with very low vegetation cover
      L = 0.5  -> intermediate (default, suitable for arid/semi-arid:
                  Rajasthan, Vidarbha, Anantapur)
      L = 0.25 -> areas with high vegetation cover
      L = 0.0  -> equivalent to NDVI (no correction)

    Args:
        image : ee.Image with Sentinel-2 SR bands.
        L     : Soil brightness correction factor (default 0.5).

    Returns:
        ee.Image with a single float band named 'SAVI', or None on failure.
    """
    if not _ee_ready() or image is None:
        return None
    try:
        savi = image.expression(
            "((NIR - RED) / (NIR + RED + L)) * (1.0 + L)",
            {
                "NIR": image.select("B8"),
                "RED": image.select("B4"),
                "L":   L,
            },
        ).rename("SAVI")
        logger.debug("calculate_savi: OK (L=%.2f)", L)
        return savi
    except Exception as exc:
        logger.error("calculate_savi failed: %s", exc)
        return None


# =============================================================================
# 4. NDBI -- Normalized Difference Built-up Index
# =============================================================================

def calculate_ndbi(image: "ee.Image") -> Optional["ee.Image"]:
    """
    Compute NDBI from a Sentinel-2 SR image (Zha et al. 2003).

    Formula:  NDBI = (SWIR1 - NIR) / (SWIR1 + NIR)
                   = (B11   - B8 ) / (B11   + B8 )

    Range     : -1 to 1
    Positive  -> built-up / urban areas encroaching on watershed land.
    Negative  -> vegetation or water.

    Detects urban expansion and impervious-surface growth over time.

    Args:
        image : ee.Image with Sentinel-2 SR bands.

    Returns:
        ee.Image with a single float band named 'NDBI', or None on failure.
    """
    if not _ee_ready() or image is None:
        return None
    try:
        ndbi = image.normalizedDifference(["B11", "B8"]).rename("NDBI")
        logger.debug("calculate_ndbi: OK")
        return ndbi
    except Exception as exc:
        logger.error("calculate_ndbi failed: %s", exc)
        return None


# =============================================================================
# 5. BSI -- Bare Soil Index
# =============================================================================

def calculate_bsi(image: "ee.Image") -> Optional["ee.Image"]:
    """
    Compute BSI from a Sentinel-2 SR image (Rikimaru et al. 2002).

    Formula:  BSI = ((SWIR1 + Red) - (NIR + Blue))
                   / ((SWIR1 + Red) + (NIR + Blue))
                  = ((B11 + B4) - (B8 + B2))
                   / ((B11 + B4) + (B8 + B2))

    Range     : -1 to 1
    High BSI  -> bare / exposed soil, eroded land, desert.
    Low BSI   -> vegetation or built-up areas.

    Detects topsoil loss and active erosion that NDVI cannot distinguish
    from low-vegetation areas.

    Args:
        image : ee.Image with Sentinel-2 SR bands.

    Returns:
        ee.Image with a single float band named 'BSI', or None on failure.
    """
    if not _ee_ready() or image is None:
        return None
    try:
        bsi = image.expression(
            "((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))",
            {
                "SWIR": image.select("B11"),
                "RED":  image.select("B4"),
                "NIR":  image.select("B8"),
                "BLUE": image.select("B2"),
            },
        ).rename("BSI")
        logger.debug("calculate_bsi: OK")
        return bsi
    except Exception as exc:
        logger.error("calculate_bsi failed: %s", exc)
        return None


# =============================================================================
# 6. COMPOSITE -- all indices in one call
# =============================================================================

def calculate_all_indices(
    image: "ee.Image",
    savi_L: float = 0.5,
) -> Optional["ee.Image"]:
    """
    Calculate every spectral index and add all bands to the original image.

    Output bands (in addition to the original Sentinel-2 bands):
      NDVI, NDWI, SAVI, NDBI, BSI

    Args:
        image  : ee.Image with Sentinel-2 SR bands.
        savi_L : Soil brightness factor forwarded to calculate_savi().

    Returns:
        ee.Image with original bands + 5 index bands, or None on failure.
    """
    if not _ee_ready() or image is None:
        return None
    try:
        ndvi = calculate_ndvi(image)
        ndwi = calculate_ndwi(image)
        savi = calculate_savi(image, L=savi_L)
        ndbi = calculate_ndbi(image)
        bsi  = calculate_bsi(image)

        bands_to_add = [b for b in [ndvi, ndwi, savi, ndbi, bsi] if b is not None]
        if not bands_to_add:
            logger.warning("calculate_all_indices: no index bands computed.")
            return image

        result = image.addBands(bands_to_add)
        logger.info(
            "calculate_all_indices: added %d index band(s).",
            len(bands_to_add),
        )
        return result

    except Exception as exc:
        logger.error("calculate_all_indices failed: %s", exc)
        return None


# =============================================================================
# 7. STATISTICS -- reduceRegion wrapper
# =============================================================================

def get_index_stats(
    index_image: "ee.Image",
    geometry: "ee.Geometry",
    scale: int = 10,
) -> Optional[Dict[str, float]]:
    """
    Compute mean, min, max, and standard deviation for an index image.

    Uses a combined ee.Reducer (single server-side pass) to minimise API
    calls and latency.

    Args:
        index_image : Single-band ee.Image (e.g. from calculate_ndvi()).
        geometry    : AOI geometry.
        scale       : Pixel resolution in metres (default 10 for Sentinel-2).

    Returns:
        dict: {"mean": 0.45, "min": 0.10, "max": 0.80, "std": 0.15}
        or None on failure.
    """
    if not _ee_ready() or index_image is None or geometry is None:
        return None
    try:
        combined_reducer = (
            ee.Reducer.mean()
            .combine(ee.Reducer.min(),    sharedInputs=True)
            .combine(ee.Reducer.max(),    sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
        )
        raw: dict = index_image.reduceRegion(
            reducer=combined_reducer,
            geometry=geometry,
            scale=scale,
            maxPixels=1e9,
        ).getInfo()

        # reduceRegion keys are "<band>_mean", "<band>_min", etc.
        def _pick(suffix: str) -> Optional[float]:
            for k, v in raw.items():
                if k.endswith(suffix) and v is not None:
                    return round(float(v), 6)
            return None

        result = {
            "mean": _pick("_mean") or _pick("mean"),
            "min":  _pick("_min")  or _pick("min"),
            "max":  _pick("_max")  or _pick("max"),
            "std":  _pick("_stdDev") or _pick("stdDev"),
        }
        logger.info("get_index_stats: %s", result)
        return result

    except Exception as exc:
        logger.error("get_index_stats failed: %s", exc)
        return None


# =============================================================================
# 8. WATER BODY DETECTION
# =============================================================================

def detect_water_bodies(
    image: "ee.Image",
    geometry: "ee.Geometry",
    threshold: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """
    Detect open water bodies using NDWI and return their total area.

    Workflow:
    1. Compute NDWI = (B3 - B8) / (B3 + B8).
    2. Create binary mask: pixel = 1 where NDWI > threshold, else 0.
    3. Multiply by pixel area (m2) and sum over the AOI.
    4. Convert to hectares.

    Args:
        image     : ee.Image with Sentinel-2 SR bands.
        geometry  : AOI geometry.
        threshold : NDWI threshold for water detection (default 0.0).
                    Raise to ~0.1 to reduce commission errors in humid areas;
                    lower to ~-0.1 for turbid / shallow water.

    Returns:
        dict:
          {
            "water_area_ha": 12.8,        # float - detected water in hectares
            "water_mask":    <ee.Image>,  # binary mask (1=water, 0=land)
            "threshold":     0.0,         # threshold used
          }
        or None on failure.
    """
    if not _ee_ready() or image is None or geometry is None:
        return None
    try:
        # 1. NDWI
        ndwi = calculate_ndwi(image)
        if ndwi is None:
            logger.error("detect_water_bodies: NDWI computation returned None.")
            return None

        # 2. Binary water mask
        water_mask = ndwi.gt(threshold).rename("water_mask")

        # 3. Area calculation
        pixel_area   = ee.Image.pixelArea()           # m2 per pixel
        water_pixels = water_mask.multiply(pixel_area)

        area_result: dict = water_pixels.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9,
        ).getInfo()

        # Key is "water_mask" (the band name set above)
        area_m2 = float(area_result.get("water_mask", 0) or 0)
        area_ha = round(area_m2 / 10_000, 4)

        logger.info(
            "detect_water_bodies: %.2f ha detected (threshold=%.2f).",
            area_ha, threshold,
        )
        return {
            "water_area_ha": area_ha,
            "water_mask":    water_mask,
            "threshold":     threshold,
        }

    except Exception as exc:
        logger.error("detect_water_bodies failed: %s", exc)
        return None


# =============================================================================
# 9. TIMESERIES GENERATORS
# =============================================================================
# NOTE: Every GEE API call takes 2-5 s. A full 8-year series = 30-40 s.
# Always pass results through gee_engine.cache_gee_result() and display
# an st.progress() bar in app.py during computation.

_MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def generate_ndvi_timeseries(
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
    buffer_km: float = 5,
    geometry=None,
) -> Optional[List[Dict]]:
    """
    Build a year-by-year NDVI timeseries using monsoon-season composites.

    For each year a cloud-filtered Sentinel-2 median composite is built for
    the Indian monsoon window (June 1 – October 31), NDVI is calculated, and
    the spatial mean is extracted over the buffered AOI.

    Args:
        lat, lon    : Centre of the watershed (decimal degrees).
        start_year  : First year of the series (inclusive).
        end_year    : Last year of the series (inclusive).
        buffer_km   : AOI radius in km (default 5).

    Returns:
        List of dicts sorted by year::

            [
              {"year": 2019, "ndvi_mean": 0.38, "ndvi_min": 0.05, "ndvi_max": 0.71},
              {"year": 2020, "ndvi_mean": 0.43, ...},
              ...
            ]

        Returns None if every year fails (dashboard falls back to demo data).
        Years where the GEE call fails are silently skipped.
    """
    if not _ee_ready():
        return None

    try:
        if geometry is None:
            from backend.gee_engine import _make_geometry
            geometry = _make_geometry(lat, lon, buffer_km * 1000)
    except Exception as exc:
        logger.error("generate_ndvi_timeseries: geometry creation failed: %s", exc)
        return None

    results: List[Dict] = []

    for year in range(start_year, end_year + 1):
        try:
            start_date = f"{year}-06-01"
            end_date   = f"{year}-10-31"

            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(geometry)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )

            composite = collection.median().clip(geometry)
            ndvi_img   = calculate_ndvi(composite)
            if ndvi_img is None:
                continue

            stats = ndvi_img.reduceRegion(
                reducer=(
                    ee.Reducer.mean()
                    .combine(ee.Reducer.min(), sharedInputs=True)
                    .combine(ee.Reducer.max(), sharedInputs=True)
                ),
                geometry=geometry,
                scale=10,
                maxPixels=1e9,
            ).getInfo()

            ndvi_mean = stats.get("NDVI_mean") or stats.get("nd_mean")
            ndvi_min  = stats.get("NDVI_min")  or stats.get("nd_min")
            ndvi_max  = stats.get("NDVI_max")  or stats.get("nd_max")

            if ndvi_mean is None:
                logger.warning("generate_ndvi_timeseries: no mean for %d.", year)
                continue

            results.append({
                "year":      year,
                "ndvi_mean": round(float(ndvi_mean), 4),
                "ndvi_min":  round(float(ndvi_min),  4) if ndvi_min  is not None else None,
                "ndvi_max":  round(float(ndvi_max),  4) if ndvi_max  is not None else None,
            })
            logger.info("generate_ndvi_timeseries: %d -> NDVI mean=%.4f", year, ndvi_mean)

        except Exception as exc:
            logger.error(
                "generate_ndvi_timeseries: year %d failed (%s), skipping.", year, exc
            )
            continue

    if not results:
        logger.error("generate_ndvi_timeseries: all years failed — returning None.")
        return None

    return sorted(results, key=lambda r: r["year"])


def generate_water_timeseries(
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
    buffer_km: float = 5,
    geometry=None,
) -> Optional[List[Dict]]:
    """
    Build a year-by-year water-body area timeseries using post-monsoon composites.

    Post-monsoon (October – November) is used because water retention at this
    point best measures the effectiveness of the watershed structures: harvested
    water should still be present in tanks, check-dams, and percolation ponds.

    Args:
        lat, lon    : Centre of the watershed (decimal degrees).
        start_year  : First year of the series (inclusive).
        end_year    : Last year of the series (inclusive).
        buffer_km   : AOI radius in km (default 5).

    Returns:
        List of dicts sorted by year::

            [
              {"year": 2019, "ndwi_mean": -0.10, "water_area_ha": 2.5},
              {"year": 2020, "ndwi_mean":  0.05, "water_area_ha": 7.1},
              ...
            ]

        Returns None if every year fails.
    """
    if not _ee_ready():
        return None

    try:
        if geometry is None:
            from backend.gee_engine import _make_geometry
            geometry = _make_geometry(lat, lon, buffer_km * 1000)
    except Exception as exc:
        logger.error("generate_water_timeseries: geometry creation failed: %s", exc)
        return None

    results: List[Dict] = []

    for year in range(start_year, end_year + 1):
        try:
            # Post-monsoon window: October-November
            start_date = f"{year}-10-01"
            end_date   = f"{year}-11-30"

            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(geometry)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )

            count = collection.size().getInfo()
            if count == 0:
                logger.info(
                    "generate_water_timeseries: year %d — 0 images, skipping.",
                    year
                )
                continue

            composite = collection.median().clip(geometry)

            # -- NDWI mean and Water Area ------------------------------------
            ndwi_img = calculate_ndwi(composite)
            if ndwi_img is None:
                continue

            water_area = (
                ndwi_img.gt(0.0)
                .multiply(ee.Image.pixelArea())
                .rename("water_area_m2")
            )

            stats_image = ee.Image.cat([
                ndwi_img.rename("NDWI"),
                water_area,
            ])

            stats = stats_image.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    ee.Reducer.sum(),
                    sharedInputs=False,
                ),
                geometry=geometry,
                scale=10,
                maxPixels=1e9,
                bestEffort=True,
            ).getInfo()

            ndwi_mean = (
                stats.get("NDWI_mean")
                or stats.get("mean")
                or stats.get("nd_mean")
            )
            if ndwi_mean is None:
                logger.info("generate_water_timeseries: no data for %d, skipping.", year)
                continue

            area_m2 = float(
                stats.get("water_area_m2_sum")
                or stats.get("sum")
                or 0
            )
            area_ha = round(area_m2 / 10_000, 4)

            results.append({
                "year":         year,
                "ndwi_mean":    round(float(ndwi_mean), 4) if ndwi_mean is not None else None,
                "water_area_ha": area_ha,
            })
            logger.info(
                "generate_water_timeseries: %d -> water=%.2f ha, ndwi_mean=%.4f",
                year, area_ha, ndwi_mean or 0,
            )

        except Exception as exc:
            logger.error(
                "generate_water_timeseries: year %d failed — skipping.",
                year,
                exc_info=True,
            )
            continue

    if not results:
        logger.error("generate_water_timeseries: all years failed — returning None.")
        return None

    return sorted(results, key=lambda r: r["year"])


def generate_monthly_ndvi(
    lat: float,
    lon: float,
    year: int,
    buffer_km: float = 5,
) -> Optional[List[Dict]]:
    """
    Build a month-by-month NDVI profile for a given calendar year.

    Each month's Sentinel-2 median composite is used, cloud-filtered to < 20%.
    If a month has no usable images the entry is still included with
    ``ndvi_mean: None`` so the chart has a full 12-point x-axis.

    The seasonal curve reveals how long the post-monsoon greenness lasts:
    a successful watershed project shows elevated NDVI extending into
    November and December compared to the baseline year.

    Args:
        lat, lon  : Centre of the watershed (decimal degrees).
        year      : Calendar year to profile.
        buffer_km : AOI radius in km (default 5).

    Returns:
        List of 12 dicts::

            [
              {"month": 1, "month_name": "Jan", "ndvi_mean": 0.25},
              {"month": 2, "month_name": "Feb", "ndvi_mean": 0.22},
              ...
              {"month": 12, "month_name": "Dec", "ndvi_mean": 0.31},
            ]

        Returns None if GEE is unavailable or the geometry cannot be created.
    """
    if not _ee_ready():
        return None

    try:
        from backend.gee_engine import _make_geometry
        geometry = _make_geometry(lat, lon, buffer_km * 1000)
    except Exception as exc:
        logger.error("generate_monthly_ndvi: geometry creation failed: %s", exc)
        return None

    results: List[Dict] = []

    for month in range(1, 13):
        month_name = _MONTH_ABBR[month - 1]
        entry: Dict = {"month": month, "month_name": month_name, "ndvi_mean": None}

        try:
            # Build ISO date range for the month
            start_date = f"{year}-{month:02d}-01"
            if month == 12:
                end_date = f"{year + 1}-01-01"
            else:
                end_date = f"{year}-{month + 1:02d}-01"

            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(geometry)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )

            count = collection.size().getInfo()
            if count == 0:
                logger.info(
                    "generate_monthly_ndvi: no images for %d-%02d, using None.",
                    year, month,
                )
                results.append(entry)
                continue

            composite = collection.median().clip(geometry)
            ndvi_img  = calculate_ndvi(composite)
            if ndvi_img is None:
                results.append(entry)
                continue

            stats = ndvi_img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=10,
                maxPixels=1e9,
            ).getInfo()

            ndvi_val = stats.get("NDVI") or stats.get("nd")
            if ndvi_val is not None:
                entry["ndvi_mean"] = round(float(ndvi_val), 4)

            logger.info(
                "generate_monthly_ndvi: %d-%02d -> NDVI mean=%s",
                year, month, entry["ndvi_mean"],
            )

        except Exception as exc:
            logger.error(
                "generate_monthly_ndvi: month %d/%d failed (%s), using None.",
                month, year, exc,
            )

        results.append(entry)

    return results
