import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def db(tmp_path):
    from motel.db import MotelDB

    return MotelDB(db_path=str(tmp_path / "motel.db"))


def test_schema_creates_tables(db):
    conn = sqlite3.connect(db.db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert {"rooms", "guests", "reservations", "alerts"} <= tables


def test_room_list_empty_on_fresh_db(db):
    assert db.room_list() == []


def test_desk_overview_returns_dict(db):
    overview = db.desk_overview()
    assert isinstance(overview, dict)
    for key in (
        "occupied_count",
        "total_rooms",
        "arrivals_today",
        "departures_today",
        "dirty_rooms",
        "unresolved_alerts",
    ):
        assert key in overview


def test_booking_create_and_list(db):
    db.room_upsert("101", name="Room 101", type="standard")
    res = db.booking_create(
        guest_name="Jane Smith",
        check_in="2026-06-01",
        check_out="2026-06-03",
        room_id="101",
        rate_per_night=89.0,
    )
    assert res["status"] == "confirmed"
    assert res["total_amount"] == 178.0
    assert res["room_id"] == "101"
    bookings = db.bookings_list(for_date="2026-06-01")
    assert len(bookings) == 1
    assert bookings[0]["guest_name"] == "Jane Smith"


def test_guest_checkin_checkout(db):
    db.room_upsert("102", name="Room 102")
    res = db.booking_create("Bob Jones", "2026-06-01", "2026-06-02", "102", 79.0)
    res_id = res["id"]
    checked_in = db.guest_checkin(res_id)
    assert checked_in["status"] == "checked_in"
    checked_out = db.guest_checkout(res_id)
    assert checked_out["status"] == "checked_out"
    room = db.room_list(status="dirty")
    assert any(r["id"] == "102" for r in room)


def test_alert_create_and_resolve(db):
    alert = db.alert_create("Guest locked out", alert_type="urgent", room_id="103")
    assert alert["resolved"] == 0
    assert db.desk_overview()["unresolved_alerts"] == 1
    db.alert_resolve(alert["id"])
    assert db.desk_overview()["unresolved_alerts"] == 0


def test_dashboard_stats_occupancy(db):
    db.room_upsert("201", name="Room 201")
    db.room_upsert("202", name="Room 202")
    db.room_update_status("201", "occupied")
    stats = db.dashboard_stats()
    assert stats["total_rooms"] == 2
    assert stats["occupancy_pct"] == 50.0


def test_work_order_schema_exists(db):
    conn = sqlite3.connect(db.db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "work_orders" in tables


def test_work_order_create_and_list(db):
    wo = db.work_order_create(
        title="Bathroom drain slow",
        category="plumbing",
        location="5",
        priority="medium",
        description="Room 5 bathroom drain is slow",
        due_date="2026-05-20",
    )
    assert wo["status"] == "open"
    assert wo["category"] == "plumbing"
    assert wo["location"] == "5"
    assert wo["room_blocks_occupancy"] == 0

    wos = db.work_order_list()
    assert len(wos) == 1
    assert wos[0]["id"] == wo["id"]

    # Filter by status
    wos_open = db.work_order_list(status="open")
    assert len(wos_open) == 1


def test_work_order_update_appends_notes(db):
    wo = db.work_order_create(
        title="Leaky faucet",
        category="plumbing",
        location="7",
    )
    wo_id = wo["id"]

    db.work_order_update(wo_id, notes="First note from inspection")
    updated = db.work_order_update(wo_id, notes="Called plumber, awaiting response")

    # Check notes are appended with timestamps
    assert "First note from inspection" in updated["notes"]
    assert "Called plumber, awaiting response" in updated["notes"]
    assert "[" in updated["notes"]  # timestamp present


def test_work_order_complete_nonrecurring(db):
    wo = db.work_order_create(
        title="One-time repair",
        category="cosmetic",
        location="3",
        recurrence=None,
    )
    wo_id = wo["id"]

    result = db.work_order_complete(wo_id, notes="Completed successfully", actual_cost=45.50)
    assert result["completed"]["status"] == "completed"
    assert result["completed"]["actual_cost"] == 45.50
    assert result["next_work_order_id"] is None


def test_work_order_complete_recurring_creates_next(db):
    wo = db.work_order_create(
        title="HVAC filter replacement",
        category="hvac",
        location="common",
        priority="medium",
        recurrence="quarterly",
        due_date="2026-05-15",
    )
    wo_id = wo["id"]

    result = db.work_order_complete(wo_id, notes="Filter replaced", actual_cost=25.0)
    assert result["completed"]["status"] == "completed"
    assert result["next_work_order_id"] is not None

    # Verify next work order exists
    next_wo = db.work_order_list(status="open")
    assert len(next_wo) == 1
    next_id = next_wo[0]["id"]
    assert next_id == result["next_work_order_id"]
    assert next_wo[0]["recurrence"] == "quarterly"


def test_work_order_summary(db):
    from datetime import date, timedelta

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    next_week = (date.today() + timedelta(days=10)).isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Create work orders with various statuses and priorities
    db.work_order_create(
        title="Critical drain",
        category="plumbing",
        location="5",
        priority="critical",
        due_date=today,
    )
    db.work_order_create(
        title="Medium inspection",
        category="structural",
        location="common",
        priority="medium",
        due_date=tomorrow,
    )
    db.work_order_create(
        title="Overdue repair",
        category="cosmetic",
        location="2",
        priority="low",
        due_date=yesterday,
    )

    summary = db.work_order_summary()
    assert summary["counts_by_status"]["open"] == 3
    assert summary["counts_by_priority"]["critical"] == 1
    assert summary["counts_by_priority"]["medium"] == 1
    assert len(summary["overdue"]) == 1
    assert len(summary["due_this_week"]) >= 2


def test_work_order_overdue_filter(db):
    from datetime import date, timedelta

    yesterday = (date.today() - timedelta(days=1)).isoformat()

    db.work_order_create(
        title="Overdue task",
        category="plumbing",
        location="4",
        due_date=yesterday,
    )
    db.work_order_create(
        title="Current task",
        category="hvac",
        location="5",
        due_date=date.today().isoformat(),
    )

    overdue = db.work_order_list(overdue_only=True)
    assert len(overdue) == 1
    assert overdue[0]["title"] == "Overdue task"


def test_desk_overview_includes_work_order_counts(db):
    from datetime import date, timedelta

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Create a critical work order (should appear in open_critical_work_orders)
    db.work_order_create(
        title="Critical issue",
        category="safety",
        location="1",
        priority="critical",
        due_date=today,
    )

    # Create an overdue work order (should appear in overdue_work_orders)
    db.work_order_create(
        title="Overdue task",
        category="plumbing",
        location="2",
        priority="low",
        due_date=yesterday,
    )

    overview = db.desk_overview()
    assert "open_critical_work_orders" in overview
    assert "overdue_work_orders" in overview
    assert overview["open_critical_work_orders"] == 1
    assert overview["overdue_work_orders"] == 1


# ─── Config Table Tests (NEW) ───────────────────────────────────────


def test_config_table_exists(db):
    """Verify config table is created during schema initialization."""
    conn = sqlite3.connect(db.db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "config" in tables


def test_config_set_and_get_basic(db):
    """Test basic config_set and config_get operations."""
    db.config_set("voice.public_host", "abc123.trycloudflare.com")
    assert db.config_get("voice.public_host") == "abc123.trycloudflare.com"


def test_config_get_with_default(db):
    """Test config_get returns default when key not found."""
    result = db.config_get("voice.nonexistent", default="default_value")
    assert result == "default_value"


def test_config_get_empty_default(db):
    """Test config_get returns empty string when no default specified."""
    result = db.config_get("voice.missing")
    assert result == ""


def test_config_set_upsert(db):
    """Test that config_set updates existing keys (upsert behavior)."""
    db.config_set("voice.hermes_url", "http://localhost:8652")
    assert db.config_get("voice.hermes_url") == "http://localhost:8652"

    # Update the same key
    db.config_set("voice.hermes_url", "http://localhost:9999")
    assert db.config_get("voice.hermes_url") == "http://localhost:9999"


def test_config_all_empty(db):
    """Test config_all returns empty dict on fresh database."""
    result = db.config_all()
    assert isinstance(result, dict)
    assert len(result) == 0


def test_config_all_multiple_keys(db):
    """Test config_all returns all keys as dict."""
    db.config_set("voice.public_host", "tunnel.example.com")
    db.config_set("voice.hermes_url", "http://localhost:8652")
    db.config_set("voice.twilio_phone", "+1-555-0100")

    result = db.config_all()
    assert len(result) == 3
    assert result["voice.public_host"] == "tunnel.example.com"
    assert result["voice.hermes_url"] == "http://localhost:8652"
    assert result["voice.twilio_phone"] == "+1-555-0100"


def test_config_set_empty_string(db):
    """Test that config_set can store empty strings."""
    db.config_set("voice.optional_field", "")
    assert db.config_get("voice.optional_field") == ""
    assert db.config_all()["voice.optional_field"] == ""


def test_config_set_special_characters(db):
    """Test config_set preserves special characters in values."""
    special_value = "wss://tunnel.trycloudflare.com:443?token=abc123-def456"
    db.config_set("voice.websocket_url", special_value)
    assert db.config_get("voice.websocket_url") == special_value


def test_config_set_long_value(db):
    """Test config_set handles long string values."""
    long_key = "voice.api_key"
    long_value = "sk-" + "x" * 200
    db.config_set(long_key, long_value)
    assert db.config_get(long_key) == long_value


def test_booking_update_not_found_error(db):
    """Test booking_update raises error when booking doesn't exist."""
    with pytest.raises(Exception):  # Should raise ValueError or KeyError
        db.booking_update("nonexistent-id", status="checked_in")


def test_alert_resolve_not_found_error(db):
    """Test alert_resolve raises error when alert doesn't exist."""
    with pytest.raises(Exception):  # Should raise ValueError or KeyError
        db.alert_resolve("nonexistent-alert-id")


def test_work_order_update_field_isolation(db):
    """Test work_order_update only updates specified fields."""
    wo = db.work_order_create(
        title="Original title",
        category="plumbing",
        location="5",
        priority="low",
        description="Original description",
    )
    wo_id = wo["id"]

    # Update only priority
    updated = db.work_order_update(wo_id, priority="critical")
    assert updated["priority"] == "critical"
    assert updated["title"] == "Original title"
    assert updated["description"] == "Original description"


def test_work_order_update_status_transition(db):
    """Test work_order_update status transitions."""
    wo = db.work_order_create(
        title="Status test",
        category="hvac",
        location="common",
        priority="high",
    )
    wo_id = wo["id"]

    # Transition to in_progress
    updated = db.work_order_update(wo_id, status="in_progress")
    assert updated["status"] == "in_progress"

    # Transition to blocked
    updated = db.work_order_update(wo_id, status="blocked")
    assert updated["status"] == "blocked"


def test_work_order_complete_nonrecurring_sets_actual_cost(db):
    """Test work_order_complete properly sets actual_cost."""
    wo = db.work_order_create(
        title="Simple repair",
        category="cosmetic",
        location="1",
        estimated_cost=50.0,
    )
    wo_id = wo["id"]

    result = db.work_order_complete(wo_id, actual_cost=42.75)
    assert result["completed"]["actual_cost"] == 42.75


def test_work_order_recurrence_monthly(db):
    """Test monthly recurrence creates next work order with same recurrence."""
    wo = db.work_order_create(
        title="Monthly inspection",
        category="structural",
        location="common",
        recurrence="monthly",
        due_date="2026-05-15",
    )
    wo_id = wo["id"]

    result = db.work_order_complete(wo_id)
    next_wo = db.work_order_list(status="open")[0]

    # Next work order exists and has monthly recurrence
    assert result["next_work_order_id"] is not None
    assert next_wo["recurrence"] == "monthly"
    # due_date is set to first of next month
    assert next_wo["due_date"].startswith("2026-06")


def test_work_order_recurrence_quarterly(db):
    """Test quarterly recurrence creates next work order approximately 3 months later."""
    wo = db.work_order_create(
        title="Quarterly HVAC check",
        category="hvac",
        location="common",
        recurrence="quarterly",
        due_date="2026-05-15",
    )
    wo_id = wo["id"]

    result = db.work_order_complete(wo_id)
    next_wo = db.work_order_list(status="open")[0]

    # Next work order exists and has quarterly recurrence
    assert result["next_work_order_id"] is not None
    assert next_wo["recurrence"] == "quarterly"
    # due_date should be approximately 91 days later (August)
    assert next_wo["due_date"].startswith("2026-08")


def test_work_order_recurrence_annually(db):
    """Test annually recurrence creates next work order approximately 1 year later."""
    wo = db.work_order_create(
        title="Annual inspection",
        category="structural",
        location="common",
        recurrence="annually",
        due_date="2026-05-15",
    )
    wo_id = wo["id"]

    result = db.work_order_complete(wo_id)
    next_wo = db.work_order_list(status="open")[0]

    # Next work order exists and has annual recurrence
    assert result["next_work_order_id"] is not None
    assert next_wo["recurrence"] == "annually"
    # due_date should be approximately 365 days later (May 2027)
    assert next_wo["due_date"].startswith("2027-05")
