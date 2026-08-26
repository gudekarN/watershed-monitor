"""
geo_photos/photo_handler.py
===========================
GPS-tagged photo ingestion, thumbnail generation, and Folium popup rendering
for the AquaVeda watershed monitoring dashboard.

Dependencies
------------
  exifread  : pip install exifread
  Pillow    : pip install Pillow

Both are optional at import time. If missing, functions that require them
return graceful error dicts rather than raising ImportError so the rest of
the dashboard continues to work.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import math

logger = logging.getLogger(__name__)

# -- Optional imports ---------------------------------------------------------
try:
    import exifread
    _EXIF_OK = True
except ImportError:
    exifread = None
    _EXIF_OK = False
    logger.warning("photo_handler: exifread not installed -- GPS extraction disabled.")

try:
    from PIL import Image as _PILImage
    _PIL_OK = True
except ImportError:
    _PILImage = None
    _PIL_OK = False
    logger.warning("photo_handler: Pillow not installed -- thumbnail generation disabled.")

# -- File paths ---------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_SAMPLE_PHOTOS_PATH = os.path.join(_DATA_DIR, "sample_photo_metadata.json")
_UPLOADED_PHOTOS_PATH = os.path.join(_DATA_DIR, "uploaded_photos.json")


# =============================================================================
# 1. GPS EXTRACTION
# =============================================================================

def _dms_to_decimal(dms_values: Any, ref: str) -> float:
    """Convert EXIF DMS (degrees/minutes/seconds) IFDRationals to decimal degrees."""
    d = float(dms_values.values[0].num) / float(dms_values.values[0].den)
    m = float(dms_values.values[1].num) / float(dms_values.values[1].den)
    s = float(dms_values.values[2].num) / float(dms_values.values[2].den)
    decimal = d + (m / 60.0) + (s / 3600.0)
    if str(ref).strip().upper() in ("S", "W"):
        decimal = -decimal
    return decimal


def _haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Return great-circle distance between two GPS points in metres."""
    earth_radius_m = 6_371_000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2.0) ** 2
    )

    return earth_radius_m * 2.0 * math.atan2(
        math.sqrt(a),
        math.sqrt(max(0.0, 1.0 - a)),
    )


def find_nearest_reference_observation(
    lat: float,
    lon: float,
    watershed_id: str,
    max_distance_m: float = 500.0,
) -> Dict[str, Any]:
    """
    Match a GPS coordinate to the nearest known sample field observation.

    This is a prototype/demo reference match, not an authoritative structure
    registry. The reference records come from sample_photo_metadata.json.

    Returns:
        {
            "matched": True/False,
            "distance_m": float,
            "reference": {...},
            "match_type": "sample_field_observation"
        }

    A match is accepted only when the nearest observation is within
    max_distance_m.
    """
    result: Dict[str, Any] = {
        "matched": False,
        "distance_m": None,
        "reference": None,
        "match_type": "sample_field_observation",
    }

    if lat is None or lon is None or not watershed_id:
        return result

    if not os.path.isfile(_SAMPLE_PHOTOS_PATH):
        result["error"] = "sample_photo_metadata.json not found"
        return result

    try:
        with open(_SAMPLE_PHOTOS_PATH, "r", encoding="utf-8") as fh:
            sample_records = json.load(fh)

        if not isinstance(sample_records, list):
            return result

        candidates = [
            item
            for item in sample_records
            if item.get("watershed_id") == watershed_id
            and item.get("lat") is not None
            and item.get("lon") is not None
        ]

        if not candidates:
            result["error"] = "No reference observations for watershed"
            return result

        nearest = None
        nearest_distance = float("inf")

        for candidate in candidates:
            distance = _haversine_distance_m(
                float(lat),
                float(lon),
                float(candidate["lat"]),
                float(candidate["lon"]),
            )

            if distance < nearest_distance:
                nearest_distance = distance
                nearest = candidate

        if nearest is None:
            return result

        result["distance_m"] = round(nearest_distance, 1)

        if nearest_distance <= max_distance_m:
            result["matched"] = True
            result["reference"] = nearest

        return result

    except Exception as exc:
        logger.error(
            "find_nearest_reference_observation failed: %s",
            exc,
        )
        result["error"] = str(exc)
        return result


