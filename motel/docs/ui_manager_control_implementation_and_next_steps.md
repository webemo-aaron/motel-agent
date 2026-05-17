# Manager Control: Implementation Summary & Next Steps

**Last updated:** 2026-05-16  
**Scope:** West Bethel Motel Manager Control UI + motel API manager configuration/audit/versioning

## 1) What is implemented now

### Manager UI information architecture
- Added **Manager Control** workspace with a **left sidebar** and focused sections:
  - Rooms
  - Door Locks
  - Housekeeping
  - Audit Log
  - Config Versions
- Reduced scrolling via filters, compact mode, quick selectors, and keyboard shortcuts.

### Rooms management
- Live room list with status actions:
  - Set Available
  - Set Maintenance
- Room metadata editing:
  - room_type
  - max_occupancy
  - preferred_cleaner
  - lock_battery_status
  - out_of_order_reason
- Bulk operations:
  - Select all / dirty / maintenance / available / invert / clear
  - Bulk apply cleaner and room type
  - Confirm-before-apply
  - Undo last bulk update (client-side pre-save rollback)
- Validation:
  - room_type required
  - max_occupancy bounded

### Door lock management
- Door lock policy editor:
  - provider
  - code_rotation_policy
  - default_code_length
- Per-room rotate code action and last-rotated tracking.
- Sidebar warning counts for rotation/battery risk.

### Housekeeping management
- Editable defaults:
  - default_turnover_minutes
  - deep_clean_minutes
  - prioritize_same_day_arrivals
- Checklist editor:
  - add/edit/remove
  - reorder

### Audit log + governance UX
- Audit timeline with diff rendering (before/after by field path).
- Diff controls:
  - path filter
  - quick chips (`rooms`, `door_locks`, `housekeeping`)
- Raw JSON expansion per entry.
- Per-row copy + CSV export for filtered diffs.

### Configuration versioning + rollback
- Version snapshots recorded on manager config saves and lock rotations.
- Version history UI with restore actions.
- Compare tooling:
  - compare any two versions
  - compare historical version vs current live config
  - restore shortcut from compare view
- Safety gates for rollback:
  - typed `RESTORE` confirmation
  - production-only token re-entry safeguard

### Backend policy/security controls
- Manager write guard via `MOTEL_MANAGER_WRITE_TOKEN`:
  - enforced on write/restore/export operations
- Server-authenticated actor identity for manager writes (MC-101 baseline):
  - trusted actor headers: `x-authenticated-user`, `x-forwarded-user`, `x-remote-user`
  - production (`MOTEL_ENV=production`) rejects legacy `x-manager-actor` spoofing
  - production requires authenticated actor header presence
- Server-side config validation with 422 responses on invalid payloads.
- Audit log persistence in JSONL with before/after metadata.

### Tamper-evident auditing
- Hash-chain added to new audit records:
  - `prev_hash`
  - `hash`
- Chain verification endpoint:
  - `GET /api/motel/manager/audit-log/verify`
- Signed audit export bundle endpoint:
  - `POST /api/motel/manager/audit-log/export`
  - emits `.jsonl` + `.manifest.json` with SHA-256 + signature

---

## 2) API surface added/extended

### Manager config & operations
- `GET /api/motel/manager/config`
- `POST /api/motel/manager/config`
- `POST /api/motel/manager/config/door-locks/rotate`

### Audit
- `GET /api/motel/manager/audit-log`
- `GET /api/motel/manager/audit-log/verify`
- `POST /api/motel/manager/audit-log/export`

### Versioning
- `GET /api/motel/manager/config/versions`
- `GET /api/motel/manager/config/versions/{version_id}`
- `POST /api/motel/manager/config/restore`

---

## 3) Storage artifacts

- `motel/data/manager_control_config.json`
- `motel/data/manager_audit_log.jsonl`
- `motel/data/manager_config_versions.jsonl`
- `motel/data/manager_config_versions/*.json`
- `motel/data/manager_audit_exports/*`

---

## 4) Validation completed (already executed)

- Python compile checks (`py_compile`) for backend changes.
- Frontend production builds (`npm run build`) after each milestone.
- Runtime API tests for:
  - write auth enforcement (`403` on missing/invalid token)
  - validation failure handling (`422`)
  - version create/list/restore behavior
  - audit chain verify pass/fail detection (including tamper simulation)
  - signed export manifest integrity (hash + signature match)

---

## 5) Recommended next steps (implementation plan)

## Phase 1 — Identity, authorization, and trust (highest priority)
1. Replace localStorage token pattern with real auth/session model.
2. Bind actor identity server-side (no user-entered actor trust).
3. Add role matrix (`viewer/frontdesk/manager/admin`) across manager endpoints.
4. Add audit signing key management + key rotation policy.

**Exit criteria:** all manager writes are authenticated identities with RBAC-enforced access.

## Phase 2 — Concurrency and recovery safety
1. Add config revision/ETag and optimistic concurrency checks.
2. Block blind overwrite when server revision changed.
3. Add restore blast-radius preview (changed path count + critical-field flags).
4. Add multi-step undo/rollback chain with explicit checkpoints.

**Exit criteria:** no silent overwrite; all high-impact restore operations are previewed.

## Phase 3 — Operational execution layer
1. Move housekeeping from config-only to task execution with per-room runs.
2. Add cleaner assignment + SLA timers + missed-turnover alerts.
3. Add door lock health monitor (battery/rotation aging/failure retry queue).

**Exit criteria:** manager control provides live operations, not just static configuration.

## Phase 4 — Compliance/reporting and scale
1. Add signed export retrieval/index endpoint and retention policy controls.
2. Add weekly/monthly compliance reports from audit/version streams.
3. Add frontend performance optimization (code-splitting manager route, virtualization).

**Exit criteria:** auditable, scalable, and report-ready operational governance stack.

---

## 6) Suggested immediate sprint backlog (next 1–2 weeks)

- [ ] RBAC middleware for manager endpoints
- [ ] Server-issued auth identity for actor attribution
- [ ] Revision-based save/restore conflict protection
- [ ] Restore impact preview panel (critical paths: locks, occupancy, maintenance)
- [ ] Housekeeping execution entities (room task runs + timestamps)
- [ ] Manager smoke tests for auth + restore + verify + export flows

---

## 7) Notes for operators

- Keep `MOTEL_MANAGER_WRITE_TOKEN` set in production.
- Set `MOTEL_AUDIT_EXPORT_SECRET` to a dedicated secret (do not reuse app defaults).
- Treat restore as high-impact; use compare workflow before executing rollback.
- Run periodic `audit-log/verify` and archive signed exports for governance.


## 8) Final closure snapshot (2026-05-16T21:00:41Z)

Manager-control completion now includes operational execution and quality gates:

- Housekeeping ops: MC-401, MC-402, MC-403
- Door-lock reliability: MC-501, MC-502
- Quality hardening: MC-601 (API integration coverage), MC-602 (UI E2E)

Latest validation run:
- Backend compile checks: pass
- Web + kiosk production builds: pass
- Manager flow API suite: pass (`125 passed`)
- Kiosk/portal Playwright E2E: pass (`3 passed`)

GitHub tracking state: issues #7 through #15 are closed; execution-plan tracker issue #18 updated/closed after completion.
