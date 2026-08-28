"""
generate_demo_data.py
=====================
Standalone script that generates all sample data files needed for the
Watershed Monitoring prototype to run without Google Earth Engine.

Usage:
    python data/generate_demo_data.py

Output files are written to the data/ directory (same folder as this script).
"""

import json
from pathlib import Path

# All output files are written relative to this script's own directory (data/)
DATA_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# FILE 1 - sample_watersheds.json
# ---------------------------------------------------------------------------

def _sample_watersheds():
    return [
        {
            "id": "hiware_bazar",
            "name": "Hiware Bazar",
            "state": "Maharashtra",
            "district": "Ahilyanagar",
            "lat": 19.3516,
            "lon": 74.5535,
            "project_type": "Integrated Watershed Development",
            "start_year": 2019,
            "structures": {
                "check_dams": 8,
                "farm_ponds": 15,
                "contour_trenches": 2200,
                "percolation_tanks": 4,
                "gabion_structures": 6,
            },
            "area_sq_km": 18.5,
            "annual_rainfall_mm": 450,
            "elevation_range": "550m - 780m",
            "description": "Model village watershed project in semi-arid Maharashtra",
        },
        {
            "id": "ralegan_siddhi",
            "name": "Ralegan Siddhi",
            "state": "Maharashtra",
            "district": "Ahilyanagar",
            "lat": 18.8752,
            "lon": 74.4960,
            "project_type": "Community Watershed Management",
            "start_year": 2018,
            "structures": {
                "check_dams": 5,
                "farm_ponds": 10,
                "contour_trenches": 1800,
                "percolation_tanks": 3,
                "gabion_structures": 4,
            },
            "area_sq_km": 22.3,
            "annual_rainfall_mm": 500,
            "elevation_range": "520m - 720m",
            "description": "Anna Hazare's model village watershed",
        },
        {
            "id": "arvari_river",
            "name": "Arvari River Basin",
            "state": "Rajasthan",
            "district": "Alwar",
            "lat": 27.5530,
            "lon": 76.6346,
            "project_type": "River Rejuvenation",
            "start_year": 2017,
            "structures": {
                "check_dams": 12,
                "farm_ponds": 8,
                "contour_trenches": 3000,
                "percolation_tanks": 6,
                "gabion_structures": 10,
            },
            "area_sq_km": 45.8,
            "annual_rainfall_mm": 620,
            "elevation_range": "340m - 580m",
            "description": "Rajendra Singh's river rejuvenation - Arvari Parliament",
        },
        {
            "id": "sukhomajri",
            "name": "Sukhomajri",
            "state": "Haryana",
            "district": "Panchkula",
            "lat": 30.7400,
            "lon": 76.8920,
            "project_type": "Soil and Water Conservation",
            "start_year": 2020,
            "structures": {
                "check_dams": 3,
                "farm_ponds": 6,
                "contour_trenches": 1200,
                "percolation_tanks": 2,
                "gabion_structures": 3,
            },
            "area_sq_km": 12.1,
            "annual_rainfall_mm": 1100,
            "elevation_range": "450m - 900m",
            "description": "Pioneer watershed management project in Shivalik hills",
        },
        {
            "id": "anantapur",
            "name": "Anantapur Watershed",
            "state": "Andhra Pradesh",
            "district": "Anantapur",
            "lat": 14.6819,
            "lon": 77.6006,
            "project_type": "MGNREGA Watershed",
            "start_year": 2019,
            "structures": {
                "check_dams": 6,
                "farm_ponds": 20,
                "contour_trenches": 2500,
                "percolation_tanks": 5,
                "gabion_structures": 8,
            },
            "area_sq_km": 28.7,
            "annual_rainfall_mm": 550,
            "elevation_range": "300m - 520m",
            "description": "Driest district in AP - critical watershed intervention",
        },
    ]


# ---------------------------------------------------------------------------
# FILE 2 - ndvi_timeseries.json
# ---------------------------------------------------------------------------

