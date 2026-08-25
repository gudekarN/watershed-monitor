"""
backend/watershed.py
====================
Watershed delineation and hydrology analysis using pre-computed GEE datasets.

Uses WWF HydroBASINS and HydroSHEDS data. Does not use custom hydrology algorithms.
"""

import json
import logging
import os
from typing import Any, Dict

try:
    import ee
    _EE_OK = True
except ImportError:
    ee = None
    _EE_OK = False

logger = logging.getLogger(__name__)

def _ee_ready() -> bool:
    if not _EE_OK or ee is None:
        return False
    try:
        return bool(ee.data.is_initialized())
    except Exception:
        return False

def delineate_watershed(lat: float, lon: float) -> Dict[str, Any]:
    """Get watershed boundary containing the given point.
    
    Uses WWF HydroBASINS Level 7 — pre-computed watershed polygons
    covering the entire globe. No custom hydrology needed.
    """
    if not _ee_ready():
        return {
            'geometry': None,
            'geojson': None,
            'area_sq_km': None,
            'basin_id': None,
            'success': False,
            'error': 'GEE not available'
        }

    try:
        # Load HydroBASINS Level 7 (good resolution for district-level projects)
        basins = ee.FeatureCollection('WWF/HydroSHEDS/v1/Basins/hybas_7')
        
        # Find basin containing the point
        point = ee.Geometry.Point([lon, lat])  # GEE uses [lon, lat] order
        basin = basins.filterBounds(point).first()
        
        # Get geometry and properties
        basin_geometry = basin.geometry()
        area_sq_km = basin_geometry.area().divide(1e6).getInfo()
        basin_id = basin.get('HYBAS_ID').getInfo()
        
        # Convert to GeoJSON for Folium display
        geojson = basin_geometry.getInfo()
        
        return {
            'geometry': basin_geometry,      # ee.Geometry for GEE operations
            'geojson': geojson,              # dict for Folium
            'area_sq_km': round(area_sq_km, 2),
            'basin_id': basin_id,
            'success': True
        }
    except Exception as e:
        logger.error(f"Watershed delineation failed: {e}")
        return {
            'geometry': None,
            'geojson': None,
            'area_sq_km': None,
            'basin_id': None,
            'success': False,
            'error': str(e)
        }

def get_drainage_network(geometry: "ee.Geometry") -> Dict[str, Any]:
    """Get stream/river network within the watershed."""
    if not _ee_ready() or geometry is None:
        return {'geojson': None, 'count': 0, 'success': False}
        
    try:
        rivers = ee.FeatureCollection('WWF/HydroSHEDS/v1/FreeFlowingRivers')
        local_rivers = rivers.filterBounds(geometry)
        geojson = local_rivers.getInfo()
        return {
            'geojson': geojson,
            'count': local_rivers.size().getInfo(),
            'success': True
        }
    except Exception as e:
        logger.error(f"Drainage network failed: {e}")
        return {'geojson': None, 'count': 0, 'success': False}

def get_terrain_stats(geometry: "ee.Geometry") -> Dict[str, Any]:
    """Calculate terrain statistics for the watershed."""
    if not _ee_ready() or geometry is None:
        return {'success': False, 'error': 'GEE not available or geometry None'}

    try:
        dem = ee.Image('USGS/SRTMGL1_003')
        slope = ee.Terrain.slope(dem)  # This DOES work in current GEE
        
        # Elevation stats
        elev_stats = dem.reduceRegion(
            reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
            geometry=geometry,
            scale=30,
            maxPixels=1e9
        ).getInfo()
        
        # Slope stats
        slope_stats = slope.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
            geometry=geometry,
            scale=30,
            maxPixels=1e9
        ).getInfo()
        
        return {
            'elevation_min': round(elev_stats.get('elevation_min', 0), 1),
            'elevation_max': round(elev_stats.get('elevation_max', 0), 1),
            'elevation_mean': round(elev_stats.get('elevation_mean', 0), 1),
            'slope_mean': round(slope_stats.get('slope_mean', 0), 1),
            'slope_max': round(slope_stats.get('slope_max', 0), 1),
            'success': True
        }
    except Exception as e:
        logger.error(f"Terrain stats failed: {e}")
        return {'success': False, 'error': str(e)}

def get_slope_image(geometry: "ee.Geometry") -> Any:
    """
    Returns ee.Image of slope clipped to watershed boundary
    For erosion risk visualization on map
    """
    if not _ee_ready() or geometry is None:
        return None
        
    try:
        dem = ee.Image('USGS/SRTMGL1_003')
        slope = ee.Terrain.slope(dem).clip(geometry)
        return slope
    except Exception as e:
        logger.error(f"Slope image failed: {e}")
        return None

