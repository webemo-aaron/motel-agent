"""
West Bethel Motel REST API — kiosk-facing reads and writes.

Start:  python -m motel.api
"""

from __future__ import annotations

import asyncio
import csv
import json
import hashlib
import base64
import os
import uuid
import requests
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from typing import AsyncGenerator, Optional

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.middleware.cors import CORSMiddleware
    try:
        from sse_starlette.responses import EventSourceResponse
    except ImportError:
        from sse_starlette.sse import EventSourceResponse
except ImportError:
    raise SystemExit(
        "fastapi/uvicorn/sse-starlette not installed. Run: uv pip install fastapi uvicorn sse-starlette"
    )

from pydantic import BaseModel

from motel.db import MotelDB

app = FastAPI(title="West Bethel Motel API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{os.environ.get('MOTEL_KIOSK_PORT', '5182')}",
        f"http://localhost:{os.environ.get('MOTEL_API_PORT', '8653')}",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

_db: Optional[MotelDB] = None
_voice_wake_event = asyncio.Event()
_ADMIN_SESSIONS: dict[str, str] = {}


def get_db() -> MotelDB:
    global _db
    if _db is None:
        _db = MotelDB()
    return _db


@app.get("/api/motel/overview")
def overview():
    return get_db().desk_overview()


@app.get("/api/motel/stats")
def stats():
    return get_db().dashboard_stats()


@app.get("/api/motel/rooms")
def rooms(status: Optional[str] = None):
    return get_db().room_list(status=status)


@app.get("/api/motel/reservations")
def reservations(for_date: Optional[str] = None, status: Optional[str] = None):
    rows = get_db().bookings_list(for_date=for_date, status=status)
    cfg = _load_manager_config()
    return [_decorate_reservation_stay_class(r, cfg) for r in rows]


class CheckinRequest(BaseModel):
    reservation_id: str


class CheckoutRequest(BaseModel):
    reservation_id: str


class RoomStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None


class WorkOrderCreate(BaseModel):
    title: str
    category: str
    location: str
    priority: str = "medium"
    description: str = ""
    estimated_cost: Optional[float] = None
    due_date: Optional[str] = None
    vendor: Optional[str] = None
    recurrence: Optional[str] = None
    room_blocks_occupancy: bool = False


class WorkOrderPatch(BaseModel):
    status: Optional[str] = None
    scheduled_date: Optional[str] = None
    vendor: Optional[str] = None
    actual_cost: Optional[float] = None
    priority: Optional[str] = None
    estimated_cost: Optional[float] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


class TaskRunUpdateBody(BaseModel):
    assignee: str = ""


class VoiceSettingsBody(BaseModel):
    public_host: Optional[str] = None
    hermes_url: Optional[str] = None
    hermes_api_key: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    ifttt_webhook_key: Optional[str] = None
    ifttt_event_name: Optional[str] = None


@app.post("/api/motel/checkin")
def checkin(body: CheckinRequest):
    reservation = _reservation_by_id(body.reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail=f"Reservation {body.reservation_id} not found")

    cfg = _load_manager_config()
    tier = _classify_stay_tier(reservation, cfg)
    if tier in {"medium", "long"}:
        packet = _latest_packets_by_reservation().get(body.reservation_id)
        if not packet or str(packet.get("status", "")).strip() != "signed":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "medium_stay_contract_required",
                    "reservation_id": body.reservation_id,
                    "stay_tier": tier,
                },
            )

    try:
        return get_db().guest_checkin(body.reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/motel/checkout")
def checkout(body: CheckoutRequest):
    try:
        rec = get_db().guest_checkout(body.reservation_id)
        room_id = str(rec.get('room_id', '')) if isinstance(rec, dict) else ''
        task_run = _create_turnover_task_run(room_id or 'unknown', source='checkout')
        return {**(rec if isinstance(rec, dict) else {}), 'task_run': task_run}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.patch("/api/motel/rooms/{room_id}")
def update_room(room_id: str, body: RoomStatusRequest):
    return get_db().room_update_status(room_id, body.status, body.notes)


@app.get("/api/motel/marvin-context")
def marvin_context():
    """Return operational insights from Marvin's decision framework."""
    overview = get_db().desk_overview()
    total = overview.get("total_rooms", 17)
    occupied = overview.get("occupied_count", 0)
    dirty = overview.get("dirty_rooms", 0)
    arrivals = overview.get("arrivals_today", 0)
    alerts = overview.get("unresolved_alerts", 0)

    occupancy_pct = round((occupied / total) * 100) if total > 0 else 0

    insights = []

    # Critical: unresolved alerts
    if alerts > 0:
        insights.append({
            "type": "alert",
            "priority": "critical",
            "message": f"{alerts} unresolved alert{'s' if alerts != 1 else ''}. Check Telegram immediately.",
            "context": {"unresolved_alerts": alerts},
        })

    # High: occupancy strategy
    if occupancy_pct > 80:
        insights.append({
            "type": "recommendation",
            "priority": "high",
            "message": "High occupancy (>80%). Prioritize same-day arrivals for turnover.",
            "context": {"occupancy_pct": occupancy_pct},
        })

    # High: dirty rooms with arrivals
    if dirty > 0 and arrivals > 0:
        insights.append({
            "type": "priority",
            "priority": "high",
            "message": f"{dirty} dirty room{'s' if dirty != 1 else ''} with {arrivals} arrival{'s' if arrivals != 1 else ''} today. Coordinate turnover priority.",
            "context": {"dirty_rooms": dirty, "arrivals": arrivals},
        })

    # Medium: low occupancy
    if occupancy_pct < 35:
        insights.append({
            "type": "recommendation",
            "priority": "medium",
            "message": "Low occupancy (<35%). Consider offering early check-in or upgrades.",
            "context": {"occupancy_pct": occupancy_pct},
        })

    # Medium: many dirty rooms
    if dirty > 5:
        insights.append({
            "type": "recommendation",
            "priority": "medium",
            "message": "Multiple rooms need cleaning. Confirm housekeeping staffing and estimates.",
            "context": {"dirty_rooms": dirty},
        })

    return {
        "insights": insights,
        "overview": overview,
        "timestamp": overview.get("date", ""),
    }


@app.get("/api/motel/manager/strategy")
def manager_strategy():
    """Unified manager portal payload for occupancy growth + event monetization."""
    db = get_db()
    overview = db.desk_overview()
    stats = db.dashboard_stats()
    try:
        work_summary = db.work_order_summary()
    except Exception:
        work_summary = {}

    occupancy = float(stats.get("occupancy_pct", 0.0))
    unresolved_alerts = int(overview.get("unresolved_alerts", 0))
    dirty_rooms = int(overview.get("dirty_rooms", 0))
    arrivals = int(overview.get("arrivals_today", 0))

    if occupancy < 35:
        strategy_phase = "demand_generation"
        strategic_focus = [
            "Push direct-booking offers with 2-night and 3-night incentives",
            "Prioritize contractor and weekday value packages",
            "Launch social proof and partner outreach cadence",
        ]
    elif occupancy <= 70:
        strategy_phase = "conversion_optimization"
        strategic_focus = [
            "Protect ADR with package-based upsells vs discounting",
            "Prioritize family and outdoor weekend bundles",
            "Convert inquiries quickly with 24-hour quote SLA",
        ]
    else:
        strategy_phase = "yield_management"
        strategic_focus = [
            "Hold inventory for late high-yield demand on peak dates",
            "Prioritize event blocks with release dates",
            "Focus operations on turnover speed and review quality",
        ]

    operational_risks = []
    if unresolved_alerts > 0:
        operational_risks.append(
            f"{unresolved_alerts} unresolved alerts require manager follow-up"
        )
    if dirty_rooms > 0 and arrivals > 0:
        operational_risks.append(
            f"{dirty_rooms} dirty rooms with {arrivals} arrivals today — turnover priority risk"
        )

    return {
        "timestamp": overview.get("date"),
        "strategy_phase": strategy_phase,
        "occupancy_pct": occupancy,
        "revenue_today": float(stats.get("revenue_today", 0.0)),
        "strategic_focus": strategic_focus,
        "operational_risks": operational_risks,
        "packages": [
            {
                "name": "Route 2 QuickStop",
                "segment": "Pass-through travelers",
                "pricing_hint": "BAR, 1-night",
            },
            {
                "name": "Bethel Basecamp Weekend",
                "segment": "Leisure weekend guests",
                "pricing_hint": "2-night bundle, 10% package incentive",
            },
            {
                "name": "Crew & Contractor Weekly",
                "segment": "Work crews",
                "pricing_hint": "Pay 6 nights stay 7",
            },
            {
                "name": "Family Kitchen Stay",
                "segment": "Families and long-weekend groups",
                "pricing_hint": "Kitchen access add-on",
            },
            {
                "name": "Ride Bethel (Aventon)",
                "segment": "Outdoor and adventure travelers",
                "pricing_hint": "Add-on: $55 half-day / $85 full-day",
            },
        ],
        "event_products": [
            "Family reunion buyout + shared kitchen scheduling",
            "Wedding overflow block + welcome mixer in house",
            "Micro-retreat (8–25 guests) with workshop setup",
            "Team offsite with lodging + meeting hub",
        ],
        "integration_endpoints": {
            "api": "/api/motel",
            "gateway": "http://localhost:8652",
            "codex": "http://localhost:8654",
            "kiosk": "http://localhost:5182",
        },
        "work_orders": work_summary,
    }


class CampaignPlanBody(BaseModel):
    week: str
    channel: str
    objective: str
    offer: str
    budget: float = 0.0
    owner: str = "manager"
    status: str = "planned"


class EventPlanBody(BaseModel):
    date: str
    title: str
    event_type: str
    expected_guests: int = 0
    room_block: int = 0
    notes: str = ""
    status: str = "planned"


class LeadBody(BaseModel):
    name: str
    segment: str
    contact: str = ""
    source: str = "direct"
    est_value: float = 0.0
    stage: str = "new"
    notes: str = ""


class LeadPatchBody(BaseModel):
    stage: Optional[str] = None
    notes: Optional[str] = None


class EBikeBookingBody(BaseModel):
    guest_name: str
    date: str
    duration: str
    bikes: int = 1
    status: str = "reserved"


class EBikeSettingsBody(BaseModel):
    fleet_size: int = 6
    half_day_rate: float = 55.0
    full_day_rate: float = 85.0


def _read_json_config(key: str, default):
    raw = get_db().config_get(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _write_json_config(key: str, value) -> None:
    get_db().config_set(key, json.dumps(value))


def _inventory_available_on(target_date: str) -> int:
    db = get_db()
    rooms = db.room_list()
    total = len(rooms)
    bookings = db.bookings_list(for_date=target_date, status=None)
    active = [b for b in bookings if b.get("status") in {"confirmed", "checked_in"}]
    return max(total - len(active), 0)


@app.get("/api/motel/manager/plan")
def manager_plan_get():
    campaigns = _read_json_config("manager.campaigns", [])
    events = _read_json_config("manager.events", [])
    leads = _read_json_config("manager.leads", [])
    ebike_settings = _read_json_config(
        "manager.ebike.settings",
        {"fleet_size": 6, "half_day_rate": 55.0, "full_day_rate": 85.0},
    )
    ebike_bookings = _read_json_config("manager.ebike.bookings", [])

    return {
        "campaigns": campaigns,
        "events": events,
        "leads": leads,
        "ebike": {"settings": ebike_settings, "bookings": ebike_bookings},
    }


@app.post("/api/motel/manager/campaigns")
def manager_campaign_create(body: CampaignPlanBody):
    campaigns = _read_json_config("manager.campaigns", [])
    item = {
        "id": f"cmp_{uuid.uuid4().hex[:8]}",
        "week": body.week,
        "channel": body.channel,
        "objective": body.objective,
        "offer": body.offer,
        "budget": body.budget,
        "owner": body.owner,
        "status": body.status,
        "created_at": date.today().isoformat(),
    }
    campaigns.append(item)
    _write_json_config("manager.campaigns", campaigns)
    return item


@app.post("/api/motel/manager/events")
def manager_event_create(body: EventPlanBody):
    events = _read_json_config("manager.events", [])
    available = _inventory_available_on(body.date)
    if body.room_block > available:
        raise HTTPException(status_code=400, detail=f"Room block exceeds available inventory ({available})")
    item = {
        "id": f"evt_{uuid.uuid4().hex[:8]}",
        "date": body.date,
        "title": body.title,
        "event_type": body.event_type,
        "expected_guests": body.expected_guests,
        "room_block": body.room_block,
        "notes": body.notes,
        "status": body.status,
    }
    events.append(item)
    _write_json_config("manager.events", events)
    return item


@app.patch("/api/motel/manager/events/{event_id}")
def manager_event_update(event_id: str, body: EventPlanBody):
    events = _read_json_config("manager.events", [])
    for i, ev in enumerate(events):
        if ev.get("id") == event_id:
            available = _inventory_available_on(body.date)
            if body.room_block > available:
                raise HTTPException(status_code=400, detail=f"Room block exceeds available inventory ({available})")
            events[i] = {
                **ev,
                "date": body.date,
                "title": body.title,
                "event_type": body.event_type,
                "expected_guests": body.expected_guests,
                "room_block": body.room_block,
                "notes": body.notes,
                "status": body.status,
            }
            _write_json_config("manager.events", events)
            return events[i]
    raise HTTPException(status_code=404, detail="Event not found")


@app.post("/api/motel/manager/leads")
def manager_lead_create(body: LeadBody):
    leads = _read_json_config("manager.leads", [])
    item = {
        "id": f"lead_{uuid.uuid4().hex[:8]}",
        "name": body.name,
        "segment": body.segment,
        "contact": body.contact,
        "source": body.source,
        "est_value": body.est_value,
        "stage": body.stage,
        "notes": body.notes,
        "updated_at": date.today().isoformat(),
    }
    leads.append(item)
    _write_json_config("manager.leads", leads)
    return item


@app.patch("/api/motel/manager/leads/{lead_id}")
def manager_lead_update(lead_id: str, body: LeadPatchBody):
    leads = _read_json_config("manager.leads", [])
    history = _read_json_config("manager.lead.history", {})
    for i, lead in enumerate(leads):
        if lead.get("id") == lead_id:
            if body.stage is not None:
                lead["stage"] = body.stage
            if body.notes is not None:
                lead["notes"] = body.notes
            lead["updated_at"] = date.today().isoformat()
            leads[i] = lead
            trail = history.get(lead_id, [])
            trail.append({"date": date.today().isoformat(), "stage": lead.get("stage"), "notes": lead.get("notes", "")})
            history[lead_id] = trail
            _write_json_config("manager.lead.history", history)
            _write_json_config("manager.leads", leads)
            return lead
    raise HTTPException(status_code=404, detail="Lead not found")


@app.get("/api/motel/manager/leads/{lead_id}/history")
def manager_lead_history(lead_id: str):
    history = _read_json_config("manager.lead.history", {})
    return {"lead_id": lead_id, "history": history.get(lead_id, [])}



@app.post("/api/motel/manager/ebike/settings")
def manager_ebike_settings(body: EBikeSettingsBody):
    item = {
        "fleet_size": body.fleet_size,
        "half_day_rate": body.half_day_rate,
        "full_day_rate": body.full_day_rate,
    }
    _write_json_config("manager.ebike.settings", item)
    return item


@app.post("/api/motel/manager/ebike/bookings")
def manager_ebike_booking(body: EBikeBookingBody):
    bookings = _read_json_config("manager.ebike.bookings", [])
    settings = _read_json_config("manager.ebike.settings", {"fleet_size": 6, "half_day_rate": 55.0, "full_day_rate": 85.0})
    fleet = int(settings.get("fleet_size", 6))
    reserved = sum(int(b.get("bikes", 0)) for b in bookings if b.get("date") == body.date and b.get("status") in {"reserved", "checked_out"})
    if reserved + body.bikes > fleet:
        raise HTTPException(status_code=400, detail=f"E-bike overbooked: {reserved}/{fleet} already reserved")
    item = {
        "id": f"bike_{uuid.uuid4().hex[:8]}",
        "guest_name": body.guest_name,
        "date": body.date,
        "duration": body.duration,
        "bikes": body.bikes,
        "status": body.status,
    }
    bookings.append(item)
    _write_json_config("manager.ebike.bookings", bookings)
    return item




@app.get("/api/motel/manager/weekly-briefing")
def manager_weekly_briefing():
    db = get_db()
    overview = db.desk_overview()
    stats = db.dashboard_stats()
    plan = {
        "campaigns": _read_json_config("manager.campaigns", []),
        "events": _read_json_config("manager.events", []),
        "leads": _read_json_config("manager.leads", []),
        "ebike_bookings": _read_json_config("manager.ebike.bookings", []),
    }

    leads = plan["leads"]
    won = len([l for l in leads if l.get("stage") == "won"])
    qualified = len([l for l in leads if l.get("stage") in {"qualified", "proposal"}])

    briefing = (
        f"Manager Briefing — {overview.get('date')}\n"
        f"Occupancy: {stats.get('occupancy_pct', 0)}% ({overview.get('occupied_count')}/{overview.get('total_rooms')} rooms)\n"
        f"Revenue today: ${stats.get('revenue_today', 0):.2f}\n"
        f"Arrivals/Departures: {overview.get('arrivals_today')}/{overview.get('departures_today')}\n"
        f"Dirty rooms: {overview.get('dirty_rooms')}\n"
        f"Unresolved alerts: {overview.get('unresolved_alerts')}\n"
        f"Campaigns planned: {len(plan['campaigns'])}\n"
        f"Events in pipeline: {len(plan['events'])}\n"
        f"Qualified+proposal leads: {qualified} | Won leads: {won}\n"
        f"Aventon bookings queued: {len(plan['ebike_bookings'])}\n"
    )

    actions = []
    if overview.get("unresolved_alerts", 0) > 0:
        actions.append("Resolve unresolved alerts first and clear operator queue.")
    if stats.get("occupancy_pct", 0) < 35:
        actions.append("Push direct-booking and midweek package campaigns today.")
    if overview.get("dirty_rooms", 0) > 0 and overview.get("arrivals_today", 0) > 0:
        actions.append("Prioritize same-day arrival turnover rooms by 3 PM.")
    if not actions:
        actions.append("Maintain current strategy and focus on conversion + reviews.")

    return {"briefing": briefing, "actions": actions}




@app.post("/api/motel/manager/send-weekly-briefing")
def manager_send_weekly_briefing():
    payload = manager_weekly_briefing()
    message = payload["briefing"] + "\nActions:\n- " + "\n- ".join(payload["actions"])
    return get_db().alert_create(message=message, alert_type="urgent")



@app.get("/api/motel/manager/recommendations")
def manager_recommendations():
    stats = get_db().dashboard_stats()
    plan = manager_plan_get()
    recs = []
    if stats.get("occupancy_pct", 0) < 35:
        recs.append({"priority": "high", "item": "Launch 48-hour direct-booking flash for Sun-Thu"})
    if len(plan.get("leads", [])) < 5:
        recs.append({"priority": "high", "item": "Add 10 new group/event leads this week"})
    if len(plan.get("events", [])) == 0:
        recs.append({"priority": "medium", "item": "Publish at least 1 event package for next month"})
    if stats.get("dirty_rooms", 0) > 0 and stats.get("arrivals_today", 0) > 0:
        recs.append({"priority": "high", "item": "Turn over dirty rooms before 3 PM arrivals"})
    if not recs:
        recs.append({"priority": "low", "item": "Maintain current strategy and optimize conversion scripts"})

    funnel = {
        "new": len([l for l in plan.get("leads", []) if l.get("stage") == "new"]),
        "qualified": len([l for l in plan.get("leads", []) if l.get("stage") == "qualified"]),
        "proposal": len([l for l in plan.get("leads", []) if l.get("stage") == "proposal"]),
        "won": len([l for l in plan.get("leads", []) if l.get("stage") == "won"]),
        "lost": len([l for l in plan.get("leads", []) if l.get("stage") == "lost"]),
    }
    return {"recommendations": recs, "funnel": funnel}


@app.patch("/api/motel/manager/ebike/bookings/{booking_id}")
def manager_ebike_booking_update(booking_id: str, body: EBikeBookingBody):
    bookings = _read_json_config("manager.ebike.bookings", [])
    for i, b in enumerate(bookings):
        if b.get("id") == booking_id:
            bookings[i] = {**b, "guest_name": body.guest_name, "date": body.date, "duration": body.duration, "bikes": body.bikes, "status": body.status}
            _write_json_config("manager.ebike.bookings", bookings)
            return bookings[i]
    raise HTTPException(status_code=404, detail="E-bike booking not found")


@app.delete("/api/motel/manager/ebike/bookings/{booking_id}")
def manager_ebike_booking_delete(booking_id: str):
    bookings = _read_json_config("manager.ebike.bookings", [])
    next_bookings = [b for b in bookings if b.get("id") != booking_id]
    if len(next_bookings) == len(bookings):
        raise HTTPException(status_code=404, detail="E-bike booking not found")
    _write_json_config("manager.ebike.bookings", next_bookings)
    return {"deleted": booking_id}




@app.get("/api/motel/manager/export/weekly")
def manager_export_weekly():
    stats = get_db().dashboard_stats()
    overview = get_db().desk_overview()
    plan = manager_plan_get()
    recs = manager_recommendations()
    briefing = manager_weekly_briefing()
    return {
        "snapshot_date": date.today().isoformat(),
        "overview": overview,
        "stats": stats,
        "plan": plan,
        "recommendations": recs,
        "briefing": briefing,
    }


@app.post("/api/motel/manager/recovery-sprint")
def manager_recovery_sprint():
    stats = get_db().dashboard_stats()
    campaigns = _read_json_config("manager.campaigns", [])
    leads = _read_json_config("manager.leads", [])

    created = {"campaigns": [], "leads": []}
    today = date.today().isoformat()

    if stats.get("occupancy_pct", 0) < 35:
        templates = [
            {"week": "Week Now", "channel": "email", "objective": "direct bookings", "offer": "Sun-Thu 2-night basecamp bundle", "budget": 200.0, "owner": "manager", "status": "planned", "created_at": today},
            {"week": "Week Now", "channel": "social", "objective": "last-minute occupancy", "offer": "Route 2 QuickStop + Aventon add-on", "budget": 120.0, "owner": "manager", "status": "planned", "created_at": today},
        ]
        for t in templates:
            t["id"] = f"cmp_{uuid.uuid4().hex[:8]}"
            campaigns.append(t)
            created["campaigns"].append(t)

        lead_templates = [
            {"name": "Sunday River Wedding Planner Outreach", "segment": "wedding", "contact": "", "source": "partner", "est_value": 1800.0, "stage": "new", "notes": "Auto-seeded recovery sprint", "updated_at": today},
            {"name": "Corporate Midweek Retreat Prospect", "segment": "corporate", "contact": "", "source": "direct", "est_value": 2200.0, "stage": "new", "notes": "Auto-seeded recovery sprint", "updated_at": today},
        ]
        for l in lead_templates:
            l["id"] = f"lead_{uuid.uuid4().hex[:8]}"
            leads.append(l)
            created["leads"].append(l)

    _write_json_config("manager.campaigns", campaigns)
    _write_json_config("manager.leads", leads)

    return {"triggered": stats.get("occupancy_pct", 0) < 35, "created": created, "occupancy_pct": stats.get("occupancy_pct", 0)}




class ManagerAutomationSettingsBody(BaseModel):
    auto_recovery_enabled: bool = True
    recovery_threshold_pct: float = 35.0
    auto_briefing_alert_enabled: bool = False
    auto_archive_prune_enabled: bool = True
    audit_export_retention_days: int = 90


@app.get("/api/motel/manager/automation/settings")
def manager_automation_settings_get():
    settings = _read_json_config(
        "manager.automation.settings",
        {
            "auto_recovery_enabled": True,
            "recovery_threshold_pct": 35.0,
            "auto_briefing_alert_enabled": False,
            "auto_archive_prune_enabled": True,
            "audit_export_retention_days": 90,
        },
    )
    return settings


@app.post("/api/motel/manager/automation/settings")
def manager_automation_settings_set(body: ManagerAutomationSettingsBody):
    payload = {
        "auto_recovery_enabled": body.auto_recovery_enabled,
        "recovery_threshold_pct": body.recovery_threshold_pct,
        "auto_briefing_alert_enabled": body.auto_briefing_alert_enabled,
        "auto_archive_prune_enabled": body.auto_archive_prune_enabled,
        "audit_export_retention_days": max(1, min(int(body.audit_export_retention_days), 3650)),
    }
    _write_json_config("manager.automation.settings", payload)
    return payload


@app.post("/api/motel/manager/automation/run-daily")
def manager_automation_run_daily():
    settings = manager_automation_settings_get()
    stats = get_db().dashboard_stats()
    actions = []

    if settings.get("auto_recovery_enabled", True) and stats.get("occupancy_pct", 0) < float(settings.get("recovery_threshold_pct", 35.0)):
        recovery = manager_recovery_sprint()
        actions.append({"type": "recovery_sprint", "result": recovery})

    if settings.get("auto_briefing_alert_enabled", False):
        alert = manager_send_weekly_briefing()
        actions.append({"type": "briefing_alert", "result": alert})

    if settings.get("auto_archive_prune_enabled", True):
        retention_result = _run_audit_retention_job(int(settings.get("audit_export_retention_days", 90)))
        actions.append({"type": "audit_retention", "result": retention_result})

    run = {
        "date": date.today().isoformat(),
        "occupancy_pct": stats.get("occupancy_pct", 0),
        "settings": settings,
        "actions": actions,
    }

    logs = _read_json_config("manager.automation.logs", [])
    logs.append(run)
    _write_json_config("manager.automation.logs", logs[-30:])
    return run


@app.get("/api/motel/manager/automation/logs")
def manager_automation_logs():
    return {"logs": _read_json_config("manager.automation.logs", [])}




DATA_DIR = Path(__file__).resolve().parent / "data"


def _rates_read_json_file(name: str, default):
    p = DATA_DIR / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _rates_read_csv_rows(name: str) -> list[dict]:
    p = DATA_DIR / name
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@app.get("/api/motel/rates/health")
def rates_health():
    payload = _rates_read_json_file("competitor_rate_pipeline_health.json", {})
    if payload:
        return payload
    checks = {
        "snapshot_csv": (DATA_DIR / "competitor_rates_v2_latest.csv").exists(),
        "alerts_csv": (DATA_DIR / "competitor_rate_alerts.csv").exists(),
        "dates_json": (DATA_DIR / "rate_query_dates_2y.json").exists(),
    }
    return {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "healthy": all(checks.values()),
        "checks": checks,
    }


@app.get("/api/motel/rates/snapshot")
def rates_snapshot(limit: int = 100):
    rows = _rates_read_csv_rows("competitor_rates_v2_latest.csv")
    rows = rows[: max(0, min(limit, 500))]
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(rows),
        "items": rows,
    }


@app.get("/api/motel/rates/alerts")
def rates_alerts(limit: int = 100):
    rows = _rates_read_csv_rows("competitor_rate_alerts.csv")
    acked = set(_read_json_config("rates.alerts.acked", []))
    rows = rows[: max(0, min(limit, 500))]
    items = []
    for i, r in enumerate(rows):
        alert_id = r.get("id") or f"alert_{i}_{r.get('property','na')}_{r.get('stay_date','na')}"
        items.append({**r, "id": alert_id, "acknowledged": alert_id in acked})
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(items),
        "items": items,
    }


