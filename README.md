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
- High Approver: per-tract inputs (unit scaling) and approve buttons to raise budgets/approve requests when over budget.
- Admin: reset the in-memory sample data and edit/add tracts via an editable table.

Early alpha; all rights reserved; not for distribution.

## State model

- Global shared state is an in-memory Python dictionary (`TRACTS`) protected by a lock. It holds `current_bid`, `max_budget`, `approved_over_budget`, `requested_budget`, `high_bidder`, and `last_updated` per tract.
- Bid updates clear any prior approval and reset high-bidder; approvals do not set high-bidder (only the monitor toggle controls it).
- Budget requests are tracked per-tract and cleared on approval or new bid.
- State is not persisted; restarting the app restores the sample data.

## Architecture notes

- Server‑side polling: the UI is driven by a single lightweight server callback that updates `snapshot-store` every 500 ms. All pages read from this snapshot for consistent cross‑window state.
- Socket.IO (foundation only): the server broadcasts updated snapshots after every state mutation (bid update, approval, high‑bidder toggle, admin edits). The client currently initializes a Socket.IO connection, but the UI is still driven by server polling while real‑time push support is developed.
- Client-side rendering: monitor/bidder labels update via Dash clientside callbacks to avoid disrupting text entry in input fields.
- Server-side state changes: all mutations (bid updates, high‑bidder toggles, budget requests, approvals, resets, and admin edits) acquire a lock and update the shared in‑memory dictionary (`TRACTS`), followed by a Socket.IO broadcast.
- No external services: state is purely in‑memory; restarting the app restores the sample data. Future versions may swap this for Redis or a database for durability and multi‑process scaling.

## VS Code launch config

A ready-to-go debugger configuration is in `.vscode/launch.json` (`Python: Dash app`). Set a breakpoint in `app.py`, press F5, and you can debug with the integrated terminal.
