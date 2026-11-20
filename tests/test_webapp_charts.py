"""Unit tests for webapp/charts.py's Plotly chart builders."""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "webapp"))

import charts  # noqa: E402


def test_spending_time_series_plots_one_line_trace_in_order() -> None:
    results = [
        {"label": 2023, "amount": 100},
        {"label": 2024, "amount": 250},
    ]
    fig = charts.spending_time_series(results, "Obligations by year")

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "scatter"
    assert list(trace.x) == [2023, 2024]
    assert list(trace.y) == [100, 250]
    assert trace.line.color == charts.SEQUENTIAL_BLUE


def test_spending_time_series_treats_missing_amount_as_zero() -> None:
    fig = charts.spending_time_series([{"label": 2023, "amount": None}], "Title")
    assert list(fig.data[0].y) == [0]


def test_ranked_bar_puts_largest_value_last_so_it_renders_on_top() -> None:
    # Caller passes results already sorted largest-first, as the CSOSA tools do.
    results = [
        {"label": "Acme Corp", "amount": 300},
        {"label": "Beta LLC", "amount": 200},
        {"label": "Gamma Inc", "amount": 100},
    ]
    fig = charts.ranked_bar(results, "Top recipients")

    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "bar"
    assert trace.orientation == "h"
    # Reversed so Plotly (which stacks categories bottom-to-top) draws the
    # largest value at the top of the chart.
    assert list(trace.y) == ["Gamma Inc", "Beta LLC", "Acme Corp"]
    assert list(trace.x) == [100, 200, 300]
    assert trace.marker.color == charts.SEQUENTIAL_BLUE


def test_ranked_bar_formats_dollar_labels() -> None:
    fig = charts.ranked_bar([{"label": "A", "amount": 1234}], "Title")
    assert fig.data[0].text == ("$1,234",)
