from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import threading
from typing import Dict, Any

import dash
from dash import Dash, Input, Output, State, ALL, MATCH, dcc, html, dash_table, clientside_callback
from dash.dash_table import FormatTemplate
import plotly.express as px
import plotly.graph_objects as go
from flask_socketio import SocketIO


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app.log"),
    ],
)
logger = logging.getLogger("auction")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Shared, in-memory state for all users. In production this would move to a DB or cache.
INITIAL_STATE: Dict[str, Dict[str, Any]] = {
    "Tract 1": {
        "current_bid": 120_000.00,
        "max_budget": 150_000.00,
        "approved_over_budget": False,
        "requested_budget": None,
        "high_bidder": False,
        "last_updated": _now(),
    },
    "Tract 2": {
        "current_bid": 210_500.00,
        "max_budget": 200_000.00,
        "approved_over_budget": False,
        "requested_budget": None,
        "high_bidder": False,
        "last_updated": _now(),
    },
    "Tract 3": {
        "current_bid": 95_250.00,
        "max_budget": 110_000.00,
        "approved_over_budget": False,
        "requested_budget": None,
        "high_bidder": False,
        "last_updated": _now(),
    },
}

STATE_LOCK = threading.Lock()
TRACTS: Dict[str, Dict[str, Any]] = {name: data.copy() for name, data in INITIAL_STATE.items()}

app = Dash(__name__, update_title=None)
app.title = "Auction Control"
app.suppress_callback_exceptions = True
server = app.server
# Socket.IO for real-time push of state snapshots (development: allow all origins)
socketio = SocketIO(server, cors_allowed_origins="*")


def currency(value: float) -> str:
    return f"${value:,.2f}"


