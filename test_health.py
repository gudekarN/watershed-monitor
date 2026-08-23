import json
from backend.health_score import calculate_watershed_health

def run_test(name, change_data, ts_data):
    res = calculate_watershed_health(change_data, ts_data)
    print(f"\n--- {name} ---")
    print(f"Total: {res['total_score']} ({res['grade']})")
    print(f"Veg: {res['vegetation_score']}/35")
    print(f"Water: {res['water_score']}/35")
    print(f"Erosion: {res['erosion_score']}/20")
    print(f"Sust: {res['sustainability_score']}/10")
    
# 1. Large positive NDVI/water/erosion improvements
cd_large = {
    "vegetation": {"change": 0.5},
    "water": {"change_percent": 500},
    "erosion": {"reduction_percent": 80}
}
run_test("Large Positive", cd_large, [{"ndvi_mean": 0.1}, {"ndvi_mean": 0.2}, {"ndvi_mean": 0.3}, {"ndvi_mean": 0.4}, {"ndvi_mean": 0.5}])

# 2. Zero improvements
cd_zero = {
    "vegetation": {"change": 0.0},
    "water": {"change_percent": 0.0},
    "erosion": {"reduction_percent": 0.0}
}
run_test("Zero Improvements", cd_zero, [{"ndvi_mean": 0.1}, {"ndvi_mean": 0.1}, {"ndvi_mean": 0.1}, {"ndvi_mean": 0.1}])

# 3. Negative improvements
cd_neg = {
    "vegetation": {"change": -0.2},
    "water": {"change_percent": -50.0},
    "erosion": {"reduction_percent": -10.0}
}
run_test("Negative Improvements", cd_neg, [{"ndvi_mean": 0.5}, {"ndvi_mean": 0.4}, {"ndvi_mean": 0.3}, {"ndvi_mean": 0.2}])

# 4. Small incremental changes around the old threshold boundaries
cd_small = {
    "vegetation": {"change": 0.06}, # old threshold was 0.05
    "water": {"change_percent": 11.0}, # old threshold was 10
    "erosion": {"reduction_percent": 16.0} # old threshold was 15
}
run_test("Small Incremental", cd_small, [{"ndvi_mean": 0.1}, {"ndvi_mean": 0.12}, {"ndvi_mean": 0.11}, {"ndvi_mean": 0.15}])

# 5. Fewer than 4 NDVI observations
run_test("Fewer than 4 Obs", cd_small, [{"ndvi_mean": 0.1}, {"ndvi_mean": 0.2}])

# 6. Exactly 4 NDVI observations
run_test("Exactly 4 Obs", cd_small, [{"ndvi_mean": 0.1}, {"ndvi_mean": 0.2}, {"ndvi_mean": 0.15}, {"ndvi_mean": 0.25}])