def _ndvi_timeseries():
    return {
        # Strong recovery - model project
        "hiware_bazar": [
            {"year": 2017, "ndvi_mean": 0.22, "ndvi_max": 0.45, "ndvi_min": 0.08},
            {"year": 2018, "ndvi_mean": 0.25, "ndvi_max": 0.48, "ndvi_min": 0.10},
            {"year": 2019, "ndvi_mean": 0.31, "ndvi_max": 0.52, "ndvi_min": 0.12},
            {"year": 2020, "ndvi_mean": 0.38, "ndvi_max": 0.58, "ndvi_min": 0.15},
            {"year": 2021, "ndvi_mean": 0.44, "ndvi_max": 0.63, "ndvi_min": 0.18},
            {"year": 2022, "ndvi_mean": 0.49, "ndvi_max": 0.68, "ndvi_min": 0.22},
            {"year": 2023, "ndvi_mean": 0.53, "ndvi_max": 0.72, "ndvi_min": 0.25},
            {"year": 2024, "ndvi_mean": 0.58, "ndvi_max": 0.76, "ndvi_min": 0.28},
        ],
        # Good recovery - community-driven
        "ralegan_siddhi": [
            {"year": 2017, "ndvi_mean": 0.20, "ndvi_max": 0.42, "ndvi_min": 0.07},
            {"year": 2018, "ndvi_mean": 0.26, "ndvi_max": 0.50, "ndvi_min": 0.11},
            {"year": 2019, "ndvi_mean": 0.32, "ndvi_max": 0.55, "ndvi_min": 0.13},
            {"year": 2020, "ndvi_mean": 0.37, "ndvi_max": 0.60, "ndvi_min": 0.16},
            {"year": 2021, "ndvi_mean": 0.42, "ndvi_max": 0.64, "ndvi_min": 0.19},
            {"year": 2022, "ndvi_mean": 0.46, "ndvi_max": 0.67, "ndvi_min": 0.21},
            {"year": 2023, "ndvi_mean": 0.50, "ndvi_max": 0.70, "ndvi_min": 0.24},
            {"year": 2024, "ndvi_mean": 0.54, "ndvi_max": 0.74, "ndvi_min": 0.27},
        ],
        # Excellent - river rejuvenation, longest history
        "arvari_river": [
            {"year": 2017, "ndvi_mean": 0.24, "ndvi_max": 0.47, "ndvi_min": 0.09},
            {"year": 2018, "ndvi_mean": 0.30, "ndvi_max": 0.54, "ndvi_min": 0.13},
            {"year": 2019, "ndvi_mean": 0.37, "ndvi_max": 0.60, "ndvi_min": 0.17},
            {"year": 2020, "ndvi_mean": 0.44, "ndvi_max": 0.65, "ndvi_min": 0.21},
            {"year": 2021, "ndvi_mean": 0.51, "ndvi_max": 0.70, "ndvi_min": 0.25},
            {"year": 2022, "ndvi_mean": 0.57, "ndvi_max": 0.74, "ndvi_min": 0.29},
            {"year": 2023, "ndvi_mean": 0.62, "ndvi_max": 0.78, "ndvi_min": 0.33},
            {"year": 2024, "ndvi_mean": 0.66, "ndvi_max": 0.82, "ndvi_min": 0.36},
        ],
        # Moderate - recent project (only since 2020)
        "sukhomajri": [
            {"year": 2020, "ndvi_mean": 0.28, "ndvi_max": 0.50, "ndvi_min": 0.12},
            {"year": 2021, "ndvi_mean": 0.32, "ndvi_max": 0.54, "ndvi_min": 0.14},
            {"year": 2022, "ndvi_mean": 0.36, "ndvi_max": 0.57, "ndvi_min": 0.17},
            {"year": 2023, "ndvi_mean": 0.39, "ndvi_max": 0.60, "ndvi_min": 0.19},
            {"year": 2024, "ndvi_mean": 0.42, "ndvi_max": 0.63, "ndvi_min": 0.21},
        ],
        # Poor - barely improved, the "failing" example
        "anantapur": [
            {"year": 2017, "ndvi_mean": 0.20, "ndvi_max": 0.38, "ndvi_min": 0.06},
            {"year": 2018, "ndvi_mean": 0.21, "ndvi_max": 0.39, "ndvi_min": 0.06},
            {"year": 2019, "ndvi_mean": 0.22, "ndvi_max": 0.40, "ndvi_min": 0.07},
            {"year": 2020, "ndvi_mean": 0.21, "ndvi_max": 0.38, "ndvi_min": 0.06},
            {"year": 2021, "ndvi_mean": 0.23, "ndvi_max": 0.41, "ndvi_min": 0.07},
            {"year": 2022, "ndvi_mean": 0.24, "ndvi_max": 0.42, "ndvi_min": 0.07},
            {"year": 2023, "ndvi_mean": 0.26, "ndvi_max": 0.44, "ndvi_min": 0.08},
            {"year": 2024, "ndvi_mean": 0.28, "ndvi_max": 0.45, "ndvi_min": 0.08},
        ],
    }


# ---------------------------------------------------------------------------
# FILE 3 - water_timeseries.json
# ---------------------------------------------------------------------------