def extract_gps_from_photo(image_file: Any) -> Dict[str, Any]:
    """
    Extract GPS coordinates and shooting metadata from an uploaded photo.

    Reads EXIF tags using *exifread*. The file pointer is always reset to 0
    before returning so subsequent reads (e.g. Pillow thumbnail) work.

    Args:
        image_file : A file-like object as returned by ``st.file_uploader()``.
                     Must support ``.read()`` and ``.seek()``.

    Returns:
        On success::

            {
                "has_gps":  True,
                "lat":      19.3520,
                "lon":      74.5540,
                "datetime": "2024-06-15 10:30:00",
                "camera":   "Samsung Galaxy A54",
            }

        When GPS tags are absent::

            {"has_gps": False, "datetime": "...", "camera": "..."}

        When exifread is not installed::

            {"has_gps": False, "error": "exifread not installed"}
    """
    if not _EXIF_OK:
        return {"has_gps": False, "error": "exifread not installed"}

    result: Dict[str, Any] = {"has_gps": False}

    try:
        image_file.seek(0)
        tags = exifread.process_file(image_file, details=False)

        # -- GPS coordinates --------------------------------------------------
        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_tag = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")

        if lat_tag and lat_ref and lon_tag and lon_ref:
            lat = _dms_to_decimal(lat_tag, str(lat_ref))
            lon = _dms_to_decimal(lon_tag, str(lon_ref))
            result["has_gps"] = True
            result["lat"]     = round(lat, 6)
            result["lon"]     = round(lon, 6)
        else:
            logger.info("extract_gps_from_photo: no GPS tags found in image.")

        # -- Timestamp --------------------------------------------------------
        dt_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if dt_tag:
            try:
                # EXIF format: "YYYY:MM:DD HH:MM:SS"
                dt_str = str(dt_tag).replace(":", "-", 2)
                result["datetime"] = dt_str
            except Exception:
                result["datetime"] = str(dt_tag)

        # -- Camera make / model ----------------------------------------------
        make  = tags.get("Image Make",  "")
        model = tags.get("Image Model", "")
        if make or model:
            result["camera"] = f"{make} {model}".strip()

    except Exception as exc:
        logger.error("extract_gps_from_photo failed: %s", exc)
        result["error"] = str(exc)
    finally:
        try:
            image_file.seek(0)
        except Exception:
            pass

    return result


# =============================================================================
# 2. THUMBNAIL GENERATION
# =============================================================================

