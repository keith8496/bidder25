# bidder25

Dash multi-page prototype for an auction bidding team (Bid Monitor, Bidder, High Approver, View Only, Admin). Now modularized: layouts in `ui/pages.py`, UI helpers in `ui/components.py` and `ui/charts.py`, callbacks in `callbacks/`.

## Quick start

1) Create and activate a virtual environment (recommended):
```
python3 -m venv .venv
source .venv/bin/activate
```

2) Install dependencies:
```
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3) Run the app:
```
python app.py
```

Open http://127.0.0.1:8050 and use the top nav to switch between pages.

## What’s in the app

- View Only: read-only dashboard with current bid table, % of budget gauge bars, and bid-by-tract chart.
- Bid Monitor: choose a tract, enter a new asking price (unit scaling with Exact/K/MM), toggle high-bidder, and push updates with Enter.
- Bidder: choose a tract; see current bid, max budget, requested budget, elapsed time since last update, and a status light for approval.
- High Approver: per‑tract inputs (unit scaling) and approve buttons. When a bidder requests a higher budget, the approver screen automatically adopts the same unit (Exact/K/MM) the bidder used, ensuring both users see the same value format.
- Admin: reset the in-memory sample data and edit/add tracts via an editable table.

Early alpha; all rights reserved; not for distribution.

## State model

- Global shared state is an in-memory Python dictionary (`TRACTS`) protected by a lock. It holds `current_bid`, `max_budget`, `approved_over_budget`, `requested_budget`, `high_bidder`, and `last_updated` per tract.
- Bid updates clear any prior approval and reset high-bidder; approvals do not set high-bidder (only the monitor toggle controls it).
- Budget requests are tracked per-tract and cleared on approval or new bid.
- State is not persisted; restarting the app restores the sample data.

### Unit Handling & Normalization

- All bid, request, and approval inputs use a consistent unit model (Exact = 1, K = 1,000, MM = 1,000,000).
- State always stores the *scaled numeric value* and remembers the user-selected input unit when relevant (e.g., `requested_unit` for budget requests).
- The High Approver page mirrors the bidder’s `requested_unit` whenever a budget request exists, ensuring users see matching units.
- Any mutation that changes the bid automatically clears pending requests and resets high-bidder status.

## Architecture notes

- App entry: `app.py` wires Dash + Flask-SocketIO, sets the base layout, and delegates callbacks to `callbacks/server.py` and `callbacks/client.py`. UI layouts come from `ui/pages.py`; shared UI helpers live in `ui/components.py`, `ui/charts.py`, and `ui/common.py`.
- Server‑side polling: a lightweight server callback updates `snapshot-store` every 500 ms. All pages render from this store for consistent cross‑window state.
- Socket.IO: every state mutation triggers a broadcast of the latest snapshot. Clients receive these snapshots and log them to `window.latestSnapshot`; UI updates still rely on server polling.
- Client-side rendering: monitor/bidder labels update via Dash clientside callbacks to avoid disrupting text entry in input fields.
- Server-side state changes: all mutations (bid updates, high‑bidder toggles, budget requests, approvals, resets, and admin edits) acquire a lock and update the shared in‑memory dictionary (`TRACTS`), followed by a Socket.IO broadcast.
- No external services: state is purely in‑memory; restarting the app restores the sample data. Future versions may swap this for Redis or a database for durability and multi‑process scaling.

## Current Architecture (Dec 2025)

- **State model:** shared in-memory dict (`TRACTS`) protected by a lock; `snapshot_state()` is the read model; every mutation triggers a Socket.IO `broadcast_snapshot()`.
- **UI model:** pages built in `ui/pages.py`; shared UI helpers in `ui/common.py`, `ui/charts.py`, `ui/components.py`; base container and validation layout in `app.py`.
- **Callbacks:** server callbacks live in `callbacks/server.py`; clientside callbacks in `callbacks/client.py`.
- **Data flow:** `snapshot-store` polls every 500 ms; all pages render from it. Socket.IO also emits snapshots after mutations (currently used for logging; polling drives UI).

## Workflow Assumptions

- The Bid Monitor is the authoritative interface for setting bids during live auctions.
- High Bidder status is explicitly user-controlled via the Bid Monitor and never inferred by approvals.
- Bidders request budget increases; approvers validate and approve them. Requests auto-clear upon approval or new bids.
- Real-time integrity: when two users have Bid Monitor or Approver screens open simultaneously, all changes propagate through the shared snapshot model.
- Default unit on all pages is "K" unless a bidder request specifies otherwise.

## VS Code launch config

A ready-to-go debugger configuration is in `.vscode/launch.json` (`Python: Dash app`). Set a breakpoint in `app.py`, press F5, and you can debug with the integrated terminal.

## Development Notes

- Single-process, in-memory model; not safe for multi-worker deployments without a shared backend.
- Modularized layouts and callbacks; prefer editing `ui/` and `callbacks/` rather than `app.py`.
- A VS Code debug config (`Python: Dash app`) is included for stepping through callbacks and state transitions.
