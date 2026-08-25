from unittest.mock import patch, MagicMock
from backend.watershed import calculate_erosion_risk

@patch("backend.watershed.ee")
@patch("backend.watershed._ee_ready", return_value=True)
def test_watershed_optimizations(mock_ready, mock_ee):
    geom = MagicMock()
    ndvi_image = MagicMock()
    
    # Mock dem, slope, risk image creations
    mock_ee.Image.return_value = MagicMock()
    mock_ee.Terrain.slope.return_value = MagicMock()
    
    mock_area_stats = {
        "very_low_m2": 10000,
        "low_m2": 20000,
        "medium_m2": 30000,
        "high_m2": 40000,
        "very_high_m2": 50000,
    }
    mock_area_reduce = MagicMock()
    mock_area_reduce.getInfo.return_value = mock_area_stats
    
    cat_instance = MagicMock()
    mock_ee.Image.cat.return_value = cat_instance
    cat_instance.reduceRegion.return_value = mock_area_reduce
    
    risk_result = calculate_erosion_risk(geom, ndvi_image)
    
    print("Success:", risk_result.get("success"))
    print("Class areas:", risk_result.get("class_areas"))
    
    class_areas = risk_result.get("class_areas")
    assert class_areas["Very Low"] == 1.0
    assert class_areas["Low"] == 2.0
    assert class_areas["Medium"] == 3.0
    assert class_areas["High"] == 4.0
    assert class_areas["Very High"] == 5.0
    
    assert cat_instance.reduceRegion.call_count == 1
    print("Erosion reduceRegion calls:", cat_instance.reduceRegion.call_count)

if __name__ == "__main__":
    test_watershed_optimizations()
