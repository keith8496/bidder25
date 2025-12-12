# state.py
from datetime import datetime, timezone
import logging
import threading
from typing import Dict, Any, Optional, List

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
        "requested_unit": None,
        "high_bidder": False,
        "last_updated": _now(),
    },
    "Tract 2": {
        "current_bid": 210_500.00,
        "max_budget": 200_000.00,
        "approved_over_budget": False,
        "requested_budget": None,
        "requested_unit": None,
        "high_bidder": False,
        "last_updated": _now(),
    },
    "Tract 3": {
        "current_bid": 95_250.00,
        "max_budget": 110_000.00,
        "approved_over_budget": False,
        "requested_budget": None,
        "requested_unit": None,
        "high_bidder": False,
        "last_updated": _now(),
    },
}

STATE_LOCK = threading.Lock()
TRACTS: Dict[str, Dict[str, Any]] = {name: data.copy() for name, data in INITIAL_STATE.items()}


def unit_multiplier(unit: str) -> float:
    return {"1": 1.0, "K": 1_000.0, "MM": 1_000_000.0}.get(unit or "1", 1.0)


def snapshot_state() -> Dict[str, Dict[str, Any]]:
    """
    Authoritative read model of all tracts.

    Returns a dict of tracts with primitive values only (no datetime objects)
    so it can be serialized or used by UI layers.
    """
    with STATE_LOCK:
        return {
            tract: {
                "current_bid": data["current_bid"],
                "max_budget": data["max_budget"],
                "approved_over_budget": data["approved_over_budget"],
                "requested_budget": data.get("requested_budget"),
                "requested_unit": data.get("requested_unit"),
                "high_bidder": data.get("high_bidder", False),
                "last_updated": data["last_updated"].isoformat(),
            }
            for tract, data in TRACTS.items()
        }


def update_bid(tract: str, amount: float) -> None:
    with STATE_LOCK:
        if tract not in TRACTS:
            logger.warning("Update requested for unknown tract %s", tract)
            return
        TRACTS[tract]["current_bid"] = amount
        TRACTS[tract]["last_updated"] = _now()
        TRACTS[tract]["approved_over_budget"] = False
        TRACTS[tract]["requested_budget"] = None
        TRACTS[tract]["requested_unit"] = None
        TRACTS[tract]["high_bidder"] = False
        logger.info("Updated %s bid to %.2f", tract, amount)


def approve_over_budget(tract: str, new_budget: Optional[float] = None) -> None:
    with STATE_LOCK:
        if tract in TRACTS:
            if new_budget is not None:
                TRACTS[tract]["max_budget"] = new_budget
            TRACTS[tract]["approved_over_budget"] = True
            TRACTS[tract]["requested_budget"] = None
            TRACTS[tract]["requested_unit"] = None
            logger.info(
                "Approved budget for %s: max_budget=%.2f",
                tract,
                TRACTS[tract]["max_budget"],
            )
        else:
            logger.warning("Approval requested for unknown tract %s", tract)


def request_budget_increase(tract: str, amount: float, unit: Optional[str] = None) -> None:
    with STATE_LOCK:
        if tract not in TRACTS:
            logger.warning("Request for unknown tract %s", tract)
            return
        TRACTS[tract]["requested_budget"] = amount
        TRACTS[tract]["requested_unit"] = unit
        TRACTS[tract]["approved_over_budget"] = False
        logger.info("Requested budget increase for %s to %.2f (%s)", tract, amount, unit)


def set_high_bidder(tract: str, is_high: bool) -> None:
    with STATE_LOCK:
        if tract not in TRACTS:
            logger.warning("High bidder toggle for unknown tract %s", tract)
            return
        TRACTS[tract]["high_bidder"] = bool(is_high)
        logger.info("Set high bidder status for %s to %s", tract, bool(is_high))


def reset_state() -> None:
    with STATE_LOCK:
        for tract, data in INITIAL_STATE.items():
            TRACTS[tract] = data.copy()
    logger.info("State reset to initial sample values")


def apply_table_updates(rows: Any) -> None:
    """
    Apply edited rows from the admin table to TRACTS.

    This does basic numeric validation and resets approval/high-bidder flags.
    """
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
            TRACTS[name]["requested_unit"] = None
            TRACTS[name]["high_bidder"] = False
            logger.info("Admin table update for %s: bid=%.2f, max=%.2f", name, bid, budget)


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
            "requested_unit": None,
            "high_bidder": False,
            "last_updated": _now(),
        }
        logger.info("Added new tract %s (bid=%.2f, max=%.2f)", name, current_bid, max_budget)
    return True


def table_rows(snapshot: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"tract": name, "current_bid": data["current_bid"], "max_budget": data["max_budget"]}
        for name, data in snapshot.items()
    ]


def tract_options():
    with STATE_LOCK:
        return [{"label": name, "value": name} for name in TRACTS.keys()]


def safe_pct_of_budget(current_bid: float, max_budget: float) -> float:
    """
    Compute % of budget used, with validation and clamping.
    - If max_budget is None or <= 0, return 0.0 to avoid division errors.
    - Clamp the result between 0.0 and 150.0.
    """
    try:
        if max_budget is None or max_budget <= 0:
            return 0.0
        pct = (current_bid / max_budget) * 100.0
    except Exception:
        logger.exception("Error computing pct_of_budget for current_bid=%r max_budget=%r", current_bid, max_budget)
        return 0.0
    pct = round(pct, 1)
    if pct < 0.0:
        pct = 0.0
    if pct > 150.0:
        pct = 150.0
    return pct