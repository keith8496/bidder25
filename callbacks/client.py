# callbacks/client.py
"""Client-side (JavaScript) Dash callback registration."""

from __future__ import annotations

from dash import Input, Output


def register_clientside_callbacks(app) -> None:
    """Register all client-side callbacks."""

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
        Input({"type": "tract-dropdown", "role": "monitor"}, "value"),
    )

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
        Input({"type": "tract-dropdown", "role": "bidder"}, "value"),
    )

    app.clientside_callback(
        """
        function(signal) {
            if (!signal) {
                return "";
            }
            const el = document.getElementById("monitor-price");
            if (el && typeof el.focus === "function") {
                el.focus();
                if (typeof el.select === "function") {
                    el.select();
                }
            }
            // Return some dummy content for the hidden div.
            return "";
        }
        """,
        Output("monitor-focus-anchor", "children"),
        Input("monitor-focus-signal", "data"),
    )
