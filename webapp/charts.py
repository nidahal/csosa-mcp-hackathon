"""Plotly chart builders for CSOSA tool results.

Colors follow the Anthropic dataviz skill's validated reference palette
(light-mode chart surface): sequential blue for normal values, status red
for a value past an optional budget guardrail. Red is never used alone —
whenever a budget is set, a legend names both colors and a dashed threshold
line marks the guardrail itself.
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
CRITICAL_RED = "#d03b3b"  # status "critical" — over-budget only, not a series hue
FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _base_layout(title: str, showlegend: bool = False) -> go.Layout:
    return go.Layout(
        title=dict(text=title, font=dict(color=PRIMARY_INK, size=16)),
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(color=SECONDARY_INK, family=FONT_FAMILY),
        margin=dict(l=10, r=10, t=50, b=10),
        showlegend=showlegend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )


def spending_time_series(
    results: list[dict[str, Any]], title: str, budget: float | None = None
) -> go.Figure:
    """A fiscal-year obligations line chart (single series).

    If `budget` is set, draws a dashed guardrail line at that amount and
    marks any point past it in red (with a legend entry — never color alone).
    """
    labels = [r.get("label") for r in results]
    amounts = [r.get("amount") or 0 for r in results]
    over = [budget is not None and a > budget for a in amounts]
    marker_colors = [CRITICAL_RED if o else SEQUENTIAL_BLUE for o in over]

    fig = go.Figure(layout=_base_layout(title, showlegend=budget is not None))
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=amounts,
            mode="lines+markers",
            line=dict(color=SEQUENTIAL_BLUE, width=2),
            marker=dict(size=9, color=marker_colors, line=dict(width=1, color=SURFACE)),
            hovertemplate="<b>FY%{x}</b><br>Obligated: $%{y:,.0f}<extra></extra>",
            showlegend=False,
        )
    )
    if budget is not None:
        fig.add_hline(
            y=budget,
            line_dash="dash",
            line_color=MUTED_INK,
            annotation_text=f"Budget: ${budget:,.0f}",
            annotation_position="top left",
            annotation_font_color=SECONDARY_INK,
        )
        if any(over):
            # Dummy trace purely to give "over budget" a legend entry —
            # the line/marker above already carries the real data.
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker=dict(size=9, color=CRITICAL_RED),
                    name="Over budget",
                    showlegend=True,
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
    results: list[dict[str, Any]],
    title: str,
    value_title: str = "Amount ($)",
    budget: float | None = None,
) -> go.Figure:
    """A horizontal ranked bar chart from [{"label", "amount"}, ...], largest
    on top. Hover names the entity and its amount directly.

    If `budget` is set, draws a dashed guardrail line at that amount and
    recolors any bar past it red, with a legend naming both colors.
    """
    items = list(reversed(results))  # largest on top
    labels = [str(r.get("label")) for r in items]
    amounts = [r.get("amount") or 0 for r in items]
    over = [budget is not None and a > budget for a in amounts]

    fig = go.Figure(layout=_base_layout(title, showlegend=budget is not None))

    def _bar_trace(
        indices: list[int], color: str, name: str, over_label: bool
    ) -> go.Bar:
        suffix = " — over budget" if over_label else ""
        hover = f"<b>%{{y}}</b><br>Amount: $%{{x:,.0f}}{suffix}<extra></extra>"
        return go.Bar(
            x=[amounts[i] for i in indices],
            y=[labels[i] for i in indices],
            orientation="h",
            name=name,
            marker=dict(color=color),
            text=[f"${amounts[i]:,.0f}" for i in indices],
            textposition="outside",
            textfont=dict(color=SECONDARY_INK),
            hovertemplate=hover,
            showlegend=budget is not None,
        )

    within_idx = [i for i, o in enumerate(over) if not o]
    over_idx = [i for i, o in enumerate(over) if o]
    if within_idx:
        fig.add_trace(
            _bar_trace(within_idx, SEQUENTIAL_BLUE, "Within budget", over_label=False)
        )
    if over_idx:
        fig.add_trace(
            _bar_trace(over_idx, CRITICAL_RED, "Over budget", over_label=True)
        )

    if budget is not None:
        fig.add_vline(
            x=budget,
            line_dash="dash",
            line_color=MUTED_INK,
            annotation_text=f"Budget: ${budget:,.0f}",
            annotation_position="top",
            annotation_font_color=SECONDARY_INK,
        )

    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRIDLINE,
        zeroline=False,
        color=MUTED_INK,
        title=value_title,
        tickformat="$,.0f",
    )
    fig.update_yaxes(
        showgrid=False,
        color=PRIMARY_INK,
        categoryorder="array",
        categoryarray=labels,
    )
    return fig
