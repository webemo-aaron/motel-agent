#!/usr/bin/env python3
"""
Seed the West Bethel Motel database with realistic test data.

Idempotent: Safe to run multiple times. Creates data only if it doesn't exist.
Reflects actual motel operations: arrivals today, departures, dirty rooms, alerts.

Run via: python -m motel.scripts.seed_database
Or:      python motel/scripts/seed_database.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from motel.db import MotelDB


def seed_database() -> None:
    """Populate database with realistic test data."""
    db = MotelDB()

    # Check if already seeded
    existing_rooms = db.room_list()
    if existing_rooms:
        print(f"Database already seeded ({len(existing_rooms)} rooms exist). Skipping.")
        return

    print("Seeding West Bethel Motel database...")

    # ── Create Rooms ────────────────────────────────────────────────────────────

    rooms_data = [
        ("101", "Room 101", 1, "standard", 2),
        ("102", "Room 102", 1, "standard", 2),
        ("103", "Room 103", 1, "deluxe", 3),
        ("104", "Room 104", 1, "standard", 2),
        ("105", "Room 105", 1, "suite", 4),
        ("201", "Room 201", 2, "standard", 2),
        ("202", "Room 202", 2, "standard", 2),
        ("203", "Room 203", 2, "deluxe", 3),
        ("204", "Room 204", 2, "standard", 2),
        ("205", "Room 205", 2, "suite", 4),
    ]

    print(f"  Creating {len(rooms_data)} rooms...")
    for room_id, name, floor, room_type, capacity in rooms_data:
        db.room_upsert(
            room_id, name=name, floor=floor, type=room_type, max_occupancy=capacity
        )

    # ── Create Reservations ──────────────────────────────────────────────────────

    today = date.today()
    reservations_data = [
        # Today's arrivals
        (
            "John Smith",
            today,
            today + timedelta(days=1),
            "101",
            89.0,
            "john@example.com",
            "555-0101",
            1,
            "Early check-in requested",
        ),
        (
            "Sarah Johnson",
            today,
            today + timedelta(days=2),
            "102",
            99.0,
            "sarah@example.com",
            "555-0102",
            2,
            "",
        ),
        # Tomorrow's arrivals
        (
            "Michael Chen",
            today + timedelta(days=1),
            today + timedelta(days=4),
            "104",
            79.0,
            "michael@example.com",
            "555-0104",
            1,
            "Business trip, needs quiet room",
        ),
        # Next week
        (
            "Emma Wilson",
            today + timedelta(days=7),
            today + timedelta(days=9),
            "105",
            109.0,
            "emma@example.com",
            "555-0105",
            2,
            "Anniversary vacation",
        ),
        # Already checked in (for checkout flow testing)
        (
            "Robert Davis",
            today - timedelta(days=2),
            today,
            "201",
            89.0,
            "robert@example.com",
            "555-0201",
            1,
            "",
        ),
    ]

    print(f"  Creating {len(reservations_data)} reservations...")
    for (
        guest_name,
        check_in,
        check_out,
        room_id,
        rate,
        email,
        phone,
        party_size,
        special_requests,
    ) in reservations_data:
        res = db.booking_create(
            guest_name=guest_name,
            check_in=check_in.isoformat(),
            check_out=check_out.isoformat(),
            room_id=room_id,
            rate_per_night=rate,
            email=email,
            phone=phone,
            party_size=party_size,
            special_requests=special_requests,
        )
        status = res.get("status", "unknown")
        print(f"    ✓ {guest_name} → Room {room_id} ({status})")

    # ── Mark rooms occupied/dirty for realism ────────────────────────────────────

    print("  Marking rooms with realistic status...")
    db.room_update_status("101", "occupied", "John Smith checked in")
    db.room_update_status("102", "occupied", "Sarah Johnson checked in")
    db.room_update_status("201", "dirty", "Robert Davis checking out today")

    # Mark Robert Davis as checked_in for checkout flow testing
    robert_res = [r for r in db.bookings_list() if r["guest_name"] == "Robert Davis"]
    if robert_res:
        db.booking_update(robert_res[0]["id"], status="checked_in")

    # ── Create sample alerts ────────────────────────────────────────────────────

    print("  Creating sample alerts...")
    db.alert_create(
        message="Room 201: Guest requested early departure",
        alert_type="urgent",
        room_id="201",
    )

    # ── Summary ──────────────────────────────────────────────────────────────────

    overview = db.desk_overview()
    print("\n--- Database Seeded ---")
    print(f"Rooms: {overview['total_rooms']} total")
    print(f"  Occupied: {overview['occupied_count']}")
    print(f"  Dirty: {overview['dirty_rooms']}")
    print(f"Arrivals today: {overview['arrivals_today']}")
    print(f"Departures today: {overview['departures_today']}")
    print(f"Unresolved alerts: {overview['unresolved_alerts']}")


if __name__ == "__main__":
    seed_database()
