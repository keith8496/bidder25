# ui/common.py
"""
Shared UI helpers and formatting utilities.

This module contains *presentation-only* logic used by layouts,
charts, and components. It must not mutate state or import Dash callbacks.
"""

from typing import Optional


# ---- Formatting helpers ----

def currency(value: Optional[float]) -> str:
    """
    Format a numeric value as USD currency for display (2 decimal places).
    None-safe and tolerant of bad input.
    """
    try:
        if value is None:
            return "—"
        return f"${value:,.2f}"
    except Exception:
        return "—"


def seconds_to_hms(seconds: Optional[float]) -> str:
    """
    Convert seconds to HH:MM:SS for UI display.
    """
    try:
        if seconds is None:
            return "—"
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return "—"


# ---- Shared UI constants ----

STATUS_COLORS = {
    "ok": "seagreen",
    "warn": "darkorange",
    "error": "crimson",
}

DOT_STYLE = {
    "width": "12px",
    "height": "12px",
    "borderRadius": "50%",
    "display": "inline-block",
    "marginRight": "6px",
}