def get_demo_watershed(watershed_id: str) -> Dict[str, Any]:
    """
    Loads pre-generated GeoJSON from data/watershed_boundary_{id}.geojson
    Returns same format dict as delineate_watershed but from file.
    Used when GEE is unavailable.
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, 'data', f'watershed_boundary_{watershed_id}.geojson')
        
        if not os.path.exists(file_path):
            logger.error(f"Demo file not found: {file_path}")
            return {
                'geometry': None,
                'geojson': None,
                'area_sq_km': None,
                'basin_id': watershed_id,
                'success': False,
                'error': 'Demo file not found'
            }
            
        with open(file_path, 'r', encoding='utf-8') as f:
            geojson = json.load(f)
            
        return {
            'geometry': None, # We don't have ee.Geometry here
            'geojson': geojson,
            'area_sq_km': 15.0, # Dummy area
            'basin_id': watershed_id,
            'success': True
        }
    except Exception as e:
        logger.error(f"get_demo_watershed failed: {e}")
        return {
            'geometry': None,
            'geojson': None,
            'area_sq_km': None,
            'basin_id': watershed_id,
            'success': False,
            'error': str(e)
        }

def calculate_erosion_risk(geometry: "ee.Geometry", ndvi_image: "ee.Image" = None) -> Dict[str, Any]:
    """Calculate erosion risk map from slope and vegetation."""
    if not _ee_ready() or geometry is None:
        return {'success': False, 'error': 'GEE not available'}

    try:
        dem = ee.Image('USGS/SRTMGL1_003')
        slope = ee.Terrain.slope(dem).clip(geometry)
        
        # Normalize slope: 0-45 degrees -> 0-1
        slope_normalized = slope.divide(45).min(1)
        
        if ndvi_image is not None:
            # Inverse NDVI: less vegetation = more erosion risk
            inverse_ndvi = ee.Image(1).subtract(ndvi_image.select('NDVI')).clip(geometry)
            # Ensure range 0-1
            inverse_ndvi = inverse_ndvi.max(0).min(1)
            
            # Combined risk: 60% slope + 40% inverse vegetation
            risk = slope_normalized.multiply(0.6).add(inverse_ndvi.multiply(0.4))
        else:
            risk = slope_normalized
        
        risk = risk.rename('erosion_risk').clip(geometry)
        
        # Classify into 5 classes
        # 0-0.2: Very Low, 0.2-0.4: Low, 0.4-0.6: Medium, 0.6-0.8: High, 0.8-1.0: Very High
        classified = (risk.multiply(5).floor().min(4)).rename('erosion_class')
        
        # Get all erosion-class areas in ONE GEE reduction.
        #
        # Each class is represented as a separate band containing pixel area
        # only where that class is present. This avoids five independent
        # reduceRegion().getInfo() calls.

        class_names = [
            'Very Low',
            'Low',
            'Medium',
            'High',
            'Very High',
        ]

        area_bands = [
            classified.eq(0)
                .multiply(ee.Image.pixelArea())
                .rename('very_low_m2'),

            classified.eq(1)
                .multiply(ee.Image.pixelArea())
                .rename('low_m2'),

            classified.eq(2)
                .multiply(ee.Image.pixelArea())
                .rename('medium_m2'),

            classified.eq(3)
                .multiply(ee.Image.pixelArea())
                .rename('high_m2'),

            classified.eq(4)
                .multiply(ee.Image.pixelArea())
                .rename('very_high_m2'),
        ]

        class_area_image = ee.Image.cat(area_bands)

        area_result = class_area_image.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=30,
            maxPixels=1e9,
        ).getInfo()

        class_areas = {
            'Very Low': round(float(area_result.get('very_low_m2', 0) or 0) / 10000, 1),
            'Low':      round(float(area_result.get('low_m2', 0) or 0) / 10000, 1),
            'Medium':   round(float(area_result.get('medium_m2', 0) or 0) / 10000, 1),
            'High':     round(float(area_result.get('high_m2', 0) or 0) / 10000, 1),
            'Very High':round(float(area_result.get('very_high_m2', 0) or 0) / 10000, 1),
        }
        
        return {
            'risk_image': risk,
            'classified_image': classified,
            'class_areas': class_areas,
            'success': True
        }
    except Exception as e:
        logger.error(f"Calculate erosion risk failed: {e}")
        return {'success': False, 'error': str(e)}

def compare_erosion(geometry: "ee.Geometry", before_image: "ee.Image", after_image: "ee.Image") -> Dict[str, Any]:
    """
    Calculate erosion risk for both before and after images.
    Compare: how many hectares moved from High/Very High to lower classes.
    Returns change statistics.
    """
    if not _ee_ready() or geometry is None:
        return {'success': False, 'error': 'GEE not available'}

    try:
        before_risk = calculate_erosion_risk(geometry, before_image)
        after_risk = calculate_erosion_risk(geometry, after_image)

        if not before_risk.get('success') or not after_risk.get('success'):
            return {'success': False, 'error': 'Erosion risk calculation failed'}

        before_areas = before_risk['class_areas']
        after_areas = after_risk['class_areas']

        # High/Very High total before and after
        high_risk_before = before_areas.get('High', 0) + before_areas.get('Very High', 0)
        high_risk_after = after_areas.get('High', 0) + after_areas.get('Very High', 0)

        # Hectares improved (moved from High/Very High to lower classes)
        improved_ha = round(high_risk_before - high_risk_after, 1)

        return {
            'before_areas': before_areas,
            'after_areas': after_areas,
            'high_risk_before_ha': high_risk_before,
            'high_risk_after_ha': high_risk_after,
            'improved_ha': improved_ha,
            'success': True
        }
    except Exception as e:
        logger.error(f"Compare erosion failed: {e}")
        return {'success': False, 'error': str(e)}
