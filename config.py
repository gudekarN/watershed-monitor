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

# Authoritative fallback watershed configuration.
# Used by app.py when data/sample_watersheds.json cannot be loaded.
# data/sample_watersheds.json is the primary source; this list must stay in sync with it.
SAMPLE_WATERSHEDS = [
    {
        "id": "hiware_bazar",
        "name": "Hiware Bazar, Maharashtra",
        "lat": 19.3516,
        "lon": 74.5535,
        "state": "Maharashtra",
        "district": "Ahilyanagar",
        "project_type": "Integrated Watershed Development",
        "start_year": 2019
    },
    {
        "id": "ralegan_siddhi",
        "name": "Ralegan Siddhi, Maharashtra",
        "lat": 18.8752,
        "lon": 74.4960,
        "state": "Maharashtra",
        "district": "Ahilyanagar",
        "project_type": "Community Watershed Management",
        "start_year": 2018
    },
    {
        "id": "arvari_river",
        "name": "Arvari River Basin, Rajasthan",
        "lat": 27.5530,
        "lon": 76.6346,
        "state": "Rajasthan",
        "district": "Alwar",
        "project_type": "River Rejuvenation",
        "start_year": 2017
    },
    {
        "id": "sukhomajri",
        "name": "Sukhomajri, Haryana",
        "lat": 30.7400,
        "lon": 76.8920,
        "state": "Haryana",
        "district": "Panchkula",
        "project_type": "Soil & Water Conservation",
        "start_year": 2020
    },
    {
        "id": "anantapur",
        "name": "Anantapur Watershed, Andhra Pradesh",
        "lat": 14.6819,
        "lon": 77.6006,
        "state": "Andhra Pradesh",
        "district": "Anantapur",
        "project_type": "MGNREGA Watershed",
        "start_year": 2019
    }
]


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
      2. [Streamlit Cloud] If ``st.secrets`` contains a ``[gee_service_account]``
         section, use those credentials to build a service-account credential
         object and call ``ee.Initialize(credentials=..., project=EE_PROJECT_ID)``.
         No secret values are written to logs.
      3. Attempt ``ee.Initialize(project=EE_PROJECT_ID)`` — succeeds on systems
         already authenticated via ``earthengine authenticate`` or a service-
         account credential file (local / Open Mode).
      4. If that raises any exception, fall back to ``ee.Authenticate()`` (opens a
         browser OAuth flow) and then retry ``ee.Initialize(project=EE_PROJECT_ID)``.
      5. If all attempts fail, set GEE_AVAILABLE=False and DEMO_MODE=True and
         print a human-readable warning so the app can fall back gracefully.
      6. On success, set GEE_AVAILABLE=True and DEMO_MODE=False.

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

    # --- Attempt 0: Streamlit Secrets service-account authentication ---
    # This path is active only when running on Streamlit Cloud (or any
    # environment where streamlit is installed and st.secrets is populated).
    # No private-key or token values are written to stdout/logs.
    try:
        import streamlit as st  # noqa: PLC0415 – optional, may not be installed

        sa_secrets = st.secrets.get("gee_service_account")
        if sa_secrets:
            sa_email = sa_secrets.get("client_email", "")
            # Build a credentials object from the private key stored in secrets.
            # ee.ServiceAccountCredentials accepts the raw PEM string directly.
            credentials = ee.ServiceAccountCredentials(
                email=sa_email,
                key_data=sa_secrets.get("private_key", ""),
            )
            ee.Initialize(credentials=credentials, project=EE_PROJECT_ID)
            GEE_AVAILABLE = True
            DEMO_MODE = False
            print(
                f"[INFO] Google Earth Engine initialised via Streamlit Secrets "
                f"service account (project={EE_PROJECT_ID})."
            )
            return True
    except ImportError:
        # streamlit is not installed — running locally, skip this path
        pass
    except Exception as sa_error:
        # Log the error class/message but never the key material itself
        print(
            f"[INFO] Streamlit Secrets service-account init failed "
            f"({type(sa_error).__name__}: {sa_error}). "
            "Falling back to local authentication."
        )

    # --- Attempt 1: silent init (already authenticated, local / Open Mode) ---
    try:
        ee.Initialize(project=EE_PROJECT_ID)
        GEE_AVAILABLE = True
        DEMO_MODE = False
        print(f"[INFO] Google Earth Engine initialised (project={EE_PROJECT_ID}).")
        return True
    except Exception as first_error:
        print(f"[INFO] Silent GEE init failed ({first_error}). Trying OAuth flow...")

    # --- Attempt 2: interactive OAuth authentication (local / Live Mode) ---
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
