"""
backend/health_score.py
=======================
Watershed health scoring engine for AquaVeda.

Converts satellite change-detection metrics into a single 0-100 health score
with letter grade, sub-scores, and actionable recommendations.

Output schema matches data/health_scores.json exactly so the dashboard can
swap live and demo scores transparently.

Scoring rubric (total 100 points)
----------------------------------
  Vegetation (NDVI change)  : 0-35 pts
  Water retention change    : 0-35 pts
  Erosion risk reduction    : 0-20 pts
  Trend sustainability      : 0-10 pts
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_HEALTH_SCORES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "health_scores.json",
)


# =============================================================================
# 1. RECOMMENDATION GENERATOR
# =============================================================================

def generate_recommendations(
    veg_score: int,
    water_score: int,
    erosion_score: int,
    sust_score: int,
    change_data: Dict[str, Any],
) -> List[str]:
    """
    Generate a prioritised list of actionable recommendations based on
    which sub-scores are below their respective thresholds.

    Args:
        veg_score     : Vegetation sub-score (0-35).
        water_score   : Water retention sub-score (0-35).
        erosion_score : Erosion risk reduction sub-score (0-20).
        sust_score    : Trend sustainability sub-score (0-10).
        change_data   : Full change-detection dict (for context-sensitive tips).

    Returns:
        List of recommendation strings (never empty — always at least one entry).
    """
    recommendations: List[str] = []

    # -- Vegetation -----------------------------------------------------------
    if veg_score < 15:
        recommendations.append(
            "Plant native species on barren patches — indigenous drought-resistant "
            "varieties (Acacia, Prosopis, Pongamia) establish faster in arid zones."
        )
        recommendations.append(
            "Launch an agroforestry program to combine crop income with permanent "
            "vegetation cover on degraded slopes."
        )
    elif veg_score < 25:
        recommendations.append(
            "Vegetation improving but pace needs acceleration — add contour trenches "
            "at 3 m vertical intervals on slopes to increase soil moisture retention."
        )

    # -- Water ----------------------------------------------------------------
    if water_score < 12:
        recommendations.append(
            "Water retention critically insufficient — inspect all check dams for "
            "structural damage and repair silt escape channels before monsoon."
        )
        recommendations.append(
            "Farm ponds losing water to seepage — consider HDPE lining for the "
            "two largest ponds to increase effective storage by 40-60%."
        )
    elif water_score < 20:
        recommendations.append(
            "Water area growing slowly — construct 2-3 additional percolation tanks "
            "in the upper catchment to recharge the aquifer during peak monsoon."
        )

    # -- Erosion --------------------------------------------------------------
    if erosion_score < 10:
        recommendations.append(
            "Soil erosion still high — extend contour bunding across all slopes "
            "exceeding 15 degrees to break runoff velocity."
        )
        recommendations.append(
            "Build gabion structures at identified active gully heads before next "
            "monsoon to prevent gully extension into productive farmland."
        )
    elif erosion_score < 15:
        recommendations.append(
            "Erosion reduction progressing — prioritise live brush check-dams in "
            "seasonal stream channels to trap sediment before it reaches reservoirs."
        )

    # -- Sustainability / trend -----------------------------------------------
    if sust_score < 5:
        recommendations.append(
            "Improvement trend is inconsistent across years — organise community "
            "maintenance training to ensure structures are repaired between seasons."
        )

    # -- All good -------------------------------------------------------------
    if not recommendations:
        recommendations.append(
            "Project performing well across all indicators — maintain current "
            "maintenance schedule and document practices for knowledge transfer."
        )
        recommendations.append(
            "Consider replicating the most successful interventions in the "
            "neighbouring sub-watershed to amplify catchment-level impact."
        )

    return recommendations


# =============================================================================
# 2. MAIN SCORING FUNCTION
# =============================================================================

def calculate_watershed_health(
    change_data: Dict[str, Any],
    timeseries_data: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Calculate a composite watershed health score from change-detection metrics.

    Args:
        change_data     : Dict matching the schema of ``data/change_data.json``,
                          i.e. with top-level keys ``vegetation``, ``water``,
                          ``erosion``.  Either live GEE output or demo data.
        timeseries_data : Optional list of annual NDVI records produced by
                          ``indices.generate_ndvi_timeseries()``. Each record
                          must have an ``"ndvi_mean"`` key. At least 4 records
                          are needed for a meaningful sustainability score;
                          fewer defaults to neutral (5 pts).

    Returns:
        dict matching ``data/health_scores.json`` schema::

            {
                "total_score":          78,
                "grade":                "Good",
                "grade_emoji":          "🟡",
                "vegetation_score":     28,
                "water_score":          28,
                "erosion_score":        15,
                "sustainability_score": 7,
                "recommendations":      ["...", "..."],
            }
    """
    # -------------------------------------------------------------------------
    # Safe accessor — returns 0.0 if key is missing / None
    # -------------------------------------------------------------------------
    def _safe(section: str, key: str, default: float = 0.0) -> float:
        try:
            val = change_data.get(section, {}).get(key, default)
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    # =========================================================================
    # 1. VEGETATION SCORE (max 35)
    # =========================================================================
    ndvi_change = _safe("vegetation", "change")

    if ndvi_change > 0.20:
        veg_score = 35
    elif ndvi_change > 0.15:
        veg_score = 30
    elif ndvi_change > 0.10:
        veg_score = 25
    elif ndvi_change > 0.05:
        veg_score = 15
    elif ndvi_change > 0.00:
        veg_score = 8
    else:
        veg_score = 0

    # =========================================================================
    # 2. WATER SCORE (max 35)
    # =========================================================================
    water_change_pct = _safe("water", "change_percent")

    if water_change_pct > 200:
        water_score = 35
    elif water_change_pct > 100:
        water_score = 28
    elif water_change_pct > 50:
        water_score = 20
    elif water_change_pct > 10:
        water_score = 12
    elif water_change_pct > 0:
        water_score = 5
    else:
        water_score = 0

    # =========================================================================
    # 3. EROSION SCORE (max 20)
    # =========================================================================
    erosion_reduction = _safe("erosion", "reduction_percent")

    if erosion_reduction > 50:
        erosion_score = 20
    elif erosion_reduction > 30:
        erosion_score = 15
    elif erosion_reduction > 15:
        erosion_score = 10
    elif erosion_reduction > 0:
        erosion_score = 5
    else:
        erosion_score = 0

    # =========================================================================
    # 4. SUSTAINABILITY SCORE (max 10)
    # =========================================================================
    sustainability_score = 5  # neutral default when no timeseries

    if timeseries_data is not None and len(timeseries_data) >= 4:
        try:
            ndvi_values = [
                float(d["ndvi_mean"])
                for d in timeseries_data
                if d.get("ndvi_mean") is not None
            ]
            if len(ndvi_values) >= 4:
                # Count years where NDVI improved over the previous year
                improving_years = sum(
                    1
                    for i in range(1, len(ndvi_values))
                    if ndvi_values[i] > ndvi_values[i - 1]
                )
                consistency = improving_years / (len(ndvi_values) - 1)

                if consistency > 0.8:
                    sustainability_score = 10
                elif consistency > 0.6:
                    sustainability_score = 7
                elif consistency > 0.4:
                    sustainability_score = 5
                else:
                    sustainability_score = 3
        except Exception as exc:
            logger.warning(
                "calculate_watershed_health: sustainability calc error: %s", exc
            )

    # =========================================================================
    # 5. TOTAL & GRADE
    # =========================================================================
    total_score = veg_score + water_score + erosion_score + sustainability_score
    total_score = min(100, max(0, total_score))  # clamp 0-100

    if total_score >= 80:
        grade, emoji = "Excellent", "✅"
    elif total_score >= 60:
        grade, emoji = "Good", "🟡"
    elif total_score >= 40:
        grade, emoji = "Average", "🟠"
    else:
        grade, emoji = "Poor", "🔴"

    # =========================================================================
    # 6. RECOMMENDATIONS
    # =========================================================================
    recommendations = generate_recommendations(
        veg_score, water_score, erosion_score, sustainability_score, change_data
    )

    result = {
        "total_score":          total_score,
        "grade":                grade,
        "grade_emoji":          emoji,
        "vegetation_score":     veg_score,
        "water_score":          water_score,
        "erosion_score":        erosion_score,
        "sustainability_score": sustainability_score,
        "recommendations":      recommendations,
    }

    logger.info(
        "calculate_watershed_health: score=%d (%s) | veg=%d water=%d "
        "erosion=%d sust=%d | recs=%d",
        total_score, grade,
        veg_score, water_score, erosion_score, sustainability_score,
        len(recommendations),
    )

    return result