class RateAlertAckBody(BaseModel):
    alert_id: str


@app.post("/api/motel/rates/alerts/ack")
def rates_alert_ack(body: RateAlertAckBody):
    acked = _read_json_config("rates.alerts.acked", [])
    if body.alert_id not in acked:
        acked.append(body.alert_id)
        _write_json_config("rates.alerts.acked", acked[-500:])
    return {"acknowledged": body.alert_id, "count": len(acked)}




@app.get("/api/motel/rates/calendar")
def rates_calendar():
    raw_days = _rates_read_json_file("rate_query_dates_2y.json", [])
    raw_events = _rates_read_json_file("local_events_bethel_region.json", [])

    if isinstance(raw_days, dict):
        days = raw_days.get("dates", [])
        from_date = raw_days.get("window_start")
        to_date = raw_days.get("window_end")
    else:
        days = raw_days if isinstance(raw_days, list) else []
        from_date = days[0] if days else None
        to_date = days[-1] if days else None

    if isinstance(raw_events, dict):
        local_events = raw_events.get("events", [])
    else:
        local_events = raw_events if isinstance(raw_events, list) else []

    return {
        "from": from_date,
        "to": to_date,
        "days": days,
        "local_events": local_events,
    }



@app.get("/api/motel/rates/competitors")
def rates_competitors(days: int = 30, market: str = "all"):
    days = max(1, min(days, 365))
    today = date.today()

    # Priority sources: API feed -> snapshot CSV
    api_feed = _rates_read_json_file("competitor_api_feed.json", {"items": []})
    feed_items = api_feed.get("items", []) if isinstance(api_feed, dict) else []
    snapshot = _rates_read_csv_rows("competitor_rates_v2_latest.csv")

    merged = []
    for r in feed_items:
        merged.append({**r, "source_type": "api_feed", "confidence": "high"})
    for r in snapshot:
        merged.append({
            "property": r.get("property"),
            "market": r.get("market") or r.get("city") or "Bethel",
            "stay_date": r.get("stay_date") or r.get("check_in"),
            "rate": r.get("rate") or r.get("estimated_rate_usd") or r.get("nightly_rate"),
            "last_seen": r.get("last_seen") or r.get("timestamp"),
            "source_type": "scrape_csv",
            "confidence": "medium",
        })

    by_prop = {}
    for r in merged:
        prop = str(r.get("property") or "Unknown").strip()
        if not prop:
            continue
        mkt = str(r.get("market") or "").strip()
        if market != "all" and mkt != market:
            continue
        sd = str(r.get("stay_date") or "").strip()
        try:
            d = date.fromisoformat(sd[:10])
        except Exception:
            continue
        if d < today or d > (today + timedelta(days=days)):
            continue
        try:
            rate = float(str(r.get("rate")))
        except Exception:
            rate = None

        rec = by_prop.setdefault(prop, {"property": prop, "count": 0, "rates": [], "markets": set(), "last_seen": "", "sources": set(), "confidence": "medium"})
        rec["count"] += 1
        if rate is not None:
            rec["rates"].append(rate)
        if mkt:
            rec["markets"].add(mkt)
        ls = str(r.get("last_seen") or "")
        if ls > rec["last_seen"]:
            rec["last_seen"] = ls
        st = str(r.get("source_type") or "")
        if st:
            rec["sources"].add(st)
        if str(r.get("confidence")) == "high":
            rec["confidence"] = "high"

    items = []
    for rec in by_prop.values():
        rates = sorted(rec["rates"])
        median = rates[len(rates)//2] if rates else None
        items.append({
            "property": rec["property"],
            "count": rec["count"],
            "median_rate": median,
            "min_rate": rates[0] if rates else None,
            "markets": sorted(rec["markets"]),
            "last_seen": rec["last_seen"],
            "sources": sorted(rec["sources"]),
            "confidence": rec["confidence"],
        })
    items.sort(key=lambda x: (-x["count"], x["median_rate"] if x["median_rate"] is not None else 1e9))
    return {"generated_at": datetime.utcnow().isoformat() + "Z", "days": days, "market": market, "count": len(items), "items": items[:20]}

@app.get("/api/motel/rates/summary")
def rates_summary():
    health = rates_health()
    snap = rates_snapshot()
    alerts = rates_alerts()
    return {
        "health": health,
        "snapshot_count": snap.get("count", 0),
        "alerts_count": alerts.get("count", 0),
        "sample_snapshot": snap.get("items", [])[:5],
        "sample_alerts": alerts.get("items", [])[:5],
    }




@app.get("/api/motel/manager/qa-summary")
def manager_qa_summary(hours: int = 24):
    history_path = Path('/tmp/portal_qa_history.jsonl')
    if not history_path.exists():
        return {
            "window_hours": hours,
            "total_runs": 0,
            "pass_count": 0,
            "fail_count": 0,
            "last_run": None,
            "recent_failures": [],
        }

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, hours))
    runs = []
    for line in history_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        ts_raw = item.get("ts")
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace('Z', '+00:00'))
        except Exception:
            continue
        if ts < cutoff:
            continue
        item['_ts'] = ts
        runs.append(item)

    runs.sort(key=lambda r: r['_ts'], reverse=True)
    pass_count = sum(1 for r in runs if r.get('status') == 'pass')
    fail_count = sum(1 for r in runs if r.get('status') == 'fail')
    recent_failures = [
        {
            "ts": r.get('ts'),
            "summary": r.get('summary', ''),
            "log_tail": r.get('log_tail', ''),
        }
        for r in runs if r.get('status') == 'fail'
    ][:5]

    last = runs[0] if runs else None
    return {
        "window_hours": hours,
        "total_runs": len(runs),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "last_run": {
            "ts": last.get('ts'),
            "status": last.get('status'),
            "summary": last.get('summary'),
        } if last else None,
        "recent_failures": recent_failures,
    }