def seconds_to_hms(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def snapshot_state() -> Dict[str, Dict[str, Any]]:
    with STATE_LOCK:
        return {
            tract: {
                "current_bid": data["current_bid"],
                "max_budget": data["max_budget"],
                "approved_over_budget": data["approved_over_budget"],
                "requested_budget": data.get("requested_budget"),
                "high_bidder": data.get("high_bidder", False),
                "last_updated": data["last_updated"].isoformat(),
            }
            for tract, data in TRACTS.items()
        }

# Emit the current snapshot to all connected Socket.IO clients.
def broadcast_snapshot() -> None:
    """
    Emit the current snapshot to all connected Socket.IO clients.
    Called after state mutations complete.
    """
    try:
        socketio.emit("snapshot", snapshot_state(), broadcast=True)
    except Exception:
        logger.exception("Error broadcasting snapshot via Socket.IO")


def unit_multiplier(unit: str) -> float:
    return {"1": 1.0, "K": 1_000.0, "MM": 1_000_000.0}.get(unit or "1", 1.0)


def update_bid(tract: str, amount: float) -> None:
    with STATE_LOCK:
        if tract not in TRACTS:
            logger.warning("Update requested for unknown tract %s", tract)
            return
        TRACTS[tract]["current_bid"] = amount
        TRACTS[tract]["last_updated"] = _now()
        TRACTS[tract]["approved_over_budget"] = False
        TRACTS[tract]["requested_budget"] = None
        TRACTS[tract]["high_bidder"] = False
        logger.info("Updated %s bid to %.2f", tract, amount)
    # State changed; broadcast updated snapshot
    broadcast_snapshot()


def approve_over_budget(tract: str, new_budget: float = None) -> None:
    with STATE_LOCK:
        if tract in TRACTS:
            if new_budget is not None:
                TRACTS[tract]["max_budget"] = new_budget
            TRACTS[tract]["approved_over_budget"] = True
            TRACTS[tract]["requested_budget"] = None
            logger.info(
                "Approved budget for %s: max_budget=%.2f",
                tract,
                TRACTS[tract]["max_budget"],
            )
        else:
            logger.warning("Approval requested for unknown tract %s", tract)
    # State changed; broadcast updated snapshot
    broadcast_snapshot()


def request_budget_increase(tract: str, amount: float) -> None:
    with STATE_LOCK:
        if tract not in TRACTS:
            logger.warning("Request for unknown tract %s", tract)
            return
        TRACTS[tract]["requested_budget"] = amount
        TRACTS[tract]["approved_over_budget"] = False
        logger.info("Requested budget increase for %s to %.2f", tract, amount)
    # State changed; broadcast updated snapshot
    broadcast_snapshot()


def set_high_bidder(tract: str, is_high: bool) -> None:
    with STATE_LOCK:
        if tract not in TRACTS:
            logger.warning("High bidder toggle for unknown tract %s", tract)
            return
        TRACTS[tract]["high_bidder"] = bool(is_high)
        logger.info("Set high bidder status for %s to %s", tract, bool(is_high))
    # State changed; broadcast updated snapshot
    broadcast_snapshot()


def reset_state() -> None:
    with STATE_LOCK:
        for tract, data in INITIAL_STATE.items():
            TRACTS[tract] = data.copy()
    logger.info("State reset to initial sample values")
    # State changed; broadcast updated snapshot
    broadcast_snapshot()


def apply_table_updates(rows: Any) -> None:
    if not isinstance(rows, list):
        return
    with STATE_LOCK:
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("tract")
            if not name or name not in TRACTS:
                continue
            try:
                bid = float(row.get("current_bid", TRACTS[name]["current_bid"]))
                budget = float(row.get("max_budget", TRACTS[name]["max_budget"]))
            except (TypeError, ValueError):
                logger.warning("Invalid numeric values in admin table for tract %s: %s", name, row)
                continue
            TRACTS[name]["current_bid"] = bid
            TRACTS[name]["max_budget"] = budget
            TRACTS[name]["last_updated"] = _now()
            TRACTS[name]["approved_over_budget"] = False
            TRACTS[name]["requested_budget"] = None
            logger.info("Admin table update for %s: bid=%.2f, max=%.2f", name, bid, budget)
    # State changed; broadcast updated snapshot
    broadcast_snapshot()


def add_tract(name: str, current_bid: float, max_budget: float) -> bool:
    name = name.strip()
    if not name:
        return False
    with STATE_LOCK:
        if name in TRACTS:
            return False
        TRACTS[name] = {
            "current_bid": current_bid,
            "max_budget": max_budget,
            "approved_over_budget": False,
            "requested_budget": None,
            "high_bidder": False,
            "last_updated": _now(),
        }
        logger.info("Added new tract %s (bid=%.2f, max=%.2f)", name, current_bid, max_budget)
    # State changed; broadcast updated snapshot
    broadcast_snapshot()
    return True


def table_rows(snapshot):
    return [
        {"tract": name, "current_bid": data["current_bid"], "max_budget": data["max_budget"]}
        for name, data in snapshot.items()
    ]


def tract_options():
    return [{"label": name, "value": name} for name in TRACTS.keys()]


def build_budget_progress(snapshot):
    names = list(snapshot.keys())
    pct_to_budget = [
        min(round((data["current_bid"] / data["max_budget"]) * 100, 1), 150) for data in snapshot.values()
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


def build_bid_bar(snapshot):
    names = list(snapshot.keys())
    bids = [data["current_bid"] for data in snapshot.values()]
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


def build_summary_table(snapshot):
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
        over_budget = data["current_bid"] > data["max_budget"]
        status = "Over budget" if over_budget else "Within budget"
        if over_budget and data["approved_over_budget"]:
            status = "Over budget (approved)"
        high = data.get("high_bidder", False)
        rows.append(
            html.Tr(
                [
                    html.Td(name),
                    html.Td(currency(data["current_bid"]), style={"textAlign": "right", "whiteSpace": "nowrap"}),
                    html.Td(currency(data["max_budget"]), style={"textAlign": "right", "whiteSpace": "nowrap"}),
                    html.Td(
                        html.Span(
                            "●",
                            style={
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
    return html.Div(
        [
            navigation(pathname),
            html.H2("Bid Monitor"),
            html.P("Update asking price for a tract. Enter updates and press Enter to submit."),
            html.Div(
                [
                    html.Label("Tract"),
                    dcc.Dropdown(id="monitor-tract", options=tract_options(), value=list(TRACTS.keys())[0], clearable=False),
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
                        value="1",
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
        ]
    )


def bidder_layout(pathname: str):
    return html.Div(
        [
            navigation(pathname),
            html.H2("Bidder"),
            html.P("Choose a tract to see its current asking price and approval status."),
            dcc.Dropdown(id="bidder-tract", options=tract_options(), value=list(TRACTS.keys())[0], clearable=False),
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
                    dcc.Input(
                        id="bidder-request-amount",
                        type="number",
                        step="0.01",
                        placeholder="Enter desired max budget",
                        style={"width": "220px", "marginRight": "8px"},
                    ),
                    dcc.RadioItems(
                        id="bidder-unit",
                        options=[
                            {"label": "Exact", "value": "1"},
                            {"label": "K", "value": "K"},
                            {"label": "MM", "value": "MM"},
                        ],
                        value="1",
                        inline=True,
                        style={"marginTop": "6px"},
                    ),
                    html.Button("Submit request", id="bidder-request-btn", n_clicks=0),
                    html.Div(id="bidder-request-feedback", style={"marginTop": "6px", "fontWeight": "bold"}),
                ],
                style={"marginTop": "14px"},
            ),
        ]
    )


def approver_layout(pathname: str):
    snapshot = snapshot_state()
    return html.Div(
        [
            navigation(pathname),
            html.H2("High Approver"),
            html.P("Approve bids that exceed their max budget."),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(tract, style={"fontWeight": "bold"}),
                            html.Div(id={"type": "approver-row", "tract": tract}, style={"marginBottom": "6px"}),
                            dcc.Input(
                                id={"type": "approver-input", "tract": tract},
                                type="number",
                                step="0.01",
                                style={"width": "200px", "marginRight": "8px"},
                                placeholder="Requested/new budget",
                            ),
                            dcc.RadioItems(
                                id={"type": "approver-unit", "tract": tract},
                                options=[
                                    {"label": "Exact", "value": "1"},
                                    {"label": "K", "value": "K"},
                                    {"label": "MM", "value": "MM"},
                                ],
                                value="1",
                                inline=True,
                                style={"marginBottom": "6px"},
                            ),
                            html.Button(
                                f"Approve over budget for {tract}",
                                id={"type": "approve-button", "tract": tract},
                                n_clicks=0,
                                style={"padding": "8px 12px", "marginBottom": "12px"},
                            ),
                        ],
                        style={"border": "1px solid #ddd", "borderRadius": "6px", "padding": "10px"},
                    )
                    for tract in snapshot.keys()
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(240px, 1fr))", "gap": "12px"},
            ),
            html.Div(id="approver-status", style={"marginTop": "12px", "fontWeight": "bold"}),
        ]
    )


def admin_layout(pathname: str):
    snapshot = snapshot_state()
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
            dash_table.DataTable(
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
                data=table_rows(snapshot),
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


app.layout = html.Div(
    [
        dcc.Location(id="url"),
        html.H1("Auction Bidding Control Center"),
        dcc.Store(id="snapshot-store", data=snapshot_state()),
        dcc.Interval(id="state-interval", interval=500, n_intervals=0),
        html.Div(id="page-container"),
    ],
    style={"maxWidth": "1100px", "margin": "0 auto", "padding": "18px"},
)

# Validation layout makes Dash aware of dynamic pages/IDs used by callbacks.
app.validation_layout = html.Div(
    [
        app.layout,
        view_only_layout("/view"),
        monitor_layout("/monitor"),
        bidder_layout("/bidder"),
        approver_layout("/approver"),
        admin_layout("/admin"),
    ]
)

# Custom index template so we can add Socket.IO client script inline.
# For now we simply connect and log snapshots; later we can wire these into dcc.Store.
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script src="https://cdn.socket.io/4.7.2/socket.io.min.js" crossorigin="anonymous"></script>
        <script type="text/javascript">
            document.addEventListener('DOMContentLoaded', function() {
                try {
                    var socket = io();
                    socket.on('connect', function() {
                        console.log('[Socket.IO] Connected');
                    });
                    socket.on('disconnect', function(reason) {
                        console.log('[Socket.IO] Disconnected:', reason);
                    });
                    socket.on('snapshot', function(data) {
                        console.log('[Socket.IO] Snapshot received', data);
                        // Stash the most recent snapshot globally for future Dash wiring.
                        window.latestSnapshot = data;
                    });
                } catch (e) {
                    console.error('Socket.IO init failed', e);
                }
            });
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


@app.callback(Output("page-container", "children"), Input("url", "pathname"))
def render_page(pathname: str):
    pathname = pathname or "/view"
    if pathname == "/monitor":
        return monitor_layout(pathname)
    if pathname == "/bidder":
        return bidder_layout(pathname)
    if pathname == "/approver":
        return approver_layout(pathname)
    if pathname == "/admin":
        return admin_layout(pathname)
    return view_only_layout(pathname)




# Poll the server for the latest snapshot on a fixed interval.
@app.callback(
    Output("snapshot-store", "data"),
    Input("state-interval", "n_intervals"),
)
def update_snapshot_store(_tick):
    return snapshot_state()


@app.callback(
    Output("view-table", "children"),
    Output("budget-progress", "figure"),
    Output("bid-bar", "figure"),
    Input("snapshot-store", "data"),
)
def refresh_view_only(snapshot):
    if not snapshot:
        return dash.no_update, dash.no_update, dash.no_update
    return build_summary_table(snapshot), build_budget_progress(snapshot), build_bid_bar(snapshot)


app.clientside_callback(
    """
    function(snapshot, tract) {
        if (!snapshot || !tract || !snapshot[tract]) {
            return ["—", "—", "—", "—", "Unknown", {backgroundColor: "gray"}, "Unknown"];
        }
        const info = snapshot[tract];
        const fmt = (v) => "$" + (v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        const over = info.current_bid > info.max_budget;
        const approved = info.approved_over_budget;
        const color = over ? (approved ? "seagreen" : "crimson") : "gray";
        const status = over ? (approved ? "Over budget — approved" : "Over budget") : "Within budget";
        const req = info.requested_budget ? fmt(info.requested_budget) : "None";
        const last = info.last_updated ? new Date(info.last_updated).toLocaleTimeString() : "—";
        return [
            fmt(info.current_bid),
            fmt(info.max_budget),
            req,
            last,
            status,
            {backgroundColor: color, display: "inline-block", width: "12px", height: "12px", borderRadius: "50%", marginRight: "6px"},
            info.high_bidder ? "Yes" : "No",
        ];
    }
    """,
    Output("monitor-current-bid", "children"),
    Output("monitor-max-budget", "children"),
    Output("monitor-requested", "children"),
    Output("monitor-last-updated", "children"),
    Output("monitor-status-text", "children"),
    Output("monitor-status-dot", "style"),
    Output("monitor-high-text", "children"),
    Input("snapshot-store", "data"),
    Input("monitor-tract", "value"),
)


@app.callback(
    Output("monitor-feedback", "children"),
    Output("monitor-price", "value"),
    Input("monitor-price", "n_submit"),
    State("monitor-tract", "value"),
    State("monitor-price", "value"),
    State("monitor-unit", "value"),
    prevent_initial_call=True,
)
def handle_monitor_submit(n_submit, tract: str, raw_amount, unit):
    if tract is None or raw_amount is None:
        return html.Span("Select a tract and enter a valid amount.", style={"color": "crimson"}), dash.no_update
    try:
        amount = float(raw_amount)
    except (TypeError, ValueError):
        return html.Span("Amount must be a number.", style={"color": "crimson"}), dash.no_update
    amount *= unit_multiplier(unit)
    update_bid(tract, amount)
    return html.Span(
        f"Updated {tract} to {currency(amount)} at {_now().strftime('%H:%M:%S')}.",
        style={"color": "seagreen"},
    ), ""


@app.callback(
    Output("monitor-high-feedback", "children"),
    Input("monitor-high-toggle", "value"),
    State("monitor-tract", "value"),
    prevent_initial_call=True,
)
def handle_monitor_high_toggle(values, tract):
    if not tract:
        return "Select a tract first."
    is_high = "high" in (values or [])
    set_high_bidder(tract, is_high)
    return f"High bidder status set to {'YES' if is_high else 'NO'} for {tract}."


@app.callback(
    Output("monitor-high-toggle", "value"),
    Input("monitor-tract", "value"),
)
def sync_monitor_high(tract):
    if not tract:
        return []
    info = snapshot_state().get(tract)
    return ["high"] if info and info.get("high_bidder") else []


app.clientside_callback(
    """
    function(snapshot, tract) {
        if (!snapshot || !tract || !snapshot[tract]) {
            return ["—", "—", "None", "00:00:00", "Unknown", {backgroundColor: "gray"}];
        }
        const info = snapshot[tract];
        const fmt = (v) => "$" + (v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        const over = info.current_bid > info.max_budget;
        const approved = info.approved_over_budget;
        const color = over ? (approved ? "seagreen" : "crimson") : "gray";
        const status = over ? (approved ? "Over budget — approved" : "Over budget") : "Within budget";
        const requested = info.requested_budget ? fmt(info.requested_budget) : "None";
        const last = info.last_updated ? new Date(info.last_updated) : null;
        const delta = last ? Math.max(0, Math.floor((Date.now() - last.getTime()) / 1000)) : null;
        const hms = delta !== null ? new Date(delta * 1000).toISOString().substr(11, 8) : "00:00:00";
        return [
            fmt(info.current_bid),
            fmt(info.max_budget),
            requested,
            hms,
            status,
            {backgroundColor: color, display: "inline-block", width: "12px", height: "12px", borderRadius: "50%", marginRight: "6px"},
        ];
    }
    """,
    Output("bidder-current-bid", "children"),
    Output("bidder-max-budget", "children"),
    Output("bidder-requested", "children"),
    Output("bidder-elapsed", "children"),
    Output("bidder-status-text", "children"),
    Output("bidder-status-dot", "style"),
    Input("snapshot-store", "data"),
    Input("bidder-tract", "value"),
)


@app.callback(
    Output("bidder-request-feedback", "children"),
    Output("bidder-request-feedback", "style"),
    Input("bidder-request-btn", "n_clicks"),
    State("bidder-tract", "value"),
    State("bidder-request-amount", "value"),
    State("bidder-unit", "value"),
    prevent_initial_call=True,
)
def handle_bidder_request(n_clicks, tract, amount, unit):
    if not n_clicks:
        return dash.no_update, dash.no_update
    if not tract:
        return "Select a tract first.", {"color": "crimson"}
    try:
        req_amount = float(amount) * unit_multiplier(unit)
    except (TypeError, ValueError):
        return "Enter a numeric requested budget.", {"color": "crimson"}
    request_budget_increase(tract, req_amount)
    return f"Requested budget of {currency(req_amount)} for {tract}.", {"color": "seagreen"}


@app.callback(
    Output({"type": "approver-row", "tract": MATCH}, "children"),
    Output({"type": "approve-button", "tract": MATCH}, "children"),
    Output({"type": "approve-button", "tract": MATCH}, "disabled"),
    Output({"type": "approver-input", "tract": MATCH}, "value"),
    Input({"type": "approve-button", "tract": MATCH}, "n_clicks"),
    Input("snapshot-store", "data"),
    State({"type": "approve-button", "tract": MATCH}, "id"),
    State({"type": "approver-input", "tract": MATCH}, "value"),
    State({"type": "approver-unit", "tract": MATCH}, "value"),
    prevent_initial_call=False,
)
def update_single_approver(n_clicks, _snapshot, btn_id, input_value, unit_value):
    tract = btn_id["tract"]
    snapshot = _snapshot or {}
    info = snapshot.get(tract)
    if not info:
        return "Unknown tract.", "Approve", True, dash.no_update
    ctx = dash.callback_context
    triggered = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else None
    if isinstance(ctx.triggered_id, dict) and ctx.triggered_id.get("tract") == tract and n_clicks:
        try:
            new_budget = float(input_value) if input_value is not None else None
        except (TypeError, ValueError):
            new_budget = None
        if new_budget is not None:
            new_budget *= unit_multiplier(unit_value)
        if info["current_bid"] > info["max_budget"] or (info.get("requested_budget") and new_budget):
            approve_over_budget(tract, new_budget)
            snapshot = snapshot_state()
            info = snapshot.get(tract)
    over_budget = info["current_bid"] > info["max_budget"]
    approved = info["approved_over_budget"]
    requested = info.get("requested_budget")
    button_label = f"Approve budget for {tract}"
    disabled = (not over_budget and not requested) or approved
    row_text = f"Current bid: {currency(info['current_bid'])} | Max: {currency(info['max_budget'])} | "
    row_text += f"Requested: {currency(requested) if requested else '—'} | Status: "
    if over_budget and approved:
        row_text += "Over budget (approved)"
    elif over_budget:
        row_text += "Over budget — needs approval"
    else:
        row_text += "Within budget"
    input_val = requested if requested is not None else info["max_budget"]
    return row_text, button_label, disabled, input_val


@app.callback(
    Output("approver-status", "children"),
    Input({"type": "approve-button", "tract": ALL}, "n_clicks"),
    State({"type": "approve-button", "tract": ALL}, "id"),
    prevent_initial_call=True,
)
def show_latest_approval(_clicks, ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        return ""
    trig = ctx.triggered_id
    if isinstance(trig, dict) and trig.get("tract"):
        return f"Approved over-budget spend for {trig['tract']} at {_now().strftime('%H:%M:%S')}."
    return ""


@app.callback(
    Output("admin-table", "data"),
    Output("admin-feedback", "children"),
    Output("admin-feedback", "style"),
    Input("admin-reset", "n_clicks"),
    Input("admin-add-tract", "n_clicks"),
    Input("admin-table", "data_timestamp"),
    State("admin-new-name", "value"),
    State("admin-new-bid", "value"),
    State("admin-new-max", "value"),
    State("admin-table", "data"),
    prevent_initial_call=True,
)
def handle_admin_actions(reset_clicks, add_clicks, _ts, name, bid, max_budget, rows):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update
    trig = ctx.triggered_id

    if trig == "admin-reset":
        reset_state()
        snapshot = snapshot_state()
        return table_rows(snapshot), "State reset to sample values.", {"color": "seagreen"}

    if trig == "admin-add-tract":
        if not name:
            return dash.no_update, "Enter a tract name.", {"color": "crimson"}
        try:
            bid_val = float(bid) if bid is not None else 0.0
            max_val = float(max_budget) if max_budget is not None else 0.0
        except (TypeError, ValueError):
            return dash.no_update, "Bid and max must be numbers.", {"color": "crimson"}
        created = add_tract(name, bid_val, max_val)
        if not created:
            return dash.no_update, "Tract already exists or name invalid.", {"color": "crimson"}
        snapshot = snapshot_state()
        return table_rows(snapshot), f"Added tract {name}.", {"color": "seagreen"}

    if trig == "admin-table":
        apply_table_updates(rows)
        snapshot = snapshot_state()
        return table_rows(snapshot), "Table changes saved.", {"color": "seagreen"}

    return dash.no_update, dash.no_update, dash.no_update


if __name__ == "__main__":
    debug = os.getenv("DASH_DEBUG", "1") not in {"0", "false", "False"}
    # Use Socket.IO's runner so WebSocket transport is enabled.
    # Default to port 8050 so it matches the typical Dash dev port, but allow override via PORT env.
    port = int(os.getenv("PORT", "8050"))
    socketio.run(server, debug=debug, port=port, use_reloader=False)