# =============================================================================
# 3. DEMO FALLBACK
# =============================================================================

def get_demo_health_score(watershed_id: str) -> Dict[str, Any]:
    """
    Load a pre-computed health score from ``data/health_scores.json``.

    Used when GEE is unavailable or when the user wants the instant demo
    view without waiting for live computation.

    Args:
        watershed_id : Key into health_scores.json, e.g. ``"hiware_bazar"``.

    Returns:
        Health score dict matching the ``calculate_watershed_health()`` schema,
        or a neutral default dict if the key / file is not found.
    """
    try:
        with open(_HEALTH_SCORES_PATH, "r", encoding="utf-8") as fh:
            all_scores: Dict[str, Any] = json.load(fh)

        if watershed_id in all_scores:
            logger.info("get_demo_health_score: loaded '%s' from cache.", watershed_id)
            return all_scores[watershed_id]

        # Fallback to first available entry
        if all_scores:
            first_key = next(iter(all_scores))
            logger.warning(
                "get_demo_health_score: '%s' not found, using '%s'.",
                watershed_id, first_key,
            )
            return all_scores[first_key]

    except FileNotFoundError:
        logger.error(
            "get_demo_health_score: health_scores.json not found at %s",
            _HEALTH_SCORES_PATH,
        )
    except Exception as exc:
        logger.error("get_demo_health_score failed: %s", exc)

    # Hard-coded neutral fallback so the dashboard never crashes
    return {
        "total_score":          50,
        "grade":                "Average",
        "grade_emoji":          "🟠",
        "vegetation_score":     15,
        "water_score":          15,
        "erosion_score":        10,
        "sustainability_score": 10,
        "recommendations":      ["Health score data unavailable — running in demo mode."],
    }
