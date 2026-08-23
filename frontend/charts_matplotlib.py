"""
frontend/charts_matplotlib.py
==============================
Matplotlib chart functions for embedding in PDF reports.

IMPORTANT: Uses Agg backend (non-interactive) — plotly/kaleido NOT used.
All functions write a PNG to disk and return the path.
"""

import os
import math

import matplotlib
matplotlib.use('Agg')  # Must be before pyplot import
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np

# ─── Colour palette ───────────────────────────────────────────────────────────
_GREEN  = "#1a9850"
_LBLUE  = "#4fc3f7"
_RED    = "#d73027"
_ORANGE = "#f46d43"
_YELLOW = "#fee08b"
_GRAY   = "#9e9e9e"

_RISK_COLORS = {
    "Very Low":  "#1a9850",
    "Low":       "#91cf60",
    "Medium":    "#fee08b",
    "High":      "#f46d43",
    "Very High": "#d73027",
}

_LANDUSE_COLORS = {
    "Water":             "#3b82f6",
    "Dense Vegetation":  "#16a34a",
    "Sparse Vegetation": "#86efac",
    "Barren":            "#d97706",
    "Built-up":          "#6b7280",
}

_DARK_BG    = "#1e293b"
_PANEL_BG   = "#0f172a"
_TEXT_COLOR = "#e2e8f0"


def _apply_dark_theme(fig, ax):
    """Apply a consistent dark theme to a figure/axes."""
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_PANEL_BG)
    ax.tick_params(colors=_TEXT_COLOR, labelsize=9)
    ax.xaxis.label.set_color(_TEXT_COLOR)
    ax.yaxis.label.set_color(_TEXT_COLOR)
    ax.title.set_color(_TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_edgecolor("#334155")


# ─────────────────────────────────────────────────────────────────────────────
# 1. NDVI TREND LINE CHART
# ─────────────────────────────────────────────────────────────────────────────

def create_ndvi_trend_matplotlib(timeseries_data, project_start_year, save_path):
    """NDVI trend line chart saved as PNG.

    Parameters
    ----------
    timeseries_data   : list of dicts with keys ``year`` and ``ndvi_mean``
    project_start_year: int or None  — draws a vertical annotation line
    save_path         : str          — full path to output PNG file
    """
    if not timeseries_data:
        return None

    years = [d["year"] for d in timeseries_data]
    ndvi  = [d["ndvi_mean"] for d in timeseries_data]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=100)
    _apply_dark_theme(fig, ax)

    # Fill range band if min/max available
    ndvi_max = [d.get("ndvi_max", d["ndvi_mean"]) for d in timeseries_data]
    ndvi_min = [d.get("ndvi_min", d["ndvi_mean"]) for d in timeseries_data]
    ax.fill_between(years, ndvi_min, ndvi_max, alpha=0.10, color=_GREEN)

    # Main line
    ax.plot(years, ndvi, marker="o", color=_GREEN, linewidth=2.5,
            markersize=8, label="Mean NDVI", zorder=5)
    ax.fill_between(years, ndvi, alpha=0.15, color=_GREEN)

    # Healthy threshold
    ax.axhline(y=0.4, color=_RED, linestyle="--", linewidth=1.5,
               alpha=0.8, label="Healthy Threshold (0.4)")
    ax.text(years[0] + 0.1, 0.42, "Healthy Threshold", fontsize=8,
            color=_RED, alpha=0.9)

    # Project start line
    if project_start_year and years[0] <= project_start_year <= years[-1]:
        ax.axvline(x=project_start_year, color=_GRAY, linestyle=":",
                   linewidth=1.5, alpha=0.8)
        ax.annotate(
            "Project Started ↓",
            xy=(project_start_year, max(ndvi) * 0.88),
            fontsize=9, color=_GRAY, ha="center",
            arrowprops=None,
        )

    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("NDVI", fontsize=12)
    ax.set_title("Vegetation Health Trend (NDVI)", fontsize=14, fontweight="bold")
    ax.set_ylim(0, 1.0)
    ax.set_xticks(years)
    ax.grid(True, alpha=0.2, color="#334155")
    ax.legend(loc="lower right", facecolor=_DARK_BG,
              labelcolor=_TEXT_COLOR, edgecolor="#334155", fontsize=9)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
    plt.savefig(save_path, bbox_inches="tight", dpi=100, facecolor=_DARK_BG)
    plt.close()
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# 2. WATER AREA BAR CHART
# ─────────────────────────────────────────────────────────────────────────────