def _water_timeseries():
    return {
        "hiware_bazar": [
            {"year": 2017, "water_area_ha": 1.8,  "ndwi_mean": -0.15},
            {"year": 2018, "water_area_ha": 2.5,  "ndwi_mean": -0.08},
            {"year": 2019, "water_area_ha": 3.2,  "ndwi_mean": -0.02},
            {"year": 2020, "water_area_ha": 5.8,  "ndwi_mean":  0.10},
            {"year": 2021, "water_area_ha": 8.2,  "ndwi_mean":  0.18},
            {"year": 2022, "water_area_ha": 10.5, "ndwi_mean":  0.25},
            {"year": 2023, "water_area_ha": 11.8, "ndwi_mean":  0.30},
            {"year": 2024, "water_area_ha": 12.8, "ndwi_mean":  0.35},
        ],
        "ralegan_siddhi": [
            {"year": 2017, "water_area_ha": 2.2,  "ndwi_mean": -0.12},
            {"year": 2018, "water_area_ha": 3.0,  "ndwi_mean": -0.05},
            {"year": 2019, "water_area_ha": 4.5,  "ndwi_mean":  0.05},
            {"year": 2020, "water_area_ha": 6.8,  "ndwi_mean":  0.12},
            {"year": 2021, "water_area_ha": 9.0,  "ndwi_mean":  0.20},
            {"year": 2022, "water_area_ha": 11.2, "ndwi_mean":  0.27},
            {"year": 2023, "water_area_ha": 13.0, "ndwi_mean":  0.32},
            {"year": 2024, "water_area_ha": 14.5, "ndwi_mean":  0.38},
        ],
        "arvari_river": [
            {"year": 2017, "water_area_ha": 5.5,  "ndwi_mean":  0.02},
            {"year": 2018, "water_area_ha": 8.0,  "ndwi_mean":  0.10},
            {"year": 2019, "water_area_ha": 12.0, "ndwi_mean":  0.18},
            {"year": 2020, "water_area_ha": 18.5, "ndwi_mean":  0.26},
            {"year": 2021, "water_area_ha": 24.0, "ndwi_mean":  0.33},
            {"year": 2022, "water_area_ha": 30.0, "ndwi_mean":  0.40},
            {"year": 2023, "water_area_ha": 35.5, "ndwi_mean":  0.46},
            {"year": 2024, "water_area_ha": 40.2, "ndwi_mean":  0.51},
        ],
        "sukhomajri": [
            {"year": 2020, "water_area_ha": 1.5, "ndwi_mean": -0.10},
            {"year": 2021, "water_area_ha": 2.2, "ndwi_mean": -0.04},
            {"year": 2022, "water_area_ha": 3.0, "ndwi_mean":  0.04},
            {"year": 2023, "water_area_ha": 3.8, "ndwi_mean":  0.10},
            {"year": 2024, "water_area_ha": 4.5, "ndwi_mean":  0.15},
        ],
        "anantapur": [
            {"year": 2017, "water_area_ha": 0.8, "ndwi_mean": -0.30},
            {"year": 2018, "water_area_ha": 1.0, "ndwi_mean": -0.28},
            {"year": 2019, "water_area_ha": 1.2, "ndwi_mean": -0.25},
            {"year": 2020, "water_area_ha": 0.9, "ndwi_mean": -0.29},
            {"year": 2021, "water_area_ha": 1.1, "ndwi_mean": -0.26},
            {"year": 2022, "water_area_ha": 1.3, "ndwi_mean": -0.24},
            {"year": 2023, "water_area_ha": 1.5, "ndwi_mean": -0.22},
            {"year": 2024, "water_area_ha": 1.4, "ndwi_mean": -0.23},
        ],
    }


# ---------------------------------------------------------------------------
# FILE 4 - change_data.json
# ---------------------------------------------------------------------------

