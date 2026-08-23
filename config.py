import os
from pathlib import Path
from dotenv import load_dotenv

try:
    import ee
except ImportError:
    ee = None

# Load environment variables from .env file
load_dotenv()

EE_PROJECT_ID = os.getenv("EE_PROJECT_ID")

# Global flags
GEE_AVAILABLE = False
DEMO_MODE = True

# Dictionary of 5 sample watershed locations in India
WATERSHEDS = {
    "Hiware Bazar": {
        "name": "Hiware Bazar",
        "lat": 18.9667,
        "lon": 74.6833,
        "state": "Maharashtra",
        "district": "Ahmednagar",
        "project_type": "Water Conservation",
        "start_year": 1990,
        "structures_count": 52
    },
    "Ralegan Siddhi": {
        "name": "Ralegan Siddhi",
        "lat": 19.0067,
        "lon": 74.3411,
        "state": "Maharashtra",
        "district": "Ahmednagar",
        "project_type": "Watershed Development",
        "start_year": 1975,
        "structures_count": 48
    },
    "Arvari River": {
        "name": "Arvari River",
        "lat": 27.2667,
        "lon": 76.1333,
        "state": "Rajasthan",
        "district": "Alwar",
        "project_type": "River Revival",
        "start_year": 1986,
        "structures_count": 375
    },
    "Sukhomajri": {
        "name": "Sukhomajri",
        "lat": 30.8242,
        "lon": 76.8837,
        "state": "Haryana",
        "district": "Panchkula",
        "project_type": "Soil & Water Conservation",
        "start_year": 1970,
        "structures_count": 4
    },
    "Lakshman Jhula": {
        "name": "Lakshman Jhula",
        "lat": 30.1235,
        "lon": 78.3276,
        "state": "Uttarakhand",
        "district": "Pauri Garhwal",
        "project_type": "Himalayan Watershed",
        "start_year": 2005,
        "structures_count": 15
    }
}

# Date ranges for before/after analysis
DATE_RANGES = {
    "BEFORE": {"start": "2019-01-01", "end": "2019-12-31"},
    "AFTER": {"start": "2024-01-01", "end": "2024-12-31"}
}

# Color palettes for map visualization
PALETTES = {
    "default": ['blue', 'green', 'orange', 'red']
}

# Constants for index thresholds
THRESHOLDS = {
    "NDVI_HEALTHY": 0.4,
    "NDWI_WATER": 0.0
}

# Vis_params dictionaries
NDVI_VIS = {'min': -0.2, 'max': 0.8, 'palette': ['red', 'yellow', 'green']}
NDWI_VIS = {'min': -0.5, 'max': 0.5, 'palette': ['brown', 'white', 'blue']}
SAVI_VIS = {'min': -0.2, 'max': 0.8, 'palette': ['red', 'orange', 'green']}
SLOPE_VIS = {'min': 0, 'max': 45, 'palette': ['green', 'yellow', 'red']}

# Required demo JSON/GeoJSON files that must exist in data/ for DEMO_MODE
DEMO_DATA_FILES = [
    "watershed_boundary.geojson",
    "structures.geojson",
    "ndvi_timeseries.json",
    "ndwi_timeseries.json",
    "savi_timeseries.json",
    "ndbi_timeseries.json",
    "health_scores.json",
    "change_stats.json",
    "watershed_stats.json",
]


def initialize_gee() -> bool:
    """
    Initialize Google Earth Engine (GEE) for the application.

    Strategy:
      1. Reload EE_PROJECT_ID from .env in case the file was updated at runtime.
      2. Attempt ee.Initialize(project=EE_PROJECT_ID) — succeeds on systems that
         are already authenticated via ``earthengine authenticate`` or a service
         account credential file.
      3. If that raises any exception, fall back to ee.Authenticate() (opens a
         browser OAuth flow) and then retry ee.Initialize(project=EE_PROJECT_ID).
      4. If both attempts fail, set GEE_AVAILABLE=False and DEMO_MODE=True and
         print a human-readable warning so the app can fall back gracefully.
      5. On success, set GEE_AVAILABLE=True and DEMO_MODE=False.

    Returns:
        bool: True if GEE initialised successfully, False otherwise.
    """
    global GEE_AVAILABLE, DEMO_MODE, EE_PROJECT_ID

    # Re-read project ID (allows runtime .env edits to take effect)
    load_dotenv(override=True)
    EE_PROJECT_ID = os.getenv("EE_PROJECT_ID")

    if ee is None:
        print(
            "[WARNING] earthengine-api package not found. "
            "Running in DEMO MODE."
        )
        GEE_AVAILABLE = False
        DEMO_MODE = True
        return False

    if not EE_PROJECT_ID or EE_PROJECT_ID == "your-gee-project-id-here":
        print(
            "[WARNING] EE_PROJECT_ID is not set in .env. "
            "Please add your GEE project ID. Running in DEMO MODE."
        )
        GEE_AVAILABLE = False
        DEMO_MODE = True
        return False

    # --- Attempt 1: silent init (already authenticated) ---
    try:
        ee.Initialize(project=EE_PROJECT_ID)
        GEE_AVAILABLE = True
        DEMO_MODE = False
        print(f"[INFO] Google Earth Engine initialised (project={EE_PROJECT_ID}).")
        return True
    except Exception as first_error:
        print(f"[INFO] Silent GEE init failed ({first_error}). Trying OAuth flow...")

    # --- Attempt 2: interactive OAuth authentication ---
    try:
        ee.Authenticate()
        ee.Initialize(project=EE_PROJECT_ID)
        GEE_AVAILABLE = True
        DEMO_MODE = False
        print(
            f"[INFO] Google Earth Engine initialised after OAuth "
            f"(project={EE_PROJECT_ID})."
        )
        return True
    except Exception as second_error:
        print(
            f"[WARNING] GEE initialisation failed after OAuth attempt: "
            f"{second_error}\n"
            "Running in DEMO MODE — pre-cached sample data will be used."
        )
        GEE_AVAILABLE = False
        DEMO_MODE = True
        return False


def check_demo_data_exists() -> bool:
    """
    Verify that all required demo JSON/GeoJSON files are present in the
    ``data/`` directory relative to this config file.

    This is called at startup when the app runs in DEMO_MODE to ensure
    pre-cached sample data is available before the dashboard tries to
    render charts and maps.

    Returns:
        bool: True if every file in DEMO_DATA_FILES exists, False if any
              are missing (missing file paths are printed to stdout).
    """
    data_dir = Path(__file__).parent / "data"
    missing = [
        fname
        for fname in DEMO_DATA_FILES
        if not (data_dir / fname).is_file()
    ]

    if missing:
        print(
            f"[WARNING] {len(missing)} demo data file(s) missing from {data_dir}:"
        )
        for fname in missing:
            print(f"  - {fname}")
        print(
            "Run  python data/generate_demo_data.py  to create them."
        )
        return False

    print(f"[INFO] All {len(DEMO_DATA_FILES)} demo data files found in {data_dir}.")
    return True
