"""
data/validate_open_vs_live.py
==============================
AquaVeda -- Local Open Mode vs Live Snapshot Validator

Reads data/live_snapshot.json (produced by generate_open_mode_from_live.py)
and the four Open Mode JSON files, then compares every SYNCHRONIZED field.

This script makes ZERO GEE API calls.

Classification
--------------
SYNCHRONIZED (compared):
  - change_data: vegetation.*, water.area_*/change_*, erosion.*
  - health_scores: total_score, *_score, grade, grade_emoji
  - ndvi_timeseries: year, ndvi_mean, ndvi_min, ndvi_max
  - water_timeseries: year, ndwi_mean, water_area_ha

OPEN-ONLY (not compared -- expected to differ):
  - change_data: landuse, water.months_with_water_*, water.new_water_bodies
  - health_scores: recommendations (text; not numerically verified)
  - monthly_ndvi, rainfall, before/after imagery

Usage:
    python data/validate_open_vs_live.py
    echo $?   # 0 = all PASS, 1 = one or more FAIL

Tolerance:
    Float comparisons use math.isclose(rel_tol=1e-3, abs_tol=1e-3) which
    accounts for the rounding already applied inside backend/ modules.
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# -- Paths ---------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SNAPSHOT_PATH      = os.path.join(_SCRIPT_DIR, "live_snapshot.json")
CHANGE_DATA_PATH   = os.path.join(_SCRIPT_DIR, "change_data.json")
HEALTH_SCORES_PATH = os.path.join(_SCRIPT_DIR, "health_scores.json")
NDVI_TS_PATH       = os.path.join(_SCRIPT_DIR, "ndvi_timeseries.json")
WATER_TS_PATH      = os.path.join(_SCRIPT_DIR, "water_timeseries.json")

_ABS_TOL = 1e-3
_REL_TOL = 1e-3

# =============================================================================
# HELPERS
# =============================================================================

PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compare(
    label: str,
    expected: Any,
    actual: Any,
) -> bool:
    global PASS_COUNT, FAIL_COUNT
    # Both None -- treat as match
    if expected is None and actual is None:
        PASS_COUNT += 1
        print(f"  PASS  {label} = None")
        return True

    # One is None
    if expected is None or actual is None:
        FAIL_COUNT += 1
        print(f"  FAIL  {label}: expected={expected!r}, actual={actual!r}")
        return False

    # Numeric float
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            e, a = float(expected), float(actual)
            if math.isclose(e, a, rel_tol=_REL_TOL, abs_tol=_ABS_TOL):
                PASS_COUNT += 1
                print(f"  PASS  {label}: snapshot={e}, open_mode={a}")
                return True
            else:
                FAIL_COUNT += 1
                print(
                    f"  FAIL  {label}: snapshot={e}, open_mode={a} "
                    f"(diff={abs(e-a):.6f})"
                )
                return False
        except (TypeError, ValueError):
            pass

    # Integer / other
    if expected == actual:
        PASS_COUNT += 1
        print(f"  PASS  {label}: {expected!r}")
        return True
    else:
        FAIL_COUNT += 1
        print(f"  FAIL  {label}: snapshot={expected!r}, open_mode={actual!r}")
        return False


def _skip(label: str, reason: str) -> None:
    global SKIP_COUNT
    SKIP_COUNT += 1
    print(f"  SKIP  {label} -- {reason}")


# =============================================================================
# SECTION VALIDATORS
# =============================================================================

def _validate_vegetation(ws_id: str, snap_veg: Dict, open_veg: Dict) -> None:
    fields = [
        "ndvi_before", "ndvi_after", "change",
        "improved_area_ha", "declined_area_ha", "unchanged_area_ha",
        "percent_improved",
    ]
    for f in fields:
        _compare(f"{ws_id}.vegetation.{f}", snap_veg.get(f), open_veg.get(f))


def _validate_water(ws_id: str, snap_wat: Dict, open_wat: Dict) -> None:
    synchronized_fields = ["area_before_ha", "area_after_ha", "change_ha", "change_percent"]
    for f in synchronized_fields:
        _compare(f"{ws_id}.water.{f}", snap_wat.get(f), open_wat.get(f))
    # OPEN-ONLY: skip
    for f in ["new_water_bodies", "months_with_water_before", "months_with_water_after"]:
        _skip(f"{ws_id}.water.{f}", "OPEN-ONLY: not computed in Live Mode")


def _validate_erosion(ws_id: str, snap_ero: Dict, open_ero: Dict) -> None:
    for f in ["high_risk_before_ha", "high_risk_after_ha", "reduction_percent"]:
        _compare(f"{ws_id}.erosion.{f}", snap_ero.get(f), open_ero.get(f))
    # classes_before / classes_after -- compare each class
    for period in ("classes_before", "classes_after"):
        snap_cls = snap_ero.get(period, {})
        open_cls = open_ero.get(period, {})
        all_keys = set(snap_cls) | set(open_cls)
        for k in sorted(all_keys):
            _compare(
                f"{ws_id}.erosion.{period}.{k}",
                snap_cls.get(k),
                open_cls.get(k),
            )


def _validate_health(ws_id: str, snap_hs: Dict, open_hs: Dict) -> None:
    for f in [
        "total_score", "vegetation_score", "water_score",
        "erosion_score", "sustainability_score",
    ]:
        _compare(f"{ws_id}.health.{f}", snap_hs.get(f), open_hs.get(f))
    # Grade is a string -- direct equality
    _compare(f"{ws_id}.health.grade", snap_hs.get("grade"), open_hs.get("grade"))
    _compare(
        f"{ws_id}.health.grade_emoji",
        snap_hs.get("grade_emoji"),
        open_hs.get("grade_emoji"),
    )
    # Recommendations are text -- skip numeric comparison
    _skip(f"{ws_id}.health.recommendations", "OPEN-ONLY: text, not numerically compared")


def _validate_ndvi_ts(
    ws_id: str, snap_ts: List[Dict], open_ts: List[Dict]
) -> None:
    if len(snap_ts) != len(open_ts):
        global FAIL_COUNT
        FAIL_COUNT += 1
        print(
            f"  FAIL  {ws_id}.ndvi_timeseries: "
            f"length mismatch snapshot={len(snap_ts)}, open_mode={len(open_ts)}"
        )
        return

    snap_by_year = {r["year"]: r for r in snap_ts}
    open_by_year = {r["year"]: r for r in open_ts}
    all_years    = sorted(set(snap_by_year) | set(open_by_year))

    for yr in all_years:
        sv = snap_by_year.get(yr, {})
        ov = open_by_year.get(yr, {})
        for f in ["ndvi_mean", "ndvi_min", "ndvi_max"]:
            _compare(f"{ws_id}.ndvi_ts[{yr}].{f}", sv.get(f), ov.get(f))


def _validate_water_ts(
    ws_id: str, snap_ts: List[Dict], open_ts: List[Dict]
) -> None:
    if len(snap_ts) != len(open_ts):
        global FAIL_COUNT
        FAIL_COUNT += 1
        print(
            f"  FAIL  {ws_id}.water_timeseries: "
            f"length mismatch snapshot={len(snap_ts)}, open_mode={len(open_ts)}"
        )
        return

    snap_by_year = {r["year"]: r for r in snap_ts}
    open_by_year = {r["year"]: r for r in open_ts}
    all_years    = sorted(set(snap_by_year) | set(open_by_year))

    for yr in all_years:
        sv = snap_by_year.get(yr, {})
        ov = open_by_year.get(yr, {})
        for f in ["ndwi_mean", "water_area_ha"]:
            _compare(f"{ws_id}.water_ts[{yr}].{f}", sv.get(f), ov.get(f))


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    print("=" * 72)
    print("AquaVeda -- Open Mode vs Live Snapshot Validator")
    print("No GEE calls are made by this script.")
    print("=" * 72)

    # -- Load files ------------------------------------------------------------
    snapshot   = _load_json(SNAPSHOT_PATH)
    change_all = _load_json(CHANGE_DATA_PATH)
    health_all = _load_json(HEALTH_SCORES_PATH)
    ndvi_all   = _load_json(NDVI_TS_PATH)
    water_all  = _load_json(WATER_TS_PATH)

    meta = snapshot.get("_meta", {})
    print(f"Snapshot generated : {meta.get('generated_at', 'unknown')}")
    print(f"Tolerance          : rel={_REL_TOL}, abs={_ABS_TOL}")
    print()

    ws_ids = [k for k in snapshot if not k.startswith("_")]

    for ws_id in ws_ids:
        print(f"\n{'-' * 60}")
        print(f"Watershed: {ws_id}")
        print(f"{'-' * 60}")

        snap = snapshot[ws_id]
        snap_cr   = snap.get("change_result", {})
        snap_hs   = snap.get("health_score", {})
        snap_ndvi = snap.get("ndvi_timeseries", [])
        snap_wat  = snap.get("water_timeseries", [])

        open_cd   = change_all.get(ws_id, {})
        open_hs   = health_all.get(ws_id, {})
        open_ndvi = ndvi_all.get(ws_id, [])
        open_wat  = water_all.get(ws_id, [])

        # -- SYNCHRONIZED sections -------------------------------------------
        print("\n  [Vegetation]")
        _validate_vegetation(ws_id, snap_cr.get("vegetation", {}), open_cd.get("vegetation", {}))

        print("\n  [Water]")
        _validate_water(ws_id, snap_cr.get("water", {}), open_cd.get("water", {}))

        print("\n  [Erosion]")
        _validate_erosion(ws_id, snap_cr.get("erosion", {}), open_cd.get("erosion", {}))

        print("\n  [Health Score]")
        _validate_health(ws_id, snap_hs, open_hs)

        print("\n  [NDVI Timeseries]")
        _validate_ndvi_ts(ws_id, snap_ndvi, open_ndvi)

        print("\n  [Water Timeseries]")
        _validate_water_ts(ws_id, snap_wat, open_wat)

        # -- OPEN-ONLY (explicit skip log) ------------------------------------
        print("\n  [Open-Only Fields -- not compared]")
        _skip(f"{ws_id}.change_data.landuse", "OPEN-ONLY: K-Means, not in Live pipeline")
        _skip(f"{ws_id}.monthly_ndvi",        "OPEN-ONLY: not computed in Live Mode")
        _skip(f"{ws_id}.rainfall",            "OPEN-ONLY: not computed in Live Mode")
        _skip(f"{ws_id}.before_after_imagery","Live=GEE tiles; Open=local PNG assets (not comparable)")

    # -- Summary ---------------------------------------------------------------
    print()
    print("=" * 72)
    total = PASS_COUNT + FAIL_COUNT + SKIP_COUNT
    print(
        f"RESULTS:  {PASS_COUNT} PASS  |  {FAIL_COUNT} FAIL  |  "
        f"{SKIP_COUNT} SKIP  |  {total} total"
    )
    if FAIL_COUNT == 0:
        print("STATUS: ALL SYNCHRONIZED FIELDS PASS")
    else:
        print(f"STATUS: {FAIL_COUNT} FIELD(S) FAILED -- "
              "review the output above and rerun generate_open_mode_from_live.py if needed.")
    print("=" * 72)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
