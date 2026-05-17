# React Scaffold Plan — Rate Intelligence + Ops Command Center

## Target frontend
- Base: `web/src`
- Router/pages location: `web/src/pages`
- Shared UI components: `web/src/components`
- API clients/hooks: `web/src/lib` and `web/src/hooks`

## New Pages
1. `web/src/pages/CommandCenterPage.tsx`
2. `web/src/pages/RateIntelligencePage.tsx`
3. `web/src/pages/FrontDeskBoardPage.tsx`
4. `web/src/pages/HousekeepingMaintenancePage.tsx`
5. `web/src/pages/OperatorConsolePage.tsx`

## New Components
- `web/src/components/rates/PipelineHealthBadge.tsx`
- `web/src/components/rates/CompetitorSnapshotTable.tsx`
- `web/src/components/rates/RateChangeFeed.tsx`
- `web/src/components/rates/DemandCalendar.tsx`
- `web/src/components/rates/RateSimulatorPanel.tsx`
- `web/src/components/ops/KpiCardGrid.tsx`
- `web/src/components/ops/ActionQueueBoard.tsx`
- `web/src/components/ops/HousekeepingLane.tsx`
- `web/src/components/ops/MaintenanceLane.tsx`
- `web/src/components/ops/IncidentTimeline.tsx`

## New Hooks
- `web/src/hooks/useRateHealth.ts`
- `web/src/hooks/useRateSnapshot.ts`
- `web/src/hooks/useRateAlerts.ts`
- `web/src/hooks/useRateCalendar.ts`
- `web/src/hooks/useRateSimulator.ts`
- `web/src/hooks/useDeskOverview.ts`

## New API client modules
- `web/src/lib/ratesApi.ts`
- `web/src/lib/opsApi.ts`

## Suggested TypeScript types
- `web/src/lib/types/rates.ts`
- `web/src/lib/types/ops.ts`

## Routing integration
- Add nav entries + routes in app router (likely `web/src/App.tsx`):
  - `/command-center`
  - `/rate-intelligence`
  - `/front-desk-board`
  - `/housekeeping-maintenance`
  - `/operator-console`

## Milestone breakdown
### Milestone 1 (MVP/Read-only)
- CommandCenterPage + KPI cards + pipeline health badge
- RateIntelligencePage with snapshot table + alerts feed
- Uses:
  - `GET /api/rates/health`
  - `GET /api/rates/snapshot`
  - `GET /api/rates/alerts`

### Milestone 2 (Ops actions)
- FrontDeskBoardPage action queue wired to bookings/rooms/alerts endpoints
- HousekeepingMaintenancePage with dirty/maintenance lanes + work order list

### Milestone 3 (Decision support)
- DemandCalendar + Strategy Simulator
- Alert acknowledge action + server persistence

## State model
- Query/caching: React Query or existing data layer
- Polling intervals:
  - desk overview: 30s
  - rates snapshot/alerts: 5m
  - health: 2m
- Error handling:
  - Panel-level fallback, never full-page crash

## Definition of Done (engineering)
- All new pages behind role-aware nav visibility
- All endpoint payloads validated against `motel/docs/rate_intelligence_api_schemas.json`
- Lighthouse accessibility pass for key pages
- No blocking UI if rate endpoints unavailable