def create_photo_thumbnail(
    image_file: Any,
    size: tuple = (200, 150),
) -> Optional[str]:
    """
    Resize an uploaded image and return it as a base64 data-URI.

    The data-URI can be embedded directly in Folium popup HTML without any
    separate server request.

    Args:
        image_file : File-like object (Streamlit upload or open file handle).
        size       : Maximum bounding box ``(width, height)`` in pixels.
                     ``Image.thumbnail()`` preserves the aspect ratio.

    Returns:
        ``"data:image/jpeg;base64,<encoded>"`` string, or ``None`` on failure.
    """
    if not _PIL_OK:
        logger.warning("create_photo_thumbnail: Pillow not installed.")
        return None

    try:
        image_file.seek(0)
        img = _PILImage.open(image_file)

        # Convert to RGB so we can always save as JPEG
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        img.thumbnail(size, _PILImage.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=70, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    except Exception as exc:
        logger.error("create_photo_thumbnail failed: %s", exc)
        return None
    finally:
        try:
            image_file.seek(0)
        except Exception:
            pass


def create_photo_image_b64(
    image_file: Any,
    max_size: tuple = (800, 600),
    quality: int = 90,
) -> Optional[str]:
    """
    Encode an uploaded image at display quality for the field-verification card.

    Unlike ``create_photo_thumbnail`` (200×150 / q=70 for Folium map popups),
    this produces a larger, higher-quality representation suitable for
    displaying inside a Streamlit card via ``st.image()``.

    Args:
        image_file : File-like object (Streamlit upload or open file handle).
        max_size   : Maximum bounding box ``(width, height)``. Aspect ratio
                     is always preserved.
        quality    : JPEG quality (0–95). Defaults to 90.

    Returns:
        ``"data:image/jpeg;base64,<encoded>"`` string, or ``None`` on failure.
    """
    if not _PIL_OK:
        logger.warning("create_photo_image_b64: Pillow not installed.")
        return None

    try:
        image_file.seek(0)
        img = _PILImage.open(image_file)

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        img.thumbnail(max_size, _PILImage.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    except Exception as exc:
        logger.error("create_photo_image_b64 failed: %s", exc)
        return None
    finally:
        try:
            image_file.seek(0)
        except Exception:
            pass


# =============================================================================
# 3. SAVE PHOTO ENTRY
# =============================================================================

def save_photo_entry(
    metadata: Dict[str, Any],
    project_name: str,
    photo_base64: Optional[str] = None,
    photo_image_b64: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist a new geo-photo entry to ``data/uploaded_photos.json``.

    The JSON file is created if it does not yet exist. Each entry receives a
    unique timestamp-based ID so repeated uploads never overwrite each other.

    Args:
        metadata       : dict that should include at minimum:
                         lat, lon, type, status, description, date.
                         Any extra keys are preserved.
        project_name   : Watershed / project name (stored as ``watershed_id``).
        photo_base64   : Optional base64 data-URI *thumbnail* (200x150 / q=70).
                         Used for Folium map popup HTML only.
        photo_image_b64: Optional base64 data-URI at display quality (800x600 /
                         q=90). Used for the Field Verification card display.
                         Stored separately from ``thumbnail_b64`` so the Folium
                         popup always gets the smaller blob.

    Returns:
        The newly created entry dict (including the generated ``id``).
    """
    entry_id = f"upload_{int(time.time() * 1000)}"

    entry: Dict[str, Any] = {
        "id":            entry_id,
        "watershed_id":  project_name,
        "lat":           metadata.get("lat"),
        "lon":           metadata.get("lon"),
        "type":          metadata.get("type", "Field Photo"),
        "status":        metadata.get("status", "Functional"),
        "water_level":   metadata.get("water_level", ""),
        "date":          metadata.get("date", datetime.now().strftime("%Y-%m-%d")),
        "description":   metadata.get("description", ""),
        "verified":      bool(metadata.get("verified", False)),
        "source":        "uploaded",

        # GPS/reference matching metadata.
        "verification_status": metadata.get(
            "verification_status",
            "pending_reference_match",
        ),
        "reference_observation_id": metadata.get(
            "reference_observation_id"
        ),
        "reference_distance_m": metadata.get(
            "reference_distance_m"
        ),
        "reference_match_type": metadata.get(
            "reference_match_type"
        ),
    }

    # thumbnail_b64 — small blob for Folium map popup HTML
    if photo_base64:
        entry["thumbnail_b64"] = photo_base64

    # photo_image_b64 — larger, higher-quality blob for card display
    if photo_image_b64:
        entry["photo_image_b64"] = photo_image_b64

    # -- Load existing entries ------------------------------------------------
    existing: List[Dict] = []
    if os.path.isfile(_UPLOADED_PHOTOS_PATH):
        try:
            with open(_UPLOADED_PHOTOS_PATH, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
            if not isinstance(existing, list):
                existing = []
        except Exception as exc:
            logger.warning("save_photo_entry: could not read existing file: %s", exc)
            existing = []

    existing.append(entry)

    # -- Write back -----------------------------------------------------------
    try:
        os.makedirs(os.path.dirname(_UPLOADED_PHOTOS_PATH), exist_ok=True)
        with open(_UPLOADED_PHOTOS_PATH, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2, ensure_ascii=False)
        logger.info("save_photo_entry: saved entry %s (total=%d).", entry_id, len(existing))
    except Exception as exc:
        logger.error("save_photo_entry: write failed: %s", exc)

    return entry


# =============================================================================
# 4. LOAD ALL PHOTOS
# =============================================================================

def load_all_photos(
    watershed_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Load and merge sample + user-uploaded geo-photos.

    Sample photos come from ``data/sample_photo_metadata.json`` (always
    present). Uploaded photos from ``data/uploaded_photos.json`` (optional —
    created when users upload via the dashboard).

    Args:
        watershed_id : If provided, only photos whose ``watershed_id`` field
                       matches this value are returned. Pass ``None`` to get
                       all photos across all watersheds.

    Returns:
        Merged, optionally filtered list of photo dicts. Preserves insertion
        order: sample photos first, uploaded photos appended.
    """
    photos: List[Dict] = []

    # -- Sample photos --------------------------------------------------------
    try:
        if os.path.isfile(_SAMPLE_PHOTOS_PATH):
            with open(_SAMPLE_PHOTOS_PATH, "r", encoding="utf-8") as fh:
                sample = json.load(fh)
            if isinstance(sample, list):
                photos.extend(sample)
            logger.info("load_all_photos: loaded %d sample photos.", len(sample))
    except Exception as exc:
        logger.error("load_all_photos: could not read sample photos: %s", exc)

    # -- Uploaded photos ------------------------------------------------------
    try:
        if os.path.isfile(_UPLOADED_PHOTOS_PATH):
            with open(_UPLOADED_PHOTOS_PATH, "r", encoding="utf-8") as fh:
                uploaded = json.load(fh)
            if isinstance(uploaded, list):
                photos.extend(uploaded)
            logger.info("load_all_photos: loaded %d uploaded photos.", len(uploaded))
    except Exception as exc:
        logger.error("load_all_photos: could not read uploaded photos: %s", exc)

    # -- Filter by watershed --------------------------------------------------
    if watershed_id is not None:
        photos = [p for p in photos if p.get("watershed_id") == watershed_id]

    return photos


# =============================================================================
# 5. FOLIUM POPUP HTML
# =============================================================================

def create_photo_popup_html(photo_data: Dict[str, Any]) -> str:
    """
    Generate an inline HTML string for a Folium marker popup.

    The popup shows:
      - Structure type and status badge (colour-coded)
      - GPS coordinates and date
      - Description text
      - Water level if present
      - Embedded thumbnail image if ``thumbnail_b64`` is in photo_data

    Args:
        photo_data : A photo dict as returned by ``load_all_photos()``.

    Returns:
        HTML string ready to pass to ``folium.Popup(html=..., max_width=300)``.
    """
    status = photo_data.get("status", "Unknown")
    status_color_map = {
        "Functional":   "#28a745",
        "Needs Repair": "#ffc107",
        "Damaged":      "#dc3545",
        "Dry":          "#6c757d",
    }
    badge_bg    = status_color_map.get(status, "#6c757d")
    badge_color = "black" if status == "Needs Repair" else "white"

    lat = photo_data.get("lat", 0.0)
    lon = photo_data.get("lon", 0.0)

    water_level_html = ""
    if photo_data.get("water_level"):
        water_level_html = (
            f'<br><span style="font-size:11px; color:#888;">'
            f'💧 Water Level: {photo_data["water_level"]}</span>'
        )

    # Thumbnail — only included when a base64 blob is present
    thumbnail_html = ""
    if photo_data.get("thumbnail_b64"):
        thumbnail_html = (
            f'<img src="{photo_data["thumbnail_b64"]}" '
            f'style="width:100%; border-radius:4px; margin-bottom:6px;" />'
        )

    verification_status = photo_data.get(
        "verification_status",
        "not_matched",
    )

    reference_distance = photo_data.get("reference_distance_m")
    reference_id = photo_data.get("reference_observation_id")
    reference_match_type = photo_data.get("reference_match_type")

    verification_label = (
        verification_status.replace("_", " ").title()
        if verification_status
        else "Not Matched"
    )

    if verification_status == "reference_match":
        verification_bg = "#dcfce7"
        verification_color = "#166534"
    elif verification_status == "reference_type_mismatch":
        verification_bg = "#fef3c7"
        verification_color = "#92400e"
    elif verification_status in ("no_reference_match", "gps_unavailable"):
        verification_bg = "#f1f5f9"
        verification_color = "#475569"
    else:
        verification_bg = "#f1f5f9"
        verification_color = "#475569"

    reference_html = ""

    if reference_distance is not None:
        try:
            reference_html += (
                f'<br><span style="font-size:11px; color:#666;">'
                f'📏 Reference distance: {float(reference_distance):.1f} m'
                f'</span>'
            )
        except (TypeError, ValueError):
            pass

    if reference_id is not None:
        reference_html += (
            f'<br><span style="font-size:11px; color:#666;">'
            f'🔎 Reference observation: #{reference_id}'
            f'</span>'
        )

    if reference_match_type:
        reference_html += (
            f'<br><span style="font-size:10px; color:#888;">'
            f'Source: {reference_match_type.replace("_", " ").title()}'
            f'</span>'
        )

    # Pre-compute the manually-verified snippet so it can be safely
    # interpolated into the f-string below.  Embedding a Python
    # conditional directly inside {{ }} in an f-string only escapes the
    # braces — it does NOT evaluate the expression — causing the raw
    # Python source to appear as visible text in the rendered popup.
    manually_verified_html = (
        '<span style="display:block; margin-top:6px; font-size:10px; color:#888;">'
        "✓ Manually verified"
        "</span>"
        if photo_data.get("verified")
        else ""
    )

    html = f"""
<div style="width:260px; font-family:Arial, sans-serif; font-size:13px;">
  {thumbnail_html}

  <h4 style="margin:0 0 4px 0; color:#1a1a2e;">
    {photo_data.get('type', 'Structure')}
  </h4>

  <p style="margin:0 0 4px 0; color:#888; font-size:11px;">
    📍 {lat:.4f}, {lon:.4f}&nbsp;&nbsp;
    📅 {photo_data.get('date', 'N/A')}
    {water_level_html}
  </p>

  <p style="margin:4px 0 6px 0; color:#333;">
    {photo_data.get('description', '')}
  </p>

  <span style="
    background:{badge_bg};
    color:{badge_color};
    padding:2px 10px;
    border-radius:10px;
    font-size:11px;
    font-weight:600;">
    {status}
  </span>

  <div style="
    margin-top:8px;
    padding:7px;
    background:{verification_bg};
    color:{verification_color};
    border-radius:6px;
    font-size:11px;
    font-weight:600;">
    📍 Verification: {verification_label}
    {reference_html}
  </div>

  {manually_verified_html}

</div>
""".strip()

    return html
