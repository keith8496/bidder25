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
- Bid Monitor: choose a tract, enter a new asking price, press Enter to push an update with a confirmation banner.
- Bidder: choose a tract; see current bid, max budget, elapsed time since last update, and a red/green indicator for over-budget approval.
- High Approver: per-tract buttons that enable when the bid exceeds budget; approving locks the button until a new bid arrives.
- Admin: reset the in-memory sample data.

## State model

- Global shared state is an in-memory Python dictionary (`TRACTS`) protected by a lock. It holds `current_bid`, `max_budget`, `approved_over_budget`, and `last_updated` per tract.
- Bid updates clear any prior approval; approvals are per-tract and re-required after each new bid.
- State is not persisted; restarting the app restores the sample data.

## VS Code launch config

A ready-to-go debugger configuration is in `.vscode/launch.json` (`Python: Dash app`). Set a breakpoint in `app.py`, press F5, and you can debug with the integrated terminal.