def create_water_area_matplotlib(timeseries_data, save_path):
    """Bar chart of water body area over time.

    Parameters
    ----------
    timeseries_data : list of dicts with keys ``year`` and ``water_area_ha``
    save_path       : str
    """
    if not timeseries_data:
        return None

    years = [d["year"] for d in timeseries_data]
    areas = [d["water_area_ha"] for d in timeseries_data]
    base  = areas[0] if areas[0] > 0 else 1.0

    fig, ax = plt.subplots(figsize=(10, 5), dpi=100)
    _apply_dark_theme(fig, ax)

    # Gradient bar colour based on relative area
    bar_colors = [
        "#1565C0" if a <= base else (
            "#1976d2" if a < base * 1.5 else (
                "#42a5f5" if a < base * 2.0 else _LBLUE
            )
        )
        for a in areas
    ]

    bars = ax.bar(years, areas, color=bar_colors, edgecolor="#334155",
                  linewidth=0.6, width=0.6, zorder=3)

    # Percentage change annotations on top of each bar
    for bar, area in zip(bars, areas):
        pct = ((area - base) / base) * 100
        label = f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%"
        color = _GREEN if pct >= 0 else _RED
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(areas) * 0.02,
            label,
            ha="center", va="bottom", fontsize=9,
            color=color, fontweight="bold",
        )

    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("Area (Hectares)", fontsize=12)
    ax.set_title("Water Body Area Growth (Hectares)", fontsize=14, fontweight="bold")
    ax.set_xticks(years)
    ax.grid(True, alpha=0.2, axis="y", color="#334155")
    ax.set_ylim(0, max(areas) * 1.20)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
    plt.savefig(save_path, bbox_inches="tight", dpi=100, facecolor=_DARK_BG)
    plt.close()
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# 3. HEALTH GAUGE (semi-circular)
# ─────────────────────────────────────────────────────────────────────────────

def create_health_gauge_matplotlib(score, grade, save_path):
    """Semi-circular gauge chart for the watershed health score.

    Parameters
    ----------
    score     : int / float   0-100
    grade     : str           e.g. "A", "B+"
    save_path : str
    """
    score = max(0, min(100, score))

    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_BG)
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.6, 1.2)
    ax.set_aspect("equal")
    ax.axis("off")

    # ── Colored arc segments (180° semi-circle, 0° at left, 180° at right) ──
    # We map score 0-100 onto 180° (π radians), starting at left (π) going to right (0).
    segments = [
        (0,   39,  "#d73027"),  # Red
        (40,  59,  "#f46d43"),  # Orange
        (60,  79,  "#fee08b"),  # Yellow
        (80, 100,  "#1a9850"),  # Green
    ]

    def score_to_angle(s):
        """Map score 0-100 → radian angle on the upper semi-circle."""
        return math.pi * (1.0 - s / 100.0)

    for s_start, s_end, color in segments:
        theta1 = math.degrees(score_to_angle(s_end))   # matplotlib expects degrees
        theta2 = math.degrees(score_to_angle(s_start))
        wedge = mpatches.Wedge(
            center=(0, 0), r=1.0, theta1=theta1, theta2=theta2,
            width=0.28, facecolor=color, edgecolor=_DARK_BG, linewidth=2, alpha=0.9
        )
        ax.add_patch(wedge)

    # ── Needle ────────────────────────────────────────────────────────────────
    needle_angle = score_to_angle(score)
    needle_x = 0.75 * math.cos(needle_angle)
    needle_y = 0.75 * math.sin(needle_angle)
    ax.annotate(
        "", xy=(needle_x, needle_y), xytext=(0, 0),
        arrowprops=dict(
            arrowstyle="-|>",
            color="white",
            lw=2.5,
            mutation_scale=18,
        ),
    )
    # Pivot dot
    ax.add_patch(plt.Circle((0, 0), 0.06, color="white", zorder=10))

    # ── Score text in center ──────────────────────────────────────────────────
    ax.text(0, -0.18, str(int(score)),
            ha="center", va="center", fontsize=40, fontweight="bold",
            color="white")
    ax.text(0, -0.42, f"Grade: {grade}",
            ha="center", va="center", fontsize=13,
            color=_TEXT_COLOR, fontweight="bold")

    # ── Labels at ends of gauge ───────────────────────────────────────────────
    ax.text(-1.1, 0, "0",   ha="center", va="center", fontsize=10, color=_TEXT_COLOR)
    ax.text( 1.1, 0, "100", ha="center", va="center", fontsize=10, color=_TEXT_COLOR)
    ax.text(0, 1.1, "Watershed Health Score",
            ha="center", va="bottom", fontsize=12, fontweight="bold", color=_TEXT_COLOR)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
    plt.savefig(save_path, bbox_inches="tight", dpi=100, facecolor=_DARK_BG)
    plt.close()
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# 4. EROSION COMPARISON (grouped bar)
# ─────────────────────────────────────────────────────────────────────────────

