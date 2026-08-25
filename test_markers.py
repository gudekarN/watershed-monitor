import folium
from frontend.map_builder import add_structure_markers

# Test 1: Only structures dictionary
m1 = folium.Map()
data1 = {"structures": {"Check Dams": 8}}
add_structure_markers(m1, data1)
# folium.Map stores added elements in _children
markers1 = [c for c in m1._children.values() if isinstance(c, folium.Marker)]
print(f"Test 1 Markers Count: {len(markers1)} (Expected: 0)")

# Test 2: Real structure locations
m2 = folium.Map()
data2 = {
    "structure_locations": [
        {
            "type": "Check Dam",
            "name": "CD-01",
            "lat": 19.352,
            "lon": 74.554
        }
    ]
}
add_structure_markers(m2, data2)
markers2 = [c for c in m2._children.values() if isinstance(c, folium.Marker)]
print(f"Test 2 Markers Count: {len(markers2)} (Expected: 1)")

with open("frontend/map_builder.py", "r") as f:
    content = f.read()
if "random" in content:
    print("Test 3: 'random' found in map_builder.py! Please check if it's used.")
else:
    print("Test 3: 'random' is successfully removed from map_builder.py.")
