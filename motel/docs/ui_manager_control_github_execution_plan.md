# Manager Control — GitHub Execution Plan (Epics, Tickets, Acceptance Criteria)

**Date:** 2026-05-16  
**Project area:** West Bethel Motel manager-control stack (UI + API + governance)

This document is structured so each ticket can be copied directly into GitHub Issues.

---

## Epic 1 — Auth, Identity, and RBAC Hardening

### MC-101: Server-authenticated actor identity
**Goal**: Stop trusting client-supplied actor strings.  
**Scope**:
- Add auth middleware to motel API
- Extract actor from authenticated identity/session
- Deprecate `x-manager-actor` for production path

**Acceptance Criteria**:
- [ ] Manager write endpoints attribute actor from server identity only
- [ ] Client-supplied actor header is ignored/rejected in production mode
- [ ] Audit entries contain authenticated actor id
- [ ] Unit/API tests cover identity attribution

---

### MC-102: Role-based access control for manager endpoints
**Goal**: Enforce least privilege by role.  
**Scope**:
- Roles: `viewer`, `frontdesk`, `manager`, `admin`
- Authorization matrix per endpoint
- UI gating for Manager Control write actions

**Acceptance Criteria**:
- [ ] Unauthorized roles receive 403 on restricted endpoints
- [ ] UI hides/disables write controls when role lacks permission
- [ ] Matrix documented in code and docs
- [ ] API tests for each role x endpoint path

---

### MC-103: Production auth config and bootstrap docs
**Goal**: Make secure deployment repeatable.  
**Scope**:
- Env/config templates for auth providers
- Operator runbook for key/session rotation

**Acceptance Criteria**:
- [ ] Production setup doc validated on clean environment
- [ ] Key/session rotation steps documented and tested


## Epic 2 — Config Concurrency and Safe Restore

### MC-201: Revision/ETag optimistic concurrency
**Goal**: Prevent blind overwrite.  
**Scope**:
- Add config revision id / ETag to GET config
- Require matching revision on save/restore

**Acceptance Criteria**:
- [ ] Save/restore without current revision fails with conflict response
- [ ] UI shows conflict message and reload option
- [ ] Tests cover stale client conflict flow

---

### MC-202: Restore impact preview
**Goal**: Show blast radius before rollback.  
**Scope**:
- Compare target version vs live config
- Summarize changed paths + critical domains

**Acceptance Criteria**:
- [ ] Restore modal lists changed path count and critical changes
- [ ] Critical domains flagged (`door_locks`, `rooms`, `housekeeping`)
- [ ] User must explicitly acknowledge impact before restore executes

---

### MC-203: Multi-step rollback history
**Goal**: Improve recovery beyond last-step undo.  
**Scope**:
- Persistent rollback checkpoints
- UI to browse and restore checkpoints

**Acceptance Criteria**:
- [ ] At least last 20 rollback checkpoints available
- [ ] Restore from checkpoint is audited with reason
- [ ] Tests validate checkpoint integrity and replay


## Epic 3 — Audit Integrity and Compliance

### MC-301: Hash-chain verifier enhancements
**Goal**: Strengthen tamper detection UX + API output.  
**Scope**:
- Add detailed verifier output (line ids, summary)
- Add warning thresholds (legacy entries, chain breaks)

**Acceptance Criteria**:
- [ ] Verifier response includes machine-parseable status details
- [ ] UI can distinguish legacy-only vs broken-chain errors
- [ ] Regression tests for tamper and recovery paths

---

### MC-302: Signed export index + retrieval API
**Goal**: Operationalize compliance handoff.  
**Scope**:
- List/export-history endpoint
- Download endpoint for manifest + jsonl bundle

**Acceptance Criteria**:
- [ ] Exports are queryable by date/export_id/actor
- [ ] Download endpoint returns immutable artifact paths
- [ ] Signature verification command documented

---

### MC-303: Retention and archival policy
**Goal**: Control storage and compliance lifecycle.  
**Scope**:
- Retention window config
- Archive + prune jobs

**Acceptance Criteria**:
- [ ] Configurable retention policy enforced by scheduled job
- [ ] Archived bundles remain signature-verifiable
- [ ] No active-chain corruption after prune/archive


## Epic 4 — Housekeeping Execution Layer

### MC-401: Room task-run entities
**Goal**: Move from static checklist config to execution tracking.  
**Scope**:
- Task run model per room turnover
- Start/complete timestamps and assignee