def _change_data():
    return {
        "hiware_bazar": {
            "vegetation": {
                "ndvi_before": 0.28, "ndvi_after": 0.58, "change": 0.30,
                "improved_area_ha": 520, "declined_area_ha": 35,
                "unchanged_area_ha": 295, "percent_improved": 61.2,
            },
            "water": {
                "area_before_ha": 3.2, "area_after_ha": 12.8,
                "change_ha": 9.6, "change_percent": 300.0,
                "new_water_bodies": 3,
                "months_with_water_before": 4, "months_with_water_after": 9,
            },
            "erosion": {
                "high_risk_before_ha": 280, "high_risk_after_ha": 95,
                "reduction_percent": 66.1,
                "classes_before": {"Very Low": 120, "Low": 180, "Medium": 270, "High": 200, "Very High": 80},
                "classes_after":  {"Very Low": 250, "Low": 280, "Medium": 220, "High": 80,  "Very High": 20},
            },
            "landuse": {
                "transition_matrix": {
                    "Barren to Vegetation": 180, "Barren to Water": 25,
                    "Sparse Veg to Dense Veg": 220, "Water to Water": 30, "Unchanged": 395,
                },
                "classes_before": {"Water": 32,  "Dense Vegetation": 180, "Sparse Vegetation": 250, "Barren": 320, "Built-up": 68},
                "classes_after":  {"Water": 128, "Dense Vegetation": 380, "Sparse Vegetation": 200, "Barren": 120, "Built-up": 72},
            },
        },
        "ralegan_siddhi": {
            "vegetation": {
                "ndvi_before": 0.26, "ndvi_after": 0.54, "change": 0.28,
                "improved_area_ha": 610, "declined_area_ha": 42,
                "unchanged_area_ha": 578, "percent_improved": 49.8,
            },
            "water": {
                "area_before_ha": 4.5, "area_after_ha": 14.5,
                "change_ha": 10.0, "change_percent": 222.2,
                "new_water_bodies": 2,
                "months_with_water_before": 5, "months_with_water_after": 10,
            },
            "erosion": {
                "high_risk_before_ha": 310, "high_risk_after_ha": 115,
                "reduction_percent": 62.9,
                "classes_before": {"Very Low": 100, "Low": 160, "Medium": 300, "High": 230, "Very High": 80},
                "classes_after":  {"Very Low": 240, "Low": 290, "Medium": 230, "High": 90,  "Very High": 20},
            },
            "landuse": {
                "transition_matrix": {
                    "Barren to Vegetation": 160, "Barren to Water": 30,
                    "Sparse Veg to Dense Veg": 200, "Water to Water": 45, "Unchanged": 795,
                },
                "classes_before": {"Water": 45,  "Dense Vegetation": 200, "Sparse Vegetation": 280, "Barren": 380, "Built-up": 95},
                "classes_after":  {"Water": 145, "Dense Vegetation": 400, "Sparse Vegetation": 220, "Barren": 150, "Built-up": 85},
            },
        },
        "arvari_river": {
            "vegetation": {
                "ndvi_before": 0.24, "ndvi_after": 0.66, "change": 0.42,
                "improved_area_ha": 1820, "declined_area_ha": 55,
                "unchanged_area_ha": 705, "percent_improved": 71.2,
            },
            "water": {
                "area_before_ha": 5.5, "area_after_ha": 40.2,
                "change_ha": 34.7, "change_percent": 630.9,
                "new_water_bodies": 8,
                "months_with_water_before": 3, "months_with_water_after": 11,
            },
            "erosion": {
                "high_risk_before_ha": 920, "high_risk_after_ha": 185,
                "reduction_percent": 79.9,
                "classes_before": {"Very Low": 200, "Low": 450, "Medium": 900, "High": 700,  "Very High": 330},
                "classes_after":  {"Very Low": 700, "Low": 900, "Medium": 750, "High": 150,  "Very High": 80},
            },
            "landuse": {
                "transition_matrix": {
                    "Barren to Vegetation": 620, "Barren to Water": 120,
                    "Sparse Veg to Dense Veg": 750, "Water to Water": 55, "Unchanged": 1035,
                },
                "classes_before": {"Water": 55,  "Dense Vegetation": 500,  "Sparse Vegetation": 800, "Barren": 1400, "Built-up": 245},
                "classes_after":  {"Water": 402, "Dense Vegetation": 1500, "Sparse Vegetation": 600, "Barren": 400,  "Built-up": 278},
            },
        },
        "sukhomajri": {
            "vegetation": {
                "ndvi_before": 0.28, "ndvi_after": 0.42, "change": 0.14,
                "improved_area_ha": 280, "declined_area_ha": 30,
                "unchanged_area_ha": 900, "percent_improved": 23.1,
            },
            "water": {
                "area_before_ha": 1.5, "area_after_ha": 4.5,
                "change_ha": 3.0, "change_percent": 200.0,
                "new_water_bodies": 1,
                "months_with_water_before": 4, "months_with_water_after": 7,
            },
            "erosion": {
                "high_risk_before_ha": 180, "high_risk_after_ha": 110,
                "reduction_percent": 38.9,
                "classes_before": {"Very Low": 80,  "Low": 120, "Medium": 200, "High": 150, "Very High": 60},
                "classes_after":  {"Very Low": 160, "Low": 180, "Medium": 200, "High": 90,  "Very High": 30},
            },
            "landuse": {
                "transition_matrix": {
                    "Barren to Vegetation": 80, "Barren to Water": 10,
                    "Sparse Veg to Dense Veg": 75, "Water to Water": 15, "Unchanged": 630,
                },
                "classes_before": {"Water": 15, "Dense Vegetation": 120, "Sparse Vegetation": 180, "Barren": 280, "Built-up": 15},
                "classes_after":  {"Water": 45, "Dense Vegetation": 230, "Sparse Vegetation": 160, "Barren": 170, "Built-up": 5},
            },
        },
        "anantapur": {
            "vegetation": {
                "ndvi_before": 0.22, "ndvi_after": 0.28, "change": 0.06,
                "improved_area_ha": 180, "declined_area_ha": 210,
                "unchanged_area_ha": 1480, "percent_improved": 9.6,
            },
            "water": {
                "area_before_ha": 1.2, "area_after_ha": 1.4,
                "change_ha": 0.2, "change_percent": 16.7,
                "new_water_bodies": 0,
                "months_with_water_before": 2, "months_with_water_after": 2,
            },
            "erosion": {
                "high_risk_before_ha": 560, "high_risk_after_ha": 530,
                "reduction_percent": 5.4,
                "classes_before": {"Very Low": 90,  "Low": 200, "Medium": 420, "High": 430, "Very High": 130},
                "classes_after":  {"Very Low": 100, "Low": 210, "Medium": 430, "High": 400, "Very High": 130},
            },
            "landuse": {
                "transition_matrix": {
                    "Barren to Vegetation": 80, "Barren to Water": 5,
                    "Sparse Veg to Dense Veg": 40, "Vegetation to Barren": 120, "Unchanged": 2025,
                },
                "classes_before": {"Water": 12, "Dense Vegetation": 150, "Sparse Vegetation": 380, "Barren": 1000, "Built-up": 158},
                "classes_after":  {"Water": 14, "Dense Vegetation": 180, "Sparse Vegetation": 380, "Barren": 1060, "Built-up": 166},
            },
        },
    }


