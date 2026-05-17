# Manager Auth Bootstrap & Rotation Runbook (MC-103)

## Purpose
Production setup guide for manager-write authentication and actor identity controls for the motel-agent manager APIs.

## Scope
- `MOTEL_MANAGER_WRITE_TOKEN` bootstrap and rotation
- Production actor identity requirements
- Reverse-proxy header forwarding for trusted identity headers
- Verification checklist and rollback steps

## Production Requirements
Set these environment variables in production:

- `MOTEL_ENV=production`
- `MOTEL_MANAGER_WRITE_TOKEN=<strong-random-secret>`

In production mode:
- `x-manager-actor` is **rejected**
- actor identity must come from one of:
  - `x-authenticated-user`
  - `x-forwarded-user`
  - `x-remote-user`

## Bootstrap Procedure
1. Generate token (example):
   - `python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY`
2. Store in secret manager (not plaintext in repo).
3. Inject as runtime env var `MOTEL_MANAGER_WRITE_TOKEN`.
4. Set `MOTEL_ENV=production`.
5. Configure reverse proxy / gateway to pass authenticated user header to API.
6. Restart service.

## Header Trust Boundary
Only a trusted gateway/proxy may set identity headers.
- Strip incoming user-supplied identity headers at edge.
- Re-add vetted identity header from auth middleware.

### Nginx pattern (example)
- `proxy_set_header X-Authenticated-User $remote_user;`
- Also strip or overwrite untrusted inbound variants.

## Rotation Procedure
1. Create new token in secret manager.
2. Update runtime env with new token.
3. Restart API process.
4. Verify writes with new token succeed.
5. Verify old token rejected.
6. Record rotation in operations log.

## Verification Checklist
Run against production-like environment:

- [ ] legacy actor header rejected in prod
  - request with `x-manager-actor` returns `403 manager_actor_header_forbidden_in_production`
- [ ] missing authenticated actor rejected in prod
  - returns `403 manager_authenticated_actor_required`
- [ ] authenticated actor + valid token succeeds
  - returns `200`
- [ ] invalid token rejected
  - returns `403 manager_write_forbidden`
- [ ] audit log actor value matches authenticated identity

## Incident / Rollback
If auth rollout blocks writes unexpectedly:
1. Confirm gateway sends identity header.
2. Confirm `MOTEL_MANAGER_WRITE_TOKEN` matches operator client.
3. Temporary rollback path (non-production only): set `MOTEL_ENV=dev` to permit legacy actor header while fixing gateway.
4. Re-enable production mode after fix.

## Operational Notes
- Rotate token on schedule (recommended: every 30–90 days) or immediately on suspected leak.
- Avoid sharing token via chat; use secret manager and per-user access control.
- Future hardening target: replace shared token with server-issued sessions/JWT + RBAC.


## RBAC Matrix (Manager Control APIs)
Roles:
- `viewer`
- `frontdesk`
- `manager`
- `admin`

Allowed operations:
- Read endpoints (`GET /api/motel/manager/config`, `audit-log`, `config/versions`, `config/versions/{id}`, `audit-log/verify`):
  - viewer, frontdesk, manager, admin
- Write endpoints (`POST /api/motel/manager/config`, `config/door-locks/rotate`, `config/restore`, `audit-log/export`):
  - manager, admin only

Production rule:
- legacy `x-manager-role` is rejected in production; use trusted `x-authenticated-role`.
