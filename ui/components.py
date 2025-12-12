# ui/components.py
"""Reusable Dash component builders for bidder25."""

from dash import html

from ui.common import DOT_STYLE, currency


def build_summary_table(snapshot: dict) -> html.Table:
    """Summary table matching the live app's View Only page."""
    snapshot = snapshot or {}

    header = [
        html.Thead(
            html.Tr(
                [
                    html.Th("Tract"),
                    html.Th("Current bid"),
                    html.Th("Max budget"),
                    html.Th("High bidder"),
                    html.Th("Status"),
                ]
            )
        )
    ]
    rows = []
    for name, data in snapshot.items():
        over_budget = data.get("current_bid", 0) > data.get("max_budget", 0)
        status = "Over budget" if over_budget else "Within budget"
        if over_budget and data.get("approved_over_budget"):
            status = "Over budget (approved)"
        high = bool(data.get("high_bidder", False))
        rows.append(
            html.Tr(
                [
                    html.Td(name),
                    html.Td(currency(data.get("current_bid")), style={"textAlign": "right", "whiteSpace": "nowrap"}),
                    html.Td(currency(data.get("max_budget")), style={"textAlign": "right", "whiteSpace": "nowrap"}),
                    html.Td(
                        html.Span(
                            "●",
                            style={
                                **DOT_STYLE,
                                "color": "seagreen" if high else "crimson",
                                "fontSize": "18px",
                                "lineHeight": "18px",
                            },
                        ),
                        style={"textAlign": "center"},
                    ),
                    html.Td(status),
                ]
            )
        )
    return html.Table(header + [html.Tbody(rows)], style={"width": "100%", "borderCollapse": "collapse"})