class QaAlertBody(BaseModel):
    message: str


@app.post("/api/motel/manager/qa-alert")
def manager_qa_alert(body: QaAlertBody):
    return get_db().alert_create(message=body.message, alert_type="urgent")



class KioskLookupRequest(BaseModel):
    last_name: str
    arrival_date: str
    phone_last4: Optional[str] = None


class KioskBookRequest(BaseModel):
    guest_name: str
    check_in: str
    check_out: str
    room_id: str
    rate_per_night: float = 0.0
    email: Optional[str] = ""
    phone: Optional[str] = ""
    party_size: int = 1
    stay_class: Optional[str] = None


class OperatorAlertBody(BaseModel):
    message: str
    alert_type: str = "urgent"
    reservation_id: Optional[str] = None
    room_id: Optional[str] = None


class AdminUnlockBody(BaseModel):
    pin: str


def _telegram_send(message: str) -> dict:
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat_id:
        return {"sent": False, "reason": "missing_env"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        ok = resp.status_code == 200 and resp.json().get('ok') is True
        return {"sent": ok, "status_code": resp.status_code, "response": resp.text[:300]}
    except Exception as e:
        return {"sent": False, "reason": str(e)}


@app.post("/api/motel/operator-alert")
def operator_alert(body: OperatorAlertBody):
    rec = get_db().alert_create(
        message=body.message,
        alert_type=body.alert_type,
        reservation_id=body.reservation_id,
        room_id=body.room_id,
    )
    tg = _telegram_send(f"[{body.alert_type.upper()}] {body.message}")
    rec["telegram"] = tg
    return rec


@app.get("/api/motel/integrations/telegram/health")
def telegram_health():
    token = bool(os.environ.get('TELEGRAM_BOT_TOKEN', '').strip())
    chat = bool(os.environ.get('TELEGRAM_CHAT_ID', '').strip())
    return {"configured": token and chat, "has_bot_token": token, "has_chat_id": chat}


@app.post("/api/motel/admin/unlock")
def admin_unlock(body: AdminUnlockBody):
    expected = os.environ.get('MOTEL_ADMIN_PIN', '2468')
    fallback = os.environ.get('MOTEL_KIOSK_TEST_PIN', '2468')
    if body.pin not in {expected, fallback}:
        raise HTTPException(status_code=401, detail='Invalid PIN')
    token = str(uuid.uuid4())
    _ADMIN_SESSIONS[token] = datetime.now(timezone.utc).isoformat()
    return {"token": token, "ok": True}


@app.post("/api/motel/admin/validate")
def admin_validate(body: dict):
    token = str(body.get('token', ''))
    return {"valid": token in _ADMIN_SESSIONS}


@app.get("/api/motel/kiosk/config")
def kiosk_config():
    return {
        "check_in_time": "3:00 PM",
        "check_out_time": "11:00 AM",
        "quiet_hours": "10 PM–8 AM",
        "property": "West Bethel Motel",
        "address": "764 W Bethel Rd, Bethel, ME",
    }


@app.post("/api/motel/kiosk/book")
def kiosk_book(body: KioskBookRequest):
    try:
        cfg = _load_manager_config()
        supplied = _normalize_stay_class(body.stay_class)
        inferred = _classify_stay_tier({"check_in": body.check_in, "check_out": body.check_out}, cfg)
        if supplied and supplied != inferred:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "stay_class_mismatch",
                    "supplied": supplied,
                    "inferred": inferred,
                },
            )
        stay_class = supplied or inferred
        rec = get_db().booking_create(
            guest_name=body.guest_name,
            check_in=body.check_in,
            check_out=body.check_out,
            room_id=body.room_id,
            rate_per_night=body.rate_per_night,
            email=body.email or "",
            phone=body.phone or "",
            source="kiosk",
            party_size=body.party_size,
            special_requests=f"stay_class:{stay_class}",
        )
        rec["stay_class"] = stay_class
        return rec
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unable to create kiosk booking: {e}")


