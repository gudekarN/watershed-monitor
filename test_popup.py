from geo_photos.photo_handler import create_photo_popup_html

def test_popup(name, data, expected_strings):
    print(f"\n--- Testing: {name} ---")
    html = create_photo_popup_html(data)
    for s in expected_strings:
        if s in html:
            print(f"PASS: found '{s}'")
        else:
            print(f"FAIL: '{s}' not found in HTML!")
            print(html)

test_popup(
    "reference_match",
    {
        "type": "Check Dam",
        "status": "Functional",
        "verification_status": "reference_match",
        "reference_distance_m": 12.5,
        "reference_observation_id": 42,
        "reference_match_type": "sample_field_observation"
    },
    [
        "#dcfce7", # verification_bg
        "#166534", # verification_color
        "Verification: Reference Match",
        "Reference distance: 12.5 m",
        "Reference observation: #42",
        "Source: Sample Field Observation"
    ]
)

test_popup(
    "reference_type_mismatch",
    {
        "type": "Farm Pond",
        "status": "Functional",
        "verification_status": "reference_type_mismatch",
        "reference_distance_m": 5.0,
        "reference_observation_id": 12,
    },
    [
        "#fef3c7", # verification_bg
        "#92400e", # verification_color
        "Verification: Reference Type Mismatch",
        "Reference distance: 5.0 m",
        "Reference observation: #12"
    ]
)

test_popup(
    "no_reference_match",
    {
        "type": "Well",
        "status": "Functional",
        "verification_status": "no_reference_match",
    },
    [
        "#f1f5f9", # verification_bg
        "#475569", # verification_color
        "Verification: No Reference Match",
    ]
)

test_popup(
    "gps_unavailable",
    {
        "type": "Well",
        "status": "Functional",
        "verification_status": "gps_unavailable",
    },
    [
        "#f1f5f9", # verification_bg
        "#475569", # verification_color
        "Verification: Gps Unavailable",
    ]
)

test_popup(
    "verified=True",
    {
        "type": "Check Dam",
        "status": "Functional",
        "verification_status": "reference_match",
        "verified": True,
    },
    [
        "✓ Manually verified"
    ]
)
