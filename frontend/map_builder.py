"""
frontend/map_builder.py
=======================
Folium map construction for the AquaVeda watershed monitoring dashboard.

All functions return either a folium.Map or modify one in-place.
The module degrades gracefully when optional dependencies (GEE, branca)
are unavailable.

Typical usage in app.py
------------------------
    from frontend.map_builder import build_complete_map

    folium_map = build_complete_map(
        watershed_data=selected_watershed,   # dict from sample_watersheds.json
        photos=load_all_photos(ws_id),
        tile_layers=get_all_tile_layers(...),
        show_layers={"NDVI (After)": True, "True Color (After)": False, ...},
    )
    st_folium(folium_map, use_container_width=True, height=520)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# -- Core dependencies ---------------------------------------------------------
try:
    import folium
    from folium import plugins as folium_plugins
    _FOLIUM_OK = True
except ImportError:
    folium = None
    folium_plugins = None
    _FOLIUM_OK = False
    logger.error("map_builder: folium not installed -- pip install folium")

try:
    import branca
    from branca.colormap import LinearColormap
    _BRANCA_OK = True
except ImportError:
    branca = None
    LinearColormap = None
    _BRANCA_OK = False
    logger.warning("map_builder: branca not installed -- legends disabled.")

# -- Optional GEE bridge ------------------------------------------------------
try:
    from backend.gee_engine import add_ee_layer_to_folium
    _GEE_BRIDGE_OK = True
except ImportError:
    add_ee_layer_to_folium = None
    _GEE_BRIDGE_OK = False

# -- Photo popup HTML ---------------------------------------------------------
try:
    from geo_photos.photo_handler import create_photo_popup_html
    _PHOTO_HANDLER_OK = True
except ImportError:
    create_photo_popup_html = None
    _PHOTO_HANDLER_OK = False

# -- Structure icon map -------------------------------------------------------
_STRUCTURE_ICONS: Dict[str, Dict[str, str]] = {
    "Check Dam":          {"icon": "tint",         "color": "blue"},
    "Farm Pond":          {"icon": "water",         "color": "cadetblue"},
    "Contour Trench":     {"icon": "arrows-alt-h",  "color": "green"},
    "Percolation Tank":   {"icon": "database",      "color": "purple"},
    "Bund":               {"icon": "minus",         "color": "darkgreen"},
    "Recharge Shaft":     {"icon": "arrow-down",    "color": "darkblue"},
    "Nala Bund":          {"icon": "water",         "color": "lightblue"},
    "default":            {"icon": "info-sign",     "color": "gray"},
}

_STATUS_COLORS: Dict[str, str] = {
    "Functional":   "green",
    "Needs Repair": "orange",
    "Damaged":      "red",
    "Dry":          "gray",
}


# =============================================================================
# 1. BASE MAP
# =============================================================================

def create_base_map(
    center_lat: float,
    center_lon: float,
    zoom: int = 12,
) -> Optional["folium.Map"]:
    """
    Create a Folium map with three switchable base tile layers.

    Layers:
      - OpenStreetMap  (default, road/place labels)
      - Esri Satellite (high-res imagery, useful for structure inspection)
      - OpenTopoMap    (contour lines, useful for terrain analysis)

    Args:
        center_lat : Latitude of the map centre.
        center_lon : Longitude of the map centre.
        zoom       : Initial zoom level (default 12 — district level).

    Returns:
        folium.Map with all three base layers added, or None if folium is
        not installed.
    """
    if not _FOLIUM_OK:
        logger.error("create_base_map: folium not available.")
        return None

    # NOTE: folium.Map already adds OpenStreetMap as the default base tile.
    # We must NOT call TileLayer("openstreetmap") again — it would duplicate
    # the entry in LayerControl.
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
        control_scale=True,
        tiles="OpenStreetMap",   # explicit default label
    )

    # Esri World Imagery (satellite, no API key required)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Tiles &copy; Esri",
        name="Satellite",
        overlay=False,
        control=True,
    ).add_to(m)

    # OpenTopoMap (terrain / contours)
    folium.TileLayer(
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr='Map data &copy; OpenStreetMap contributors | OpenTopoMap (CC-BY-SA)',
        name="Terrain",
        overlay=False,
        control=True,
    ).add_to(m)

    logger.debug("create_base_map: created map at (%.4f, %.4f) zoom=%d", center_lat, center_lon, zoom)
    return m


# =============================================================================
# 2. WATERSHED BOUNDARY
# =============================================================================

def add_watershed_boundary(
    m: "folium.Map",
    geojson_data: Any,
    name: str = "Watershed Boundary",
) -> "folium.Map":
    """
    Overlay the watershed polygon as a dashed blue border on the map.

    Args:
        m           : folium.Map to add the layer to.
        geojson_data: GeoJSON dict or file path string.
        name        : Layer name shown in the LayerControl widget.

    Returns:
        The same map (modified in-place).
    """
    if not _FOLIUM_OK or m is None:
        return m
    if geojson_data is None:
        logger.warning("add_watershed_boundary: geojson_data is None, skipping.")
        return m

    try:
        folium.GeoJson(
            geojson_data,
            name=name,
            style_function=lambda _: {
                "fillColor": "transparent",
                "color":     "#0066CC",
                "weight":    3,
                "dashArray": "10 5",
                "fillOpacity": 0.05,
            },
            highlight_function=lambda _: {
                "color":  "#003399",
                "weight": 4,
            },
            tooltip=folium.Tooltip(f"Watershed Boundary — {name}", sticky=False),
        ).add_to(m)
        logger.info("add_watershed_boundary: added '%s'.", name)
    except Exception as exc:
        logger.error("add_watershed_boundary failed: %s", exc)

    return m


# =============================================================================
# 3. GEE SATELLITE TILE LAYERS
# =============================================================================

def add_gee_tile_layers(
    m: "folium.Map",
    tile_layers_dict: Dict[str, Any],
    show_layers: Optional[Dict[str, bool]] = None,
) -> "folium.Map":
    """
    Add GEE satellite tile layers to the map based on user-selected toggles.

    Args:
        m               : folium.Map to add layers to.
        tile_layers_dict: dict returned by ``gee_engine.get_all_tile_layers()``.
                          Keys are layer names; values are tile dicts or None.
        show_layers     : dict of ``{layer_name: bool}`` from the sidebar
                          checkboxes. If None, all non-None layers are added.

    Returns:
        The same map (modified in-place).
    """
    if not _FOLIUM_OK or not _GEE_BRIDGE_OK or m is None:
        return m
    if not tile_layers_dict:
        return m

    show_layers = show_layers or {}

    for layer_name, tile_dict in tile_layers_dict.items():
        # Skip if user toggled off, or if tile_dict is None (GEE fetch failed)
        if not show_layers.get(layer_name, True):
            continue
        if tile_dict is None:
            logger.debug("add_gee_tile_layers: '%s' tile is None, skipping.", layer_name)
            continue

        try:
            add_ee_layer_to_folium(m, tile_dict, opacity=0.7)
            logger.info("add_gee_tile_layers: added '%s'.", layer_name)
        except Exception as exc:
            logger.error("add_gee_tile_layers: '%s' failed: %s", layer_name, exc)

    return m


# =============================================================================
# 4. DRAINAGE NETWORK
# =============================================================================

def add_drainage_network(
    m: "folium.Map",
    drainage_geojson: Any,
) -> "folium.Map":
    """
    Overlay river / stream lines as thin light-blue polylines.

    Args:
        m               : folium.Map.
        drainage_geojson: GeoJSON FeatureCollection dict from
                          ``watershed.get_drainage_network()``.

    Returns:
        The same map.
    """
    if not _FOLIUM_OK or m is None:
        return m
    if not drainage_geojson:
        logger.debug("add_drainage_network: no data, skipping.")
        return m

    try:
        folium.GeoJson(
            drainage_geojson,
            name="Drainage Network",
            style_function=lambda _: {
                "color":   "#4FC3F7",
                "weight":  2,
                "opacity": 0.8,
            },
            tooltip=folium.Tooltip("Stream / River", sticky=False),
        ).add_to(m)
        logger.info("add_drainage_network: added drainage network layer.")
    except Exception as exc:
        logger.error("add_drainage_network failed: %s", exc)

    return m


# =============================================================================
# 5. PHOTO MARKERS
# =============================================================================

def add_photo_markers(
    m: "folium.Map",
    photos_list: List[Dict[str, Any]],
) -> "folium.Map":
    """
    Place camera-icon markers for each geo-tagged field photo.

    Marker colour encodes structure status:
      green  = Functional
      orange = Needs Repair
      red    = Damaged / Dry

    Args:
        m           : folium.Map.
        photos_list : List of photo dicts from ``photo_handler.load_all_photos()``.

    Returns:
        The same map.
    """
    if not _FOLIUM_OK or m is None:
        return m

    added = 0
    for photo in photos_list:
        lat = photo.get("lat")
        lon = photo.get("lon")
        if lat is None or lon is None:
            continue

        try:
            status = photo.get("status", "Functional")
            icon_color = _STATUS_COLORS.get(status, "gray")
            icon = folium.Icon(icon="camera", prefix="fa", color=icon_color)

            # Build popup HTML
            if _PHOTO_HANDLER_OK and create_photo_popup_html:
                popup_html = create_photo_popup_html(photo)
            else:
                popup_html = (
                    f"<b>{photo.get('type','Photo')}</b><br>"
                    f"{photo.get('description','')}<br>"
                    f"<span style='color:gray'>{photo.get('date','')}</span>"
                )

            popup = folium.Popup(
                folium.IFrame(popup_html, width=280, height=220),
                max_width=300,
            )

            folium.Marker(
                location=[lat, lon],
                popup=popup,
                tooltip=f"{photo.get('type','Photo')} — {status}",
                icon=icon,
            ).add_to(m)
            added += 1

        except Exception as exc:
            logger.error("add_photo_markers: skipped photo %s: %s", photo.get("id"), exc)

    logger.info("add_photo_markers: added %d / %d markers.", added, len(photos_list))
    return m


# =============================================================================
# 6. STRUCTURE MARKERS
# =============================================================================

def add_structure_markers(
    m: "folium.Map",
    watershed_data: Dict[str, Any],
) -> "folium.Map":
    """
    Add infrastructure markers for each watershed structure listed in the
    watershed data dict.

    The ``structures`` key is expected to be a dict of
    ``{structure_type: count}``, e.g.::

        {"Check Dams": 52, "Farm Ponds": 38, "Contour Trenches": "1,850 m"}

    Markers are placed pseudo-randomly around the watershed centre so they
    appear on the map even without individual GPS coordinates. When real
    coordinates are present (``structure_locations`` key) those are used.

    Args:
        m              : folium.Map.
        watershed_data : Dict from ``sample_watersheds.json``.

    Returns:
        The same map.
    """
    if not _FOLIUM_OK or m is None or not watershed_data:
        return m

    import math, random
    random.seed(42)  # deterministic jitter so markers don't move on rerun

    center_lat = watershed_data.get("lat", 20.0)
    center_lon = watershed_data.get("lon", 76.0)
    structures  = watershed_data.get("structures", {})

    # If explicit point locations are available, use them
    locations = watershed_data.get("structure_locations", [])
    if locations:
        for loc in locations:
            s_type = loc.get("type", "default")
            cfg = _STRUCTURE_ICONS.get(s_type, _STRUCTURE_ICONS["default"])
            try:
                folium.Marker(
                    location=[loc["lat"], loc["lon"]],
                    tooltip=f"{s_type} — {loc.get('name','')}",
                    icon=folium.Icon(
                        icon=cfg["icon"], prefix="fa", color=cfg["color"]
                    ),
                ).add_to(m)
            except Exception as exc:
                logger.warning("add_structure_markers: %s", exc)
        return m

    # Fallback: scatter one representative marker per structure type
    radius_deg = 0.03  # ~3.3 km scatter radius
    for s_type, count in structures.items():
        # Normalise key to match icon dict (strip plurals, extra spaces)
        normalised = s_type.rstrip("s").strip()
        cfg = _STRUCTURE_ICONS.get(
            s_type,
            _STRUCTURE_ICONS.get(normalised, _STRUCTURE_ICONS["default"]),
        )
        angle = random.uniform(0, 2 * math.pi)
        dist  = random.uniform(0.4, 1.0) * radius_deg
        jlat  = center_lat + dist * math.sin(angle)
        jlon  = center_lon + dist * math.cos(angle)

        try:
            folium.Marker(
                location=[jlat, jlon],
                tooltip=f"{s_type}: {count}",
                popup=folium.Popup(
                    f"<b>{s_type}</b><br>Count: {count}", max_width=180
                ),
                icon=folium.Icon(
                    icon=cfg["icon"], prefix="fa", color=cfg["color"]
                ),
            ).add_to(m)
        except Exception as exc:
            logger.warning("add_structure_markers: icon '%s' failed (%s), using default.", cfg["icon"], exc)
            try:
                folium.Marker(
                    location=[jlat, jlon],
                    tooltip=f"{s_type}: {count}",
                    popup=folium.Popup(f"<b>{s_type}</b><br>Count: {count}", max_width=180),
                ).add_to(m)
            except Exception:
                pass

    logger.info("add_structure_markers: placed markers for %d structure types.", len(structures))
    return m


# =============================================================================
# 7. NDVI LEGEND
# =============================================================================

def add_ndvi_legend(m: "folium.Map") -> "folium.Map":
    """
    Add a colour-gradient NDVI legend to the map using branca.

    Falls back to a plain HTML legend injected via MacroElement when branca
    is not installed.

    Args:
        m : folium.Map.

    Returns:
        The same map.
    """
    if not _FOLIUM_OK or m is None:
        return m

    if _BRANCA_OK and LinearColormap is not None:
        try:
            colormap = LinearColormap(
                colors=["#d73027", "#fee08b", "#1a9850"],
                vmin=-0.2,
                vmax=0.8,
                caption="NDVI — Vegetation Health Index",
            )
            colormap.add_to(m)
            logger.info("add_ndvi_legend: branca colormap added.")
            return m
        except Exception as exc:
            logger.warning("add_ndvi_legend: branca failed (%s), using HTML fallback.", exc)

    # HTML fallback
    legend_html = """
    <div style="
        position: fixed; bottom: 40px; left: 40px; z-index: 1000;
        background: rgba(0,0,0,0.75); border-radius: 8px;
        padding: 10px 14px; color: white; font-family: Arial; font-size: 12px;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.5);">
      <b style="font-size:13px;">NDVI Legend</b><br>
      <div style="margin-top:6px;">
        <span style="background:#1a9850;padding:0 10px;">&nbsp;</span>
        &nbsp;0.6–0.8 Dense vegetation
      </div>
      <div style="margin-top:3px;">
        <span style="background:#fee08b;padding:0 10px;">&nbsp;</span>
        &nbsp;0.2–0.6 Moderate vegetation
      </div>
      <div style="margin-top:3px;">
        <span style="background:#d73027;padding:0 10px;">&nbsp;</span>
        &nbsp;&lt;0.2 Sparse / bare soil
      </div>
    </div>
    """
    try:
        m.get_root().html.add_child(folium.Element(legend_html))
        logger.info("add_ndvi_legend: HTML fallback legend added.")
    except Exception as exc:
        logger.error("add_ndvi_legend: HTML fallback failed: %s", exc)

    return m


# =============================================================================
# 8. MASTER BUILD FUNCTION
# =============================================================================

def build_complete_map(
    watershed_data: Dict[str, Any],
    photos: Optional[List[Dict]] = None,
    tile_layers: Optional[Dict[str, Any]] = None,
    show_layers: Optional[Dict[str, bool]] = None,
    drainage_geojson: Optional[Any] = None,
    watershed_geojson: Optional[Any] = None,
    zoom: int = 12,
) -> Optional["folium.Map"]:
    """
    Assemble the complete interactive watershed map.

    Pipeline
    --------
    1. Create base map (OSM / Satellite / Terrain tile layers)
    2. Add watershed boundary polygon
    3. Add GEE satellite index layers (if available and toggled on)
    4. Add drainage network polylines
    5. Add photo camera markers
    6. Add structure markers (check dams, ponds, etc.)
    7. Add NDVI colour legend
    8. Add LayerControl widget for toggling

    Args:
        watershed_data   : Dict from ``sample_watersheds.json`` — must have
                           ``lat``, ``lon``, ``name``.
        photos           : List of photo dicts from ``load_all_photos()``.
        tile_layers      : Dict from ``gee_engine.get_all_tile_layers()``.
        show_layers      : ``{layer_name: bool}`` — sidebar toggle state.
        drainage_geojson : Optional GeoJSON from ``watershed.get_drainage_network()``.
        watershed_geojson: Optional GeoJSON for the boundary polygon. Falls
                           back to ``watershed_data['boundary_geojson']`` if
                           present.
        zoom             : Initial zoom level (default 12).

    Returns:
        Fully assembled folium.Map, or None if folium is not installed.
    """
    if not _FOLIUM_OK:
        logger.error("build_complete_map: folium not available.")
        return None

    lat = watershed_data.get("lat", 20.0)
    lon = watershed_data.get("lon", 76.0)
    name = watershed_data.get("name", "Watershed")

    show_layers = show_layers or {}

    # -- 1. Base map ----------------------------------------------------------
    m = create_base_map(lat, lon, zoom=zoom)
    if m is None:
        return None

    # -- 2. Watershed boundary ------------------------------------------------
    geojson = (
        watershed_geojson
        or watershed_data.get("boundary_geojson")
        or watershed_data.get("geojson")
    )
    if geojson and show_layers.get("Watershed Boundary", True):
        add_watershed_boundary(m, geojson, name=name)

    # -- 3. GEE satellite tile layers -----------------------------------------
    if tile_layers and _GEE_BRIDGE_OK:
        add_gee_tile_layers(m, tile_layers, show_layers=show_layers)

    # -- 4. Drainage network --------------------------------------------------
    if drainage_geojson and show_layers.get("Drainage Network", True):
        add_drainage_network(m, drainage_geojson)

    # -- 5. Photo markers -----------------------------------------------------
    if photos and show_layers.get("Field Photos", True):
        add_photo_markers(m, photos)

    # -- 6. Structure markers -------------------------------------------------
    if show_layers.get("Structures", True):
        add_structure_markers(m, watershed_data)

    # -- 7. NDVI legend -------------------------------------------------------
    if show_layers.get("NDVI Legend", True):
        add_ndvi_legend(m)

    # -- 8. Layer control (collapsed to keep map clean) ----------------------
    try:
        folium.LayerControl(collapsed=True).add_to(m)
    except Exception as exc:
        logger.warning("build_complete_map: LayerControl failed: %s", exc)

    logger.info(
        "build_complete_map: assembled map for '%s' (%.4f, %.4f).",
        name, lat, lon,
    )
    return m
