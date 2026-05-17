import pytest
from datetime import date, timedelta


@pytest.fixture
def mcp_tools(tmp_path, monkeypatch):
    """Import MCP tools with isolated database."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # Import and reload to get fresh MotelDB
    import importlib
    import motel.mcp_server as mcp_mod
    importlib.reload(mcp_mod)

    return mcp_mod


# ─── Desk Overview Tool ────────────────────────────────────────────


def test_desk_overview_returns_dict(mcp_tools):
    """desk_overview() returns dict with occupancy metrics."""
    result = mcp_tools.desk_overview()
    assert isinstance(result, dict)
    assert "occupied_count" in result
    assert "total_rooms" in result
    assert "unresolved_alerts" in result


def test_desk_overview_initial_empty_state(mcp_tools):
    """desk_overview() on fresh DB returns zeros."""
    result = mcp_tools.desk_overview()
    assert result["occupied_count"] == 0
    assert result["unresolved_alerts"] == 0


# ─── Dashboard Stats Tool ──────────────────────────────────────────


def test_dashboard_stats_returns_dict(mcp_tools):
    """dashboard_stats() returns operational metrics."""
    result = mcp_tools.dashboard_stats()
    assert isinstance(result, dict)
    assert "occupancy_pct" in result
    assert "revenue_today" in result


def test_dashboard_stats_occupancy_calculation(mcp_tools):
    """dashboard_stats() calculates occupancy percentage."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")
    db.room_upsert("2", name="Room 2")
    db.room_update_status("1", "occupied")

    result = mcp_tools.dashboard_stats()
    assert result["occupancy_pct"] == 50.0


# ─── Bookings List Tool ────────────────────────────────────────────


def test_bookings_list_returns_list(mcp_tools):
    """bookings_list() returns list."""
    result = mcp_tools.bookings_list()
    assert isinstance(result, list)


def test_bookings_list_empty_on_fresh_db(mcp_tools):
    """bookings_list() returns empty list on fresh DB."""
    result = mcp_tools.bookings_list()
    assert result == []


def test_bookings_list_with_status_filter(mcp_tools):
    """bookings_list() filters by status."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")
    db.booking_create("Guest A", "2026-06-01", "2026-06-02", "1", 100.0)

    result = mcp_tools.bookings_list(status="confirmed")
    assert len(result) == 1
    assert result[0]["status"] == "confirmed"


def test_bookings_list_with_date_filter(mcp_tools):
    """bookings_list() filters by date."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")
    db.booking_create("Guest A", "2026-06-01", "2026-06-02", "1", 100.0)

    result = mcp_tools.bookings_list(for_date="2026-06-01")
    assert len(result) == 1


# ─── Booking Create Tool ──────────────────────────────────────────


def test_booking_create_creates_reservation(mcp_tools):
    """booking_create() creates and returns a booking."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")

    result = mcp_tools.booking_create(
        guest_name="John Doe",
        check_in="2026-06-01",
        check_out="2026-06-03",
        room_id="1",
        rate_per_night=100.0
    )

    assert isinstance(result, dict)
    assert result["status"] == "confirmed"
    assert result["total_amount"] == 200.0


def test_booking_create_calculates_total(mcp_tools):
    """booking_create() calculates total_amount correctly."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")

    result = mcp_tools.booking_create(
        guest_name="Guest B",
        check_in="2026-06-01",
        check_out="2026-06-05",
        room_id="1",
        rate_per_night=75.0
    )

    # 4 nights * 75.0 = 300.0
    assert result["total_amount"] == 300.0


# ─── Guest Checkin Tool ────────────────────────────────────────────


def test_guest_checkin_updates_status(mcp_tools):
    """guest_checkin() updates reservation status to checked_in."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")
    booking = db.booking_create("Guest C", "2026-06-01", "2026-06-02", "1", 100.0)

    result = mcp_tools.guest_checkin(booking["id"])

    assert result["status"] == "checked_in"


def test_guest_checkin_invalid_id_raises_error(mcp_tools):
    """guest_checkin() raises error for invalid booking ID."""
    with pytest.raises(Exception):
        mcp_tools.guest_checkin("nonexistent-id")


# ─── Guest Checkout Tool ───────────────────────────────────────────


def test_guest_checkout_updates_status(mcp_tools):
    """guest_checkout() updates reservation status to checked_out."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")
    booking = db.booking_create("Guest D", "2026-06-01", "2026-06-02", "1", 100.0)
    db.guest_checkin(booking["id"])

    result = mcp_tools.guest_checkout(booking["id"])

    assert result["status"] == "checked_out"


# ─── Room Update Status Tool ──────────────────────────────────────


def test_room_update_status_changes_status(mcp_tools):
    """room_update_status() updates room status."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")

    result = mcp_tools.room_update_status("1", "occupied")

    assert result["status"] == "occupied"


def test_room_update_status_with_notes(mcp_tools):
    """room_update_status() can include notes."""
    db = mcp_tools._get_db()
    db.room_upsert("1", name="Room 1")

    result = mcp_tools.room_update_status("1", "dirty", notes="Staining on carpet")

    assert result["status"] == "dirty"
    assert "Staining on carpet" in result.get("notes", "")


# ─── Alert Creation Tool ──────────────────────────────────────────


def test_send_operator_alert_creates_alert(mcp_tools):
    """send_operator_alert() creates and returns an alert."""
    result = mcp_tools.send_operator_alert(
        message="Guest complaint",
        alert_type="urgent",
        room_id="5"
    )

    assert isinstance(result, dict)
    assert result["resolved"] == 0


# ─── Work Order Tools ─────────────────────────────────────────────


def test_work_order_create_creates_order(mcp_tools):
    """work_order_create() creates a work order."""
    result = mcp_tools.work_order_create(
        title="Fix shower",
        category="plumbing",
        location="12",
        priority="high",
        due_date="2026-05-20"
    )

    assert result["title"] == "Fix shower"
    assert result["status"] == "open"


def test_work_order_list_returns_list(mcp_tools):
    """work_order_list() returns list of work orders."""
    result = mcp_tools.work_order_list()
    assert isinstance(result, list)


def test_work_order_list_filters_by_status(mcp_tools):
    """work_order_list() filters by status."""
    mcp_tools.work_order_create(
        title="Task 1",
        category="hvac",
        location="common"
    )

    result = mcp_tools.work_order_list(status="open")
    assert len(result) >= 1
    assert all(wo["status"] == "open" for wo in result)


def test_work_order_summary_returns_dict(mcp_tools):
    """work_order_summary() returns summary with counts and priorities."""
    mcp_tools.work_order_create(
        title="Critical repair",
        category="safety",
        location="1",
        priority="critical"
    )

    result = mcp_tools.work_order_summary()

    assert isinstance(result, dict)
    assert "counts_by_status" in result
    assert "counts_by_priority" in result


# ─── Get DB Tool ───────────────────────────────────────────────────


def test_get_db_returns_motel_db(mcp_tools):
    """_get_db() returns MotelDB instance."""
    from motel.db import MotelDB
    db = mcp_tools._get_db()
    assert isinstance(db, MotelDB)


def test_get_db_singleton(mcp_tools):
    """_get_db() returns same instance on multiple calls (singleton)."""
    db1 = mcp_tools._get_db()
    db2 = mcp_tools._get_db()
    assert db1 is db2
