# Manager Control GitHub Issue Bundle

Copy/paste each section into a new GitHub Issue.

## MC-101: Server-authenticated actor identity

**Title:** [MC-101] Server-authenticated actor identity
**Priority:** P0
**Estimate:** L
**Labels:** manager-control, west-bethel-motel, security, backend

### Goal
Stop trusting client-supplied actor strings.

### Scope
- Add auth middleware to motel API
- Extract actor from authenticated identity/session
- Deprecate `x-manager-actor` for production path

### Acceptance Criteria
- [ ] Manager write endpoints attribute actor from server identity only
- [ ] Client-supplied actor header is ignored/rejected in production mode
- [ ] Audit entries contain authenticated actor id
- [ ] Unit/API tests cover identity attribution

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-102: Role-based access control for manager endpoints

**Title:** [MC-102] Role-based access control for manager endpoints
**Priority:** P0
**Estimate:** L
**Labels:** manager-control, west-bethel-motel, security, backend

### Goal
Enforce least privilege by role.

### Scope
- Roles: `viewer`, `frontdesk`, `manager`, `admin`
- Authorization matrix per endpoint
- UI gating for Manager Control write actions

### Acceptance Criteria
- [ ] Unauthorized roles receive 403 on restricted endpoints
- [ ] UI hides/disables write controls when role lacks permission
- [ ] Matrix documented in code and docs
- [ ] API tests for each role x endpoint path

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-103: Production auth config and bootstrap docs

**Title:** [MC-103] Production auth config and bootstrap docs
**Priority:** P2
**Estimate:** S
**Labels:** manager-control, west-bethel-motel, security, backend

### Goal
Make secure deployment repeatable.

### Scope
- Env/config templates for auth providers
- Operator runbook for key/session rotation

### Acceptance Criteria
- [ ] Production setup doc validated on clean environment
- [ ] Key/session rotation steps documented and tested

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-201: Revision/ETag optimistic concurrency

**Title:** [MC-201] Revision/ETag optimistic concurrency
**Priority:** P0
**Estimate:** L
**Labels:** manager-control, west-bethel-motel, config-safety, backend, frontend

### Goal
Prevent blind overwrite.

### Scope
- Add config revision id / ETag to GET config
- Require matching revision on save/restore

### Acceptance Criteria
- [ ] Save/restore without current revision fails with conflict response
- [ ] UI shows conflict message and reload option
- [ ] Tests cover stale client conflict flow

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-202: Restore impact preview

**Title:** [MC-202] Restore impact preview
**Priority:** P1
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, config-safety, backend, frontend

### Goal
Show blast radius before rollback.

### Scope
- Compare target version vs live config
- Summarize changed paths + critical domains

### Acceptance Criteria
- [ ] Restore modal lists changed path count and critical changes
- [ ] Critical domains flagged (`door_locks`, `rooms`, `housekeeping`)
- [ ] User must explicitly acknowledge impact before restore executes

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-203: Multi-step rollback history

**Title:** [MC-203] Multi-step rollback history
**Priority:** P2
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, config-safety, backend, frontend

### Goal
Improve recovery beyond last-step undo.

### Scope
- Persistent rollback checkpoints
- UI to browse and restore checkpoints

### Acceptance Criteria
- [ ] At least last 20 rollback checkpoints available
- [ ] Restore from checkpoint is audited with reason
- [ ] Tests validate checkpoint integrity and replay

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-301: Hash-chain verifier enhancements

**Title:** [MC-301] Hash-chain verifier enhancements
**Priority:** P1
**Estimate:** M
**Labels:** manager-control, west-bethel-motel

### Goal
Strengthen tamper detection UX + API output.

### Scope
- Add detailed verifier output (line ids, summary)
- Add warning thresholds (legacy entries, chain breaks)

### Acceptance Criteria
- [ ] Verifier response includes machine-parseable status details
- [ ] UI can distinguish legacy-only vs broken-chain errors
- [ ] Regression tests for tamper and recovery paths

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-302: Signed export index + retrieval API

**Title:** [MC-302] Signed export index + retrieval API
**Priority:** P1
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, audit, compliance, backend

### Goal
Operationalize compliance handoff.

### Scope
- List/export-history endpoint
- Download endpoint for manifest + jsonl bundle

### Acceptance Criteria
- [ ] Exports are queryable by date/export_id/actor
- [ ] Download endpoint returns immutable artifact paths
- [ ] Signature verification command documented

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-303: Retention and archival policy