@app.post("/api/motel/kiosk/lookup")
def kiosk_lookup(body: KioskLookupRequest):
    candidates = get_db().bookings_list(for_date=body.arrival_date, status=None)
    ln = body.last_name.strip().lower()
    matches = []
    for r in candidates:
        name = str(r.get('guest_name', ''))
        if not name:
            continue
        if ln not in name.lower().split()[-1]:
            continue
        if body.phone_last4:
            phone = str(r.get('phone') or '')
            if not phone.endswith(body.phone_last4):
                continue
        matches.append({
            "reservation_id": r.get('id'),
            "guest_name": r.get('guest_name'),
            "check_in": r.get('check_in'),
            "check_out": r.get('check_out'),
            "status": r.get('status'),
            "room_id": r.get('room_id'),
        })
    return {"count": len(matches), "matches": matches[:5]}


@app.post("/api/motel/kiosk/room-info")
def kiosk_room_info(body: dict):
    rid = str(body.get('reservation_id', ''))
    if not rid:
        raise HTTPException(status_code=400, detail='reservation_id required')
    today = date.today().isoformat()
    all_rows = get_db().bookings_list(for_date=today, status=None)
    row = next((r for r in all_rows if r.get('id') == rid), None)
    if row is None:
        raise HTTPException(status_code=404, detail='Reservation not found')
    return {
        "reservation_id": row.get('id'),
        "guest_name": row.get('guest_name'),
        "status": row.get('status'),
        "room_id": row.get('room_id'),
        "door_code": row.get('door_code') if row.get('status') == 'checked_in' else None,
        "message": "Welcome!" if row.get('status') == 'checked_in' else "Please check in at desk or contact operator.",
    }


@app.get("/api/motel/work-orders")
def work_orders_list(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    overdue_only: bool = False,
):
    return get_db().work_order_list(
        status=status,
        priority=priority,
        location=location,
        category=category,
        overdue_only=overdue_only,
    )


@app.post("/api/motel/work-orders")
def work_orders_create(body: WorkOrderCreate):
    return get_db().work_order_create(
        title=body.title,
        category=body.category,
        location=body.location,
        priority=body.priority,
        description=body.description,
        estimated_cost=body.estimated_cost,
        due_date=body.due_date,
        vendor=body.vendor,
        recurrence=body.recurrence,
        room_blocks_occupancy=body.room_blocks_occupancy,
    )


@app.patch("/api/motel/work-orders/{work_order_id}")
def work_orders_update(work_order_id: str, body: WorkOrderPatch):
    try:
        return get_db().work_order_update(
            work_order_id,
            status=body.status,
            scheduled_date=body.scheduled_date,
            vendor=body.vendor,
            actual_cost=body.actual_cost,
            priority=body.priority,
            estimated_cost=body.estimated_cost,
            due_date=body.due_date,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/voice/wake")
async def voice_wake() -> EventSourceResponse:
    """
    SSE endpoint for kiosk browser to listen for camera wake triggers.

    IFTTT camera motion → POST /api/voice/trigger
    This endpoint streams "start" event to connected browsers.
    Browser calls SpeechRecognition.start() on receiving "start".
    """
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            while True:
                # Wait for wake event (triggered by IFTTT webhook)
                await _voice_wake_event.wait()
                yield "data: start\n\n"
                _voice_wake_event.clear()

                # Keep-alive: heartbeat every 30s for idle connections
                for _ in range(30):
                    yield "data: heartbeat\n\n"
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    return EventSourceResponse(event_stream())


@app.post("/api/voice/trigger")
async def voice_trigger():
    """
    IFTTT webhook endpoint: camera detects motion, posts here.

    Notifies all connected SSE clients in /api/voice/wake to start listening.
    Returns immediately — async event processing.
    """
    _voice_wake_event.set()
    return {"status": "triggered"}


@app.get("/api/motel/settings/voice")
def voice_settings_get():
    """Retrieve voice configuration, masking sensitive fields."""
    raw = get_db().config_all()
    masked_keys = {"voice.hermes_api_key", "voice.twilio_auth_token", "voice.ifttt_webhook_key"}

    masked = {}
    for k, v in raw.items():
        if k.startswith("voice."):
            if k in masked_keys and v:
                masked[k] = "●●●●" + v[-4:]
            else:
                masked[k] = v
    return masked


@app.post("/api/motel/settings/voice")
def voice_settings_save(body: VoiceSettingsBody):
    """Save voice configuration settings."""
    db = get_db()
    field_map = [
        ("public_host", "voice.public_host"),
        ("hermes_url", "voice.hermes_url"),
        ("hermes_api_key", "voice.hermes_api_key"),
        ("twilio_account_sid", "voice.twilio_account_sid"),
        ("twilio_auth_token", "voice.twilio_auth_token"),
        ("twilio_phone_number", "voice.twilio_phone_number"),
        ("ifttt_webhook_key", "voice.ifttt_webhook_key"),
        ("ifttt_event_name", "voice.ifttt_event_name"),
    ]

    for field, key in field_map:
        val = getattr(body, field)
        if val is not None and not val.startswith("●●●●"):
            db.config_set(key, val)

    return {"status": "saved"}


@app.get("/api/voice/status")
def voice_status():
    """Health check for voice system integration."""
    import httpx

    db = get_db()
    voice_bridge_healthy = False
    public_host = db.config_get("voice.public_host", "")
    twilio_configured = bool(
        db.config_get("voice.twilio_account_sid")
        and db.config_get("voice.twilio_auth_token")
        and db.config_get("voice.twilio_phone_number")
    )

    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get("http://localhost:8655/health")
            voice_bridge_healthy = resp.status_code == 200
    except Exception:
        pass

    return {
        "voice_bridge_healthy": voice_bridge_healthy,
        "public_host": public_host,
        "twilio_configured": twilio_configured,
    }




class RateSimulateRequest(BaseModel):
    room_type: str
    stay_date: str
    occupancy_percent: float
    lead_days: int
    competitor_median_rate: Optional[float] = None
    base_rate: Optional[float] = None
    dow_multiplier: float
    occupancy_multiplier: float
    lead_time_multiplier: float
    guardrail_min_pct: float = 0.85
    guardrail_max_pct: float = 1.60
    winter_package_mode: bool = False


def _motel_data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def _read_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _read_csv_rows(path: Path):
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


@app.get("/api/rates/health")
def rates_health():
    data_dir = _motel_data_dir()
    payload = _read_json_file(
        data_dir / "competitor_rate_pipeline_health.json",
        {
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "healthy": False,
            "checks": {
                "full": {"latest": "", "last_valid": "", "age_hours": 999999, "valid": False, "fresh": False},
                "winter": {"latest": "", "last_valid": "", "age_hours": 999999, "valid": False, "fresh": False},
                "weekend_deep": {"latest": "", "last_valid": "", "age_hours": 999999, "valid": False, "fresh": False},
            },
        },
    )
    return payload


@app.get("/api/rates/snapshot")
def rates_snapshot(market: Optional[str] = None, stay_date: Optional[str] = None, tag: Optional[str] = None):
    rows = _read_csv_rows(_motel_data_dir() / "competitor_rates_v2_latest.csv")
    out = []
    for r in rows:
        tags = [t.strip() for t in (r.get("tags") or "").split("|") if t.strip()]
        rec = {
            "property_name": r.get("property_name") or r.get("property") or "",
            "market": (r.get("market") or "other").lower(),
            "stay_date": r.get("check_in") or r.get("stay_date") or "",
            "tags": tags,
            "min_nights": int(float(r.get("min_nights") or 1)),
            "rate": float(r["rate"]) if r.get("rate") not in (None, "") else None,
            "package_total_estimate": float(r["package_rate_estimate"]) if r.get("package_rate_estimate") not in (None, "") else None,
            "source": r.get("source") or "",
            "confidence": float(r.get("confidence") or 0.0),
            "last_seen": r.get("run_ts") or datetime.utcnow().isoformat() + "Z",
        }
        if market and rec["market"] != market.lower():
            continue
        if stay_date and rec["stay_date"] != stay_date:
            continue
        if tag and tag not in rec["tags"]:
            continue
        out.append(rec)
    return {"generated_at": datetime.utcnow().isoformat() + "Z", "count": len(out), "items": out}


@app.get("/api/rates/alerts")
def rates_alerts(market: Optional[str] = None, min_delta_pct: Optional[float] = None, acknowledged: Optional[bool] = None):
    rows = _read_csv_rows(_motel_data_dir() / "competitor_rate_alerts.csv")
    ack_map = _read_json_file(_motel_data_dir() / "competitor_rate_alert_ack.json", {})
    out = []
    for i, r in enumerate(rows):
        delta = float(r.get("delta_pct") or 0.0)
        mk = (r.get("market") or "other").lower()
        alert_id = r.get("alert_id") or f"alert-{i}"
        ack = bool(ack_map.get(alert_id, {}).get("acknowledged", False))
        item = {
            "id": alert_id,
            "property_name": r.get("property_name") or r.get("property") or "",
            "market": mk,
            "stay_date": r.get("check_in") or r.get("stay_date") or "",
            "tag": r.get("tag") or "",
            "old_rate": float(r.get("old_rate") or 0.0),
            "new_rate": float(r.get("new_rate") or 0.0),
            "delta_pct": delta,
            "detected_at": r.get("detected_at") or datetime.utcnow().isoformat() + "Z",
            "acknowledged": ack,
            "acknowledged_at": ack_map.get(alert_id, {}).get("acknowledged_at"),
        }
        if market and mk != market.lower():
            continue
        if min_delta_pct is not None and abs(delta) < abs(min_delta_pct):
            continue
        if acknowledged is not None and ack != acknowledged:
            continue
        out.append(item)
    return {"generated_at": datetime.utcnow().isoformat() + "Z", "count": len(out), "items": out}


@app.get("/api/rates/calendar")
def rates_calendar(from_date: Optional[str] = None, to_date: Optional[str] = None):
    payload = _read_json_file(_motel_data_dir() / "rate_query_dates_2y.json", {"dates": []})
    dates = payload.get("dates", []) if isinstance(payload, dict) else payload
    events = _read_json_file(_motel_data_dir() / "local_events_bethel_region.json", [])
    event_map = {}
    if isinstance(events, list):
        for e in events:
            d = e.get("date")
            if d:
                event_map[d] = e.get("name")
    out = []
    for d in dates:
        date_str = d.get("date") if isinstance(d, dict) else str(d)
        tags = d.get("tags", []) if isinstance(d, dict) else []
        if from_date and date_str < from_date:
            continue
        if to_date and date_str > to_date:
            continue
        out.append({"date": date_str, "tags": tags, "event_name": event_map.get(date_str), "priority_score": float(d.get("priority", 0.0)) if isinstance(d, dict) else 0.0})
    return {"from": from_date or (out[0]["date"] if out else ""), "to": to_date or (out[-1]["date"] if out else ""), "days": out}


@app.post("/api/rates/alerts/{alert_id}/ack")
def rates_ack(alert_id: str):
    path = _motel_data_dir() / "competitor_rate_alert_ack.json"
    current = _read_json_file(path, {})
    current[alert_id] = {
        "acknowledged": True,
        "acknowledged_at": datetime.utcnow().isoformat() + "Z",
    }
    path.write_text(json.dumps(current, indent=2))
    return {"id": alert_id, "acknowledged": True, "acknowledged_at": current[alert_id]["acknowledged_at"]}


@app.post("/api/rates/simulate")
def rates_simulate(req: RateSimulateRequest):
    base = req.base_rate or req.competitor_median_rate or 100.0
    raw = base * req.dow_multiplier * req.occupancy_multiplier * req.lead_time_multiplier
    min_rate = max(base * req.guardrail_min_pct, 0)
    max_rate = base * req.guardrail_max_pct
    rec = min(max(raw, min_rate), max_rate)
    # round to nearest $5
    rec = round(rec / 5.0) * 5.0
    min_rate = round(min_rate / 5.0) * 5.0
    max_rate = round(max_rate / 5.0) * 5.0
    package_total = rec * 2 if req.winter_package_mode else None
    rationale = [
        f"base={base}",
        f"dow_multiplier={req.dow_multiplier}",
        f"occupancy_multiplier={req.occupancy_multiplier}",
        f"lead_time_multiplier={req.lead_time_multiplier}",
        f"guardrails={req.guardrail_min_pct:.2f}-{req.guardrail_max_pct:.2f}",
    ]
    if req.competitor_median_rate is not None:
        rationale.append(f"competitor_median_rate={req.competitor_median_rate}")
    return {
        "recommended_rate": rec,
        "min_rate": min_rate,
        "max_rate": max_rate,
        "package_total_estimate": package_total,
        "rationale": rationale,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("MOTEL_API_PORT", "8653"))
    uvicorn.run("motel.api:app", host="0.0.0.0", port=port, reload=False)  # noqa: S104


# --- Manager configuration endpoints (rooms, locks, housekeeping) ---
from typing import Any, Dict



def _task_runs_path() -> Path:
    return DATA_DIR / "housekeeping_task_runs.jsonl"


def _read_task_runs() -> list[dict]:
    p = _task_runs_path()
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding='utf-8').splitlines():
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def _write_task_runs(items: list[dict]) -> None:
    _task_runs_path().write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + ("\n" if items else ""), encoding='utf-8')


