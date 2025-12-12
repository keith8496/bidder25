# ui/charts.py
"""Plotly chart builders for bidder25."""

import plotly.express as px
import plotly.graph_objects as go

from state import safe_pct_of_budget
from ui.common import currency


def build_budget_progress(snapshot: dict) -> go.Figure:
    """Horizontal bar chart: % of max budget by tract."""
    snapshot = snapshot or {}
    names = list(snapshot.keys())
    pct_to_budget = [
        safe_pct_of_budget(data.get("current_bid", 0.0), data.get("max_budget", 0.0))
        for data in snapshot.values()
    ]

    fig = go.Figure(
        go.Bar(
            x=pct_to_budget,
            y=names,
            orientation="h",
            marker_color=["crimson" if pct > 100 else "seagreen" for pct in pct_to_budget],
            text=[f"{pct}%" for pct in pct_to_budget],
            textposition="inside",
        )
    )

    fig.add_vline(x=100, line_dash="dash", line_color="black")
    fig.update_layout(
        height=300,
        margin=dict(l=10, r=10, t=30, b=30),
        xaxis_title="% of max budget",
        yaxis_title="Tract",
    )
    return fig


def build_bid_bar(snapshot: dict) -> go.Figure:
    """Vertical bar chart: current bid by tract (matches live app)."""
    snapshot = snapshot or {}
    names = list(snapshot.keys())
    bids = [data.get("current_bid", 0.0) for data in snapshot.values()]

    fig = px.bar(
        x=names,
        y=bids,
        labels={"x": "Tract", "y": "Current bid"},
        text=[currency(bid) for bid in bids],
        title="Current bid price by tract",
    )
    fig.update_traces(marker_color="steelblue", textposition="outside")
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=40))
    return fig
