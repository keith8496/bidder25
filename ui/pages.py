# ui/pages.py
"""Dash page layout builders aligned with the live app IDs/routes."""

from __future__ import annotations

from typing import Dict, List

from dash import dcc, html
from dash.dash_table import DataTable
from dash.dash_table import FormatTemplate

import state
from ui.charts import build_bid_bar, build_budget_progress
from ui.components import build_summary_table


def navigation(pathname: str):
    links = [
        ("/view", "View Only"),
        ("/monitor", "Bid Monitor"),
        ("/bidder", "Bidder"),
        ("/approver", "High Approver"),
        ("/admin", "Admin"),
    ]
    return html.Div(
        [
            html.Span(
                html.A(label, href=href, style={"color": "#0a58ca" if pathname == href else "#0d6efd"}),
                style={"marginRight": "18px", "fontWeight": "700" if pathname == href else "400"},
            )
            for href, label in links
        ],
        style={"marginBottom": "12px"},
    )


def view_only_layout(pathname: str):
    return html.Div(
        [
            navigation(pathname),
            html.H2("View Only Dashboard"),
            html.P("Live snapshot of bids by tract."),
            html.Div(
                [
                    html.Div(id="view-table", style={"flex": "1"}),
                    dcc.Graph(id="budget-progress", style={"flex": "1"}),
                ],
                style={"display": "flex", "gap": "16px", "flexWrap": "wrap"},
            ),
            html.Div(
                dcc.Graph(id="bid-bar"),
                style={"marginTop": "20px"},
            ),
        ]
    )


def monitor_layout(pathname: str):
    snapshot = state.snapshot_state()
    tract_names = list(snapshot.keys())
    default_tract = tract_names[0] if tract_names else None
    return html.Div(
        [
            navigation(pathname),
            html.H2("Bid Monitor"),
            html.P("Update asking price for a tract. Enter updates and press Enter to submit."),
            html.Div(
                [
                    html.Label("Tract"),
                    dcc.Dropdown(
                        id={"type": "tract-dropdown", "role": "monitor"},
                        options=state.tract_options(),
                        value=default_tract,
                        clearable=False,
                    ),
                ],
                style={"marginBottom": "12px"},
            ),
            html.Div(id="monitor-stats", style={"marginBottom": "12px"}),
            html.Div(
                [
                    html.Div(["Current bid: ", html.Span(id="monitor-current-bid")]),
                    html.Div(["Max budget: ", html.Span(id="monitor-max-budget")]),
                    html.Div(["Requested budget: ", html.Span(id="monitor-requested")]),
                    html.Div(["Last updated: ", html.Span(id="monitor-last-updated")]),
                    html.Div(
                        [
                            html.Span("Status: ", style={"marginRight": "6px"}),
                            html.Span(
                                "",
                                id="monitor-status-dot",
                                style={
                                    "display": "inline-block",
                                    "width": "12px",
                                    "height": "12px",
                                    "borderRadius": "50%",
                                    "backgroundColor": "gray",
                                    "marginRight": "6px",
                                },
                            ),
                            html.Span(id="monitor-status-text"),
                        ]
                    ),
                    html.Div(["High bidder: ", html.Span(id="monitor-high-text")]),
                ],
                style={"marginBottom": "12px"},
            ),
            html.Div(
                [
                    dcc.RadioItems(
                        id="monitor-unit",
                        options=[
                            {"label": "Exact", "value": "1"},
                            {"label": "K", "value": "K"},
                            {"label": "MM", "value": "MM"},
                        ],
                        value="K",
                        inline=True,
                        labelStyle={"marginRight": "10px"},
                        inputStyle={"marginRight": "4px"},
                        style={"marginRight": "16px"},
                    ),
                    dcc.Input(
                        id="monitor-price",
                        type="number",
                        step="0.01",
                        debounce=True,
                        placeholder="Enter amount",
                        style={"width": "180px", "marginRight": "16px"},
                    ),
                    dcc.Checklist(
                        id="monitor-high-toggle",
                        options=[{"label": "We are high bidder", "value": "high"}],
                        value=[],
                        inputStyle={"marginRight": "6px"},
                        style={"marginRight": "16px"},
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "flexWrap": "wrap",
                    "gap": "8px",
                    "marginBottom": "8px",
                },
            ),
            html.Div(id="monitor-feedback", style={"fontWeight": "bold", "marginBottom": "4px"}),
            html.Div(id="monitor-high-feedback", style={"marginBottom": "12px"}),
            dcc.Store(id="monitor-focus-signal"),
            html.Div(id="monitor-focus-anchor", style={"display": "none"}),
        ]
    )


def bidder_layout(pathname: str):
    snapshot = state.snapshot_state()
    tract_names = list(snapshot.keys())
    default_tract = tract_names[0] if tract_names else None
    return html.Div(
        [
            navigation(pathname),
            html.H2("Bidder"),
            html.P("Choose a tract to see its current asking price and approval status."),
            dcc.Dropdown(
                id={"type": "tract-dropdown", "role": "bidder"},
                options=state.tract_options(),
                value=default_tract,
                clearable=False,
            ),
            html.Div(
                [
                    html.Div(["Current bid: ", html.Span(id="bidder-current-bid")]),
                    html.Div(["Max budget: ", html.Span(id="bidder-max-budget")]),
                    html.Div(["Requested budget: ", html.Span(id="bidder-requested")]),
                    html.Div(["Time since last update: ", html.Span(id="bidder-elapsed")]),
                    html.Div(
                        [
                            html.Span("Approval indicator: ", style={"marginRight": "8px"}),
                            html.Span(
                                "",
                                id="bidder-status-dot",
                                style={
                                    "display": "inline-block",
                                    "width": "12px",
                                    "height": "12px",
                                    "borderRadius": "50%",
                                    "backgroundColor": "gray",
                                    "marginRight": "6px",
                                },
                            ),
                            html.Span(id="bidder-status-text"),
                        ]
                    ),
                ],
                id="bidder-info",
                style={"marginTop": "16px"},
            ),
            html.Div(
                [
                    html.Label("Request higher budget"),
                    html.Div(
                        [
                            dcc.RadioItems(
                                id="bidder-unit",
                                options=[
                                    {"label": "Exact", "value": "1"},
                                    {"label": "K", "value": "K"},
                                    {"label": "MM", "value": "MM"},
                                ],
                                value="K",
                                inline=True,
                                style={"marginRight": "16px"},
                            ),
                            dcc.Input(
                                id="bidder-request-amount",
                                type="number",
                                step="0.01",
                                placeholder="Enter desired max budget",
                                style={"width": "220px"},
                            ),
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "flexWrap": "wrap",
                            "gap": "8px",
                            "marginTop": "6px",
                        },
                    ),
                    html.Div(id="bidder-request-feedback", style={"marginTop": "6px", "fontWeight": "bold"}),
                ],
                style={"marginTop": "14px"},
            ),
        ]
    )


def approver_layout(pathname: str):
    return html.Div(
        [
            navigation(pathname),
            html.H2("High Approver"),
            html.P("Approve bids that exceed their max budget."),
            dcc.Store(id={"type": "approver-tracts-store", "page": "approver"}, data=[]),
            html.Div(
                id={"type": "approver-cards", "page": "approver"},
                children=[],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(240px, 1fr))", "gap": "12px"},
            ),
            html.Div(id="approver-status", style={"marginTop": "12px", "fontWeight": "bold"}),
        ]
    )