# ---------------------------------------------------------------------------
# FILE 5 - health_scores.json
# ---------------------------------------------------------------------------

def _health_scores():
    return {
        "hiware_bazar": {
            "total_score": 82,
            "grade": "Excellent",
            "grade_emoji": "A",
            "vegetation_score": 30,
            "water_score": 32,
            "erosion_score": 15,
            "sustainability_score": 5,
            "recommendations": [
                "Continue maintaining check dam #3 near stream junction",
                "Plant fruit trees on recovered barren patches (NW zone)",
                "Consider drip irrigation for newly cultivated areas",
                "Install rain gauge at percolation tank #2 for monitoring",
            ],
        },
        "ralegan_siddhi": {
            "total_score": 75,
            "grade": "Good",
            "grade_emoji": "B",
            "vegetation_score": 25,
            "water_score": 28,
            "erosion_score": 14,
            "sustainability_score": 8,
            "recommendations": [
                "De-silt check dam #2 - sediment accumulation detected",
                "Extend contour trenches to eastern slope",
                "Monitor encroachment near south boundary",
            ],
        },
        "arvari_river": {
            "total_score": 88,
            "grade": "Excellent",
            "grade_emoji": "A",
            "vegetation_score": 33,
            "water_score": 35,
            "erosion_score": 12,
            "sustainability_score": 8,
            "recommendations": [
                "Model project - replicate practices in neighboring villages",
                "Consider fish stocking in percolation tanks",
            ],
        },
        "sukhomajri": {
            "total_score": 55,
            "grade": "Average",
            "grade_emoji": "C",
            "vegetation_score": 18,
            "water_score": 20,
            "erosion_score": 10,
            "sustainability_score": 7,
            "recommendations": [
                "Recent project - allow 2 more monsoon cycles for full impact",
                "Add 3 more check dams on northern drainage line",
                "Community training needed for structure maintenance",
            ],
        },
        "anantapur": {
            "total_score": 32,
            "grade": "Poor",
            "grade_emoji": "F",
            "vegetation_score": 8,
            "water_score": 10,
            "erosion_score": 8,
            "sustainability_score": 6,
            "recommendations": [
                "URGENT: Check dam #4 appears damaged - needs field inspection",
                "Farm ponds drying within 2 months - lining needed",
                "Groundwater recharge not detected - deeper percolation shafts needed",
                "Consider drought-resistant crop varieties for farmers",
                "Additional 2000m contour trenching needed on south-facing slopes",
            ],
        },
    }


# ---------------------------------------------------------------------------
# FILE 6 - erosion_data.json
# ---------------------------------------------------------------------------

def _erosion_data():
    return {
        "hiware_bazar": {
            "before": {"Very Low": 120, "Low": 180, "Medium": 270, "High": 200, "Very High": 80},
            "after":  {"Very Low": 250, "Low": 280, "Medium": 220, "High": 80,  "Very High": 20},
        },
        "ralegan_siddhi": {
            "before": {"Very Low": 100, "Low": 160, "Medium": 300, "High": 230, "Very High": 80},
            "after":  {"Very Low": 240, "Low": 290, "Medium": 230, "High": 90,  "Very High": 20},
        },
        "arvari_river": {
            "before": {"Very Low": 200, "Low": 450, "Medium": 900,  "High": 700, "Very High": 330},
            "after":  {"Very Low": 700, "Low": 900, "Medium": 750,  "High": 150, "Very High": 80},
        },
        "sukhomajri": {
            "before": {"Very Low": 80,  "Low": 120, "Medium": 200, "High": 150, "Very High": 60},
            "after":  {"Very Low": 160, "Low": 180, "Medium": 200, "High": 90,  "Very High": 30},
        },
        "anantapur": {
            "before": {"Very Low": 90,  "Low": 200, "Medium": 420, "High": 430, "Very High": 130},
            "after":  {"Very Low": 100, "Low": 210, "Medium": 430, "High": 400, "Very High": 130},
        },
    }


