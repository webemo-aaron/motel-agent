"""
West Bethel Motel MCP server — agent-facing tools.

Run via:  python -m motel.mcp_server
Config:   HERMES_HOME env var points to .hermes-west-bethel/
          DB lives at $HERMES_HOME/motel.db
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise SystemExit("mcp package not installed. Run: uv pip install -e '.[mcp]'")

from motel.db import MotelDB

mcp = FastMCP("west-bethel-motel")
_db: Optional[MotelDB] = None


def _get_db() -> MotelDB:
    global _db
    if _db is None:
        _db = MotelDB()
    return _db


def _load_telegram_env_fallback() -> None:
    """Load Telegram vars from the active profile only (HERMES_HOME/.env)."""
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_HOME_CHANNEL"):
        return

    hermes_home = os.environ.get("HERMES_HOME")
    if not hermes_home:
        return

    env_path = os.path.join(hermes_home, ".env")
    if not os.path.exists(env_path):
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except Exception:
        return


@mcp.tool()
def desk_overview() -> dict:
    """Current front-desk state: occupancy, arrivals, departures, dirty rooms, alerts."""
    return _get_db().desk_overview()


@mcp.tool()
def dashboard_stats() -> dict:
    """Occupancy percentage, today's revenue, arrival/departure counts."""
    return _get_db().dashboard_stats()


@mcp.tool()
def bookings_list(for_date: Optional[str] = None, status: Optional[str] = None) -> list:
    """
    List reservations. for_date is ISO date string (default: today).
    status filters by reservation status (confirmed, checked_in, checked_out, etc.).
    """
    return _get_db().bookings_list(for_date=for_date, status=status)


@mcp.tool()
def booking_create(
    guest_name: str,
    check_in: str,
    check_out: str,
    room_id: str,
    rate_per_night: float = 0.0,
    email: str = "",
    phone: str = "",
    source: str = "direct",
    party_size: int = 1,
    special_requests: str = "",
) -> dict:
    """Create a new reservation. check_in and check_out are ISO date strings (YYYY-MM-DD)."""
    return _get_db().booking_create(
        guest_name=guest_name,
        check_in=check_in,
        check_out=check_out,
        room_id=room_id,
        rate_per_night=rate_per_night,
        email=email,
        phone=phone,
        source=source,
        party_size=party_size,
        special_requests=special_requests,
    )


@mcp.tool()
def booking_update(
    reservation_id: str,
    status: Optional[str] = None,
    room_id: Optional[str] = None,
    check_in: Optional[str] = None,
    check_out: Optional[str] = None,
    notes: Optional[str] = None,
    payment_status: Optional[str] = None,
    door_code: Optional[str] = None,
) -> dict:
    """Update a reservation. Pass only the fields you want to change."""
    fields = {
        k: v
        for k, v in {
            "status": status,
            "room_id": room_id,
            "check_in": check_in,
            "check_out": check_out,
            "notes": notes,
            "payment_status": payment_status,
            "door_code": door_code,
        }.items()
        if v is not None
    }
    return _get_db().booking_update(reservation_id, **fields)


@mcp.tool()
def guest_checkin(reservation_id: str) -> dict:
    """Mark a reservation as checked in. Returns updated reservation."""
    return _get_db().guest_checkin(reservation_id)


@mcp.tool()
def guest_checkout(reservation_id: str) -> dict:
    """Mark a reservation as checked out. Marks room dirty. Returns updated reservation."""
    return _get_db().guest_checkout(reservation_id)


@mcp.tool()
def room_list(status: Optional[str] = None) -> list:
    """List all rooms. Optionally filter by status: available, occupied, dirty, maintenance."""
    return _get_db().room_list(status=status)


@mcp.tool()
def room_update_status(room_id: str, status: str, notes: Optional[str] = None) -> dict:
    """
    Update a room's status.
    Valid statuses: available, occupied, dirty, maintenance.
    """
    return _get_db().room_update_status(room_id, status, notes)


