import os
import sys

# Ensure data directory exists for tests
os.makedirs("data", exist_ok=True)

from geo_photos.photo_handler import find_nearest_reference_observation

print("\n--- Test 1: Identical Coordinate ---")
res1 = find_nearest_reference_observation(19.352, 74.554, "hiware_bazar")
print("matched:", res1["matched"])
print("distance_m:", res1["distance_m"])

print("\n--- Test 2: Very close Coordinate ---")
# 0.0001 degrees is ~11 meters
res2 = find_nearest_reference_observation(19.3521, 74.5541, "hiware_bazar")
print("matched:", res2["matched"])
print("distance_m:", res2["distance_m"])

print("\n--- Test 3: > 500m away ---")
# 0.01 degrees is ~1.1 km
res3 = find_nearest_reference_observation(19.362, 74.564, "hiware_bazar")
print("matched:", res3["matched"])
print("distance_m:", res3["distance_m"])

print("\n--- Test 4: Different watershed ---")
res4 = find_nearest_reference_observation(19.352, 74.554, "other_watershed")
print("matched:", res4["matched"])
print("distance_m:", res4.get("distance_m"))

print("\n--- Test 5: Missing watershed_id ---")
res5 = find_nearest_reference_observation(19.352, 74.554, None)
print("matched:", res5["matched"])
print("error:", res5.get("error"))

print("\n--- Test 6: Missing JSON ---")
# Temporarily mock the path to a non-existent file
import geo_photos.photo_handler
geo_photos.photo_handler._SAMPLE_PHOTOS_PATH = "data/non_existent.json"
res6 = find_nearest_reference_observation(19.352, 74.554, "hiware_bazar")
print("matched:", res6["matched"])
print("error:", res6.get("error"))