# ---------------------------------------------------------------------------
# FILE 7 - landuse_transition.json
# ---------------------------------------------------------------------------

def _landuse_transition():
    labels = ["Water", "Dense Vegetation", "Sparse Vegetation", "Barren", "Built-up"]
    return {
        "hiware_bazar": {
            "labels": labels,
            "before_areas_ha": [32,  180, 250, 320,  68],
            "after_areas_ha":  [128, 380, 200, 120,  72],
            "flows": [
                {"source": "Barren",            "target": "Sparse Vegetation",  "value": 120},
                {"source": "Barren",            "target": "Dense Vegetation",   "value": 55},
                {"source": "Barren",            "target": "Water",              "value": 25},
                {"source": "Sparse Vegetation", "target": "Dense Vegetation",   "value": 145},
                {"source": "Water",             "target": "Water",              "value": 32},
                {"source": "Dense Vegetation",  "target": "Dense Vegetation",   "value": 180},
            ],
        },
        "ralegan_siddhi": {
            "labels": labels,
            "before_areas_ha": [45,  200, 280, 380, 95],
            "after_areas_ha":  [145, 400, 220, 150, 85],
            "flows": [
                {"source": "Barren",            "target": "Sparse Vegetation",  "value": 110},
                {"source": "Barren",            "target": "Dense Vegetation",   "value": 65},
                {"source": "Barren",            "target": "Water",              "value": 30},
                {"source": "Sparse Vegetation", "target": "Dense Vegetation",   "value": 155},
                {"source": "Water",             "target": "Water",              "value": 45},
                {"source": "Dense Vegetation",  "target": "Dense Vegetation",   "value": 200},
            ],
        },
        "arvari_river": {
            "labels": labels,
            "before_areas_ha": [55,  500,  800,  1400, 245],
            "after_areas_ha":  [402, 1500, 600,  400,  278],
            "flows": [
                {"source": "Barren",            "target": "Sparse Vegetation",  "value": 380},
                {"source": "Barren",            "target": "Dense Vegetation",   "value": 240},
                {"source": "Barren",            "target": "Water",              "value": 120},
                {"source": "Sparse Vegetation", "target": "Dense Vegetation",   "value": 600},
                {"source": "Water",             "target": "Water",              "value": 55},
                {"source": "Dense Vegetation",  "target": "Dense Vegetation",   "value": 500},
            ],
        },
        "sukhomajri": {
            "labels": labels,
            "before_areas_ha": [15, 120, 180, 280, 15],
            "after_areas_ha":  [45, 230, 160, 170,  5],
            "flows": [
                {"source": "Barren",            "target": "Sparse Vegetation",  "value": 60},
                {"source": "Barren",            "target": "Dense Vegetation",   "value": 25},
                {"source": "Barren",            "target": "Water",              "value": 10},
                {"source": "Sparse Vegetation", "target": "Dense Vegetation",   "value": 75},
                {"source": "Water",             "target": "Water",              "value": 15},
                {"source": "Dense Vegetation",  "target": "Dense Vegetation",   "value": 120},
            ],
        },
        "anantapur": {
            "labels": labels,
            "before_areas_ha": [12,  150, 380, 1000, 158],
            "after_areas_ha":  [14,  180, 380, 1060, 166],
            "flows": [
                {"source": "Barren",            "target": "Sparse Vegetation",  "value": 55},
                {"source": "Barren",            "target": "Dense Vegetation",   "value": 20},
                {"source": "Barren",            "target": "Water",              "value": 5},
                {"source": "Sparse Vegetation", "target": "Barren",             "value": 95},
                {"source": "Dense Vegetation",  "target": "Barren",             "value": 25},
                {"source": "Water",             "target": "Water",              "value": 12},
            ],
        },
    }


# ---------------------------------------------------------------------------
# FILE 8 - sample_photo_metadata.json
# ---------------------------------------------------------------------------

