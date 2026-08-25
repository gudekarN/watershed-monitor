from unittest.mock import patch, MagicMock
from backend.change_detection import generate_change_summary
import backend.gee_engine

@patch("backend.change_detection._ee_ready", return_value=True)
@patch("backend.change_detection._ENGINE_OK", True)
@patch("backend.change_detection.get_sentinel2_image")
def test_prebuilt_images(mock_get_img, mock_ee_ready):
    # Mock some basic images/geometry
    img_before = MagicMock()
    img_after = MagicMock()
    geom = MagicMock()
    
    # Run the summary
    summary = generate_change_summary(
        lat=20.0,
        lon=76.0,
        before_dates={"start": "2019", "end": "2019"},
        after_dates={"start": "2024", "end": "2024"},
        before_image=img_before,
        after_image=img_after,
        geometry=geom
    )
    
    # Verify get_sentinel2_image was skipped
    assert mock_get_img.call_count == 0, f"Expected 0 calls, got {mock_get_img.call_count}"
    print("Test passed: get_sentinel2_image was called 0 times when optional images supplied.")

if __name__ == "__main__":
    test_prebuilt_images()
