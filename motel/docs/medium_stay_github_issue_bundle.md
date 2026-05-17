# Medium-Stay Program GitHub Issue Bundle

## MS-101: Stay classification + policy matrix
**Priority:** P0  
**Labels:** medium-stay, policy, backend, frontend

### Goal
Add explicit short/medium/long stay classes and enforce policy differences.

### Acceptance Criteria
- [ ] Stay classes defined (`short`, `medium`, `long`)
- [ ] Policy matrix configurable by class (notice, housekeeping cadence, deposit, billing cycle)
- [ ] Reservation API/UI reflects and validates stay class
- [ ] Tests cover policy enforcement by class

### Validation
- [ ] `python -m py_compile motel/api.py motel/db.py`
- [ ] `npm run build` in `web/` and `motel/kiosk/`
- [ ] Targeted tests pass

---

## MS-102: Legal template/version system
**Priority:** P0  
**Labels:** medium-stay, legal, compliance, backend

### Goal
Version legal templates and support jurisdiction-specific packet generation.

### Acceptance Criteria
- [ ] Template store supports versioning + effective dates
- [ ] Jurisdiction mapping supported (ME baseline)
- [ ] Immutable template audit trail recorded
- [ ] Tests cover create/read/version transitions

---

## MS-103: Contract packet generation + signature tracking
**Priority:** P0  
**Labels:** medium-stay, legal, compliance, backend, frontend

### Goal
Generate contract packets and track signature state before occupancy.

### Acceptance Criteria
- [ ] Packet generated on medium/long stay confirmation
- [ ] Signature status tracked (`pending`, `signed`, `expired`)
- [ ] Check-in blocked if required docs unsigned
- [ ] Audit entries link packet/reservation/actor

---

## MS-201: Availability protection + extension conflict engine
**Priority:** P1  
**Labels:** medium-stay, ops, backend

### Goal
Balance long-stay requests with future reservation availability.

### Acceptance Criteria
- [ ] Protected inventory windows configurable
- [ ] Extension request conflict scoring implemented
- [ ] Manager approval required on conflict threshold
- [ ] Tests cover acceptance/decline/escalation paths

---

## MS-202: Medium-stay pricing and displacement calculator
**Priority:** P2  
**Labels:** medium-stay, pricing, ops, backend

### Goal
Quantify displacement impact for long-duration requests.

### Acceptance Criteria
- [ ] Displacement score endpoint available
- [ ] Inputs include occupancy forecast + protected dates
- [ ] Decision recommendation surfaced in manager UI
- [ ] Tests cover scoring edge cases

---

## MS-301: Weekly housekeeping recurrence engine
**Priority:** P0  
**Labels:** medium-stay, housekeeping, backend, frontend

### Goal
Schedule recurring weekly housekeeping for medium/long stays.

### Acceptance Criteria
- [ ] Weekly cadence selectable at onboarding
- [ ] Recurring task-runs generated automatically
- [ ] Due/overdue states tracked with SLA timers
- [ ] Tests verify recurrence and SLA transitions

---

## MS-302: Housekeeping access and missed-service workflow
**Priority:** P1  
**Labels:** medium-stay, housekeeping, ops, backend, frontend

### Goal
Handle no-entry/missed-service scenarios with recovery workflow.

### Acceptance Criteria
- [ ] Outcome states include `completed`, `guest_declined`, `no_access`, `rescheduled`
- [ ] Repeat misses trigger operator alert
- [ ] Reschedule path audited
- [ ] Tests verify escalation thresholds

---

## MS-401: Recurring billing + deposit tracking
**Priority:** P1  
**Labels:** medium-stay, payments, backend, frontend

### Goal
Support recurring billing cycles and deposit lifecycle.

### Acceptance Criteria
- [ ] Billing cycle stored and scheduled (weekly/biweekly/monthly)
- [ ] Deposit status tracked and auditable
- [ ] Billing failures create actionable alerts
- [ ] Tests verify cycle transitions and failure handling

---

## MS-501: Compliance export for medium-stay legal packets
**Priority:** P1  
**Labels:** medium-stay, compliance, audit, backend

### Goal
Include legal packets/signatures in compliance export lifecycle.

### Acceptance Criteria
- [ ] Export index includes packet references
- [ ] Retrieval API returns immutable packet artifacts
- [ ] Signature verification docs updated
- [ ] Tests verify integrity of packet export manifests

---

## MS-601: API integration suite for medium-stay workflows
**Priority:** P1  
**Labels:** medium-stay, tests, backend

### Goal
Lock behavior for onboarding, docs, housekeeping recurrence, extensions, and billing.

### Acceptance Criteria
- [ ] Happy-path + failure-path coverage for medium-stay endpoints
- [ ] Check-in block on unsigned docs tested
- [ ] Conflict-engine and recurrence tests included
- [ ] CI-oriented targeted suite documented

---

## MS-602: UI E2E coverage for medium-stay critical flows
**Priority:** P1  
**Labels:** medium-stay, tests, frontend

### Goal
Validate medium-stay workflows in browser end-to-end.

### Acceptance Criteria
- [ ] Contract packet/signature gating flow covered
- [ ] Weekly housekeeping scheduling flow covered
- [ ] Extension request conflict/escalation flow covered
- [ ] Billing/deposit status handling covered

