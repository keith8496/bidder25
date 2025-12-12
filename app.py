import logging
import os
from pathlib import Path

from dash import Dash, dcc, html

import state  # Use module import only


# --- Modular imports ---
from realtime import init_socketio
from callbacks.server import register_server_callbacks
from callbacks.client import register_clientside_callbacks
from ui.pages import (
    view_only_layout as pages_view_only_layout,
    monitor_layout as pages_monitor_layout,
    bidder_layout as pages_bidder_layout,
    approver_layout as pages_approver_layout,
    admin_layout as pages_admin_layout,
    not_found_layout as pages_not_found_layout,
)

LOG_DIR = Path("logs")
log_handlers = [logging.StreamHandler()]
try:
    # Try to create a logs directory and attach a file handler for persistent logs.
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_handlers.append(logging.FileHandler(LOG_DIR / "app.log"))
except Exception as e:
    # In read-only or constrained environments, fall back to console-only logging.
    print(f"Warning: could not initialize file logging in {LOG_DIR}: {e}")

logging.basicConfig(
    level=logging.WARN,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger("auction")
# Explicitly document at runtime that this app assumes a single-process, in-memory state model.
logger.warning(
    "bidder25 running with in-memory state and a single-process Socket.IO server; "
    "do NOT deploy with multiple workers/processes without adding a shared state backend."
)


app = Dash(__name__, update_title=None)
app.title = "Auction Control"
app.suppress_callback_exceptions = True
server = app.server
# Socket.IO for real-time push of state snapshots (development: allow all origins)
socketio = init_socketio(server)


app.layout = html.Div(
    [
        dcc.Location(id="url"),
        html.H1("Auction Bidding Control Center"),
        dcc.Store(id="snapshot-store", data=state.snapshot_state()),
        dcc.Interval(id="state-interval", interval=500, n_intervals=0),
        html.Div(id="page-container"),
    ],
    style={"maxWidth": "1100px", "margin": "0 auto", "padding": "18px"},
)

# Validation layout makes Dash aware of dynamic pages/IDs used by callbacks.
app.validation_layout = html.Div(
    [
        app.layout,
        pages_view_only_layout("/view"),
        pages_monitor_layout("/monitor"),
        pages_bidder_layout("/bidder"),
        pages_approver_layout("/approver"),
        pages_admin_layout("/admin"),
        pages_not_found_layout("/404"),
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

# --- Modular callback wiring (currently scaffolds/no-ops) ---
register_server_callbacks(app, socketio)
register_clientside_callbacks(app)
if __name__ == "__main__":
    debug = os.getenv("DASH_DEBUG", "1") not in {"0", "false", "False"}
    # Use Socket.IO's runner so WebSocket transport is enabled.
    # Default to port 8050 so it matches the typical Dash dev port, but allow override via PORT env.
    port = int(os.getenv("PORT", "8050"))
    socketio.run(server, debug=debug, port=port, use_reloader=False)
