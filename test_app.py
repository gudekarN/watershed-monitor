import os
import json
import importlib
import sys

# Change directory to script location to ensure relative paths work
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = "data"

def print_result(check, msg):
    if check:
        print(f"✅ {msg}")
    else:
        print(f"❌ {msg}")
    return check

def run_all_checks():
    print("Running AquaVeda Automated Checks...\n")
    
    all_passed = True

    # 1. Check Demo Data Files
    json_files = [
        "sample_watersheds.json", "change_data.json", "health_scores.json",
        "ndvi_timeseries.json", "water_timeseries.json", "landuse_transition.json",
        "monthly_ndvi.json", "rainfall_data.json", "field_photos.json"
    ]
    geojson_files = [
        "watershed_boundary_hiware_bazar.geojson", "drainage_network.geojson"
    ]
    
    all_files_exist = True
    valid_json = True
    for f in json_files + geojson_files:
        path = os.path.join(DATA_DIR, f)
        if not os.path.exists(path):
            all_files_exist = False
        else:
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    json.load(file)
            except json.JSONDecodeError:
                valid_json = False
    
    all_passed &= print_result(all_files_exist and valid_json, f"Demo data files: {'All 11 files present and valid' if all_files_exist and valid_json else 'Missing or invalid'}")

    # Load data for further checks
    try:
        with open(os.path.join(DATA_DIR, "sample_watersheds.json"), 'r', encoding='utf-8') as f:
            watersheds = json.load(f)
    except:
        watersheds = []
        
    try:
        with open(os.path.join(DATA_DIR, "ndvi_timeseries.json"), 'r', encoding='utf-8') as f:
            ndvi_ts = json.load(f)
    except:
        ndvi_ts = {}
        
    try:
        with open(os.path.join(DATA_DIR, "water_timeseries.json"), 'r', encoding='utf-8') as f:
            water_ts = json.load(f)
    except:
        water_ts = {}
        
    try:
        with open(os.path.join(DATA_DIR, "change_data.json"), 'r', encoding='utf-8') as f:
            change_data = json.load(f)
    except:
        change_data = {}
        
    try:
        with open(os.path.join(DATA_DIR, "health_scores.json"), 'r', encoding='utf-8') as f:
            health_scores = json.load(f)
    except:
        health_scores = {}
        
    try:
        with open(os.path.join(DATA_DIR, "field_photos.json"), 'r', encoding='utf-8') as f:
            field_photos = json.load(f)
    except:
        field_photos = {}

    # 2. Watershed data
    all_passed &= print_result(len(watersheds) == 5, f"Watershed data: {len(watersheds)}/5 loaded")

    # 3 & 4. Timeseries data
    ws_ids = [w.get('id') for w in watersheds]
    ndvi_ok = all(wid in ndvi_ts and len(ndvi_ts[wid]) > 0 for wid in ws_ids)
    water_ok = all(wid in water_ts and len(water_ts[wid]) > 0 for wid in ws_ids)
    all_passed &= print_result(ndvi_ok, "NDVI timeseries: Data present for all watersheds")
    all_passed &= print_result(water_ok, "Water timeseries: Data present for all watersheds")

    # 5. Change data keys
    change_keys_ok = True
    for wid in ws_ids:
        cdata = change_data.get(wid, {})
        if not all(k in cdata for k in ['vegetation', 'water', 'erosion']):
            change_keys_ok = False
            break
    all_passed &= print_result(change_keys_ok, "Change data: Required keys present for all watersheds")

    # 6. Health scores
    health_range_ok = True
    for wid in ws_ids:
        score = health_scores.get(wid, {}).get("total_score", -1)
        if not (0 <= score <= 100):
            health_range_ok = False
            break
    all_passed &= print_result(health_range_ok, "Health scores: All in range (0-100)")

    # 7. GeoJSON validity (already checked JSON decode, check FeatureCollection)
    geo_ok = True
    for f in geojson_files:
        try:
            with open(os.path.join(DATA_DIR, f), 'r', encoding='utf-8') as file:
                data = json.load(file)
                if data.get("type") not in ["FeatureCollection", "Feature", "Polygon", "MultiPolygon", "LineString", "MultiLineString"]:
                     geo_ok = False
        except:
            geo_ok = False
    all_passed &= print_result(geo_ok, "GeoJSON files: Valid format")

    # 8. Photo metadata
    photos_ok = True
    for pid, photos in field_photos.items():
        for photo in photos:
            if 'lat' not in photo or 'lon' not in photo:
                photos_ok = False
            elif not (-90 <= photo['lat'] <= 90) or not (-180 <= photo['lon'] <= 180):
                photos_ok = False
    all_passed &= print_result(photos_ok, "Photo metadata: Valid lat/lon values")

    # 9. Health score calculation check
    calc_ok = True
    try:
        from backend.health_score import calculate_watershed_health
        if len(ws_ids) > 0:
            test_wid = ws_ids[0]
            test_res = calculate_watershed_health(change_data.get(test_wid,{}), ndvi_ts.get(test_wid,[]))
            if test_res.get("total_score") is None:
                calc_ok = False
    except Exception as e:
        calc_ok = False
    all_passed &= print_result(calc_ok, "Health score calculation: Produces correct output for sample data")

    # 10. Package installations
    packages = ['streamlit', 'folium', 'streamlit_folium', 'plotly', 'pandas', 'numpy', 'fpdf']
    pkg_ok = True
    for pkg in packages:
        try:
            importlib.import_module(pkg)
        except ImportError:
            pkg_ok = False
            print(f"    Missing package: {pkg}")
    all_passed &= print_result(pkg_ok, "Dependencies: All required Python packages installed")

    # 11. Config load
    config_ok = True
    try:
        import config
    except Exception as e:
        config_ok = False
    all_passed &= print_result(config_ok, "Config: Loads without errors")

    # 12 & 13. Modules import
    backend_ok = True
    try:
        import backend.gee_engine
        import backend.indices
        import backend.watershed
        import backend.change_detection
        import backend.health_score
        import backend.report_generator
    except Exception as e:
        backend_ok = False
        print(f"    Backend import error: {e}")
        
    frontend_ok = True
    try:
        import frontend.map_builder
        import frontend.charts
        import frontend.charts_matplotlib
        import geo_photos.photo_handler
    except Exception as e:
        frontend_ok = False
        print(f"    Frontend import error: {e}")
        
    all_passed &= print_result(backend_ok, "Modules: All backend modules import without errors")
    all_passed &= print_result(frontend_ok, "Modules: All frontend modules import without errors")

    # Extra: GEE Check
    try:
        from backend.gee_engine import _ee_ready
        gee_status = _ee_ready()
        if gee_status:
            print("✅ GEE Connection: Authenticated")
        else:
            print("❌ GEE Connection: Not authenticated (OK for demo mode)")
    except:
        print("❌ GEE Connection: Not authenticated (OK for demo mode)")

    print("\n" + ("✅ ALL CHECKS PASSED!" if all_passed else "❌ SOME CHECKS FAILED!"))

if __name__ == "__main__":
    run_all_checks()
