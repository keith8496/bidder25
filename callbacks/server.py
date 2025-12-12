# callbacks/server.py
"""Server-side (Python) Dash callback registration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import dash
from dash import ALL, MATCH, Input, Output, State, dash_table, dcc, html
from realtime import broadcast_snapshot as rt_broadcast_snapshot
import state

logger = logging.getLogger("auction")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def currency(value: float) -> str:
    return f"${value:,.2f}"


def register_server_callbacks(app, socketio) -> None:
    """Register all server-side callbacks."""

    def broadcast_snapshot() -> None:
        try:
            rt_broadcast_snapshot(socketio, state.snapshot_state())
        except Exception:
            logger.exception("Error broadcasting snapshot via Socket.IO")

    @app.callback(Output("page-container", "children"), Input("url", "pathname"))
    def render_page(pathname: str):
        from ui.pages import (
            approver_layout,
            bidder_layout,
            monitor_layout,
            admin_layout,
            not_found_layout,
            view_only_layout,
        )

        pathname = pathname or "/view"
        if pathname == "/monitor":
            return monitor_layout(pathname)
        if pathname == "/bidder":
            return bidder_layout(pathname)
        if pathname == "/approver":
            return approver_layout(pathname)
        if pathname == "/admin":
            return admin_layout("/admin")
        if pathname in ("/view", "/"):
            return view_only_layout("/view")
        return not_found_layout(pathname)

    @app.callback(
        Output("snapshot-store", "data"),
        Input("state-interval", "n_intervals"),
    )
    def update_snapshot_store(_tick):
        return state.snapshot_state()

    @app.callback(
        Output("view-table", "children"),
        Output("budget-progress", "figure"),
        Output("bid-bar", "figure"),
        Input("snapshot-store", "data"),
    )
    def refresh_view_only(snapshot):
        from ui.charts import build_budget_progress, build_bid_bar
        from ui.components import build_summary_table

        if not snapshot:
            return dash.no_update, dash.no_update, dash.no_update
        return (
            build_summary_table(snapshot),
            build_budget_progress(snapshot),
            build_bid_bar(snapshot),
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
            return (
                html.Span("Select a tract and enter a valid amount.", style={"color": "crimson"}),
                dash.no_update,
            )
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            return html.Span("Amount must be a number.", style={"color": "crimson"}), dash.no_update
        amount *= state.unit_multiplier(unit)
        state.update_bid(tract, amount)
        broadcast_snapshot()
        return (
            html.Span(
                f"Updated {tract} to {currency(amount)} at {_now().strftime('%H:%M:%S')}.",
                style={"color": "seagreen"},
            ),
            "",
        )

    @app.callback(
        Output("monitor-high-feedback", "children"),
        Output("monitor-focus-signal", "data"),
        Input("monitor-high-toggle", "value"),
        State("monitor-tract", "value"),
        prevent_initial_call=True,
    )
    def handle_monitor_high_toggle(values, tract):
        if not tract:
            return "Select a tract first.", None
        is_high = "high" in (values or [])
        info = state.snapshot_state().get(tract)
        if info is not None and bool(info.get("high_bidder")) == is_high:
            return f"High bidder status is already {'YES' if is_high else 'NO'} for {tract}.", None
        state.set_high_bidder(tract, is_high)
        broadcast_snapshot()
        return f"High bidder status set to {'YES' if is_high else 'NO'} for {tract}.", _now().isoformat()

    @app.callback(
        Output("monitor-high-toggle", "value"),
        Input("snapshot-store", "data"),
        Input("monitor-tract", "value"),
    )
    def sync_monitor_high(snapshot, tract):
        if not tract:
            return []
        snapshot = snapshot or {}
        info = snapshot.get(tract)
        if not info:
            return []
        return ["high"] if info.get("high_bidder") else []

    @app.callback(
        Output("bidder-request-feedback", "children"),
        Output("bidder-request-feedback", "style"),
        Output("bidder-request-amount", "value"),
        Input("bidder-request-amount", "n_submit"),
        State("bidder-tract", "value"),
        State("bidder-request-amount", "value"),
        State("bidder-unit", "value"),
        prevent_initial_call=True,
    )
    def handle_bidder_request(n_submit, tract, amount, unit):
        if not tract:
            return "Select a tract first.", {"color": "crimson"}, dash.no_update
        try:
            req_amount = float(amount) * state.unit_multiplier(unit)
        except (TypeError, ValueError):
            return "Enter a numeric requested budget.", {"color": "crimson"}, dash.no_update
        state.request_budget_increase(tract, req_amount, unit)
        broadcast_snapshot()
        return f"Requested budget of {currency(req_amount)} for {tract}.", {"color": "seagreen"}, ""

    @app.callback(
        Output({"type": "approver-row", "tract": MATCH}, "children"),
        Output({"type": "approve-button", "tract": MATCH}, "children"),
        Output({"type": "approve-button", "tract": MATCH}, "disabled"),
        Output({"type": "approver-input", "tract": MATCH}, "value"),
        Output({"type": "approver-unit", "tract": MATCH}, "value"),
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
            return "Unknown tract.", "Approve", True, dash.no_update, dash.no_update
        ctx = dash.callback_context
        triggered = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else None
        if isinstance(ctx.triggered_id, dict) and ctx.triggered_id.get("tract") == tract and n_clicks:
            try:
                new_budget = float(input_value) if input_value is not None else None
            except (TypeError, ValueError):
                new_budget = None
            if new_budget is not None:
                new_budget *= state.unit_multiplier(unit_value)
            if info["current_bid"] > info["max_budget"] or (info.get("requested_budget") and new_budget):
                state.approve_over_budget(tract, new_budget)
                broadcast_snapshot()
                snapshot = state.snapshot_state()
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
        current_unit = unit_value or "K"
        requested_unit = info.get("requested_unit")
        effective_unit = requested_unit or current_unit
        input_val = requested if requested is not None else info["max_budget"]
        if input_val is not None:
            factor = state.unit_multiplier(effective_unit)
            if factor:
                input_val = round(input_val / factor, 2)
        return row_text, button_label, disabled, input_val, effective_unit

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
            state.reset_state()
            broadcast_snapshot()
            snapshot = state.snapshot_state()
            return state.table_rows(snapshot), "State reset to sample values.", {"color": "seagreen"}

        if trig == "admin-add-tract":
            if not name:
                return dash.no_update, "Enter a tract name.", {"color": "crimson"}
            try:
                bid_val = float(bid) if bid is not None else 0.0
                max_val = float(max_budget) if max_budget is not None else 0.0
            except (TypeError, ValueError):
                return dash.no_update, "Bid and max must be numbers.", {"color": "crimson"}
            if max_val <= 0:
                return dash.no_update, "Max budget must be greater than zero.", {"color": "crimson"}
            created = state.add_tract(name, bid_val, max_val)
            if not created:
                return dash.no_update, "Tract already exists or name invalid.", {"color": "crimson"}
            broadcast_snapshot()
            snapshot = state.snapshot_state()
            return state.table_rows(snapshot), f"Added tract {name}.", {"color": "seagreen"}

        if trig == "admin-table":
            invalid_tracts = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                name = row.get("tract")
                try:
                    max_val = float(row.get("max_budget")) if row.get("max_budget") is not None else None
                except (TypeError, ValueError):
                    continue
                if max_val is None or max_val <= 0:
                    if name:
                        invalid_tracts.append(name)
            if invalid_tracts:
                msg = "Max budget must be greater than zero for: " + ", ".join(invalid_tracts) + "."
                return dash.no_update, msg, {"color": "crimson"}

            state.apply_table_updates(rows)
            broadcast_snapshot()
            snapshot = state.snapshot_state()
            return state.table_rows(snapshot), "Table changes saved.", {"color": "seagreen"}

        return dash.no_update, dash.no_update, dash.no_update
