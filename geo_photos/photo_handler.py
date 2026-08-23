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
from typing import Any, Dict, List, Optional

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


# =============================================================================
# 3. SAVE PHOTO ENTRY
# =============================================================================

def save_photo_entry(
    metadata: Dict[str, Any],
    project_name: str,
    photo_base64: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist a new geo-photo entry to ``data/uploaded_photos.json``.

    The JSON file is created if it does not yet exist. Each entry receives a
    unique timestamp-based ID so repeated uploads never overwrite each other.

    Args:
        metadata    : dict that should include at minimum:
                      lat, lon, type, status, description, date.
                      Any extra keys are preserved.
        project_name: Watershed / project name (stored as ``watershed_id``).
        photo_base64: Optional base64 data-URI thumbnail to embed.

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
        "verified":      False,
        "source":        "uploaded",
    }

    if photo_base64:
        entry["thumbnail_b64"] = photo_base64

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
  {'<span style="margin-left:6px; font-size:10px; color:#888;">✓ Verified</span>' if photo_data.get('verified') else ''}
</div>
""".strip()

    return html