@mcp.tool()
def send_operator_alert(
    message: str,
    alert_type: str = "urgent",
    room_id: Optional[str] = None,
    reservation_id: Optional[str] = None,
) -> dict:
    """
    Log an alert and send a Telegram message to the operator.
    alert_type: urgent, maintenance, no_show, complaint.
    """
    from datetime import datetime

    import httpx

    alert = _get_db().alert_create(
        message=message,
        alert_type=alert_type,
        room_id=room_id,
        reservation_id=reservation_id,
    )

    _load_telegram_env_fallback()
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_HOME_CHANNEL", "")

    if bot_token and chat_id:
        room_line = f"Room: {room_id}" if room_id else ""
        text = (
            f"WEST BETHEL ALERT [{alert_type.upper()}]\n"
            + (f"{room_line}\n" if room_line else "")
            + f"{message}\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            "Reply to this message or call the front desk."
        )
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            if resp.is_success:
                with _get_db()._connect() as conn:
                    conn.execute(
                        "UPDATE alerts SET sent_to_telegram = 1 WHERE id = ?",
                        (alert["id"],),
                    )
                alert["sent_to_telegram"] = 1
        except Exception as exc:
            alert["telegram_error"] = str(exc)

    return alert


@mcp.tool()
def work_order_create(
    title: str,
    category: str,
    location: str,
    priority: str = "medium",
    description: str = "",
    estimated_cost: Optional[float] = None,
    due_date: Optional[str] = None,
    vendor: Optional[str] = None,
    recurrence: Optional[str] = None,
    room_blocks_occupancy: bool = False,
) -> dict:
    """
    Create a work order. category: plumbing/electrical/hvac/structural/cosmetic/safety/capital/preventive/cleaning.
    priority: critical/high/medium/low. recurrence: monthly/quarterly/annually or omit for one-time.
    Set room_blocks_occupancy=True if the room cannot be occupied until resolved.
    """
    return _get_db().work_order_create(
        title=title,
        category=category,
        location=location,
        priority=priority,
        description=description,
        estimated_cost=estimated_cost,
        due_date=due_date,
        vendor=vendor,
        recurrence=recurrence,
        room_blocks_occupancy=room_blocks_occupancy,
    )


@mcp.tool()
def work_order_list(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    overdue_only: bool = False,
) -> list:
    """
    List work orders with optional filters. status: open/in_progress/scheduled/completed/deferred/cancelled.
    overdue_only=True returns items past due_date that are not completed or cancelled.
    Results are sorted by priority (critical first) then by due_date.
    """
    return _get_db().work_order_list(
        status=status,
        priority=priority,
        location=location,
        category=category,
        overdue_only=overdue_only,
    )


@mcp.tool()
def work_order_update(
    work_order_id: str,
    status: Optional[str] = None,
    scheduled_date: Optional[str] = None,
    vendor: Optional[str] = None,
    actual_cost: Optional[float] = None,
    priority: Optional[str] = None,
    estimated_cost: Optional[float] = None,
    due_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Update a work order. Pass only the fields you want to change.
    notes are appended (not replaced) with a timestamp.
    """
    return _get_db().work_order_update(
        work_order_id,
        status=status,
        scheduled_date=scheduled_date,
        vendor=vendor,
        actual_cost=actual_cost,
        priority=priority,
        estimated_cost=estimated_cost,
        due_date=due_date,
        notes=notes,
    )


@mcp.tool()
def work_order_complete(
    work_order_id: str,
    notes: Optional[str] = None,
    actual_cost: Optional[float] = None,
) -> dict:
    """
    Mark a work order completed. If recurring, automatically creates the next work order.
    Returns {"completed": {...}, "next_work_order_id": "..." or None}.
    """
    return _get_db().work_order_complete(
        work_order_id,
        notes=notes,
        actual_cost=actual_cost,
    )


@mcp.tool()
def work_order_summary() -> dict:
    """
    Snapshot for daily/weekly review: counts by status and priority, overdue list,
    due-this-week list, and capital improvement cost total.
    """
    return _get_db().work_order_summary()


@mcp.tool()
def alert_resolve(alert_id: str) -> dict:
    """Mark an alert as resolved."""
    return _get_db().alert_resolve(alert_id)


if __name__ == "__main__":
    mcp.run()