def _create_turnover_task_run(room_id: str, source: str = 'checkout') -> dict:
    task_id = f"tr_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    rec = {
        'task_run_id': task_id,
        'room_id': str(room_id),
        'status': 'open',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'started_at': None,
        'completed_at': None,
        'assignee': '',
        'source': source,
    }
    items = _read_task_runs()
    items.append(rec)
    _write_task_runs(items)
    return rec

def _manager_config_path() -> Path:
    return DATA_DIR / "manager_control_config.json"

def _default_manager_config() -> Dict[str, Any]:
    return {
        "rooms": {},
        "door_locks": {
            "provider": "manual",
            "code_rotation_policy": "on_checkout",
            "default_code_length": 4,
            "rooms": {}
        },
        "housekeeping": {
            "default_turnover_minutes": 40,
            "deep_clean_minutes": 70,
            "prioritize_same_day_arrivals": True,
            "checklist": ["Linens replaced", "Bathroom sanitized", "Amenities restocked", "Door code verified"]
        },
        "medium_stay": {
            "enabled": True,
            "tiers": {
                "short": {
                    "min_nights": 1,
                    "max_nights": 6,
                    "notice_period_days": 0,
                    "housekeeping_interval_days": 0,
                    "deposit_required": False,
                    "billing_cycle": "per_stay"
                },
                "medium": {
                    "min_nights": 7,
                    "max_nights": 27,
                    "notice_period_days": 7,
                    "housekeeping_interval_days": 7,
                    "deposit_required": True,
                    "billing_cycle": "weekly"
                },
                "long": {
                    "min_nights": 28,
                    "max_nights": 180,
                    "notice_period_days": 14,
                    "housekeeping_interval_days": 7,
                    "deposit_required": True,
                    "billing_cycle": "monthly"
                }
            },
            "protected_inventory_weekend_pct": 30,
            "extension_conflict_threshold": 70
        }
    }

def _load_manager_config() -> Dict[str, Any]:
    p = _manager_config_path()
    if not p.exists():
        cfg = _default_manager_config()
        p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    base = _default_manager_config()
    base.update(raw if isinstance(raw, dict) else {})
    return base

def _save_manager_config(cfg: Dict[str, Any]) -> None:
    _manager_config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _manager_config_revision(cfg: Dict[str, Any]) -> str:
    payload = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()



def _manager_versions_dir() -> Path:
    d = DATA_DIR / "manager_config_versions"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _manager_versions_index_path() -> Path:
    return DATA_DIR / "manager_config_versions.jsonl"

def _record_manager_config_version(actor: str, action: str, config: Dict[str, Any], metadata: dict | None = None) -> str:
    version_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    _manager_versions_dir().joinpath(f"{version_id}.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    entry = {
        "version_id": version_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "metadata": metadata or {},
        "snapshot_file": f"manager_config_versions/{version_id}.json",
    }
    with _manager_versions_index_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return version_id

def _read_manager_config_version(version_id: str) -> Dict[str, Any]:
    p = _manager_versions_dir().joinpath(f"{version_id}.json")
    if not p.exists():
        raise HTTPException(status_code=404, detail="manager_config_version_not_found")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"manager_config_version_corrupt: {e}")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=500, detail="manager_config_version_invalid")
    return raw



def _manager_rollback_checkpoints_dir() -> Path:
    d = DATA_DIR / "manager_rollback_checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manager_rollback_checkpoints_index_path() -> Path:
    return DATA_DIR / "manager_rollback_checkpoints.jsonl"


def _record_rollback_checkpoint(actor: str, config: Dict[str, Any], reason: str, restored_from: str) -> str:
    checkpoint_id = datetime.now(timezone.utc).strftime("ckpt_%Y%m%dT%H%M%S%fZ")
    _manager_rollback_checkpoints_dir().joinpath(f"{checkpoint_id}.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    rec = {
        "checkpoint_id": checkpoint_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "reason": reason,
        "restored_from": restored_from,
        "snapshot_file": f"manager_rollback_checkpoints/{checkpoint_id}.json",
    }
    with _manager_rollback_checkpoints_index_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return checkpoint_id


def _read_rollback_checkpoint(checkpoint_id: str) -> Dict[str, Any]:
    p = _manager_rollback_checkpoints_dir().joinpath(f"{checkpoint_id}.json")
    if not p.exists():
        raise HTTPException(status_code=404, detail="rollback_checkpoint_not_found")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rollback_checkpoint_corrupt: {e}")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=500, detail="rollback_checkpoint_invalid")
    return raw

def _manager_audit_log_path() -> Path:
    return DATA_DIR / "manager_audit_log.jsonl"


def _medium_stay_templates_path() -> Path:
    return DATA_DIR / "medium_stay_legal_templates.jsonl"


def _append_medium_stay_template_record(rec: Dict[str, Any]) -> None:
    p = _medium_stay_templates_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _list_medium_stay_templates() -> list[Dict[str, Any]]:
    p = _medium_stay_templates_path()
    if not p.exists():
        return []
    items: list[Dict[str, Any]] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            items.append(obj)
    return items


def _latest_template_versions() -> dict[str, Dict[str, Any]]:
    latest: dict[str, Dict[str, Any]] = {}
    for item in _list_medium_stay_templates():
        tid = str(item.get("template_id", "")).strip()
        if not tid:
            continue
        prev = latest.get(tid)
        if prev is None or str(item.get("ts", "")) >= str(prev.get("ts", "")):
            latest[tid] = item
    return latest


def _medium_stay_packets_path() -> Path:
    return DATA_DIR / "medium_stay_contract_packets.jsonl"


def _append_medium_stay_packet_record(rec: Dict[str, Any]) -> None:
    p = _medium_stay_packets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _list_medium_stay_packets() -> list[Dict[str, Any]]:
    p = _medium_stay_packets_path()
    if not p.exists():
        return []
    items: list[Dict[str, Any]] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            items.append(obj)
    return items


def _latest_packets_by_reservation() -> dict[str, Dict[str, Any]]:
    latest: dict[str, Dict[str, Any]] = {}
    for item in _list_medium_stay_packets():
        rid = str(item.get("reservation_id", "")).strip()
        if not rid:
            continue
        prev = latest.get(rid)
        if prev is None or str(item.get("ts", "")) >= str(prev.get("ts", "")):
            latest[rid] = item
    return latest


