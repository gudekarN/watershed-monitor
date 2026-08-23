"""
frontend/charts.py
==================
All Plotly chart/visualisation functions for the AquaVeda dashboard.

Every function returns a go.Figure so callers can do:
    st.plotly_chart(fig, use_container_width=True)

Dark-theme-ready: paper_bgcolor and plot_bgcolor are transparent so they
inherit whatever Streamlit theme is active.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import plotly.express as px

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared layout defaults applied to every figure
# ---------------------------------------------------------------------------
_BASE_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(14,20,36,0.6)",
    font=dict(family="Inter, Arial, sans-serif", size=12, color="#e2e8f0"),
    margin=dict(l=60, r=30, t=70, b=60),
    title=dict(
        font=dict(size=15, color="#f1f5f9"),
        x=0.02, xanchor="left", pad=dict(b=15)
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="right",  x=1,
        font=dict(size=11, color="#e2e8f0"),
        bgcolor="rgba(0,0,0,0)",
    ),
    hoverlabel=dict(bgcolor="rgba(15,25,45,0.95)", font_size=12, font_color="#f1f5f9"),
)

_GRID_STYLE = dict(
    showgrid=True,
    gridcolor="rgba(255,255,255,0.07)",
    zeroline=False,
    tickfont=dict(size=10, color="#94a3b8"),
    title_font=dict(color="#e2e8f0"),
)


def _apply_base(fig: go.Figure, title: str) -> go.Figure:
    """Apply shared layout and set the title."""
    layout = dict(_BASE_LAYOUT)
    layout["title"] = dict(_BASE_LAYOUT["title"], text=title)
    fig.update_layout(**layout)
    return fig


# =============================================================================
# 1. NDVI TREND LINE CHART
# =============================================================================

def ndvi_trend_chart(
    timeseries_data: List[Dict],
    project_start_year: Optional[int] = None,
) -> go.Figure:
    """
    Yearly NDVI trend with healthy-threshold reference line and optional
    project-start annotation.

    Args:
        timeseries_data   : List of dicts with 'year' and 'ndvi_mean' keys.
                            Optionally 'ndvi_min' and 'ndvi_max' for error band.
        project_start_year: If set, draws a vertical 'Project Started' marker.

    Returns:
        go.Figure (line chart).
    """
    if not timeseries_data:
        fig = go.Figure()
        return _apply_base(fig, "Vegetation Health Trend (NDVI) — No Data")

    years = [d["year"] for d in timeseries_data]
    means = [d.get("ndvi_mean", 0) for d in timeseries_data]
    mins  = [d.get("ndvi_min") for d in timeseries_data]
    maxs  = [d.get("ndvi_max") for d in timeseries_data]

    fig = go.Figure()

    # -- Min-max shaded band (if available) -----------------------------------
    if all(v is not None for v in mins + maxs):
        fig.add_trace(go.Scatter(
            x=years + years[::-1],
            y=maxs + mins[::-1],
            fill="toself",
            fillcolor="rgba(26,152,80,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            showlegend=False,
            name="NDVI Range",
        ))

    # -- Mean NDVI line -------------------------------------------------------
    fig.add_trace(go.Scatter(
        x=years,
        y=means,
        mode="lines+markers",
        name="NDVI Mean",
        line=dict(color="#1a9850", width=3),
        marker=dict(size=8, symbol="circle", color="#1a9850",
                    line=dict(width=2, color="#ffffff")),
        fill="tozeroy",
        fillcolor="rgba(26,152,80,0.10)",
        hovertemplate="<b>%{x}</b><br>NDVI: %{y:.3f}<extra></extra>",
    ))

    # -- Healthy threshold line -----------------------------------------------
    fig.add_hline(
        y=0.4,
        line=dict(color="#ef5350", width=1.5, dash="dash"),
        annotation_text="Healthy Threshold (0.4)",
        annotation_position="top right",
        annotation_font=dict(size=10, color="#ef5350"),
    )

    # -- Project start annotation ---------------------------------------------
    if project_start_year and project_start_year in years:
        fig.add_vline(
            x=project_start_year,
            line=dict(color="rgba(255,255,255,0.4)", width=1.5, dash="dot"),
            annotation_text="Project Started",
            annotation_position="top left",
            annotation_font=dict(size=10, color="rgba(255,255,255,0.7)"),
        )

    fig.update_xaxes(title_text="Year", **_GRID_STYLE, dtick=1)
    fig.update_yaxes(title_text="NDVI", range=[0, 1.0], **_GRID_STYLE)
    return _apply_base(fig, "Vegetation Health Trend (NDVI)")


# =============================================================================
# 2. WATER AREA BAR CHART
# =============================================================================

def water_area_chart(timeseries_data: List[Dict]) -> go.Figure:
    """
    Annual water body area as blue bars with percentage-change annotations.

    Args:
        timeseries_data : List of dicts with 'year' and 'water_area_ha' keys.

    Returns:
        go.Figure (bar chart).
    """
    if not timeseries_data:
        fig = go.Figure()
        return _apply_base(fig, "Water Body Area Over Time — No Data")

    years  = [d["year"] for d in timeseries_data]
    areas  = [d.get("water_area_ha", 0) for d in timeseries_data]
    base   = areas[0] if areas[0] else 1  # avoid division by zero

    pct_labels = []
    for i, a in enumerate(areas):
        if i == 0:
            pct_labels.append("Baseline")
        else:
            pct = round((a - base) / base * 100, 0)
            pct_labels.append(f"+{int(pct)}%" if pct >= 0 else f"{int(pct)}%")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years,
        y=areas,
        name="Water Area (ha)",
        marker=dict(
            color=areas,
            colorscale=[[0, "#90CAF9"], [1, "#1565C0"]],
            showscale=False,
            line=dict(width=0),
        ),
        text=pct_labels,
        textposition="outside",
        textfont=dict(size=11, color="#90CAF9"),
        hovertemplate="<b>%{x}</b><br>Area: %{y:.1f} ha<extra></extra>",
    ))

    fig.update_xaxes(title_text="Year", **_GRID_STYLE, dtick=1)
    fig.update_yaxes(title_text="Water Area (ha)", **_GRID_STYLE)
    return _apply_base(fig, "Water Body Area Over Time (Hectares)")


# =============================================================================
# 3. HEALTH SCORE GAUGE
# =============================================================================

def health_score_gauge(
    score: int,
    grade: str,
    grade_emoji: str,
) -> go.Figure:
    """
    Plotly gauge/indicator for the overall watershed health score.

    Args:
        score       : Integer 0-100.
        grade       : e.g. "Excellent", "Good", "Average", "Poor".
        grade_emoji : Emoji matching the grade.

    Returns:
        go.Figure (gauge indicator).
    """
    if score >= 80:
        bar_color = "#1a9850"
    elif score >= 60:
        bar_color = "#fee08b"
    elif score >= 40:
        bar_color = "#fdae61"
    else:
        bar_color = "#d73027"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(
            font=dict(size=48, color=bar_color),
            suffix="",
        ),
        title=dict(
            text=f"Watershed Health Score<br><span style='font-size:18px'>{grade_emoji} {grade}</span>",
            font=dict(size=14, color="#e2e8f0"),
        ),
        gauge=dict(
            axis=dict(
                range=[0, 100],
                tickwidth=1,
                tickcolor="#4a5568",
                tickfont=dict(size=10, color="#a0aec0"),
                nticks=6,
            ),
            bar=dict(color=bar_color, thickness=0.25),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0,  39],  color="rgba(229,57,53,0.15)"),
                dict(range=[40, 59],  color="rgba(253,174,97,0.15)"),
                dict(range=[60, 79],  color="rgba(254,224,139,0.15)"),
                dict(range=[80, 100], color="rgba(26,152,80,0.15)"),
            ],
            threshold=dict(
                line=dict(color=bar_color, width=3),
                thickness=0.8,
                value=score,
            ),
        ),
    ))

    fig.update_layout(
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", color="#e2e8f0"),
        margin=dict(l=20, r=20, t=90, b=20),   # tall top margin so title never clips
    )
    return fig


# =============================================================================
# 4. BEFORE / AFTER COMPARISON GROUPED BAR CHART
# =============================================================================

def change_comparison_chart(change_data: Dict[str, Any]) -> go.Figure:
    """
    Side-by-side before/after bars for the four key change metrics.

    Args:
        change_data : Dict with 'vegetation', 'water', 'erosion' sub-dicts
                      (matches change_data.json schema).

    Returns:
        go.Figure (grouped bar chart).
    """
    veg   = change_data.get("vegetation", {})
    water = change_data.get("water", {})
    er    = change_data.get("erosion", {})

    categories = ["NDVI Mean", "NDWI (approx.)", "Water Area (ha)", "High Erosion (ha)"]
    befores = [
        veg.get("ndvi_before", 0),
        round((water.get("area_before_ha", 0)) / max(water.get("area_before_ha", 1), 1) * 0.3 - 0.15, 3),
        water.get("area_before_ha", 0),
        er.get("high_risk_before_ha", 0),
    ]
    afters = [
        veg.get("ndvi_after", 0),
        round((water.get("area_after_ha", 0)) / max(water.get("area_after_ha", 1), 1) * 0.3 - 0.05, 3),
        water.get("area_after_ha", 0),
        er.get("high_risk_after_ha", 0),
    ]

    # Delta labels
    def _delta(b, a):
        if b == 0:
            return "N/A"
        pct = (a - b) / abs(b) * 100
        return f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%"

    deltas = [_delta(b, a) for b, a in zip(befores, afters)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Before",
        x=categories,
        y=befores,
        marker_color="rgba(120,120,140,0.7)",
        hovertemplate="<b>%{x}</b> Before<br>%{y:.3f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="After",
        x=categories,
        y=afters,
        marker_color=["#1a9850", "#4FC3F7", "#2196F3", "#fc8d59"],
        hovertemplate="<b>%{x}</b> After<br>%{y:.3f}<extra></extra>",
        text=deltas,
        textposition="outside",
        textfont=dict(size=11, color="#a0aec0"),
    ))

    fig.update_layout(barmode="group")
    fig.update_xaxes(**_GRID_STYLE)
    fig.update_yaxes(title_text="Value", **_GRID_STYLE)
    return _apply_base(fig, "Before vs After — Key Change Metrics")


# =============================================================================
# 5. EROSION RISK DONUT CHART
# =============================================================================

def erosion_pie_chart(erosion_classes: Dict[str, float]) -> go.Figure:
    """
    Donut chart of erosion risk area by class (Very Low → Very High).

    Args:
        erosion_classes : Dict e.g. {"Very Low": 250, "Low": 280, ...} in ha.

    Returns:
        go.Figure (donut pie).
    """
    if not erosion_classes:
        fig = go.Figure()
        return _apply_base(fig, "Erosion Risk Distribution — No Data")

    labels = list(erosion_classes.keys())
    values = list(erosion_classes.values())

    # Colour ramp: green (low risk) → red (high risk)
    color_map = {
        "Very Low":  "#1a9850",
        "Low":       "#91cf60",
        "Medium":    "#fee08b",
        "High":      "#fc8d59",
        "Very High": "#d73027",
    }
    colors = [color_map.get(lbl, "#888888") for lbl in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.45,
        marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0.3)", width=1)),
        textinfo="label+percent",
        textfont=dict(size=11),
        hovertemplate="<b>%{label}</b><br>%{value:.0f} ha (%{percent})<extra></extra>",
        sort=False,
    ))

    fig.update_layout(
        annotations=[dict(
            text="Erosion<br>Risk",
            x=0.5, y=0.5,
            font=dict(size=13, color="#e2e8f0"),
            showarrow=False,
        )],
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", color="#e2e8f0"),
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(orientation="v", font=dict(size=11)),
        title=dict(
            text="Erosion Risk Distribution",
            font=dict(size=15, color="#e2e8f0"),
            x=0.02, xanchor="left",
        ),
    )
    return fig


# =============================================================================
# 6. RAINFALL vs NDVI DUAL-AXIS CHART
# =============================================================================

def rainfall_ndvi_chart(
    rainfall_data: List[Dict],
    monthly_ndvi_data: List[Dict],
) -> go.Figure:
    """
    Dual-axis chart: blue rainfall bars (left) + green NDVI line (right).

    Args:
        rainfall_data    : List of {month, rainfall_mm} dicts.
        monthly_ndvi_data: List of {month, ndvi} dicts.

    Returns:
        go.Figure (dual-axis combo chart).
    """
    months_r  = [d.get("month", "") for d in rainfall_data]
    rain_vals = [d.get("rainfall_mm", 0) for d in rainfall_data]

    months_n  = [d.get("month", "") for d in monthly_ndvi_data]
    ndvi_vals = [d.get("ndvi", 0) or 0 for d in monthly_ndvi_data]

    fig = go.Figure()

    # Rainfall bars (left Y-axis)
    fig.add_trace(go.Bar(
        x=months_r,
        y=rain_vals,
        name="Rainfall (mm)",
        marker=dict(
            color=rain_vals,
            colorscale=[[0, "#90CAF9"], [1, "#0D47A1"]],
            showscale=False,
            opacity=0.8,
        ),
        yaxis="y1",
        hovertemplate="<b>%{x}</b><br>Rainfall: %{y:.0f} mm<extra></extra>",
    ))

    # NDVI line (right Y-axis)
    fig.add_trace(go.Scatter(
        x=months_n,
        y=ndvi_vals,
        name="NDVI",
        mode="lines+markers",
        line=dict(color="#1a9850", width=2.5),
        marker=dict(size=7, color="#1a9850", line=dict(width=1.5, color="#ffffff")),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>NDVI: %{y:.3f}<extra></extra>",
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", size=12, color="#e2e8f0"),
        margin=dict(l=60, r=60, t=60, b=60),
        hoverlabel=dict(bgcolor="rgba(30,30,50,0.9)", font_size=12),
        title=dict(
            text="Rainfall vs Vegetation Response",
            font=dict(size=15, color="#e2e8f0"),
            x=0.02, xanchor="left", pad=dict(b=15),
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=11),
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.08)",
            zeroline=False,
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            title="Rainfall (mm)",
            showgrid=True,
            gridcolor="rgba(255,255,255,0.08)",
            zeroline=False,
            title_font=dict(color="#90CAF9"),
            tickfont=dict(color="#90CAF9", size=10),
        ),
        yaxis2=dict(
            title="NDVI",
            overlaying="y",
            side="right",
            range=[0, 1.0],
            showgrid=False,
            zeroline=False,
            title_font=dict(color="#1a9850"),
            tickfont=dict(color="#1a9850", size=10),
        ),
    )
    return fig


# =============================================================================
# 7. LAND-USE SANKEY DIAGRAM
# =============================================================================

def landuse_sankey(transition_data: Dict[str, Any]) -> go.Figure:
    """
    Sankey diagram showing land-use transformation between two periods.

    The 'flows' list in transition_data drives the link widths.

    Args:
        transition_data : Dict with keys:
                          'labels'          : list of class names
                          'before_areas_ha' : list of areas before (ha)
                          'after_areas_ha'  : list of areas after  (ha)
                          'flows'           : list of {source, target, value}

    Returns:
        go.Figure (Sankey diagram).
    """
    labels_raw     = transition_data.get("labels", [])
    before_areas   = transition_data.get("before_areas_ha", [])
    after_areas    = transition_data.get("after_areas_ha",  [])
    flows          = transition_data.get("flows", [])

    if not labels_raw or not flows:
        fig = go.Figure()
        return _apply_base(fig, "Land Use Transformation — No Data")

    n = len(labels_raw)

    # Node labels: "Class (Before)" | "Class (After)"
    all_labels = (
        [f"{lbl} (Before)" for lbl in labels_raw]
        + [f"{lbl} (After)"  for lbl in labels_raw]
    )

    # Node colours — class-specific palette, duplicated for before/after
    _CLASS_COLORS = {
        "Water":            "#1565C0",
        "Dense Vegetation": "#1a9850",
        "Sparse Vegetation":"#91cf60",
        "Barren":           "#d4a843",
        "Built-up":         "#9e9e9e",
    }
    default_colors = ["#4FC3F7", "#66BB6A", "#FFEE58", "#FF7043", "#AB47BC"]

    node_colors = []
    for lbl in labels_raw:
        c = _CLASS_COLORS.get(lbl, default_colors[labels_raw.index(lbl) % len(default_colors)])
        node_colors.append(c)
    # Slightly lighter for "After" nodes
    node_colors_all = node_colors + [c.replace(")", ", 0.65)").replace("rgb", "rgba")
                                      if c.startswith("rgb") else c
                                      for c in node_colors]

    # Build index lookup
    before_idx = {lbl: i     for i, lbl in enumerate(labels_raw)}
    after_idx  = {lbl: i + n for i, lbl in enumerate(labels_raw)}

    # Hex -> valid rgba converter
    def _hex_to_rgba(hex_color: str, alpha: float = 0.35) -> str:
        h = hex_color.lstrip("#")
        rv, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({rv},{g},{b},{alpha})"

    sources, targets, values, link_colors = [], [], [], []
    for flow in flows:
        src_lbl = flow.get("source", "")
        tgt_lbl = flow.get("target", "")
        val     = float(flow.get("value", 0))
        if src_lbl in before_idx and tgt_lbl in after_idx and val > 0:
            sources.append(before_idx[src_lbl])
            targets.append(after_idx[tgt_lbl])
            values.append(val)
            base_c = node_colors[before_idx[src_lbl]]
            link_colors.append(
                _hex_to_rgba(base_c) if base_c.startswith("#") else "rgba(100,180,100,0.3)"
            )

    # Node hover labels with area info
    node_hover = (
        [f"{lbl}<br>{before_areas[i]} ha" for i, lbl in enumerate(labels_raw)]
        + [f"{lbl}<br>{after_areas[i]} ha"  for i, lbl in enumerate(labels_raw)]
    )

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20,
            thickness=18,
            line=dict(color="rgba(255,255,255,0.1)", width=0.5),
            label=all_labels,
            color=node_colors + node_colors,   # same palette both sides
            customdata=node_hover,
            hovertemplate="%{customdata}<extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
            hovertemplate=(
                "%{source.label} → %{target.label}<br>"
                "Area transferred: %{value:.0f} ha<extra></extra>"
            ),
        ),
    ))

    fig.update_layout(
        title=dict(
            text="Land Use Transformation",
            font=dict(size=15, color="#e2e8f0"),
            x=0.02, xanchor="left",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", size=11, color="#e2e8f0"),
        margin=dict(l=20, r=20, t=60, b=20),
        height=400,
    )
    return fig