def admin_layout(pathname: str):
    snapshot = state.snapshot_state()
    return html.Div(
        [
            navigation(pathname),
            html.H2("Admin"),
            html.P("Set up tracts, bids, and budgets. Reset restores sample data."),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("New tract name"),
                            dcc.Input(
                                id="admin-new-name",
                                type="text",
                                placeholder="Tract 4",
                                value="",
                                style={"width": "200px"},
                            ),
                        ],
                        style={"marginRight": "8px"},
                    ),
                    html.Div(
                        [
                            html.Label("Current bid"),
                            dcc.Input(
                                id="admin-new-bid",
                                type="number",
                                step="0.01",
                                placeholder="0.00",
                                value="",
                                style={"width": "140px"},
                            ),
                        ],
                        style={"marginRight": "8px"},
                    ),
                    html.Div(
                        [
                            html.Label("Max budget"),
                            dcc.Input(
                                id="admin-new-max",
                                type="number",
                                step="0.01",
                                placeholder="0.00",
                                value="",
                                style={"width": "140px"},
                            ),
                        ],
                        style={"marginRight": "8px"},
                    ),
                    html.Button("Add tract", id="admin-add-tract", n_clicks=0, style={"alignSelf": "flex-end"}),
                ],
                style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginBottom": "12px"},
            ),
            DataTable(
                id="admin-table",
                columns=[
                    {"name": "Tract", "id": "tract", "editable": False},
                    {
                        "name": "Current bid",
                        "id": "current_bid",
                        "type": "numeric",
                        "format": FormatTemplate.money(2),
                    },
                    {
                        "name": "Max budget",
                        "id": "max_budget",
                        "type": "numeric",
                        "format": FormatTemplate.money(2),
                    },
                ],
                data=state.table_rows(snapshot),
                editable=True,
                row_deletable=False,
                style_cell={"padding": "6px", "textAlign": "left"},
                style_table={"marginBottom": "10px", "minWidth": "320px"},
            ),
            html.Div(
                [
                    html.Button("Reset sample data", id="admin-reset", n_clicks=0, style={"marginRight": "10px"}),
                    html.Span(
                        "Tip: edit Current bid/Max budget cells directly; tract names are fixed. Use the form above to add more tracts.",
                        style={"fontStyle": "italic"},
                    ),
                ],
                style={"marginBottom": "8px"},
            ),
            html.Div(id="admin-feedback", style={"marginBottom": "12px"}),
        ]
    )


def not_found_layout(pathname: str):
    return html.Div(
        [
            navigation(pathname),
            html.H2("Page not found"),
            html.P(f"No page at path: {pathname or '/'}"),
        ]
    )