**Title:** [MC-303] Retention and archival policy
**Priority:** P2
**Estimate:** S
**Labels:** manager-control, west-bethel-motel, audit, compliance, backend

### Goal
Control storage and compliance lifecycle.

### Scope
- Retention window config
- Archive + prune jobs

### Acceptance Criteria
- [ ] Configurable retention policy enforced by scheduled job
- [ ] Archived bundles remain signature-verifiable
- [ ] No active-chain corruption after prune/archive

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-401: Room task-run entities

**Title:** [MC-401] Room task-run entities
**Priority:** P1
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, housekeeping, ops

### Goal
Move from static checklist config to execution tracking.

### Scope
- Task run model per room turnover
- Start/complete timestamps and assignee

### Acceptance Criteria
- [ ] New turnover creates task run entity
- [ ] Completion records timestamps + assignee
- [ ] API exposes open/completed runs

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-402: SLA timer and late-turnover alerts

**Title:** [MC-402] SLA timer and late-turnover alerts
**Priority:** P1
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, housekeeping, ops

### Goal
Turn housekeeping into measurable ops.

### Scope
- SLA target per room/task type
- Late threshold alerts and dashboard indicators

### Acceptance Criteria
- [ ] SLA breach creates alert with room context
- [ ] Dashboard shows late/at-risk counts
- [ ] Tests verify timer behavior around threshold transitions

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-403: Cleaner workload board

**Title:** [MC-403] Cleaner workload board
**Priority:** P2
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, housekeeping, ops

### Goal
Improve assignment balance.

### Scope
- Cleaner assignment UI + load stats
- Bulk assign/reassign tools

### Acceptance Criteria
- [ ] Manager can assign multiple rooms to cleaner in one action
- [ ] Load metrics visible by cleaner
- [ ] Assignment actions are audited

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-501: Rotation cadence monitor

**Title:** [MC-501] Rotation cadence monitor
**Priority:** P1
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, door-locks, ops

### Goal
Detect overdue/at-risk lock state quickly.

### Scope
- Rotation aging calculations
- Severity tiers and filtering

### Acceptance Criteria
- [ ] Overdue and due-soon counts shown in manager UI
- [ ] Filter supports `overdue`, `due_soon`, `ok`
- [ ] Alerting wired for overdue threshold

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-502: Lock failure retry queue

**Title:** [MC-502] Lock failure retry queue
**Priority:** P2
**Estimate:** M
**Labels:** manager-control, west-bethel-motel, door-locks, ops

### Goal
Handle transient lock-operation failures safely.

### Scope
- Queue failed operations with retry policy
- Operator visibility into failure reason/state

### Acceptance Criteria
- [ ] Failed lock ops enter retry queue with attempt counter
- [ ] Max-attempt exhaustion emits operator alert
- [ ] Queue state inspectable in manager UI/API

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-601: API integration suite for manager flows

**Title:** [MC-601] API integration suite for manager flows
**Priority:** P1
**Estimate:** L
**Labels:** manager-control, west-bethel-motel, frontend, tests

### Goal
Lock in behavior and prevent regressions.

### Scope
- Auth/RBAC tests
- Versioning/restore tests
- Audit verify/export tests

### Acceptance Criteria
- [ ] CI suite covers happy-path + failure-path for each manager endpoint
- [ ] Tamper simulation test included
- [ ] Export signature verification test included

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---

## MC-602: UI end-to-end tests for critical manager actions

**Title:** [MC-602] UI end-to-end tests for critical manager actions
**Priority:** P1
**Estimate:** L
**Labels:** manager-control, west-bethel-motel, frontend, tests

### Goal
Validate safety UX in-browser.

### Scope
- Compare-and-restore flow
- Typed RESTORE + production token safeguard
- Audit verify/export buttons
- MC-101, MC-102, MC-201
- MC-202, MC-301, MC-302
- MC-401, MC-402, MC-501
- MC-303, MC-502, MC-601, MC-602

### Acceptance Criteria
- [ ] E2E tests pass in CI for critical flows
- [ ] Restore blocked when safeguards fail
- [ ] Export/verify success and failure states covered
- [ ] Feature implemented and behind appropriate auth/role checks
- [ ] Backend + frontend tests added
- [ ] Operator-facing docs updated
- [ ] Validation evidence recorded (build/test logs)
- [ ] Auditability preserved for every write-affecting action

### Validation
- [ ] `python -m py_compile motel/api.py` (if backend touched)
- [ ] `npm run build` in `web/` (if frontend touched)
- [ ] Add/execute targeted tests and attach results

---
