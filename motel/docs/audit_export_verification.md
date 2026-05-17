# Audit Export Signature Verification

Use this command to verify a manifest signature locally:

```bash
python - <<'PY'
import json, hashlib, pathlib, os
manifest_path = pathlib.Path("<MANIFEST_PATH>")
secret = os.getenv("MOTEL_AUDIT_EXPORT_SECRET") or os.getenv("MOTEL_MANAGER_WRITE_TOKEN") or "west-bethel-default-secret"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
sig = manifest.get("signature", "")
core = {k:v for k,v in manifest.items() if k != "signature"}
payload = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
expected = hashlib.sha256((secret + "|" + payload).encode("utf-8")).hexdigest()
print("OK" if sig == expected else "MISMATCH")
PY
```

Artifact retrieval endpoints:
- `GET /api/motel/manager/audit-log/exports`
- `GET /api/motel/manager/audit-log/exports/{export_id}`
- `GET /api/motel/manager/audit-log/exports/{export_id}/download/manifest`
- `GET /api/motel/manager/audit-log/exports/{export_id}/download/audit`
