# Revenue & Ops Command Center — UI Spec (MVP v1)

## Purpose
Unify motel operations + competitor rate intelligence in one operator-facing dashboard page set.

## Information Architecture
- `/dashboard/command-center` (default landing)
- `/dashboard/rate-intelligence`
- `/dashboard/front-desk-board`
- `/dashboard/housekeeping-maintenance`
- `/dashboard/operator-console`

## 1) Command Center (Top Summary)
### Cards
- Occupancy %
- Arrivals today
- Departures today
- Dirty rooms
- Unresolved alerts
- Open critical work orders
- Overdue work orders
- Rate pipeline health (OK/FAIL)

### Data sources
- `desk_overview`
- `work_order_summary`
- `motel/data/competitor_rate_pipeline_health.json`

Refresh: 30–60s for ops cards, 5 min for pipeline health.

## 2) Rate Intelligence Page
### A. Live Snapshot Table
Columns:
- Property
- Market (Bethel / Sunday River / Gorham)
- Stay Date
- Tag(s) (holiday/event/winter_weekend_package)
- Min Nights
- Rate
- Package est. total (if winter package)
- Last seen
- Confidence/source

Source: `motel/data/competitor_rates_v2_latest.csv`

### B. Rate Change Feed
- Chronological feed of alerts (up/down %)
- Filters: market, tag, min delta %, date range
- Action: "Acknowledge"

Source: `motel/data/competitor_rate_alerts.csv`

### C. Market Calendar
- Month grid with highlighted demand dates
- Layers: federal holidays, local events, winter package windows

Sources:
- `motel/data/rate_query_dates_2y.json`
- `motel/data/local_events_bethel_region.json`

### D. Strategy Simulator (MVP-lite)
Inputs:
- Room type (SQ/DF/DQ)
- Target stay date(s)
- Occupancy band
- Optional floor/ceiling override

Output:
- Suggested rate band (min/recommended/max)
- Rationale chips: occupancy multiplier, DOW multiplier, lead-time multiplier, competitor median anchor

## 3) Front Desk Action Board
Queue blocks:
- Check-ins at risk (room not available)
- Dirty rooms with same-day arrivals
- Unresolved guest complaints/alerts
- No-show watchlist (>4 PM)

Actions:
- Check in guest
- Move room assignment
- Mark room status
- Send operator alert
- Add note

Tool/API mapping:
- `bookings_list`, `guest_checkin`, `booking_update`, `room_update_status`, `send_operator_alert`

## 4) Housekeeping + Maintenance
### Housekeeping lane
- Dirty rooms sorted by urgency:
  1) same-day arrivals
  2) early next-day arrivals
  3) standard next-day arrivals
- Fields: room, type, dirty since, ETA, assigned cleaner

### Maintenance lane
- Work orders by priority + due date
- Room-blocking badge
- Quick actions: schedule/update/complete

Tool/API mapping:
- `room_list`, `room_update_status`, `work_order_list`, `work_order_update`, `work_order_complete`

## 5) Operator Console
- Incident timeline (alerts + reservation/room context)
- Financial impact:
  - blocked-room est. revenue loss
  - top rate opportunities
- Escalation state: open/resolved

Tool/API mapping:
- `send_operator_alert`, `alert_resolve`, `dashboard_stats`, work-order + bookings tools

## Component Inventory (React)
- `KpiCardGrid`
- `PipelineHealthBadge`
- `CompetitorSnapshotTable`
- `RateChangeFeed`
- `DemandCalendar`
- `RateSimulatorPanel`
- `ActionQueueBoard`
- `HousekeepingLane`
- `MaintenanceLane`
- `IncidentTimeline`

## API Contract (Backend aggregator endpoints to add)
- `GET /api/rates/snapshot?date=...&market=...`
- `GET /api/rates/alerts?since=...&market=...&tag=...`
- `GET /api/rates/calendar?from=...&to=...`
- `GET /api/rates/health`
- `POST /api/rates/alerts/{id}/ack`
- `POST /api/rates/simulate` (input multipliers + anchors)

## UX Rules
- Color semantics:
  - Red: urgent / safety / blocking occupancy
  - Amber: SLA risk / aging dirty room
  - Green: healthy/on-time
- Show "last updated" on every card/panel.
- Non-blocking failure handling: if rate pipeline stale, ops panels still function.

## MVP Implementation Order
1. Add `Rate Intelligence` page in dashboard nav
2. Ship health badge + snapshot table + alert feed
3. Add front-desk action queue integration
4. Add housekeeping/maintenance dual lane
5. Add calendar and simulator

## Acceptance Criteria (MVP)
- Operator can identify top 5 competitor changes in <30 seconds.
- Front desk can resolve check-in risk from one board in <2 clicks/action.
- Health status shows green only when full+winter+weekend pipelines satisfy freshness SLO.
- No critical panel blocks if one data source fails.
