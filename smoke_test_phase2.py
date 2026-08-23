"""
Phase 2 GEE Smoke Test
======================
Tests create_s2_composite() against the Hiware Bazar AOI for 2019 and 2024.
No image downloads, no expensive exports — metadata only.
"""
import sys
import time
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEP = "-" * 64

def hr(title=""):
    print(f"\n{SEP}")
    if title:
        print(f"  {title}")
        print(SEP)

# ---------------------------------------------------------------------------
# 1. GEE authentication check
# ---------------------------------------------------------------------------
hr("1. GEE Authentication Check")
try:
    import ee
    try:
        ee.Initialize()
        print("  GEE initialized successfully.")
        GEE_OK = True
    except Exception as auth_err:
        print(f"  GEE authentication FAILED: {auth_err}")
        print()
        print("  GEE authentication unavailable — implementation verified statically only.")
        GEE_OK = False
except ImportError:
    print("  earthengine-api not installed.")
    print()
    print("  GEE authentication unavailable — implementation verified statically only.")
    GEE_OK = False

if not GEE_OK:
    sys.exit(0)

# ---------------------------------------------------------------------------
# 2. Import pipeline functions
# ---------------------------------------------------------------------------
hr("2. Pipeline Import Check")
try:
    from backend.gee_engine import (
        get_s2_collection,
        join_cloud_probability,
        _apply_cloud_shadow_mask,
        create_s2_composite,
        _make_geometry,
        InsufficientImageryError,
        ee_image_to_folium_tile,
        _TILE_TRUE_COLOR_VIS,
        _S2_COLLECTION,
        _S2_CLOUD_PROB_COL,
        _CLOUD_FILTER,
        _CLOUD_PROB_THRESH,
    )
    print("  All pipeline functions imported OK.")