def create_erosion_comparison_matplotlib(before_classes, after_classes, save_path):
    """Grouped bar chart: erosion risk classes before vs after.

    Parameters
    ----------
    before_classes : dict  {class_name: area_ha}
    after_classes  : dict  {class_name: area_ha}
    save_path      : str
    """
    order = ["Very Low", "Low", "Medium", "High", "Very High"]
    labels = [c for c in order if c in before_classes or c in after_classes]
    if not labels:
        labels = list(set(list(before_classes.keys()) + list(after_classes.keys())))

    x       = np.arange(len(labels))
    w       = 0.35
    before  = [before_classes.get(l, 0) for l in labels]
    after   = [after_classes.get(l, 0)  for l in labels]
    colors  = [_RISK_COLORS.get(l, _GRAY) for l in labels]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=100)
    _apply_dark_theme(fig, ax)

    bars_b = ax.bar(x - w / 2, before, w, label="Before", color=_GRAY,   alpha=0.75, edgecolor="#334155")
    bars_a = ax.bar(x + w / 2, after,  w, label="After",  color=colors,  alpha=0.90, edgecolor="#334155")

    # Value labels
    for bar in bars_b:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{bar.get_height():.0f}", ha="center", va="bottom",
                fontsize=8, color=_TEXT_COLOR)
    for bar in bars_a:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{bar.get_height():.0f}", ha="center", va="bottom",
                fontsize=8, color=_TEXT_COLOR)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_xlabel("Erosion Risk Class", fontsize=12)
    ax.set_ylabel("Area (Hectares)", fontsize=12)
    ax.set_title("Erosion Risk Distribution — Before vs After", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.2, axis="y", color="#334155")
    ax.legend(facecolor=_DARK_BG, labelcolor=_TEXT_COLOR, edgecolor="#334155")

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
    plt.savefig(save_path, bbox_inches="tight", dpi=100, facecolor=_DARK_BG)
    plt.close()
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# 5. LAND USE COMPARISON (horizontal bar)
# ─────────────────────────────────────────────────────────────────────────────