def _sample_photo_metadata():
    return [
        {
            "id": 1, "watershed_id": "hiware_bazar",
            "lat": 19.3520, "lon": 74.5540,
            "type": "Check Dam", "status": "Functional", "water_level": "80%",
            "date": "2024-06-15",
            "description": "Check dam on Hiware stream - holding water well after monsoon",
            "verified": True, "image_placeholder": "check_dam_1",
        },
        {
            "id": 2, "watershed_id": "hiware_bazar",
            "lat": 19.3490, "lon": 74.5510,
            "type": "Farm Pond", "status": "Functional", "water_level": "60%",
            "date": "2024-07-20",
            "description": "Farm pond near Patil farm - used for supplemental irrigation",
            "verified": True, "image_placeholder": "farm_pond_1",
        },
        {
            "id": 3, "watershed_id": "hiware_bazar",
            "lat": 19.3550, "lon": 74.5580,
            "type": "Contour Trench", "status": "Functional", "water_level": "N/A",
            "date": "2024-08-10",
            "description": "Contour trenches on hillslope - visible soil moisture improvement",
            "verified": True, "image_placeholder": "contour_trench_1",
        },
        {
            "id": 4, "watershed_id": "hiware_bazar",
            "lat": 19.3480, "lon": 74.5560,
            "type": "Percolation Tank", "status": "Needs Repair", "water_level": "30%",
            "date": "2024-09-05",
            "description": "Percolation tank - spillway damaged, needs maintenance",
            "verified": True, "image_placeholder": "percolation_tank_1",
        },
        {
            "id": 5, "watershed_id": "arvari_river",
            "lat": 27.5545, "lon": 76.6360,
            "type": "Check Dam", "status": "Functional", "water_level": "90%",
            "date": "2024-08-22",
            "description": "Main check dam on Arvari - river flowing continuously post-monsoon",
            "verified": True, "image_placeholder": "arvari_check_dam",
        },
        {
            "id": 6, "watershed_id": "arvari_river",
            "lat": 27.5510, "lon": 76.6320,
            "type": "Percolation Tank", "status": "Functional", "water_level": "75%",
            "date": "2024-09-10",
            "description": "Percolation tank - groundwater table risen by 4m since 2017",
            "verified": True, "image_placeholder": "arvari_percolation",
        },
        {
            "id": 7, "watershed_id": "anantapur",
            "lat": 14.6830, "lon": 77.6020,
            "type": "Check Dam", "status": "Damaged", "water_level": "0%",
            "date": "2024-05-30",
            "description": "Check dam breached during flash flood - no water retention",
            "verified": True, "image_placeholder": "check_dam_damaged",
        },
        {
            "id": 8, "watershed_id": "anantapur",
            "lat": 14.6800, "lon": 77.5990,
            "type": "Farm Pond", "status": "Dry", "water_level": "0%",
            "date": "2024-06-25",
            "description": "Farm pond completely dry - unlined, high seepage losses",
            "verified": True, "image_placeholder": "farm_pond_dry",
        },
        {
            "id": 9, "watershed_id": "sukhomajri",
            "lat": 30.7410, "lon": 76.8935,
            "type": "Gabion Structure", "status": "Functional", "water_level": "N/A",
            "date": "2024-07-18",
            "description": "Gabion check dam on seasonal stream - actively trapping sediment",
            "verified": True, "image_placeholder": "sukhomajri_gabion",
        },
        {
            "id": 10, "watershed_id": "ralegan_siddhi",
            "lat": 18.8765, "lon": 74.4975,
            "type": "Farm Pond", "status": "Functional", "water_level": "55%",
            "date": "2024-08-05",
            "description": "Lined farm pond - community-managed, shared irrigation source",
            "verified": True, "image_placeholder": "ralegan_farm_pond",
        },
    ]


# ---------------------------------------------------------------------------
# FILE 9 - watershed_boundary_hiware_bazar.geojson
# ---------------------------------------------------------------------------

def _watershed_boundary_hiware_bazar():
    coords = [
        [74.535, 19.370], [74.545, 19.375], [74.560, 19.372],
        [74.572, 19.362], [74.575, 19.350], [74.570, 19.338],
        [74.558, 19.330], [74.545, 19.328], [74.535, 19.332],
        [74.528, 19.340], [74.525, 19.352], [74.530, 19.365],
        [74.535, 19.370],  # closing vertex
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Hiware Bazar Watershed",
                    "area_sq_km": 18.5,
                    "basin_id": "hiware_bazar",
                    "state": "Maharashtra",
                },
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        ],
    }


# ---------------------------------------------------------------------------
# FILE 10 - drainage_network.geojson
# ---------------------------------------------------------------------------

def _drainage_network():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Hiware Main Stream", "stream_order": 3, "length_km": 5.2},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [74.550, 19.375], [74.549, 19.365], [74.548, 19.355],
                        [74.550, 19.345], [74.551, 19.335], [74.550, 19.328],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "East Tributary 1", "stream_order": 2, "length_km": 2.8},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [74.572, 19.360], [74.562, 19.358], [74.553, 19.355], [74.548, 19.355],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "East Tributary 2", "stream_order": 1, "length_km": 1.9},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [74.568, 19.340], [74.560, 19.342], [74.552, 19.344], [74.550, 19.345],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "West Tributary", "stream_order": 2, "length_km": 3.1},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [74.527, 19.365], [74.534, 19.362],
                        [74.540, 19.360], [74.548, 19.358], [74.548, 19.355],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "North Feeder Channel", "stream_order": 1, "length_km": 1.4},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [74.545, 19.374], [74.546, 19.370], [74.548, 19.366], [74.549, 19.365],
                    ],
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# FILE 11 - monthly_ndvi.json
# ---------------------------------------------------------------------------

