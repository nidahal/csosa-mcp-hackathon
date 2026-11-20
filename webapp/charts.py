"""Plotly chart builders for CSOSA tool results.

Colors follow the Anthropic dataviz skill's validated reference palette
(light-mode chart surface, sequential blue). Every chart here is a single
series, so no categorical-pair validation is needed — that only applies when
multiple hues appear together.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SEQUENTIAL_BLUE = "#2a78d6"
FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _base_layout(title: str) -> go.Layout:
    return go.Layout(
        title=dict(text=title, font=dict(color=PRIMARY_INK, size=16)),
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(color=SECONDARY_INK, family=FONT_FAMILY),
        margin=dict(l=10, r=10, t=50, b=10),
        showlegend=False,
    )


def spending_time_series(results: list[dict[str, Any]], title: str) -> go.Figure:
    """A fiscal-year obligations line chart (single series)."""
    labels = [r.get("label") for r in results]
    amounts = [r.get("amount") or 0 for r in results]
    fig = go.Figure(layout=_base_layout(title))
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=amounts,
            mode="lines+markers",
            line=dict(color=SEQUENTIAL_BLUE, width=2),
            marker=dict(size=8, color=SEQUENTIAL_BLUE),
            hovertemplate="FY%{x}: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_xaxes(
        showgrid=False, linecolor=BASELINE, color=MUTED_INK, title="Fiscal year"
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRIDLINE,
        zeroline=False,
        color=MUTED_INK,
        title="Obligated amount ($)",
        tickformat="$,.0f",
    )
    return fig


def ranked_bar(
    results: list[dict[str, Any]], title: str, value_title: str = "Amount ($)"
) -> go.Figure:
    """A horizontal ranked bar chart from [{"label", "amount"}, ...]."""
    items = list(reversed(results))  # largest on top
    labels = [str(r.get("label")) for r in items]
    amounts = [r.get("amount") or 0 for r in items]
    fig = go.Figure(layout=_base_layout(title))
    fig.add_trace(
        go.Bar(
            x=amounts,
            y=labels,
            orientation="h",
            marker=dict(color=SEQUENTIAL_BLUE),
            text=[f"${a:,.0f}" for a in amounts],
            textposition="outside",
            textfont=dict(color=SECONDARY_INK),
            hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
        )
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRIDLINE,
        zeroline=False,
        color=MUTED_INK,
        title=value_title,
        tickformat="$,.0f",
    )
    fig.update_yaxes(showgrid=False, color=PRIMARY_INK)
    return fig
