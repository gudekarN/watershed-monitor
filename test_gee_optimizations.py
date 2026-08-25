from unittest.mock import patch, MagicMock
from backend.change_detection import detect_vegetation_change, detect_water_change
import backend.change_detection

@patch("backend.change_detection.ee")
@patch("backend.change_detection._ee_ready", return_value=True)
@patch("backend.change_detection.calculate_ndvi")
@patch("backend.change_detection.calculate_ndwi")
@patch("backend.change_detection._pixel_area_image")
def test_gee_optimizations(mock_area, mock_ndwi, mock_ndvi, mock_ready, mock_ee):
    # Mock some basic images/geometry
    img_before = MagicMock()
    img_after = MagicMock()
    geom = MagicMock()
    
    # Mock NDVI outputs
    mock_ndvi_before = MagicMock()
    mock_ndvi_after = MagicMock()
    mock_ndvi.side_effect = [mock_ndvi_before, mock_ndvi_after]
    
    # Setup the getInfo return for vegetation
    mock_area_stats = {"improved_area_m2": 10000, "declined_area_m2": 20000, "unchanged_area_m2": 30000}
    mock_mean_stats = {"ndvi_before": 0.4, "ndvi_after": 0.5}
    
    # Mock the reduceRegion chain for vegetation
    mock_area_reduce = MagicMock()
    mock_area_reduce.getInfo.return_value = mock_area_stats
    
    mock_mean_reduce = MagicMock()
    mock_mean_reduce.getInfo.return_value = mock_mean_stats
    
    # We patch ee.Image.cat to return an object where reduceRegion returns our mocks
    cat_instance = MagicMock()
    mock_ee.Image.cat.return_value = cat_instance
    cat_instance.reduceRegion.side_effect = [mock_area_reduce, mock_mean_reduce]
    
    veg = detect_vegetation_change(img_before, img_after, geom)
    print("Vegetation success:", veg["success"])
    assert veg["improved_area_ha"] == 1.0
    assert cat_instance.reduceRegion.call_count == 2
    print("Vegetation reduceRegion calls:", cat_instance.reduceRegion.call_count)

    # Mock NDWI outputs
    mock_ndwi_before = MagicMock()
    mock_ndwi_after = MagicMock()
    mock_ndwi.side_effect = [mock_ndwi_before, mock_ndwi_after]

    mock_water_stats = {
        "water_before_area_m2": 50000,
        "water_after_area_m2": 60000,
        "new_water_area_m2": 20000,
        "lost_water_area_m2": 10000
    }
    mock_water_reduce = MagicMock()
    mock_water_reduce.getInfo.return_value = mock_water_stats

    # Reset call counts
    cat_instance.reduceRegion.reset_mock()
    cat_instance.reduceRegion.side_effect = [mock_water_reduce]
    
    water = detect_water_change(img_before, img_after, geom)
    print("Water success:", water["success"])
    assert water["area_before_ha"] == 5.0
    assert cat_instance.reduceRegion.call_count == 1
    print("Water reduceRegion calls:", cat_instance.reduceRegion.call_count)


if __name__ == "__main__":
    test_gee_optimizations()