def _reservation_by_id(reservation_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        with db._connect() as conn:  # internal helper; used for manager-control policy checks
            row = conn.execute(
                """SELECT r.*, g.name as guest_name, g.email, g.phone
                   FROM reservations r JOIN guests g ON r.guest_id = g.id
                   WHERE r.id = ?""",
                (reservation_id,),
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _normalize_stay_class(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s not in {"short", "medium", "long"}:
        raise HTTPException(status_code=400, detail="stay_class must be one of: short, medium, long")
    return s


def _serialize_stay_class(reservation: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    explicit = _normalize_stay_class(reservation.get("stay_class"))
    if explicit:
        return explicit
    # backward-compatible parse from special_requests marker
    sr = str(reservation.get("special_requests") or "")
    for token in sr.split(";"):
        token = token.strip()
        if token.startswith("stay_class:"):
            parsed = _normalize_stay_class(token.split(":", 1)[1])
            if parsed:
                return parsed
    return _classify_stay_tier(reservation, cfg)


def _decorate_reservation_stay_class(row: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["stay_class"] = _serialize_stay_class(out, cfg)
    return out


def _classify_stay_tier(reservation: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    check_in = str(reservation.get("check_in", "")).strip()
    check_out = str(reservation.get("check_out", "")).strip()
    try:
        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    except Exception:
        nights = 1
    tiers = ((cfg.get("medium_stay") or {}).get("tiers") or {}) if isinstance(cfg, dict) else {}
    for name in ("short", "medium", "long"):
        t = tiers.get(name) if isinstance(tiers, dict) else None
        if not isinstance(t, dict):
            continue
        try:
            mn = int(t.get("min_nights"))
            mx = int(t.get("max_nights"))
        except Exception:
            continue
        if mn <= nights <= mx:
            return name
    if nights >= 28:
        return "long"
    if nights >= 7:
        return "medium"
    return "short"

def _canonical_audit_payload(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _audit_entry_hash(rec_wo_hash: dict) -> str:
    return hashlib.sha256(_canonical_audit_payload(rec_wo_hash).encode("utf-8")).hexdigest()

def _last_audit_hash() -> str:
    p = _manager_audit_log_path()
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding='utf-8').splitlines()
    except Exception:
        return ""
    for ln in reversed(lines):
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        h = str(obj.get('hash', '')).strip()
        if h:
            return h
    return ""



def _manager_audit_exports_dir() -> Path:
    d = DATA_DIR / "manager_audit_exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manager_audit_exports_index_path() -> Path:
    return _manager_audit_exports_dir() / "exports_index.jsonl"


def _append_audit_export_index(entry: dict) -> None:
    with _manager_audit_exports_index_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_audit_export_index(limit: int = 200) -> list[dict]:
    p = _manager_audit_exports_index_path()
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 5000)):]
    out: list[dict] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    out.reverse()
    return out




def _manager_audit_archive_dir() -> Path:
    d = _manager_audit_exports_dir() / "archive"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_audit_retention_job(retention_days: int) -> dict:
    retention_days = max(1, min(int(retention_days), 3650))
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    items = _read_audit_export_index(limit=5000)
    archived = []
    kept = []
    arch_dir = _manager_audit_archive_dir()

    for it in items:
        ts = str(it.get('exported_at', '')).strip()
        export_id = str(it.get('export_id', '')).strip()
        try:
            when = datetime.fromisoformat(ts.replace('Z', '+00:00')) if ts else None
        except Exception:
            when = None
        if when and when < cutoff and export_id:
            for suffix in ('.manifest.json', '.jsonl'):
                src = _manager_audit_exports_dir() / f"{export_id}{suffix}"
                dst = arch_dir / src.name
                if src.exists() and not dst.exists():
                    src.replace(dst)
            updated = dict(it)
            updated['status'] = 'archived'
            updated['archived_at'] = datetime.now(timezone.utc).isoformat()
            updated['manifest_path'] = str(arch_dir / f"{export_id}.manifest.json")
            updated['audit_path'] = str(arch_dir / f"{export_id}.jsonl")
            archived.append(updated)
        else:
            kept.append(it)

    # rebuild index with archived+kept newest first preserved by read helper
    rebuilt = archived + kept
    idx = _manager_audit_exports_index_path()
    idx.write_text('', encoding='utf-8')
    for rec in reversed(rebuilt):
        _append_audit_export_index(rec)

    return {
        'retention_days': retention_days,
        'cutoff': cutoff.isoformat(),
        'archived_count': len(archived),
        'kept_count': len(kept),
    }

def _resolve_export_artifact(export_id: str, artifact: str) -> Path:
    base = _manager_audit_exports_dir()
    if artifact == "manifest":
        p = base / f"{export_id}.manifest.json"
    elif artifact == "audit":
        p = base / f"{export_id}.jsonl"
    else:
        raise HTTPException(status_code=400, detail="invalid_artifact")
    if not p.exists():
        ap = _manager_audit_archive_dir() / p.name
        if ap.exists():
            return ap
        raise HTTPException(status_code=404, detail="export_artifact_not_found")
    return p

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def _signed_manifest_blob(manifest: dict) -> str:
    secret = os.getenv('MOTEL_AUDIT_EXPORT_SECRET', '').strip() or os.getenv('MOTEL_MANAGER_WRITE_TOKEN', '').strip() or 'west-bethel-default-secret'
    payload = _canonical_audit_payload(manifest)
    sig = hashlib.sha256((secret + '|' + payload).encode('utf-8')).hexdigest()
    return sig

def _verify_audit_chain(limit: int = 1000) -> dict:
    p = _manager_audit_log_path()
    legacy_warn_threshold = 1
    if not p.exists():
        return {
            "ok": True,
            "status": "ok",
            "checked": 0,
            "legacy_count": 0,
            "broken_at": None,
            "errors": [],
            "line_details": [],
            "summary": {"legacy_warning": False, "chain_broken": False},
        }

    lines = p.read_text(encoding='utf-8').splitlines()[-max(1, min(limit, 50000)):]
    prev_hash = ""
    checked = 0
    legacy_count = 0
    errors: list[str] = []
    broken_at = None
    line_details: list[dict[str, Any]] = []

    for idx, ln in enumerate(lines):
        try:
            rec = json.loads(ln)
        except Exception:
            legacy_count += 1
            line_details.append({"line_offset": idx, "state": "legacy_non_json"})
            continue

        cur_hash = str(rec.get('hash', '')).strip()
        cur_prev = str(rec.get('prev_hash', '')).strip()
        if not cur_hash:
            legacy_count += 1
            line_details.append({"line_offset": idx, "state": "legacy_missing_hash"})
            continue

        core = {k: v for k, v in rec.items() if k != 'hash'}
        exp_hash = _audit_entry_hash(core)
        if cur_hash != exp_hash:
            errors.append(f"hash_mismatch at line_offset={idx}: expected={exp_hash} got={cur_hash}")
            line_details.append({"line_offset": idx, "state": "hash_mismatch", "expected_hash": exp_hash, "actual_hash": cur_hash})
            broken_at = idx
            break
        if cur_prev != prev_hash:
            errors.append(f"prev_hash_mismatch at line_offset={idx}: expected={prev_hash} got={cur_prev}")
            line_details.append({"line_offset": idx, "state": "prev_hash_mismatch", "expected_prev_hash": prev_hash, "actual_prev_hash": cur_prev})
            broken_at = idx
            break

        prev_hash = cur_hash
        checked += 1
        line_details.append({"line_offset": idx, "state": "verified", "hash": cur_hash})

    chain_broken = len(errors) > 0
    legacy_warning = legacy_count >= legacy_warn_threshold
    status = "broken_chain" if chain_broken else ("legacy_only" if legacy_warning else "ok")

    return {
        "ok": not chain_broken,
        "status": status,
        "checked": checked,
        "legacy_count": legacy_count,
        "broken_at": broken_at,
        "errors": errors,
        "line_details": line_details,
        "summary": {
            "legacy_warning": legacy_warning,
            "legacy_warn_threshold": legacy_warn_threshold,
            "chain_broken": chain_broken,
            "total_lines": len(lines),
            "verified_lines": checked,
        },
        "last_hash": prev_hash,
    }

def _append_manager_audit(action: str, actor: str, before: Any = None, after: Any = None, metadata: dict | None = None) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor,
        "metadata": metadata or {},
        "before": before,
        "after": after,
    }
    rec["prev_hash"] = _last_audit_hash()
    rec["hash"] = _audit_entry_hash({k: v for k, v in rec.items() if k != "hash"})
    with _manager_audit_log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def _is_production_mode() -> bool:
    mode = os.getenv("MOTEL_ENV", "").strip().lower() or os.getenv("ENV", "").strip().lower()
    return mode in {"prod", "production"}


def _resolve_authenticated_actor(request: Request) -> str:
    """Resolve actor identity from trusted server-side auth headers/context.

    Priority is intentionally server-auth headers first. In production mode, client-supplied
    x-manager-actor is rejected to prevent spoofing.
    """
    for key in ("x-authenticated-user", "x-forwarded-user", "x-remote-user"):
        v = (request.headers.get(key, "") or "").strip()
        if v:
            return v

    legacy_actor = (request.headers.get("x-manager-actor", "") or "").strip()
    if legacy_actor:
        if _is_production_mode():
            raise HTTPException(status_code=403, detail="manager_actor_header_forbidden_in_production")
        return legacy_actor

    if _is_production_mode():
        raise HTTPException(status_code=403, detail="manager_authenticated_actor_required")
    return "unknown"




def _resolve_manager_role(request: Request) -> str:
    """Resolve role from trusted auth headers. Legacy x-manager-role allowed only outside production."""
    allowed = {"viewer", "frontdesk", "manager", "admin"}
    role = (request.headers.get("x-authenticated-role", "") or "").strip().lower()
    if role in allowed:
        return role
    legacy = (request.headers.get("x-manager-role", "") or "").strip().lower()
    if legacy:
        if _is_production_mode():
            raise HTTPException(status_code=403, detail="manager_role_header_forbidden_in_production")
        if legacy in allowed:
            return legacy
    return "admin" if not _is_production_mode() else "viewer"


def _require_manager_role(request: Request, allowed_roles: set[str]) -> str:
    role = _resolve_manager_role(request)
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="manager_role_forbidden")
    return role

def _require_manager_write(request: Request) -> str:
    required = os.getenv("MOTEL_MANAGER_WRITE_TOKEN", "").strip()
    actor = _resolve_authenticated_actor(request)
    if not required:
        return actor
    supplied = request.headers.get("x-manager-token", "")
    if supplied != required:
        raise HTTPException(status_code=403, detail="manager_write_forbidden")
    return actor

def _validate_manager_config(cfg: Dict[str, Any]) -> list[str]:
    errs: list[str] = []
    room_types = {"SQ", "DF", "DQ", "H1", "H2"}
    rooms = cfg.get("rooms", {}) if isinstance(cfg, dict) else {}
    if isinstance(rooms, dict):
        for room_id, meta in rooms.items():
            if not isinstance(meta, dict):
                continue
            rt = str(meta.get("room_type", "")).strip()
            if rt and rt not in room_types:
                errs.append(f"rooms.{room_id}.room_type must be one of {sorted(room_types)}")
            occ = meta.get("max_occupancy")
            if occ is not None:
                try:
                    occ_i = int(occ)
                    if occ_i < 1 or occ_i > 12:
                        errs.append(f"rooms.{room_id}.max_occupancy must be between 1 and 12")
                except Exception:
                    errs.append(f"rooms.{room_id}.max_occupancy must be an integer")
    dl = cfg.get("door_locks", {}) if isinstance(cfg, dict) else {}
    if isinstance(dl, dict):
        if dl.get("code_rotation_policy") not in {"on_checkout", "daily", "weekly", "manual_only", None, ""}:
            errs.append("door_locks.code_rotation_policy invalid")
        dcl = dl.get("default_code_length")
        if dcl is not None:
            try:
                n = int(dcl)
                if n < 4 or n > 10:
                    errs.append("door_locks.default_code_length must be 4-10")
            except Exception:
                errs.append("door_locks.default_code_length must be integer")
    hk = cfg.get("housekeeping", {}) if isinstance(cfg, dict) else {}
    if isinstance(hk, dict):
        for k in ("default_turnover_minutes", "deep_clean_minutes"):
            v = hk.get(k)
            if v is not None:
                try:
                    iv = int(v)
                    if iv < 5 or iv > 300:
                        errs.append(f"housekeeping.{k} must be 5-300")
                except Exception:
                    errs.append(f"housekeeping.{k} must be integer")

    ms = cfg.get("medium_stay", {}) if isinstance(cfg, dict) else {}
    if isinstance(ms, dict):
        tiers = ms.get("tiers", {})
        required_tiers = ["short", "medium", "long"]
        if not isinstance(tiers, dict):
            errs.append("medium_stay.tiers must be an object")
        else:
            for tier_name in required_tiers:
                tier = tiers.get(tier_name)
                if not isinstance(tier, dict):
                    errs.append(f"medium_stay.tiers.{tier_name} must be an object")
                    continue
                for key in ("min_nights", "max_nights", "notice_period_days", "housekeeping_interval_days"):
                    try:
                        value = int(tier.get(key))
                    except Exception:
                        errs.append(f"medium_stay.tiers.{tier_name}.{key} must be integer")
                        continue
                    if value < 0:
                        errs.append(f"medium_stay.tiers.{tier_name}.{key} must be >= 0")
                try:
                    min_n = int(tier.get("min_nights"))
                    max_n = int(tier.get("max_nights"))
                    if min_n > max_n:
                        errs.append(f"medium_stay.tiers.{tier_name}.min_nights must be <= max_nights")
                except Exception:
                    pass
                billing_cycle = str(tier.get("billing_cycle", "")).strip()
                if billing_cycle not in {"per_stay", "weekly", "biweekly", "monthly"}:
                    errs.append(f"medium_stay.tiers.{tier_name}.billing_cycle invalid")
                if not isinstance(tier.get("deposit_required"), bool):
                    errs.append(f"medium_stay.tiers.{tier_name}.deposit_required must be boolean")

            try:
                short_max = int(tiers.get("short", {}).get("max_nights"))
                medium_min = int(tiers.get("medium", {}).get("min_nights"))
                medium_max = int(tiers.get("medium", {}).get("max_nights"))
                long_min = int(tiers.get("long", {}).get("min_nights"))
                if short_max >= medium_min:
                    errs.append("medium_stay tier ranges overlap between short and medium")
                if medium_max >= long_min:
                    errs.append("medium_stay tier ranges overlap between medium and long")
            except Exception:
                pass

        for key in ("protected_inventory_weekend_pct", "extension_conflict_threshold"):
            val = ms.get(key)
            if val is not None:
                try:
                    iv = int(val)
                    if iv < 0 or iv > 100:
                        errs.append(f"medium_stay.{key} must be 0-100")
                except Exception:
                    errs.append(f"medium_stay.{key} must be integer")
    return errs

@app.get('/api/motel/manager/config')
def get_manager_config(request: Request):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    cfg = _load_manager_config()
    revision_id = _manager_config_revision(cfg)
    return JSONResponse(
        content={"config": cfg, "revision_id": revision_id},
        headers={"ETag": f'"{revision_id}"'},
    )

@app.post('/api/motel/manager/config')
def save_manager_config(payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    supplied_revision = str((payload or {}).get('revision_id', '')).strip() or str(request.headers.get('if-match', '')).strip().strip('\"')
    before = _load_manager_config()
    current_revision = _manager_config_revision(before)
    if not supplied_revision:
        raise HTTPException(status_code=409, detail={"code": "revision_required", "current_revision": current_revision})
    if supplied_revision != current_revision:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict", "current_revision": current_revision})
    cfg = _load_manager_config()
    if isinstance(payload, dict):
        payload = dict(payload)
        payload.pop('revision_id', None)
        cfg.update(payload)
    errs = _validate_manager_config(cfg)
    if errs:
        raise HTTPException(status_code=422, detail={"code": "invalid_manager_config", "errors": errs})
    _save_manager_config(cfg)
    version_id = _record_manager_config_version(actor=actor, action='manager_config_save', config=cfg)
    _append_manager_audit('manager_config_save', actor=actor, before=before, after=cfg, metadata={'version_id': version_id})
    next_revision = _manager_config_revision(cfg)
    return {"ok": True, "config": cfg, "version_id": version_id, "revision_id": next_revision}

@app.post('/api/motel/manager/config/door-locks/rotate')
def rotate_door_lock_code(payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    room_id = str(payload.get('room_id', '')).strip()
    if not room_id:
        raise HTTPException(status_code=400, detail='room_id is required')
    cfg = _load_manager_config()
    locks = cfg.setdefault('door_locks', {}).setdefault('rooms', {})
    item = locks.setdefault(room_id, {})
    item['last_rotated_at'] = datetime.now(timezone.utc).isoformat()
    item['rotation_note'] = str(payload.get('note', 'Code rotated by manager')).strip()
    _save_manager_config(cfg)
    version_id = _record_manager_config_version(actor=actor, action='door_lock_rotate', config=cfg, metadata={'room_id': room_id})
    _append_manager_audit('door_lock_rotate', actor=actor, metadata={'room_id': room_id, 'note': item.get('rotation_note'), 'version_id': version_id})
    return {"ok": True, "room_id": room_id, "lock": item, "version_id": version_id}


@app.get('/api/motel/manager/medium-stay/packets')
def list_medium_stay_packets(request: Request, reservation_id: Optional[str] = None, status: Optional[str] = None):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    packets = list(_latest_packets_by_reservation().values())
    out = []
    for p in packets:
        if reservation_id and str(p.get('reservation_id')) != str(reservation_id):
            continue
        if status and str(p.get('status')) != str(status):
            continue
        out.append(p)
    out.sort(key=lambda x: str(x.get('ts', '')), reverse=True)
    return {'items': out}


@app.post('/api/motel/manager/medium-stay/packets/generate')
def generate_medium_stay_packet(payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    reservation_id = str((payload or {}).get('reservation_id', '')).strip()
    if not reservation_id:
        raise HTTPException(status_code=400, detail='reservation_id is required')

    reservation = _reservation_by_id(reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail='reservation_not_found')

    cfg = _load_manager_config()
    tier = _classify_stay_tier(reservation, cfg)
    if tier not in {'medium', 'long'}:
        raise HTTPException(status_code=400, detail='packet_required_only_for_medium_or_long_stays')

    templates = list(_latest_template_versions().values())
    jurisdiction = str((payload or {}).get('jurisdiction', 'ME')).strip().upper() or 'ME'
    active_templates = [
        t for t in templates
        if str(t.get('jurisdiction', '')).upper() == jurisdiction and str(t.get('status', '')) == 'active'
    ]
    if not active_templates:
        raise HTTPException(status_code=422, detail='no_active_templates_for_jurisdiction')

    packet_id = str(uuid.uuid4())
    rec = {
        'packet_id': packet_id,
        'reservation_id': reservation_id,
        'guest_name': reservation.get('guest_name'),
        'stay_tier': tier,
        'jurisdiction': jurisdiction,
        'template_refs': [
            {
                'template_id': t.get('template_id'),
                'name': t.get('name'),
                'version': t.get('version'),
                'effective_date': t.get('effective_date'),
            }
            for t in active_templates
        ],
        'status': 'pending',
        'created_by': actor,
        'ts': datetime.now(timezone.utc).isoformat(),
    }
    _append_medium_stay_packet_record(rec)
    _append_manager_audit('medium_stay_packet_generate', actor=actor, metadata={'packet_id': packet_id, 'reservation_id': reservation_id, 'stay_tier': tier, 'jurisdiction': jurisdiction})
    return {'ok': True, 'packet': rec}


@app.post('/api/motel/manager/medium-stay/packets/{packet_id}/sign')
def sign_medium_stay_packet(packet_id: str, payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    latest_by_res = _latest_packets_by_reservation()
    found = None
    for item in latest_by_res.values():
        if str(item.get('packet_id')) == packet_id:
            found = item
            break
    if not found:
        raise HTTPException(status_code=404, detail='packet_not_found')

    signed = dict(found)
    signed['status'] = 'signed'
    signed['signed_by'] = str((payload or {}).get('signed_by', found.get('guest_name') or 'guest')).strip()
    signed['signed_at'] = datetime.now(timezone.utc).isoformat()
    signed['signature_method'] = str((payload or {}).get('signature_method', 'manual_attestation')).strip()
    signed['signed_witness_actor'] = actor
    signed['ts'] = datetime.now(timezone.utc).isoformat()
    _append_medium_stay_packet_record(signed)
    _append_manager_audit('medium_stay_packet_sign', actor=actor, metadata={'packet_id': packet_id, 'reservation_id': signed.get('reservation_id'), 'signed_by': signed.get('signed_by')})
    return {'ok': True, 'packet': signed}




class ExtensionEvaluateBody(BaseModel):
    reservation_id: str
    requested_check_out: str


class ExtensionApproveBody(BaseModel):
    reservation_id: str
    requested_check_out: str
    rationale: Optional[str] = ""


def _active_reservations_all() -> list[dict]:
    rows = []
    for st in ("confirmed", "checked_in"):
        try:
            rows.extend(get_db().bookings_list(status=st))
        except Exception:
            continue
    return rows


def _reservation_by_id(reservation_id: str) -> Optional[dict]:
    rid = str(reservation_id)
    for row in _active_reservations_all():
        if str(row.get("id")) == rid:
            return row
    return None


def _date_range(start_iso: str, end_iso: str):
    s = date.fromisoformat(start_iso)
    e = date.fromisoformat(end_iso)
    cur = s
    while cur < e:
        yield cur
        cur += timedelta(days=1)


def _extension_conflict_eval(reservation: dict, requested_check_out: str, cfg: dict) -> dict:
    room_id = str(reservation.get("room_id", ""))
    check_in = str(reservation.get("check_in", ""))
    current_out = str(reservation.get("check_out", ""))
    req_out_date = date.fromisoformat(str(requested_check_out))
    cur_out_date = date.fromisoformat(current_out)
    if req_out_date <= cur_out_date:
        raise HTTPException(status_code=400, detail="requested_check_out must be after current check_out")

    medium = (cfg.get("medium_stay") or {}) if isinstance(cfg, dict) else {}
    protected_weekend_pct = int(medium.get("protected_inventory_weekend_pct", 30) or 30)
    threshold = int(medium.get("extension_conflict_threshold", 70) or 70)

    rows = _active_reservations_all()
    total_rooms = max(1, len(get_db().room_list()))

    hard_conflict = False
    max_deficit = 0.0
    impacted_days = []
    for d in _date_range(cur_out_date.isoformat(), req_out_date.isoformat()):
        occupied = 0
        room_taken_by_other = False
        for r in rows:
            if str(r.get("id")) == str(reservation.get("id")):
                continue
            try:
                ci = date.fromisoformat(str(r.get("check_in")))
                co = date.fromisoformat(str(r.get("check_out")))
            except Exception:
                continue
            if ci <= d < co:
                occupied += 1
                if str(r.get("room_id", "")) == room_id:
                    room_taken_by_other = True
        if room_taken_by_other:
            hard_conflict = True
        avail_pct = ((total_rooms - occupied - 1) / total_rooms) * 100.0
        if d.weekday() in (4, 5):  # Fri/Sat protection
            deficit = max(0.0, float(protected_weekend_pct) - avail_pct)
            max_deficit = max(max_deficit, deficit)
            if deficit > 0:
                impacted_days.append(d.isoformat())

    score = min(100, int(round(max_deficit * 3)))
    decision = "accept"
    requires_manager_approval = False
    if hard_conflict:
        decision = "decline"
        score = 100
    elif score >= threshold:
        decision = "escalate"
        requires_manager_approval = True

    return {
        "reservation_id": str(reservation.get("id")),
        "room_id": room_id,
        "current_check_out": current_out,
        "requested_check_out": requested_check_out,
        "protected_inventory_weekend_pct": protected_weekend_pct,
        "extension_conflict_threshold": threshold,
        "conflict_score": score,
        "hard_conflict": hard_conflict,
        "requires_manager_approval": requires_manager_approval,
        "decision": decision,
        "impacted_days": impacted_days,
    }


@app.post('/api/motel/manager/medium-stay/extensions/evaluate')
def evaluate_medium_stay_extension(body: ExtensionEvaluateBody, request: Request):
    _require_manager_role(request, {'frontdesk','manager','admin'})
    cfg = _load_manager_config()
    res = _reservation_by_id(body.reservation_id)
    if not res:
        raise HTTPException(status_code=404, detail='reservation not found')
    result = _extension_conflict_eval(res, body.requested_check_out, cfg)
    return {"ok": True, "evaluation": result}


@app.post('/api/motel/manager/medium-stay/extensions/approve')
def approve_medium_stay_extension(body: ExtensionApproveBody, request: Request):
    _require_manager_write(request)
    cfg = _load_manager_config()
    res = _reservation_by_id(body.reservation_id)
    if not res:
        raise HTTPException(status_code=404, detail='reservation not found')
    eval_result = _extension_conflict_eval(res, body.requested_check_out, cfg)
    if eval_result.get('decision') == 'decline':
        raise HTTPException(status_code=409, detail={'code': 'extension_declined', 'evaluation': eval_result})
    updated = get_db().booking_update(str(res.get('id')), check_out=body.requested_check_out)
    actor = request.headers.get('x-authenticated-user', 'manager') or 'manager'
    _append_manager_audit('medium_stay_extension_approve', actor=actor, metadata={
        'reservation_id': str(res.get('id')),
        'from_check_out': str(res.get('check_out')),
        'to_check_out': body.requested_check_out,
        'conflict_score': eval_result.get('conflict_score'),
        'decision': eval_result.get('decision'),
        'rationale': body.rationale or '',
    })
    return {'ok': True, 'evaluation': eval_result, 'reservation': _decorate_reservation_stay_class(updated, cfg)}


@app.get('/api/motel/manager/medium-stay/templates')
def list_medium_stay_templates(request: Request, jurisdiction: Optional[str] = None, include_inactive: bool = False):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    records = list(_latest_template_versions().values())
    out = []
    for rec in records:
        if jurisdiction and str(rec.get('jurisdiction', '')).upper() != str(jurisdiction).upper():
            continue
        if (not include_inactive) and rec.get('status') != 'active':
            continue
        out.append(rec)
    out.sort(key=lambda r: (str(r.get('jurisdiction', '')), str(r.get('name', '')), -int(r.get('version', 0))))
    return {'items': out}


@app.post('/api/motel/manager/medium-stay/templates')
def create_medium_stay_template(payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    name = str((payload or {}).get('name', '')).strip()
    content = str((payload or {}).get('content', '')).strip()
    jurisdiction = str((payload or {}).get('jurisdiction', 'ME')).strip().upper() or 'ME'
    effective_date = str((payload or {}).get('effective_date', date.today().isoformat())).strip()
    status = str((payload or {}).get('status', 'active')).strip().lower() or 'active'
    if not name:
        raise HTTPException(status_code=400, detail='name is required')
    if not content:
        raise HTTPException(status_code=400, detail='content is required')
    if status not in {'active', 'inactive'}:
        raise HTTPException(status_code=400, detail='status must be active|inactive')

    template_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    rec = {
        'template_id': template_id,
        'name': name,
        'jurisdiction': jurisdiction,
        'version': 1,
        'effective_date': effective_date,
        'status': status,
        'content': content,
        'ts': ts,
        'actor': actor,
        'action': 'create',
    }
    _append_medium_stay_template_record(rec)
    _append_manager_audit('medium_stay_template_create', actor=actor, metadata={'template_id': template_id, 'name': name, 'jurisdiction': jurisdiction, 'version': 1, 'status': status})
    return {'ok': True, 'template': rec}


@app.post('/api/motel/manager/medium-stay/templates/{template_id}/supersede')
def supersede_medium_stay_template(template_id: str, payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    latest = _latest_template_versions().get(template_id)
    if not latest:
        raise HTTPException(status_code=404, detail='medium_stay_template_not_found')

    content = str((payload or {}).get('content', '')).strip()
    if not content:
        raise HTTPException(status_code=400, detail='content is required')

    effective_date = str((payload or {}).get('effective_date', date.today().isoformat())).strip()

    deactivate_prev = dict(latest)
    deactivate_prev['status'] = 'inactive'
    deactivate_prev['ts'] = datetime.now(timezone.utc).isoformat()
    deactivate_prev['actor'] = actor
    deactivate_prev['action'] = 'deactivate_for_supersede'
    _append_medium_stay_template_record(deactivate_prev)

    next_version = int(latest.get('version', 1)) + 1
    new_rec = {
        'template_id': template_id,
        'name': latest.get('name'),
        'jurisdiction': latest.get('jurisdiction', 'ME'),
        'version': next_version,
        'effective_date': effective_date,
        'status': 'active',
        'content': content,
        'ts': datetime.now(timezone.utc).isoformat(),
        'actor': actor,
        'action': 'supersede',
        'supersedes_version': int(latest.get('version', 1)),
    }
    _append_medium_stay_template_record(new_rec)
    _append_manager_audit('medium_stay_template_supersede', actor=actor, metadata={'template_id': template_id, 'name': latest.get('name'), 'version': next_version, 'supersedes_version': int(latest.get('version', 1))})
    return {'ok': True, 'template': new_rec}


@app.get('/api/motel/manager/audit-log')
def get_manager_audit_log(request: Request, limit: int = 200):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    p = _manager_audit_log_path()
    if not p.exists():
        return {"items": []}
    lines = p.read_text(encoding='utf-8').splitlines()[-max(1, min(limit, 1000)):]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return {"items": out}


@app.get('/api/motel/manager/config/versions')
def list_manager_config_versions(request: Request, limit: int = 50):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    p = _manager_versions_index_path()
    if not p.exists():
        return {"items": []}
    lines = p.read_text(encoding='utf-8').splitlines()[-max(1, min(limit, 500)):]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    out.reverse()
    return {"items": out}

@app.post('/api/motel/manager/config/restore')
def restore_manager_config(payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    supplied_revision = str((payload or {}).get('revision_id', '')).strip() or str(request.headers.get('if-match', '')).strip().strip('\"')
    version_id = str((payload or {}).get('version_id', '')).strip()
    reason = str((payload or {}).get('reason', '')).strip()
    if not version_id:
        raise HTTPException(status_code=400, detail='version_id is required')
    target = _read_manager_config_version(version_id)
    errs = _validate_manager_config(target)
    if errs:
        raise HTTPException(status_code=422, detail={"code": "invalid_restore_target", "errors": errs})
    before = _load_manager_config()
    current_revision = _manager_config_revision(before)
    if not supplied_revision:
        raise HTTPException(status_code=409, detail={"code": "revision_required", "current_revision": current_revision})
    if supplied_revision != current_revision:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict", "current_revision": current_revision})
    _save_manager_config(target)
    checkpoint_id = _record_rollback_checkpoint(actor=actor, config=before, reason=reason, restored_from=version_id)
    new_version_id = _record_manager_config_version(actor=actor, action='manager_config_restore', config=target, metadata={'restored_from': version_id, 'reason': reason, 'checkpoint_id': checkpoint_id})
    _append_manager_audit('manager_config_restore', actor=actor, before=before, after=target, metadata={'restored_from': version_id, 'reason': reason, 'version_id': new_version_id, 'checkpoint_id': checkpoint_id})
    next_revision = _manager_config_revision(target)
    return {"ok": True, "restored_from": version_id, "version_id": new_version_id, "config": target, "revision_id": next_revision, "checkpoint_id": checkpoint_id}




@app.get('/api/motel/manager/config/rollback-checkpoints')
def list_manager_rollback_checkpoints(request: Request, limit: int = 20):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    p = _manager_rollback_checkpoints_index_path()
    if not p.exists():
        return {"items": []}
    lines = p.read_text(encoding='utf-8').splitlines()[-max(1, min(limit, 500)):]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    out.reverse()
    return {"items": out}


@app.get('/api/motel/manager/config/rollback-checkpoints/{checkpoint_id}')
def get_manager_rollback_checkpoint(request: Request, checkpoint_id: str):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    cfg = _read_rollback_checkpoint(checkpoint_id)
    return {"checkpoint_id": checkpoint_id, "config": cfg}


@app.post('/api/motel/manager/config/restore-checkpoint')
def restore_manager_checkpoint(payload: dict, request: Request):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    supplied_revision = str((payload or {}).get('revision_id', '')).strip() or str(request.headers.get('if-match', '')).strip().strip('"')
    checkpoint_id = str((payload or {}).get('checkpoint_id', '')).strip()
    reason = str((payload or {}).get('reason', '')).strip()
    if not checkpoint_id:
        raise HTTPException(status_code=400, detail='checkpoint_id is required')
    target = _read_rollback_checkpoint(checkpoint_id)
    errs = _validate_manager_config(target)
    if errs:
        raise HTTPException(status_code=422, detail={"code": "invalid_restore_target", "errors": errs})
    before = _load_manager_config()
    current_revision = _manager_config_revision(before)
    if not supplied_revision:
        raise HTTPException(status_code=409, detail={"code": "revision_required", "current_revision": current_revision})
    if supplied_revision != current_revision:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict", "current_revision": current_revision})
    _save_manager_config(target)
    new_version_id = _record_manager_config_version(actor=actor, action='manager_config_restore_checkpoint', config=target, metadata={'checkpoint_id': checkpoint_id, 'reason': reason})
    _append_manager_audit('manager_config_restore_checkpoint', actor=actor, before=before, after=target, metadata={'checkpoint_id': checkpoint_id, 'reason': reason, 'version_id': new_version_id})
    next_revision = _manager_config_revision(target)
    return {"ok": True, "restored_checkpoint": checkpoint_id, "version_id": new_version_id, "config": target, "revision_id": next_revision}

@app.get('/api/motel/manager/config/versions/{version_id}')
def get_manager_config_version_snapshot(request: Request, version_id: str):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    cfg = _read_manager_config_version(version_id)
    return {"version_id": version_id, "config": cfg}


@app.get('/api/motel/manager/audit-log/verify')
def verify_manager_audit_log(request: Request, limit: int = 5000):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    return _verify_audit_chain(limit=limit)


@app.post('/api/motel/manager/audit-log/export')
def export_manager_audit_log(request: Request, payload: dict | None = None):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    limit = 5000
    if isinstance(payload, dict):
        try:
            limit = int(payload.get('limit', 5000))
        except Exception:
            limit = 5000
    limit = max(1, min(limit, 50000))

    log_path = _manager_audit_log_path()
    lines = log_path.read_text(encoding='utf-8').splitlines()[-limit:] if log_path.exists() else []
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base_name = f"manager_audit_export_{stamp}"
    out_dir = _manager_audit_exports_dir()
    jsonl_path = out_dir / f"{base_name}.jsonl"
    jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding='utf-8')

    verify = _verify_audit_chain(limit=limit)
    manifest = {
        'export_id': base_name,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'actor': actor,
        'limit': limit,
        'source': str(log_path),
        'files': {
            'audit_jsonl': {
                'path': str(jsonl_path),
                'sha256': _sha256_file(jsonl_path),
                'line_count': len(lines),
            },
        },
        'verification': verify,
    }
    manifest['signature'] = _signed_manifest_blob({k:v for k,v in manifest.items() if k!='signature'})
    manifest_path = out_dir / f"{base_name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    _append_audit_export_index({
        'export_id': base_name,
        'exported_at': manifest.get('exported_at'),
        'actor': actor,
        'limit': limit,
        'manifest_path': str(manifest_path),
        'audit_path': str(jsonl_path),
        'signature': manifest.get('signature', ''),
    })

    _append_manager_audit('manager_audit_export', actor=actor, metadata={'export_id': base_name, 'limit': limit, 'manifest': str(manifest_path)})
    return {
        'ok': True,
        'export_id': base_name,
        'manifest_path': str(manifest_path),
        'audit_path': str(jsonl_path),
        'manifest': manifest,
    }


@app.get('/api/motel/manager/audit-log/exports')
def list_manager_audit_exports(request: Request, limit: int = 200, export_id: str | None = None, actor: str | None = None, start_date: str | None = None, end_date: str | None = None):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    items = _read_audit_export_index(limit=limit)
    eid = (export_id or '').strip()
    act = (actor or '').strip()
    sd = (start_date or '').strip()
    ed = (end_date or '').strip()

    def _date_ok(ts: str) -> bool:
        d = ts[:10] if ts else ''
        if sd and d < sd:
            return False
        if ed and d > ed:
            return False
        return True

    out = []
    for it in items:
        if eid and str(it.get('export_id', '')) != eid:
            continue
        if act and str(it.get('actor', '')) != act:
            continue
        if not _date_ok(str(it.get('exported_at', ''))):
            continue
        out.append(it)
    return {'items': out}


@app.get('/api/motel/manager/audit-log/exports/{export_id}')
def get_manager_audit_export(request: Request, export_id: str):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    manifest_path = _resolve_export_artifact(export_id, 'manifest')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'export_manifest_corrupt: {e}')
    return {
        'export_id': export_id,
        'manifest': manifest,
        'artifacts': {
            'manifest': str(manifest_path),
            'audit': str(_resolve_export_artifact(export_id, 'audit')),
        },
    }


@app.get('/api/motel/manager/audit-log/exports/{export_id}/download/{artifact}')
def download_manager_audit_export_artifact(request: Request, export_id: str, artifact: str):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    p = _resolve_export_artifact(export_id, artifact)
    filename = p.name
    return FileResponse(path=str(p), filename=filename, media_type='application/json' if filename.endswith('.json') else 'application/x-ndjson')


@app.post('/api/motel/manager/audit-log/retention/run')
def run_manager_audit_retention(request: Request, payload: dict | None = None):
    _require_manager_role(request, {'manager','admin'})
    actor = _require_manager_write(request)
    settings = manager_automation_settings_get()
    days = int(settings.get('audit_export_retention_days', 90))
    if isinstance(payload, dict) and payload.get('retention_days') is not None:
        days = int(payload.get('retention_days'))
    result = _run_audit_retention_job(days)
    _append_manager_audit('manager_audit_retention_run', actor=actor, metadata=result)
    return {'ok': True, **result}


@app.get('/api/motel/manager/housekeeping/task-runs')
def list_housekeeping_task_runs(request: Request, status: str | None = None):
    _require_manager_role(request, {'viewer','frontdesk','manager','admin'})
    items = _read_task_runs()
    if status:
        items = [i for i in items if str(i.get('status', '')) == status]
    items.reverse()
    return {'items': items}


@app.post('/api/motel/manager/housekeeping/task-runs/{task_run_id}/start')
def start_housekeeping_task_run(task_run_id: str, body: TaskRunUpdateBody, request: Request):
    _require_manager_role(request, {'manager','admin','frontdesk'})
    actor = _require_manager_write(request)
    items = _read_task_runs()
    for it in items:
        if str(it.get('task_run_id')) == task_run_id:
            it['status'] = 'in_progress'
            it['started_at'] = it.get('started_at') or datetime.now(timezone.utc).isoformat()
            it['assignee'] = body.assignee.strip() if body.assignee.strip() else str(it.get('assignee', ''))
            _write_task_runs(items)
            _append_manager_audit('housekeeping_task_start', actor=actor, metadata={'task_run_id': task_run_id, 'room_id': it.get('room_id'), 'assignee': it.get('assignee')})
            return {'ok': True, 'item': it}
    raise HTTPException(status_code=404, detail='task_run_not_found')


@app.post('/api/motel/manager/housekeeping/task-runs/{task_run_id}/complete')
def complete_housekeeping_task_run(task_run_id: str, body: TaskRunUpdateBody, request: Request):
    _require_manager_role(request, {'manager','admin','frontdesk'})
    actor = _require_manager_write(request)
    items = _read_task_runs()
    for it in items:
        if str(it.get('task_run_id')) == task_run_id:
            it['status'] = 'completed'
            it['started_at'] = it.get('started_at') or datetime.now(timezone.utc).isoformat()
            it['completed_at'] = datetime.now(timezone.utc).isoformat()
            if body.assignee.strip():
                it['assignee'] = body.assignee.strip()
            _write_task_runs(items)
            _append_manager_audit('housekeeping_task_complete', actor=actor, metadata={'task_run_id': task_run_id, 'room_id': it.get('room_id'), 'assignee': it.get('assignee')})
            return {'ok': True, 'item': it}
    raise HTTPException(status_code=404, detail='task_run_not_found')
