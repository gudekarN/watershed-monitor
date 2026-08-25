import pytest
from unittest.mock import patch, MagicMock
from backend.indices import generate_ndvi_timeseries, generate_water_timeseries

@patch("backend.indices.ee")
@patch("backend.indices._ee_ready", return_value=True)
@patch("backend.gee_engine._make_geometry", return_value=MagicMock())
def test_ndvi_timeseries_optimizations(mock_geom, mock_ready, mock_ee):
    # Mock for start_year=2020, end_year=2020 (1 year)
    
    mock_collection = MagicMock()
    mock_ee.ImageCollection.return_value = mock_collection
    
    # ensure filter methods return the same collection mock
    mock_collection.filterBounds.return_value = mock_collection
    mock_collection.filterDate.return_value = mock_collection
    mock_collection.filter.return_value = mock_collection
    
    # Mock composite
    mock_composite = MagicMock()
    mock_collection.median.return_value = mock_composite
    mock_composite.clip.return_value = mock_composite
    
    # Mock NDVI calculate
    with patch("backend.indices.calculate_ndvi") as mock_calc_ndvi:
        mock_ndvi_img = MagicMock()
        mock_calc_ndvi.return_value = mock_ndvi_img
        
        # Mock reduceRegion for NDVI
        mock_stats = {"NDVI_mean": 0.45, "NDVI_min": 0.1, "NDVI_max": 0.8}
        mock_reduce = MagicMock()
        mock_reduce.getInfo.return_value = mock_stats
        mock_ndvi_img.reduceRegion.return_value = mock_reduce
        
        results = generate_ndvi_timeseries(0.0, 0.0, 2020, 2020)
        
        assert len(results) == 1
        assert results[0]["year"] == 2020
        assert results[0]["ndvi_mean"] == 0.45
        assert results[0]["ndvi_min"] == 0.1
        assert results[0]["ndvi_max"] == 0.8
        
        # Verify collection.size() was not called
        assert not mock_collection.size.called, "collection.size() should not be called"
        # Verify reduceRegion was called exactly once
        assert mock_ndvi_img.reduceRegion.call_count == 1
        # Verify getInfo was called exactly once on the reduction
        assert mock_reduce.getInfo.call_count == 1

@patch("backend.indices.ee")
@patch("backend.indices._ee_ready", return_value=True)
@patch("backend.gee_engine._make_geometry", return_value=MagicMock())
def test_water_timeseries_optimizations(mock_geom, mock_ready, mock_ee):
    # Mock for start_year=2020, end_year=2020 (1 year)
    
    mock_collection = MagicMock()
    mock_ee.ImageCollection.return_value = mock_collection
    
    # ensure filter methods return the same collection mock
    mock_collection.filterBounds.return_value = mock_collection
    mock_collection.filterDate.return_value = mock_collection
    mock_collection.filter.return_value = mock_collection
    
    # Mock composite
    mock_composite = MagicMock()
    mock_collection.median.return_value = mock_composite
    mock_composite.clip.return_value = mock_composite
    
    # Mock NDWI calculate
    with patch("backend.indices.calculate_ndwi") as mock_calc_ndwi:
        mock_ndwi_img = MagicMock()
        mock_calc_ndwi.return_value = mock_ndwi_img
        
        # Mock water area methods
        mock_ndwi_gt = MagicMock()
        mock_ndwi_img.gt.return_value = mock_ndwi_gt
        mock_water_area = MagicMock()
        mock_ndwi_gt.multiply.return_value = mock_water_area
        mock_water_area.rename.return_value = mock_water_area
        
        mock_ndwi_img.rename.return_value = mock_ndwi_img
        
        # Mock cat
        mock_cat_img = MagicMock()
        mock_ee.Image.cat.return_value = mock_cat_img
        
        # Mock reduceRegion for water
        mock_stats = {"NDWI_mean": 0.2, "water_area_m2_sum": 50000}
        mock_reduce = MagicMock()
        mock_reduce.getInfo.return_value = mock_stats
        mock_cat_img.reduceRegion.return_value = mock_reduce
        
        results = generate_water_timeseries(0.0, 0.0, 2020, 2020)
        
        assert len(results) == 1
        assert results[0]["year"] == 2020
        assert results[0]["ndwi_mean"] == 0.2
        assert results[0]["water_area_ha"] == 5.0
        
        # Verify collection.size() was not called
        assert not mock_collection.size.called, "collection.size() should not be called"
        # Verify reduceRegion was called exactly once on cat_img
        assert mock_cat_img.reduceRegion.call_count == 1
        # Verify getInfo was called exactly once on the reduction
        assert mock_reduce.getInfo.call_count == 1

if __name__ == "__main__":
    pytest.main([__file__])
