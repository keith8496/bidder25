# bidder25

Dash multi-page prototype for an auction bidding team (Bid Monitor, Bidder, High Approver, View Only, Admin).

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

- Server‑side polling: the UI is driven by a single lightweight server callback that updates `snapshot-store` every 500 ms. All pages read from this snapshot for consistent cross‑window state.
- Socket.IO: every state mutation triggers a broadcast of the latest snapshot. Clients receive these snapshots and store them in `window.latestSnapshot`, but UI updates still rely on server polling.
- Client-side rendering: monitor/bidder labels update via Dash clientside callbacks to avoid disrupting text entry in input fields.
- Server-side state changes: all mutations (bid updates, high‑bidder toggles, budget requests, approvals, resets, and admin edits) acquire a lock and update the shared in‑memory dictionary (`TRACTS`), followed by a Socket.IO broadcast.
- No external services: state is purely in‑memory; restarting the app restores the sample data. Future versions may swap this for Redis or a database for durability and multi‑process scaling.

## Current Architecture (Dec 2025)

This reflects the current stable baseline of the application as of December 2025.

### State Model
- All shared state resides in a single in-memory dictionary (`TRACTS`) protected by a global lock.
- `snapshot_state()` is the authoritative read model; all UI pages derive their data from it.
- Every state mutation (bid update, high‑bidder toggle, approval, budget request, admin edits, reset) updates `TRACTS` and then triggers a `broadcast_snapshot()` Socket.IO event.

### UI Model
- Each page includes a `dcc.Store(id="snapshot-store")` that holds the latest snapshot.
- A lightweight server-side polling callback updates `snapshot-store` every 500 ms. This ensures all users remain synchronized even when multiple windows are open.
- All visual components (tables, charts, labels) render exclusively from `snapshot-store`.
- Pages use clientside callbacks for responsive UI elements (e.g., bidder/monitor labels) without interfering with text entry.

### Socket.IO Usage
- Socket.IO is fully wired: the server emits an updated snapshot after every state change.
- The browser receives snapshots and logs them to `window.latestSnapshot`.
- **However, the production UI currently relies on server polling only.** Real-time push is staged for a later release.

## Workflow Assumptions

- The Bid Monitor is the authoritative interface for setting bids during live auctions.
- High Bidder status is explicitly user-controlled via the Bid Monitor and never inferred by approvals.
- Bidders request budget increases; approvers validate and approve them. Requests auto-clear upon approval or new bids.
- Real-time integrity: when two users have Bid Monitor or Approver screens open simultaneously, all changes propagate through the shared snapshot model.
- Default unit on all pages is "K" unless a bidder request specifies otherwise.

## VS Code launch config

A ready-to-go debugger configuration is in `.vscode/launch.json` (`Python: Dash app`). Set a breakpoint in `app.py`, press F5, and you can debug with the integrated terminal.

## Development Notes

- `app.py` is the single source of truth for server, state, UI layout, and callbacks.
- The codebase is intentionally monolithic during early development. Planned improvements include modularizing layouts, callbacks, and state management.
- A VS Code debug config (`Python: Dash app`) is included for stepping through callbacks and state transitions.