def _monthly_ndvi():
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    data = {
        "hiware_bazar":   [0.30, 0.25, 0.20, 0.18, 0.15, 0.28, 0.55, 0.68, 0.72, 0.65, 0.48, 0.35],
        "ralegan_siddhi": [0.28, 0.23, 0.18, 0.16, 0.14, 0.26, 0.52, 0.65, 0.70, 0.62, 0.45, 0.32],
        "arvari_river":   [0.35, 0.30, 0.26, 0.22, 0.20, 0.32, 0.62, 0.74, 0.78, 0.72, 0.55, 0.42],
        "sukhomajri":     [0.22, 0.20, 0.18, 0.16, 0.14, 0.30, 0.56, 0.65, 0.68, 0.55, 0.38, 0.26],
        "anantapur":      [0.18, 0.15, 0.12, 0.10, 0.09, 0.18, 0.35, 0.42, 0.40, 0.30, 0.22, 0.16],
    }
    return {
        wid: [{"month": m, "ndvi": v} for m, v in zip(months, vals)]
        for wid, vals in data.items()
    }


# ---------------------------------------------------------------------------
# FILE 12 - rainfall_data.json
# ---------------------------------------------------------------------------

def _rainfall_data():
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    data = {
        "hiware_bazar":   [5,  2,  8,  12,  18,  85,  145, 120, 90,  35, 10,  3],
        "ralegan_siddhi": [6,  3,  10, 15,  22,  95,  160, 135, 100, 40, 12,  4],
        "arvari_river":   [8,  5,  10, 5,   10,  55,  175, 155, 110, 25, 8,   3],
        "sukhomajri":     [20, 25, 20, 15,  18,  65,  280, 260, 145, 30, 10,  12],
        "anantapur":      [3,  4,  6,  12,  20,  50,  110, 120, 130, 80, 22,  5],
    }
    return {
        wid: [{"month": m, "rainfall_mm": v} for m, v in zip(months, vals)]
        for wid, vals in data.items()
    }


# ---------------------------------------------------------------------------
# WRITE HELPER
# ---------------------------------------------------------------------------

def _write(filename, data):
    """Serialise data to JSON and write to DATA_DIR/<filename>. Returns path."""
    path = DATA_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------------
# FILE REGISTRY - maps output filename -> generator function
# ---------------------------------------------------------------------------

_FILES = {
    "sample_watersheds.json":                    _sample_watersheds,
    "ndvi_timeseries.json":                      _ndvi_timeseries,
    "water_timeseries.json":                     _water_timeseries,
    "change_data.json":                          _change_data,
    "health_scores.json":                        _health_scores,
    "erosion_data.json":                         _erosion_data,
    "landuse_transition.json":                   _landuse_transition,
    "sample_photo_metadata.json":                _sample_photo_metadata,
    "watershed_boundary_hiware_bazar.geojson":   _watershed_boundary_hiware_bazar,
    "drainage_network.geojson":                  _drainage_network,
    "monthly_ndvi.json":                         _monthly_ndvi,
    "rainfall_data.json":                        _rainfall_data,
}


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINTS
# ---------------------------------------------------------------------------

def generate_all_demo_data():
    """
    Generate all 12 demo data files and write them to the data/ directory.

    Each generator function builds the in-memory Python object; _write()
    serialises it to disk as pretty-printed JSON / GeoJSON.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing demo data to: {DATA_DIR.resolve()}\n")
    for filename, generator in _FILES.items():
        data = generator()
        path = _write(filename, data)
        print(f"  Created  {path.name}")


def verify_demo_data():
    """
    Check that every file generated by generate_all_demo_data() exists and
    contains valid JSON / GeoJSON. Prints a checkmark checklist.

    Returns:
        bool: True if all files are present and valid, False otherwise.
    """
    print("\nVerifying demo data files:")
    all_ok = True

    for filename in _FILES:
        path = DATA_DIR / filename
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    json.load(f)
                size_kb = path.stat().st_size / 1024
                status = f"OK  ({size_kb:.1f} KB)"
                tick = "[OK]"
            except json.JSONDecodeError as exc:
                status = f"INVALID JSON - {exc}"
                tick = "[!!]"
                all_ok = False
        else:
            status = "MISSING"
            tick = "[  ]"
            all_ok = False

        print(f"  {tick}  {filename:<50}  {status}")

    print()
    if all_ok:
        print("All files present and valid.")
    else:
        print("Some files are missing or invalid - re-run this script.")
    return all_ok


if __name__ == "__main__":
    generate_all_demo_data()
    print("\nAll demo data files generated successfully!")
    verify_demo_data()
