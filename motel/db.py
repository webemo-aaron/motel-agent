from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


class MotelDB:
    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            import os

            home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
            db_path = str(Path(home) / "motel.db")
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    floor INTEGER DEFAULT 1,
                    type TEXT DEFAULT 'standard',
                    max_occupancy INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'available',
                    current_code TEXT,
                    notes TEXT
                );
                CREATE TABLE IF NOT EXISTS guests (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    source TEXT DEFAULT 'direct',
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY,
                    guest_id TEXT REFERENCES guests(id),
                    room_id TEXT REFERENCES rooms(id),
                    check_in DATE NOT NULL,
                    check_out DATE NOT NULL,
                    status TEXT DEFAULT 'confirmed',
                    party_size INTEGER DEFAULT 1,
                    rate_per_night REAL,
                    total_amount REAL,
                    payment_status TEXT DEFAULT 'pending',
                    special_requests TEXT,
                    door_code TEXT,
                    source TEXT DEFAULT 'direct',
                    external_ref TEXT,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    type TEXT DEFAULT 'urgent',
                    reservation_id TEXT,
                    room_id TEXT,
                    message TEXT NOT NULL,
                    sent_to_telegram INTEGER DEFAULT 0,
                    resolved INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS work_orders (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    location TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'open',
                    description TEXT DEFAULT '',
                    estimated_cost REAL,
                    actual_cost REAL,
                    due_date TEXT,
                    scheduled_date TEXT,
                    vendor TEXT,
                    recurrence TEXT,
                    next_due TEXT,
                    completed_at TEXT,
                    notes TEXT DEFAULT '',
                    room_blocks_occupancy INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def room_list(self, status: Optional[str] = None) -> list[dict]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM rooms WHERE status = ? ORDER BY id", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM rooms ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def room_upsert(self, room_id: str, **fields) -> dict:
        allowed = {
            "name",
            "floor",
            "type",
            "max_occupancy",
            "status",
            "current_code",
            "notes",
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO rooms (id) VALUES (?) ON CONFLICT(id) DO NOTHING",
                (room_id,),
            )
            if data:
                set_clause = ", ".join(f"{k} = ?" for k in data)
                conn.execute(
                    f"UPDATE rooms SET {set_clause} WHERE id = ?",  # noqa: S608
                    (*data.values(), room_id),
                )
            row = conn.execute(
                "SELECT * FROM rooms WHERE id = ?", (room_id,)
            ).fetchone()
        return dict(row)

    def room_update_status(
        self, room_id: str, status: str, notes: Optional[str] = None
    ) -> dict:
        kwargs: dict[str, Any] = {"status": status}
        if notes is not None:
            kwargs["notes"] = notes
        return self.room_upsert(room_id, **kwargs)

    def guest_create(
        self,
        name: str,
        email: str = "",
        phone: str = "",
        source: str = "direct",
        notes: str = "",
    ) -> dict:
        guest_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO guests (id, name, email, phone, source, notes) VALUES (?,?,?,?,?,?)",
                (guest_id, name, email, phone, source, notes),
            )
            row = conn.execute(
                "SELECT * FROM guests WHERE id = ?", (guest_id,)
            ).fetchone()
        return dict(row)

    def booking_create(
        self,
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
        guest = self.guest_create(guest_name, email=email, phone=phone, source=source)
        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        reservation_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reservations
                   (id, guest_id, room_id, check_in, check_out, rate_per_night,
                    total_amount, party_size, special_requests, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    reservation_id,
                    guest["id"],
                    room_id,
                    check_in,
                    check_out,
                    rate_per_night,
                    rate_per_night * nights,
                    party_size,
                    special_requests,
                    source,
                ),
            )
            row = conn.execute(
                "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
        return dict(row)

    def booking_update(self, reservation_id: str, **fields) -> dict:
        allowed = {
            "room_id",
            "check_in",
            "check_out",
            "status",
            "party_size",
            "rate_per_night",
            "total_amount",
            "payment_status",
            "special_requests",
            "door_code",
            "notes",
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            raise ValueError("No valid fields to update")
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in data)
            conn.execute(
                f"UPDATE reservations SET {set_clause} WHERE id = ?",  # noqa: S608
                (*data.values(), reservation_id),
            )
            row = conn.execute(
                "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"Reservation {reservation_id} not found")
        return dict(row)

    def bookings_list(
        self, for_date: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        today = for_date or date.today().isoformat()
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """SELECT r.*, g.name as guest_name, g.email, g.phone
                       FROM reservations r JOIN guests g ON r.guest_id = g.id
                       WHERE r.status = ? ORDER BY r.check_in""",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT r.*, g.name as guest_name, g.email, g.phone
                       FROM reservations r JOIN guests g ON r.guest_id = g.id
                       WHERE r.check_in <= ? AND r.check_out >= ?
                         AND r.status NOT IN ('cancelled', 'checked_out')
                       ORDER BY r.check_in""",
                    (today, today),
                ).fetchall()
        return [dict(r) for r in rows]

    def guest_checkin(self, reservation_id: str) -> dict:
        return self.booking_update(reservation_id, status="checked_in")

    def guest_checkout(self, reservation_id: str) -> dict:
        res = self.booking_update(reservation_id, status="checked_out")
        if res.get("room_id"):
            self.room_update_status(res["room_id"], "dirty")
        return res

    def alert_create(
        self,
        message: str,
        alert_type: str = "urgent",
        reservation_id: Optional[str] = None,
        room_id: Optional[str] = None,
    ) -> dict:
        alert_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO alerts (id, type, reservation_id, room_id, message) VALUES (?,?,?,?,?)",
                (alert_id, alert_type, reservation_id, room_id, message),
            )
            row = conn.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
        return dict(row)

    def alert_resolve(self, alert_id: str) -> dict:
        with self._connect() as conn:
            conn.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))
            row = conn.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"Alert {alert_id} not found")
        return dict(row)

    def work_order_create(
        self,
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
        work_order_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO work_orders
                   (id, title, category, location, priority, description,
                    estimated_cost, due_date, vendor, recurrence, room_blocks_occupancy)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    work_order_id,
                    title,
                    category,
                    location,
                    priority,
                    description,
                    estimated_cost,
                    due_date,
                    vendor,
                    recurrence,
                    1 if room_blocks_occupancy else 0,
                ),
            )
            row = conn.execute(
                "SELECT * FROM work_orders WHERE id = ?", (work_order_id,)
            ).fetchone()
        return dict(row)

    def work_order_list(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        location: Optional[str] = None,
        category: Optional[str] = None,
        overdue_only: bool = False,
    ) -> list[dict]:
        today = date.today().isoformat()
        query = "SELECT * FROM work_orders WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if location:
            query += " AND location = ?"
            params.append(location)
        if category:
            query += " AND category = ?"
            params.append(category)
        if overdue_only:
            query += " AND due_date < ? AND status NOT IN ('completed', 'cancelled')"
            params.append(today)

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        query += " ORDER BY CASE priority"
        for p, idx in priority_order.items():
            query += f" WHEN '{p}' THEN {idx}"
        query += " END, due_date ASC NULLS LAST"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def work_order_update(
        self,
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
        allowed = {"status", "scheduled_date", "vendor", "actual_cost", "priority", "estimated_cost", "due_date"}
        data: dict[str, Any] = {}
        if status is not None and "status" in allowed:
            data["status"] = status
        if scheduled_date is not None and "scheduled_date" in allowed:
            data["scheduled_date"] = scheduled_date
        if vendor is not None and "vendor" in allowed:
            data["vendor"] = vendor
        if actual_cost is not None and "actual_cost" in allowed:
            data["actual_cost"] = actual_cost
        if priority is not None and "priority" in allowed:
            data["priority"] = priority
        if estimated_cost is not None and "estimated_cost" in allowed:
            data["estimated_cost"] = estimated_cost
        if due_date is not None and "due_date" in allowed:
            data["due_date"] = due_date

        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            if data:
                set_clause = ", ".join(f"{k} = ?" for k in data)
                conn.execute(
                    f"UPDATE work_orders SET {set_clause} WHERE id = ?",  # noqa: S608
                    (*data.values(), work_order_id),
                )

            if notes:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                current = conn.execute(
                    "SELECT notes FROM work_orders WHERE id = ?", (work_order_id,)
                ).fetchone()
                current_notes = current[0] if current and current[0] else ""
                new_notes = f"{current_notes}\n[{now}] {notes}" if current_notes else f"[{now}] {notes}"
                conn.execute(
                    "UPDATE work_orders SET notes = ? WHERE id = ?",
                    (new_notes, work_order_id),
                )

            row = conn.execute(
                "SELECT * FROM work_orders WHERE id = ?", (work_order_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"Work order {work_order_id} not found")
        return dict(row)

    def work_order_complete(
        self,
        work_order_id: str,
        notes: Optional[str] = None,
        actual_cost: Optional[float] = None,
    ) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_orders WHERE id = ?", (work_order_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Work order {work_order_id} not found")

            completed_at = datetime.now(timezone.utc).isoformat()
            self.work_order_update(
                work_order_id, status="completed", notes=notes, actual_cost=actual_cost
            )
            conn.execute(
                "UPDATE work_orders SET completed_at = ? WHERE id = ?",
                (completed_at, work_order_id),
            )

            recurrence = row["recurrence"]
            next_work_order_id = None

            if recurrence:
                completed_date = date.fromisoformat(completed_at.split("T")[0])
                if recurrence == "monthly":
                    next_due = (completed_date.replace(day=1) + timedelta(days=32)).replace(day=1)
                elif recurrence == "quarterly":
                    next_due = completed_date + timedelta(days=91)
                elif recurrence == "annually":
                    next_due = completed_date + timedelta(days=365)
                else:
                    next_due = completed_date

                next_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO work_orders
                       (id, title, category, location, priority, description,
                        recurrence, room_blocks_occupancy, due_date, status)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        next_id,
                        row["title"],
                        row["category"],
                        row["location"],
                        row["priority"],
                        row["description"],
                        recurrence,
                        row["room_blocks_occupancy"],
                        next_due.isoformat(),
                        "open",
                    ),
                )
                next_work_order_id = next_id

            completed_row = conn.execute(
                "SELECT * FROM work_orders WHERE id = ?", (work_order_id,)
            ).fetchone()

        return {
            "completed": dict(completed_row),
            "next_work_order_id": next_work_order_id,
        }

    def work_order_summary(self) -> dict:
        today = date.today().isoformat()
        future_week = (date.today() + timedelta(days=7)).isoformat()

        with self._connect() as conn:
            counts_by_status = {
                "open": conn.execute(
                    "SELECT COUNT(*) FROM work_orders WHERE status = 'open'"
                ).fetchone()[0],
                "in_progress": conn.execute(
                    "SELECT COUNT(*) FROM work_orders WHERE status = 'in_progress'"
                ).fetchone()[0],
                "scheduled": conn.execute(
                    "SELECT COUNT(*) FROM work_orders WHERE status = 'scheduled'"
                ).fetchone()[0],
                "completed_this_week": conn.execute(
                    "SELECT COUNT(*) FROM work_orders WHERE status = 'completed' AND completed_at >= ?",
                    (today,),
                ).fetchone()[0],
            }

            counts_by_priority = {}
            for p in ["critical", "high", "medium", "low"]:
                counts_by_priority[p] = conn.execute(
                    "SELECT COUNT(*) FROM work_orders WHERE priority = ? AND status IN ('open', 'in_progress')",
                    (p,),
                ).fetchone()[0]

            overdue_rows = conn.execute(
                "SELECT * FROM work_orders WHERE due_date < ? AND status NOT IN ('completed', 'cancelled') ORDER BY due_date ASC",
                (today,),
            ).fetchall()
            overdue = [dict(r) for r in overdue_rows]

            due_week_rows = conn.execute(
                "SELECT * FROM work_orders WHERE due_date >= ? AND due_date <= ? AND status NOT IN ('completed', 'cancelled') ORDER BY due_date ASC",
                (today, future_week),
            ).fetchall()
            due_week = [dict(r) for r in due_week_rows]

            capital_cost = conn.execute(
                "SELECT COALESCE(SUM(estimated_cost), 0) FROM work_orders WHERE category = 'capital' AND status = 'open'"
            ).fetchone()[0]

        return {
            "counts_by_status": counts_by_status,
            "counts_by_priority": counts_by_priority,
            "overdue": overdue,
            "due_this_week": due_week,
            "capital_estimated_total": round(capital_cost, 2) if capital_cost else 0.0,
        }

    def desk_overview(self) -> dict:
        today = date.today().isoformat()
        with self._connect() as conn:
            total_rooms = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
            occupied = conn.execute(
                "SELECT COUNT(*) FROM rooms WHERE status = 'occupied'"
            ).fetchone()[0]
            dirty = conn.execute(
                "SELECT COUNT(*) FROM rooms WHERE status = 'dirty'"
            ).fetchone()[0]
            arrivals = conn.execute(
                "SELECT COUNT(*) FROM reservations WHERE check_in = ? AND status IN ('confirmed', 'checked_in')",
                (today,),
            ).fetchone()[0]
            departures = conn.execute(
                "SELECT COUNT(*) FROM reservations WHERE check_out = ? AND status = 'checked_in'",
                (today,),
            ).fetchone()[0]
            unresolved = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE resolved = 0"
            ).fetchone()[0]
            open_critical = conn.execute(
                "SELECT COUNT(*) FROM work_orders WHERE status IN ('open', 'in_progress') AND priority = 'critical'"
            ).fetchone()[0]
            overdue = conn.execute(
                "SELECT COUNT(*) FROM work_orders WHERE due_date < ? AND status NOT IN ('completed', 'cancelled')",
                (today,),
            ).fetchone()[0]
        return {
            "date": today,
            "total_rooms": total_rooms,
            "occupied_count": occupied,
            "dirty_rooms": dirty,
            "arrivals_today": arrivals,
            "departures_today": departures,
            "unresolved_alerts": unresolved,
            "open_critical_work_orders": open_critical,
            "overdue_work_orders": overdue,
        }

    def dashboard_stats(self) -> dict:
        overview = self.desk_overview()
        total = overview["total_rooms"]
        occupied = overview["occupied_count"]
        today = date.today().isoformat()
        with self._connect() as conn:
            revenue_today = conn.execute(
                """SELECT COALESCE(SUM(rate_per_night), 0) FROM reservations
                   WHERE check_in <= ? AND check_out > ?
                     AND status IN ('confirmed', 'checked_in')""",
                (today, today),
            ).fetchone()[0]
        return {
            **overview,
            "occupancy_pct": round(occupied / total * 100, 1) if total else 0.0,
            "revenue_today": round(revenue_today, 2),
        }

    def config_get(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def config_set(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO config(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                (key, value),
            )

    def config_all(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
        return {r["key"]: r["value"] for r in rows}