def create_landuse_comparison_matplotlib(before_areas, after_areas, labels, save_path):
    """Horizontal bar chart showing land use before vs after.

    Parameters
    ----------
    before_areas : list[float]  — area in ha for each land use class (before)
    after_areas  : list[float]  — area in ha for each land use class (after)
    labels       : list[str]    — class names matching above lists
    save_path    : str
    """
    if not labels:
        return None

    y       = np.arange(len(labels))
    w       = 0.38
    colors  = [_LANDUSE_COLORS.get(l, _GRAY) for l in labels]

    fig, ax = plt.subplots(figsize=(10, max(5, len(labels) * 1.2)), dpi=100)
    _apply_dark_theme(fig, ax)

    ax.barh(y + w / 2, before_areas, w, label="Before", color=_GRAY, alpha=0.75,
            edgecolor="#334155")
    ax.barh(y - w / 2, after_areas,  w, label="After",  color=colors, alpha=0.90,
            edgecolor="#334155")

    # Change arrows & delta labels
    max_val = max(max(before_areas, default=1), max(after_areas, default=1))
    for i, (b, a, lbl) in enumerate(zip(before_areas, after_areas, labels)):
        delta = a - b
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "–")
        clr   = _GREEN if delta > 0 else (_RED if delta < 0 else _GRAY)
        ax.text(max_val * 1.04, y[i], f"{arrow} {abs(delta):.0f} ha",
                va="center", fontsize=9, color=clr, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Area (Hectares)", fontsize=12)
    ax.set_title("Land Use Change — Before vs After", fontsize=14, fontweight="bold")
    ax.set_xlim(0, max_val * 1.25)
    ax.grid(True, alpha=0.2, axis="x", color="#334155")
    ax.legend(facecolor=_DARK_BG, labelcolor=_TEXT_COLOR, edgecolor="#334155")

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
    plt.savefig(save_path, bbox_inches="tight", dpi=100, facecolor=_DARK_BG)
    plt.close()
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# 6. ORCHESTRATOR — save_all_report_charts
# ─────────────────────────────────────────────────────────────────────────────

def save_all_report_charts(analysis_data: dict, temp_dir: str = "temp_charts/") -> dict:
    """Generate all matplotlib charts needed for the PDF report.

    Parameters
    ----------
    analysis_data : dict — the ``st.session_state.analysis_results`` dict produced
                    by app.py.  Expected keys:
                      - ``ndvi_ts``       : list[dict]   NDVI timeseries
                      - ``water_ts``      : list[dict]   Water area timeseries
                      - ``health_score``  : dict         Health scoring result
                      - ``change_data``   : dict         Change detection result
                      - ``landuse``       : dict         Land use transition data
                      - ``ws_data``       : dict         Watershed metadata
    temp_dir      : str — directory where PNG files are saved

    Returns
    -------
    dict  mapping chart name → absolute file path (or None if chart failed)
    """
    os.makedirs(temp_dir, exist_ok=True)

    def _path(name):
        return os.path.join(temp_dir, f"{name}.png")

    results = {}

    # 1. NDVI trend
    try:
        ndvi_ts = analysis_data.get("ndvi_ts") or []
        ws      = analysis_data.get("ws_data", {})
        start_yr = ws.get("start_year") or ws.get("project_start_year")
        if ndvi_ts:
            results["ndvi_trend"] = create_ndvi_trend_matplotlib(
                ndvi_ts, start_yr, _path("ndvi_trend")
            )
        else:
            results["ndvi_trend"] = None
    except Exception as e:
        print(f"[WARN] ndvi_trend chart failed: {e}")
        results["ndvi_trend"] = None

    # 2. Water area
    try:
        water_ts = analysis_data.get("water_ts") or []
        if water_ts:
            results["water_area"] = create_water_area_matplotlib(
                water_ts, _path("water_area")
            )
        else:
            results["water_area"] = None
    except Exception as e:
        print(f"[WARN] water_area chart failed: {e}")
        results["water_area"] = None

    # 3. Health gauge
    try:
        health  = analysis_data.get("health_score") or {}
        score   = health.get("total_score", 0)
        grade   = health.get("grade", "—")
        results["health_gauge"] = create_health_gauge_matplotlib(
            score, grade, _path("health_gauge")
        )
    except Exception as e:
        print(f"[WARN] health_gauge chart failed: {e}")
        results["health_gauge"] = None

    # 4. Erosion comparison
    try:
        change = analysis_data.get("change_data") or {}
        erosion = change.get("erosion") or {}
        bc = erosion.get("classes_before") or {}
        ac = erosion.get("classes_after") or {}
        if bc or ac:
            results["erosion_comparison"] = create_erosion_comparison_matplotlib(
                bc, ac, _path("erosion_comparison")
            )
        else:
            results["erosion_comparison"] = None
    except Exception as e:
        print(f"[WARN] erosion_comparison chart failed: {e}")
        results["erosion_comparison"] = None

    # 5. Land use comparison
    try:
        lu      = analysis_data.get("landuse") or {}
        labels  = lu.get("labels", [])
        before  = lu.get("before_areas_ha", [])
        after   = lu.get("after_areas_ha", [])
        if labels and before and after:
            results["landuse_comparison"] = create_landuse_comparison_matplotlib(
                before, after, labels, _path("landuse_comparison")
            )
        else:
            results["landuse_comparison"] = None
    except Exception as e:
        print(f"[WARN] landuse_comparison chart failed: {e}")
        results["landuse_comparison"] = None

    return results