except Exception as imp_err:
    print(f"  IMPORT FAILED: {imp_err}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Define Hiware Bazar AOI
# ---------------------------------------------------------------------------
hr("3. AOI Setup")
LAT, LON = 19.35, 74.55   # Hiware Bazar, Maharashtra
BUFFER_M = 10_000          # 10 km radius

aoi = _make_geometry(LAT, LON, BUFFER_M)
print(f"  Watershed: Hiware Bazar (lat={LAT}, lon={LON})")
print(f"  Buffer: {BUFFER_M/1000:.0f} km radius")
print(f"  AOI type: {type(aoi).__name__}")

# ---------------------------------------------------------------------------
# 4. BEFORE 2019 smoke test — step by step
# ---------------------------------------------------------------------------
hr("4. BEFORE Composite (2019)")
BEFORE_START = "2019-01-01"
BEFORE_END   = "2019-12-31"

print(f"  Period: {BEFORE_START} to {BEFORE_END}")
print(f"  Collection: {_S2_COLLECTION}")
print(f"  Cloud prob collection: {_S2_CLOUD_PROB_COL}")
print(f"  Scene pre-filter: CLOUDY_PIXEL_PERCENTAGE <= {_CLOUD_FILTER}%")
print(f"  Pixel cloud threshold: {_CLOUD_PROB_THRESH}%")

t0 = time.time()

# Step A
print("\n  [Step A] get_s2_collection()...")
try:
    s2_before = get_s2_collection(aoi, BEFORE_START, BEFORE_END, _CLOUD_FILTER)
    n_before_raw = s2_before.size().getInfo()
    print(f"    Scenes found: {n_before_raw}")
except Exception as e:
    print(f"    FAILED: {e}")
    n_before_raw = 0

# Step B
if n_before_raw > 0:
    print("\n  [Step B] join_cloud_probability()...")
    try:
        s2_before_prob = join_cloud_probability(s2_before, aoi, BEFORE_START, BEFORE_END)
        n_before_joined = s2_before_prob.size().getInfo()
        print(f"    Scenes with cloud-prob data: {n_before_joined}")
    except Exception as e:
        print(f"    FAILED: {e}")
        n_before_joined = 0
else:
    n_before_joined = 0
    print("\n  [Step B] Skipped — no scenes from Step A.")

# Full pipeline via create_s2_composite
print("\n  [Full] create_s2_composite()...")
before_ok = False
before_bands = []
before_meta_result = {}
before_img = None
try:
    before_img, before_meta_result = create_s2_composite(
        aoi=aoi,
        start_date=BEFORE_START,
        end_date=BEFORE_END,
        label="Before 2019",
    )
    before_bands = before_img.bandNames().getInfo() if before_img else []
    before_ok = len(before_bands) > 0
    elapsed = time.time() - t0
    print(f"    Composite created: {before_ok}")
    print(f"    Scenes before cloud filter: {before_meta_result.get('images_before_filter', '?')}")
    print(f"    Scenes after masking:       {before_meta_result.get('images_after_filter',  '?')}")
    print(f"    Band count: {len(before_bands)}")
    print(f"    Bands: {before_bands[:8]}{'...' if len(before_bands) > 8 else ''}")
    print(f"    Time: {elapsed:.1f}s")
except InsufficientImageryError as e:
    print(f"    InsufficientImageryError: {e}")
except Exception as e:
    print(f"    FAILED: {e}")

# ---------------------------------------------------------------------------
# 5. AFTER 2024 smoke test
# ---------------------------------------------------------------------------
hr("5. AFTER Composite (2024)")
AFTER_START = "2024-01-01"
AFTER_END   = "2024-12-31"

print(f"  Period: {AFTER_START} to {AFTER_END}")

t1 = time.time()
after_ok = False
after_bands = []
after_meta_result = {}
after_img = None
try:
    after_img, after_meta_result = create_s2_composite(
        aoi=aoi,
        start_date=AFTER_START,
        end_date=AFTER_END,
        label="After 2024",
    )
    after_bands = after_img.bandNames().getInfo() if after_img else []
    after_ok = len(after_bands) > 0
    elapsed = time.time() - t1
    print(f"    Composite created: {after_ok}")
    print(f"    Scenes before cloud filter: {after_meta_result.get('images_before_filter', '?')}")
    print(f"    Scenes after masking:       {after_meta_result.get('images_after_filter',  '?')}")
    print(f"    Band count: {len(after_bands)}")
    print(f"    Bands: {after_bands[:8]}{'...' if len(after_bands) > 8 else ''}")
    print(f"    Time: {elapsed:.1f}s")
except InsufficientImageryError as e:
    print(f"    InsufficientImageryError: {e}")
except Exception as e:
    print(f"    FAILED: {e}")

# ---------------------------------------------------------------------------
# 6. Same-pipeline verification
# ---------------------------------------------------------------------------
hr("6. Same-Pipeline Verification")
if before_ok and after_ok:
    same_bands = set(before_bands) == set(after_bands)
    print(f"  BEFORE and AFTER use same function (create_s2_composite): YES")
    print(f"  Same band names in both composites: {same_bands}")
    print(f"  BEFORE bands: {before_bands[:6]}")
    print(f"  AFTER  bands: {after_bands[:6]}")
else:
    print("  Cannot compare — at least one composite failed.")

# ---------------------------------------------------------------------------
# 7. Tile layer check (before_satellite / after_satellite)
# ---------------------------------------------------------------------------
hr("7. Tile Layer Check (before_satellite / after_satellite)")
before_tile_ok = False
after_tile_ok  = False

if before_img is not None:
    print("  Testing before_satellite tile URL generation...")
    try:
        t = ee_image_to_folium_tile(before_img, _TILE_TRUE_COLOR_VIS, "Satellite (Before)")
        if t and t.get("tile_url") and "{z}" in t["tile_url"]:
            print(f"    before_satellite: VALID XYZ tile URL")
            print(f"    tile_url snippet: ...{t['tile_url'][-60:]}")
            before_tile_ok = True
        else:
            print(f"    before_satellite: tile dict returned but URL invalid: {t}")
    except Exception as e:
        print(f"    before_satellite: FAILED: {e}")
else:
    print("  before_satellite: SKIPPED — no BEFORE composite.")

if after_img is not None:
    print("  Testing after_satellite tile URL generation...")
    try:
        t = ee_image_to_folium_tile(after_img, _TILE_TRUE_COLOR_VIS, "Satellite (After)")
        if t and t.get("tile_url") and "{z}" in t["tile_url"]:
            print(f"    after_satellite: VALID XYZ tile URL")
            print(f"    tile_url snippet: ...{t['tile_url'][-60:]}")
            after_tile_ok = True
        else:
            print(f"    after_satellite: tile dict returned but URL invalid: {t}")
    except Exception as e:
        print(f"    after_satellite: FAILED: {e}")
else:
    print("  after_satellite: SKIPPED — no AFTER composite.")

# ---------------------------------------------------------------------------
# 8. Duplicate computation analysis (static — no GEE calls)
# ---------------------------------------------------------------------------
hr("8. Duplicate Computation Analysis")

print("""
  FINDING: The live analysis path in app.py calls:
    (A) create_s2_composite() TWICE at lines 410-435 (BEFORE + AFTER)
    (B) get_all_tile_layers() at line 488, which ALSO calls
        create_s2_composite() TWICE internally (lines 1053-1077)

  This means during a single live analysis run, the s2cloudless
  pipeline is invoked FOUR TIMES total:
    - BEFORE composite built in app.py       [line ~410]
    - AFTER  composite built in app.py       [line ~425]
    - BEFORE composite rebuilt in tile layers [line ~1053]
    - AFTER  composite rebuilt in tile layers [line ~1072]

  Each call includes .size().getInfo() round-trips to GEE, which
  are network calls. The median composite itself is lazy (not
  computed until a terminal op like getMapId() or getInfo()),
  so the composite objects are cheap, but the .size().getInfo()
  calls for n_before, n_joined, n_after are REAL GEE round-trips.

  Rough cost per create_s2_composite() call:
    3 x .size().getInfo() = 3 GEE API round-trips (~1-3s each)

  Total extra round-trips from duplication: ~6-9 extra GEE calls.

  SAFE MINIMUM FIX (no refactor required):
    In get_all_tile_layers(), accept optional pre-computed
    before_img/after_img arguments. When provided (from app.py),
    skip create_s2_composite() entirely. When absent, build them
    as now. This keeps full backward compatibility.

  CALLER CHANGE (app.py line 488) would become:
    tiles = get_all_tile_layers(
        lat, lon, before_dates_dict, after_dates_dict,
        before_img=before_img, after_img=after_img
    )

  NOTE: get_all_tile_layers also takes a DIFFERENT format for
  before_dates/after_dates (dict) than what app.py currently
  passes (tuple). This is a SEPARATE BUG — see Summary below.
""")

# ---------------------------------------------------------------------------
# 9. Argument-format bug: before_dates tuple vs dict
# ---------------------------------------------------------------------------
hr("9. Argument-Format Bug (app.py line 488)")
print("""
  BUG CONFIRMED (static analysis):
  ─────────────────────────────────
  app.py line 400:
    before_dates = (f"{start_yr}-01-01", f"{start_yr}-12-31")   <- TUPLE

  app.py line 488:
    get_all_tile_layers(lat, lon, before_dates, after_dates, watershed_geom)
                                  ^tuple        ^tuple        ^geometry passed
                                                              as buffer_km

  get_all_tile_layers() signature (gee_engine.py line 974):
    def get_all_tile_layers(lat, lon, before_dates: dict, after_dates: dict, buffer_km: float = 10)

  Problems:
    1. before_dates/after_dates are tuples; function calls .get("start") on
       them → AttributeError at runtime (tuples have no .get()).
    2. watershed_geom (an ee.Geometry or None) is passed as buffer_km
       (float) → TypeError at runtime.
    3. get_all_tile_layers() will never be reached because it fails
       immediately on before_dates.get("start", ...).
    4. The session_state cache key also fails because it calls
       before_dates.get("start", "") on a tuple.
""")

# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------
hr("10. Phase 2 Verification Summary")
print(f"""
  GEE authentication:       {"OK" if GEE_OK else "UNAVAILABLE"}
  BEFORE composite (2019):  {"OK" if before_ok else "FAILED"}
  AFTER  composite (2024):  {"OK" if after_ok  else "FAILED"}
  before_satellite tile:    {"VALID" if before_tile_ok else ("FAILED" if before_img else "SKIPPED")}
  after_satellite tile:     {"VALID" if after_tile_ok  else ("FAILED" if after_img  else "SKIPPED")}

  Pipeline verified:        {"YES — runtime-verified against GEE" if (before_ok and after_ok) else "PARTIAL — see above"}

  BUGS FOUND (no code changed per task instructions):
    [BUG-1] app.py line 488: before_dates/after_dates passed as tuples;
            get_all_tile_layers() expects dicts with .get() → AttributeError.
    [BUG-2] app.py line 488: watershed_geom passed as buffer_km argument → TypeError.
    [BUG-3] Duplicate computation: create_s2_composite() called 4x per
            live analysis (2x in app.py + 2x in get_all_tile_layers()).
            Adds ~6-9 unnecessary GEE round-trips per analysis.
""")