**Acceptance Criteria**:
- [ ] New turnover creates task run entity
- [ ] Completion records timestamps + assignee
- [ ] API exposes open/completed runs

---

### MC-402: SLA timer and late-turnover alerts
**Goal**: Turn housekeeping into measurable ops.  
**Scope**:
- SLA target per room/task type
- Late threshold alerts and dashboard indicators

**Acceptance Criteria**:
- [ ] SLA breach creates alert with room context
- [ ] Dashboard shows late/at-risk counts
- [ ] Tests verify timer behavior around threshold transitions

---

### MC-403: Cleaner workload board
**Goal**: Improve assignment balance.  
**Scope**:
- Cleaner assignment UI + load stats
- Bulk assign/reassign tools

**Acceptance Criteria**:
- [ ] Manager can assign multiple rooms to cleaner in one action
- [ ] Load metrics visible by cleaner
- [ ] Assignment actions are audited


## Epic 5 — Door Lock Reliability Ops

### MC-501: Rotation cadence monitor
**Goal**: Detect overdue/at-risk lock state quickly.  
**Scope**:
- Rotation aging calculations
- Severity tiers and filtering

**Acceptance Criteria**:
- [ ] Overdue and due-soon counts shown in manager UI
- [ ] Filter supports `overdue`, `due_soon`, `ok`
- [ ] Alerting wired for overdue threshold

---

### MC-502: Lock failure retry queue
**Goal**: Handle transient lock-operation failures safely.  
**Scope**:
- Queue failed operations with retry policy
- Operator visibility into failure reason/state

**Acceptance Criteria**:
- [ ] Failed lock ops enter retry queue with attempt counter
- [ ] Max-attempt exhaustion emits operator alert
- [ ] Queue state inspectable in manager UI/API


## Epic 6 — Test & Release Hardening

### MC-601: API integration suite for manager flows
**Goal**: Lock in behavior and prevent regressions.  
**Scope**:
- Auth/RBAC tests
- Versioning/restore tests
- Audit verify/export tests

**Acceptance Criteria**:
- [ ] CI suite covers happy-path + failure-path for each manager endpoint
- [ ] Tamper simulation test included
- [ ] Export signature verification test included

---

### MC-602: UI end-to-end tests for critical manager actions
**Goal**: Validate safety UX in-browser.  
**Scope**:
- Compare-and-restore flow
- Typed RESTORE + production token safeguard
- Audit verify/export buttons

**Acceptance Criteria**:
- [ ] E2E tests pass in CI for critical flows
- [ ] Restore blocked when safeguards fail
- [ ] Export/verify success and failure states covered


## Suggested Milestones

### Milestone A (Security Foundation, 1 sprint)
- MC-101, MC-102, MC-201

### Milestone B (Governance Reliability, 1 sprint)
- MC-202, MC-301, MC-302

### Milestone C (Operational Execution, 1–2 sprints)
- MC-401, MC-402, MC-501

### Milestone D (Hardening + Compliance, ongoing)
- MC-303, MC-502, MC-601, MC-602


## Definition of Done (global)
- [ ] Feature implemented and behind appropriate auth/role checks
- [ ] Backend + frontend tests added
- [ ] Operator-facing docs updated
- [ ] Validation evidence recorded (build/test logs)
- [ ] Auditability preserved for every write-affecting action


---

## Closure status update (2026-05-16T21:00:41Z)

All manager-control issues in this execution chain are now closed:

- MC-302 / #7 ✅
- MC-303 / #8 ✅
- MC-401 / #9 ✅
- MC-402 / #10 ✅
- MC-403 / #11 ✅
- MC-501 / #12 ✅
- MC-502 / #13 ✅
- MC-601 / #14 ✅
- MC-602 / #15 ✅

Validation evidence for the final closure pass:
- `python -m py_compile motel/api.py motel/db.py motel/mcp_server.py motel/voice_bridge.py`
- `npm run build` in `web/`
- `npm run build` in `motel/kiosk/`
- `scripts/run_tests.sh tests/test_motel_manager_rbac.py tests/motel/test_api.py tests/motel/test_db.py tests/motel/test_mcp_server.py tests/motel/test_codex_server.py` (125 passed)
- `npm run test:e2e` in `motel/kiosk/` (3 passed)
