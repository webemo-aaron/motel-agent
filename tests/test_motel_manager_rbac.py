from pathlib import Path

from fastapi.testclient import TestClient

import motel.api as motel_api


def _client(tmp_path: Path, monkeypatch, env: str = "production") -> TestClient:
    monkeypatch.setenv("MOTEL_ENV", env)
    monkeypatch.setenv("MOTEL_MANAGER_WRITE_TOKEN", "testtoken")
    monkeypatch.setattr(motel_api, "DATA_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    return TestClient(motel_api.app)


def test_viewer_can_read_but_not_write(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")

    r = client.get("/api/motel/manager/config", headers={"x-authenticated-user": "u1", "x-authenticated-role": "viewer"})
    assert r.status_code == 200

    r = client.post(
        "/api/motel/manager/config",
        headers={
            "x-manager-token": "testtoken",
            "x-authenticated-user": "u1",
            "x-authenticated-role": "viewer",
        },
        json={"housekeeping": {"default_turnover_minutes": 42}},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "manager_role_forbidden"


def test_manager_can_write(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    revision = client.get("/api/motel/manager/config", headers=headers).json()["revision_id"]
    r = client.post(
        "/api/motel/manager/config",
        headers=headers,
        json={"revision_id": revision, "housekeeping": {"default_turnover_minutes": 43}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


def test_legacy_role_header_forbidden_in_production(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    r = client.get("/api/motel/manager/config", headers={"x-authenticated-user": "m1", "x-manager-role": "manager"})
    assert r.status_code == 403
    assert r.json()["detail"] == "manager_role_header_forbidden_in_production"


def test_legacy_role_allowed_in_dev(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "dev")
    headers = {
        "x-manager-token": "testtoken",
        "x-manager-actor": "legacy",
        "x-manager-role": "manager",
    }
    revision = client.get("/api/motel/manager/config", headers=headers).json()["revision_id"]
    r = client.post(
        "/api/motel/manager/config",
        headers=headers,
        json={"revision_id": revision, "housekeeping": {"default_turnover_minutes": 44}},
    )
    assert r.status_code == 200


def test_save_requires_current_revision_and_rejects_stale(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }

    get_resp = client.get("/api/motel/manager/config", headers=headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    revision = body["revision_id"]
    assert revision

    no_rev = client.post("/api/motel/manager/config", headers=headers, json={"housekeeping": {"default_turnover_minutes": 45}})
    assert no_rev.status_code == 409
    assert no_rev.json()["detail"]["code"] == "revision_required"

    ok = client.post("/api/motel/manager/config", headers=headers, json={"revision_id": revision, "housekeeping": {"default_turnover_minutes": 46}})
    assert ok.status_code == 200

    stale = client.post("/api/motel/manager/config", headers=headers, json={"revision_id": revision, "housekeeping": {"default_turnover_minutes": 47}})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"


def test_restore_requires_current_revision_and_rejects_stale(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }

    initial = client.get("/api/motel/manager/config", headers=headers).json()
    rev1 = initial["revision_id"]

    save = client.post("/api/motel/manager/config", headers=headers, json={"revision_id": rev1, "housekeeping": {"default_turnover_minutes": 48}})
    assert save.status_code == 200

    versions = client.get("/api/motel/manager/config/versions", headers=headers).json()["items"]
    assert versions
    target_version_id = versions[0]["version_id"]

    missing = client.post("/api/motel/manager/config/restore", headers=headers, json={"version_id": target_version_id, "reason": "test"})
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "revision_required"

    stale = client.post("/api/motel/manager/config/restore", headers=headers, json={"version_id": target_version_id, "revision_id": rev1, "reason": "test"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"



def test_rollback_checkpoint_created_and_snapshot_integrity(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }

    base = client.get("/api/motel/manager/config", headers=headers).json()
    rev1 = base["revision_id"]

    save = client.post("/api/motel/manager/config", headers=headers, json={"revision_id": rev1, "housekeeping": {"default_turnover_minutes": 51}})
    assert save.status_code == 200
    rev2 = save.json()["revision_id"]

    versions = client.get("/api/motel/manager/config/versions", headers=headers).json()["items"]
    target_version_id = versions[0]["version_id"]
    restore = client.post("/api/motel/manager/config/restore", headers=headers, json={"version_id": target_version_id, "revision_id": rev2, "reason": "rollback test"})
    assert restore.status_code == 200
    checkpoint_id = restore.json().get("checkpoint_id")
    assert checkpoint_id

    ckpts = client.get("/api/motel/manager/config/rollback-checkpoints?limit=20", headers=headers)
    assert ckpts.status_code == 200
    items = ckpts.json()["items"]
    assert any(i.get("checkpoint_id") == checkpoint_id for i in items)

    snap = client.get(f"/api/motel/manager/config/rollback-checkpoints/{checkpoint_id}", headers=headers)
    assert snap.status_code == 200
    assert snap.json()["config"]["housekeeping"]["default_turnover_minutes"] == 51


def test_restore_from_checkpoint_replay(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }

    base = client.get("/api/motel/manager/config", headers=headers).json()
    rev1 = base["revision_id"]

    s1 = client.post("/api/motel/manager/config", headers=headers, json={"revision_id": rev1, "housekeeping": {"default_turnover_minutes": 60}})
    assert s1.status_code == 200
    rev2 = s1.json()["revision_id"]

    versions = client.get("/api/motel/manager/config/versions", headers=headers).json()["items"]
    v_id = versions[0]["version_id"]
    rst = client.post("/api/motel/manager/config/restore", headers=headers, json={"version_id": v_id, "revision_id": rev2, "reason": "create checkpoint"})
    assert rst.status_code == 200
    checkpoint_id = rst.json()["checkpoint_id"]
    rev3 = rst.json()["revision_id"]

    replay = client.post("/api/motel/manager/config/restore-checkpoint", headers=headers, json={"checkpoint_id": checkpoint_id, "revision_id": rev3, "reason": "replay checkpoint"})
    assert replay.status_code == 200

    live = client.get("/api/motel/manager/config", headers=headers).json()
    assert live["config"]["housekeeping"]["default_turnover_minutes"] == 60



def test_audit_verifier_status_legacy_only_vs_broken_chain(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }

    g = client.get("/api/motel/manager/config", headers=headers).json()
    rev = g["revision_id"]
    w = client.post("/api/motel/manager/config", headers=headers, json={"revision_id": rev, "housekeeping": {"default_turnover_minutes": 66}})
    assert w.status_code == 200

    verify_ok = client.get("/api/motel/manager/audit-log/verify?limit=5000", headers=headers)
    assert verify_ok.status_code == 200
    assert verify_ok.json()["status"] in {"ok", "legacy_only"}

    log_path = tmp_path / "manager_audit_log.jsonl"
    original = log_path.read_text(encoding="utf-8")
    log_path.write_text("not-json-legacy-line\n" + original, encoding="utf-8")

    verify_legacy = client.get("/api/motel/manager/audit-log/verify?limit=5000", headers=headers)
    assert verify_legacy.status_code == 200
    assert verify_legacy.json()["status"] == "legacy_only"
    assert verify_legacy.json()["summary"]["chain_broken"] is False

    lines = log_path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        if '"hash"' in ln:
            lines[i] = ln.replace('a', 'b', 1)
            break
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verify_broken = client.get("/api/motel/manager/audit-log/verify?limit=5000", headers=headers)
    assert verify_broken.status_code == 200
    payload = verify_broken.json()
    assert payload["status"] == "broken_chain"
    assert payload["summary"]["chain_broken"] is True
    assert payload["broken_at"] is not None
    assert payload["line_details"]


def test_audit_verifier_recovery_path_after_tamper_repair(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }

    g = client.get("/api/motel/manager/config", headers=headers).json()
    rev = g["revision_id"]
    w = client.post("/api/motel/manager/config", headers=headers, json={"revision_id": rev, "housekeeping": {"default_turnover_minutes": 67}})
    assert w.status_code == 200

    log_path = tmp_path / "manager_audit_log.jsonl"
    pristine = log_path.read_text(encoding="utf-8")

    tampered_lines = pristine.splitlines()
    for i, ln in enumerate(tampered_lines):
        if '"hash"' in ln:
            tampered_lines[i] = ln.replace('f', 'e', 1)
            break
    log_path.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    bad = client.get("/api/motel/manager/audit-log/verify?limit=5000", headers=headers).json()
    assert bad["status"] == "broken_chain"

    log_path.write_text(pristine, encoding="utf-8")
    recovered = client.get("/api/motel/manager/audit-log/verify?limit=5000", headers=headers).json()
    assert recovered["status"] in {"ok", "legacy_only"}
    assert recovered["summary"]["chain_broken"] is False



def test_audit_export_index_query_and_retrieval(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "manager.alice",
        "x-authenticated-role": "manager",
    }

    exp = client.post("/api/motel/manager/audit-log/export", headers=headers, json={"limit": 100})
    assert exp.status_code == 200
    export_id = exp.json()["export_id"]

    lst = client.get("/api/motel/manager/audit-log/exports?limit=50", headers=headers)
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert any(i.get("export_id") == export_id for i in items)

    by_id = client.get(f"/api/motel/manager/audit-log/exports?export_id={export_id}", headers=headers)
    assert by_id.status_code == 200
    assert len(by_id.json()["items"]) == 1

    by_actor = client.get("/api/motel/manager/audit-log/exports?actor=manager.alice", headers=headers)
    assert by_actor.status_code == 200
    assert by_actor.json()["items"]

    one = client.get(f"/api/motel/manager/audit-log/exports/{export_id}", headers=headers)
    assert one.status_code == 200
    artifacts = one.json()["artifacts"]
    assert artifacts["manifest"].endswith(f"{export_id}.manifest.json")
    assert artifacts["audit"].endswith(f"{export_id}.jsonl")

    d_manifest = client.get(f"/api/motel/manager/audit-log/exports/{export_id}/download/manifest", headers=headers)
    assert d_manifest.status_code == 200
    assert "attachment" in d_manifest.headers.get("content-disposition", "").lower()

    d_audit = client.get(f"/api/motel/manager/audit-log/exports/{export_id}/download/audit", headers=headers)
    assert d_audit.status_code == 200
    assert "attachment" in d_audit.headers.get("content-disposition", "").lower()



def test_retention_archive_moves_old_exports_and_preserves_signature(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "manager.ops",
        "x-authenticated-role": "manager",
    }

    exp = client.post("/api/motel/manager/audit-log/export", headers=headers, json={"limit": 10})
    assert exp.status_code == 200
    export_id = exp.json()["export_id"]
    sig = exp.json()["manifest"]["signature"]

    idx = tmp_path / "manager_audit_exports" / "exports_index.jsonl"
    rows = idx.read_text(encoding="utf-8").splitlines()
    import json
    obj = json.loads(rows[-1])
    obj["exported_at"] = "2000-01-01T00:00:00+00:00"
    rows[-1] = json.dumps(obj)
    idx.write_text("\n".join(rows) + "\n", encoding="utf-8")

    run = client.post("/api/motel/manager/audit-log/retention/run", headers=headers, json={"retention_days": 30})
    assert run.status_code == 200
    assert run.json()["archived_count"] >= 1

    get_exp = client.get(f"/api/motel/manager/audit-log/exports/{export_id}", headers=headers)
    assert get_exp.status_code == 200
    assert get_exp.json()["manifest"]["signature"] == sig

    dl = client.get(f"/api/motel/manager/audit-log/exports/{export_id}/download/manifest", headers=headers)
    assert dl.status_code == 200


def test_automation_daily_enforces_retention_without_chain_corruption(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "manager.ops",
        "x-authenticated-role": "manager",
    }

    set_auto = client.post("/api/motel/manager/automation/settings", json={
        "auto_recovery_enabled": False,
        "recovery_threshold_pct": 35.0,
        "auto_briefing_alert_enabled": False,
        "auto_archive_prune_enabled": True,
        "audit_export_retention_days": 1,
    })
    assert set_auto.status_code == 200

    exp = client.post("/api/motel/manager/audit-log/export", headers=headers, json={"limit": 5})
    assert exp.status_code == 200

    idx = tmp_path / "manager_audit_exports" / "exports_index.jsonl"
    rows = idx.read_text(encoding="utf-8").splitlines()
    import json
    o = json.loads(rows[-1])
    o["exported_at"] = "1999-01-01T00:00:00+00:00"
    rows[-1] = json.dumps(o)
    idx.write_text("\n".join(rows) + "\n", encoding="utf-8")

    daily = client.post("/api/motel/manager/automation/run-daily")
    assert daily.status_code == 200
    assert any(a.get("type") == "audit_retention" for a in daily.json().get("actions", []))

    verify = client.get("/api/motel/manager/audit-log/verify", headers=headers)
    assert verify.status_code == 200
    assert verify.json()["summary"]["chain_broken"] is False



def test_task_run_created_on_checkout_and_exposed_by_status(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "manager.ops",
        "x-authenticated-role": "manager",
    }

    # create reservation directly in DB fixture through API assumptions
    import motel.api as motel_api
    db = motel_api.get_db()
    db.room_upsert("1", room_type="SQ", status="available")
    r = db.booking_create(
        guest_name="Task Run Guest",
        check_in="2026-05-16",
        check_out="2026-05-17",
        room_id="1",
        rate_per_night=99.0,
    )
    db.guest_checkin(r["id"])

    co = client.post("/api/motel/checkout", json={"reservation_id": r["id"]})
    assert co.status_code == 200
    assert co.json().get("task_run")

    open_runs = client.get("/api/motel/manager/housekeeping/task-runs?status=open", headers=headers)
    assert open_runs.status_code == 200
    assert any(it.get("task_run_id") == co.json()["task_run"]["task_run_id"] for it in open_runs.json()["items"])


def test_task_run_complete_records_timestamps_and_assignee(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "manager.ops",
        "x-authenticated-role": "manager",
    }

    import motel.api as motel_api
    tr = motel_api._create_turnover_task_run("2", source="test")
    task_id = tr["task_run_id"]

    st = client.post(f"/api/motel/manager/housekeeping/task-runs/{task_id}/start", headers=headers, json={"assignee": "Cleaner A"})
    assert st.status_code == 200
    assert st.json()["item"]["started_at"]
    assert st.json()["item"]["assignee"] == "Cleaner A"

    cm = client.post(f"/api/motel/manager/housekeeping/task-runs/{task_id}/complete", headers=headers, json={"assignee": "Cleaner A"})
    assert cm.status_code == 200
    item = cm.json()["item"]
    assert item["status"] == "completed"
    assert item["started_at"]
    assert item["completed_at"]
    assert item["assignee"] == "Cleaner A"

    completed = client.get("/api/motel/manager/housekeeping/task-runs?status=completed", headers=headers)
    assert completed.status_code == 200
    assert any(it.get("task_run_id") == task_id for it in completed.json()["items"])


def test_medium_stay_defaults_present(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {"x-authenticated-user": "u1", "x-authenticated-role": "viewer"}
    resp = client.get("/api/motel/manager/config", headers=headers)
    assert resp.status_code == 200
    cfg = resp.json()["config"]
    ms = cfg.get("medium_stay")
    assert isinstance(ms, dict)
    assert ms.get("enabled") is True
    assert ms.get("tiers", {}).get("medium", {}).get("min_nights") == 7


def test_medium_stay_policy_validation_rejects_bad_values(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    current = client.get("/api/motel/manager/config", headers=headers).json()
    rev = current["revision_id"]
    bad = {
        "enabled": True,
        "tiers": {
            "short": {"min_nights": 1, "max_nights": 7, "notice_period_days": 0, "housekeeping_interval_days": 0, "deposit_required": False, "billing_cycle": "per_stay"},
            "medium": {"min_nights": 7, "max_nights": 27, "notice_period_days": 7, "housekeeping_interval_days": 7, "deposit_required": True, "billing_cycle": "weekly"},
            "long": {"min_nights": 28, "max_nights": 180, "notice_period_days": 14, "housekeeping_interval_days": 7, "deposit_required": True, "billing_cycle": "invalid_cycle"},
        },
        "protected_inventory_weekend_pct": 150,
        "extension_conflict_threshold": 70,
    }
    resp = client.post(
        "/api/motel/manager/config",
        headers=headers,
        json={"revision_id": rev, "medium_stay": bad},
    )
    assert resp.status_code == 422
    errors = resp.json()["detail"]["errors"]
    assert any("billing_cycle invalid" in e for e in errors)
    assert any("tier ranges overlap" in e for e in errors)
    assert any("protected_inventory_weekend_pct must be 0-100" in e for e in errors)


def test_medium_stay_legal_template_versioning_flow(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    mgr_headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    viewer_headers = {
        "x-authenticated-user": "v1",
        "x-authenticated-role": "viewer",
    }

    create = client.post(
        "/api/motel/manager/medium-stay/templates",
        headers=mgr_headers,
        json={
            "name": "Medium Stay Lodging Agreement",
            "jurisdiction": "ME",
            "content": "v1 legal terms",
            "effective_date": "2026-06-01",
            "status": "active",
        },
    )
    assert create.status_code == 200
    t = create.json()["template"]
    template_id = t["template_id"]
    assert t["version"] == 1

    listed = client.get("/api/motel/manager/medium-stay/templates?jurisdiction=ME", headers=viewer_headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(i["template_id"] == template_id and i["version"] == 1 for i in items)

    supersede = client.post(
        f"/api/motel/manager/medium-stay/templates/{template_id}/supersede",
        headers=mgr_headers,
        json={"content": "v2 legal terms", "effective_date": "2026-07-01"},
    )
    assert supersede.status_code == 200
    t2 = supersede.json()["template"]
    assert t2["version"] == 2
    assert t2["status"] == "active"

    listed2 = client.get("/api/motel/manager/medium-stay/templates?jurisdiction=ME", headers=viewer_headers)
    assert listed2.status_code == 200
    items2 = listed2.json()["items"]
    match = [i for i in items2 if i["template_id"] == template_id]
    assert match and match[0]["version"] == 2



def test_medium_stay_legal_template_requires_manager_write(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    viewer_headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "v1",
        "x-authenticated-role": "viewer",
    }
    resp = client.post(
        "/api/motel/manager/medium-stay/templates",
        headers=viewer_headers,
        json={"name": "x", "content": "y"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "manager_role_forbidden"


def test_medium_stay_packet_generation_and_checkin_gate(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")

    # Seed legal template
    manager_headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    t = client.post(
        "/api/motel/manager/medium-stay/templates",
        headers=manager_headers,
        json={
            "name": "Medium Stay Terms",
            "jurisdiction": "ME",
            "content": "contract terms v1",
            "effective_date": "2026-06-01",
            "status": "active",
        },
    )
    assert t.status_code == 200

    # Create medium-stay reservation (14 nights)
    room_id = "ms-room-1"
    seed_room = client.patch(f"/api/motel/rooms/{room_id}", json={"status": "available", "notes": "seed"})
    assert seed_room.status_code == 200
    book = client.post(
        "/api/motel/kiosk/book",
        json={
            "guest_name": "Alex Repeat",
            "check_in": "2031-06-10",
            "check_out": "2031-06-24",
            "room_id": room_id,
            "rate_per_night": 119.0,
            "email": "alex@example.com",
            "phone": "2075550100",
            "party_size": 2,
        },
    )
    assert book.status_code == 200
    reservation_id = book.json()["id"]

    # Check-in blocked before packet is signed
    blocked = client.post("/api/motel/checkin", json={"reservation_id": reservation_id})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "medium_stay_contract_required"

    # Generate and sign packet
    packet = client.post(
        "/api/motel/manager/medium-stay/packets/generate",
        headers=manager_headers,
        json={"reservation_id": reservation_id, "jurisdiction": "ME"},
    )
    assert packet.status_code == 200
    packet_id = packet.json()["packet"]["packet_id"]

    signed = client.post(
        f"/api/motel/manager/medium-stay/packets/{packet_id}/sign",
        headers=manager_headers,
        json={"signed_by": "Alex Repeat", "signature_method": "manual_attestation"},
    )
    assert signed.status_code == 200
    assert signed.json()["packet"]["status"] == "signed"

    # Check-in succeeds after signature
    ok = client.post("/api/motel/checkin", json={"reservation_id": reservation_id})
    assert ok.status_code == 200
    assert ok.json()["status"] == "checked_in"


def test_medium_stay_packet_generation_requires_medium_or_long(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    manager_headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    client.post(
        "/api/motel/manager/medium-stay/templates",
        headers=manager_headers,
        json={"name": "Terms", "jurisdiction": "ME", "content": "v1", "status": "active"},
    )
    room_id = "ms-room-2"
    seed_room = client.patch(f"/api/motel/rooms/{room_id}", json={"status": "available", "notes": "seed"})
    assert seed_room.status_code == 200
    short = client.post(
        "/api/motel/kiosk/book",
        json={
            "guest_name": "Short Stay",
            "check_in": "2031-06-10",
            "check_out": "2031-06-12",
            "room_id": room_id,
            "rate_per_night": 109.0,
            "email": "s@example.com",
            "phone": "2075550101",
            "party_size": 1,
        },
    )
    assert short.status_code == 200
    rid = short.json()["id"]
    gen = client.post(
        "/api/motel/manager/medium-stay/packets/generate",
        headers=manager_headers,
        json={"reservation_id": rid, "jurisdiction": "ME"},
    )
    assert gen.status_code == 400

def test_kiosk_book_rejects_stay_class_mismatch(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")

    seed = client.patch("/api/motel/rooms/ms-room-1", json={"status": "available", "notes": "seed"})
    assert seed.status_code == 200

    r = client.post(
        "/api/motel/kiosk/book",
        json={
            "guest_name": "Mismatch Guest",
            "phone": "2075551111",
            "check_in": "2031-04-01",
            "check_out": "2031-04-11",
            "room_id": "ms-room-1",
            "rate_per_night": 129,
            "party_size": 1,
            "stay_class": "short",
        },
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "stay_class_mismatch"
    assert detail["inferred"] == "medium"


def test_reservations_include_stay_class(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")

    for room_id in ("ms-room-1", "ms-room-2"):
        seed = client.patch(f"/api/motel/rooms/{room_id}", json={"status": "available", "notes": "seed"})
        assert seed.status_code == 200

    r1 = client.post(
        "/api/motel/kiosk/book",
        json={
            "guest_name": "Short Stay",
            "phone": "2075552222",
            "check_in": "2031-05-01",
            "check_out": "2031-05-03",
            "room_id": "ms-room-1",
            "rate_per_night": 149,
            "party_size": 1,
            "stay_class": "short",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["stay_class"] == "short"

    r2 = client.post(
        "/api/motel/kiosk/book",
        json={
            "guest_name": "Medium Stay",
            "phone": "2075553333",
            "check_in": "2031-05-10",
            "check_out": "2031-05-20",
            "room_id": "ms-room-2",
            "rate_per_night": 149,
            "party_size": 1,
            "stay_class": "medium",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["stay_class"] == "medium"

    listed = client.get("/api/motel/reservations?for_date=2031-05-01").json()
    assert listed and listed[0]["stay_class"] in {"short", "medium", "long"}
    by_guest = {row["guest_name"]: row for row in client.get("/api/motel/reservations?for_date=2031-05-10").json()}
    assert by_guest["Medium Stay"]["stay_class"] == "medium"


def test_medium_stay_extension_evaluate_accept_and_approve(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    manager_headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    seed = client.patch('/api/motel/rooms/ms-room-1', json={"status": "available", "notes": "seed"})
    assert seed.status_code == 200

    book = client.post('/api/motel/kiosk/book', json={
        "guest_name": "Ext Guest",
        "check_in": "2031-07-01",
        "check_out": "2031-07-10",
        "room_id": "ms-room-1",
        "rate_per_night": 139,
        "stay_class": "medium",
    })
    assert book.status_code == 200
    rid = book.json()["id"]

    ev = client.post('/api/motel/manager/medium-stay/extensions/evaluate', headers=manager_headers, json={
        "reservation_id": rid,
        "requested_check_out": "2031-07-12",
    })
    assert ev.status_code == 200
    assert ev.json()["evaluation"]["decision"] in {"accept", "escalate"}

    ap = client.post('/api/motel/manager/medium-stay/extensions/approve', headers=manager_headers, json={
        "reservation_id": rid,
        "requested_check_out": "2031-07-12",
        "rationale": "guest requested extension",
    })
    assert ap.status_code == 200
    assert ap.json()["reservation"]["check_out"] == "2031-07-12"


def test_medium_stay_extension_declines_hard_conflict(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    manager_headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    for room_id in ("ms-room-1",):
        seed = client.patch(f'/api/motel/rooms/{room_id}', json={"status": "available", "notes": "seed"})
        assert seed.status_code == 200

    base = client.post('/api/motel/kiosk/book', json={
        "guest_name": "Base Guest",
        "check_in": "2031-08-01",
        "check_out": "2031-08-05",
        "room_id": "ms-room-1",
        "rate_per_night": 139,
        "stay_class": "short",
    })
    assert base.status_code == 200
    rid = base.json()["id"]

    conflict = client.post('/api/motel/kiosk/book', json={
        "guest_name": "Conflict Guest",
        "check_in": "2031-08-06",
        "check_out": "2031-08-10",
        "room_id": "ms-room-1",
        "rate_per_night": 139,
        "stay_class": "short",
    })
    assert conflict.status_code == 200

    ev = client.post('/api/motel/manager/medium-stay/extensions/evaluate', headers=manager_headers, json={
        "reservation_id": rid,
        "requested_check_out": "2031-08-08",
    })
    assert ev.status_code == 200
    assert ev.json()["evaluation"]["decision"] == "decline"

    ap = client.post('/api/motel/manager/medium-stay/extensions/approve', headers=manager_headers, json={
        "reservation_id": rid,
        "requested_check_out": "2031-08-08",
    })
    assert ap.status_code == 409


def test_medium_stay_displacement_score_recommendations(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
        "x-manager-token": "testtoken",
    }

    for room_id in ("ms-room-1", "ms-room-2", "ms-room-3"):
        seed = client.patch(f"/api/motel/rooms/{room_id}", json={"status": "available", "notes": "seed"})
        assert seed.status_code == 200

    high = client.post('/api/motel/manager/medium-stay/pricing/displacement-score', headers=headers, json={
        "check_in": "2031-09-05",
        "check_out": "2031-09-25",
        "rate_per_night": 160,
        "protected_dates": ["2031-09-06", "2031-09-13"],
    })
    assert high.status_code == 200
    r1 = high.json()['result']
    assert r1['displacement_score'] >= 0
    assert r1['recommendation'] in {'accept','review','decline'}

    bad = client.post('/api/motel/manager/medium-stay/pricing/displacement-score', headers=headers, json={
        "check_in": "2031-09-10",
        "check_out": "2031-09-09",
        "rate_per_night": 160,
    })
    assert bad.status_code == 400


def test_weekly_housekeeping_plan_creates_recurring_runs_and_sla(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    seed = client.patch('/api/motel/rooms/ms-room-1', json={"status": "available", "notes": "seed"})
    assert seed.status_code == 200
    book = client.post('/api/motel/kiosk/book', json={
        "guest_name": "HK Guest",
        "check_in": "2031-10-01",
        "check_out": "2031-10-20",
        "room_id": "ms-room-1",
        "rate_per_night": 129,
        "stay_class": "medium",
    })
    assert book.status_code == 200
    rid = book.json()["id"]

    plan = client.post('/api/motel/manager/housekeeping/weekly-plans', headers=headers, json={
        "reservation_id": rid,
        "cadence_days": 7,
        "first_service_date": "2031-10-08",
    })
    assert plan.status_code == 200
    assert plan.json()["plan"]["cadence_days"] == 7

    runs = client.get('/api/motel/manager/housekeeping/task-runs', headers=headers)
    assert runs.status_code == 200
    weekly = [i for i in runs.json()["items"] if i.get("task_type") == "weekly_housekeeping" and i.get("reservation_id") == rid]
    assert len(weekly) >= 1
    assert weekly[0]["sla_state"] in {"due", "overdue", "met"}


def test_weekly_housekeeping_plan_rejects_short_stay(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    seed = client.patch('/api/motel/rooms/ms-room-2', json={"status": "available", "notes": "seed"})
    assert seed.status_code == 200
    book = client.post('/api/motel/kiosk/book', json={
        "guest_name": "Short HK",
        "check_in": "2031-11-01",
        "check_out": "2031-11-03",
        "room_id": "ms-room-2",
        "rate_per_night": 129,
        "stay_class": "short",
    })
    assert book.status_code == 200
    rid = book.json()["id"]

    plan = client.post('/api/motel/manager/housekeeping/weekly-plans', headers=headers, json={
        "reservation_id": rid,
        "cadence_days": 7,
    })
    assert plan.status_code == 400


def test_housekeeping_missed_service_outcomes_and_escalation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    seed = client.patch('/api/motel/rooms/ms-room-9', json={"status": "available", "notes": "seed"})
    assert seed.status_code == 200
    book = client.post('/api/motel/kiosk/book', json={
        "guest_name": "Miss Flow",
        "check_in": "2031-12-01",
        "check_out": "2031-12-20",
        "room_id": "ms-room-9",
        "rate_per_night": 129,
        "stay_class": "medium",
        "weekly_housekeeping_cadence_days": 7,
    })
    assert book.status_code == 200

    runs = client.get('/api/motel/manager/housekeeping/task-runs', headers=headers)
    assert runs.status_code == 200
    target = next(i for i in runs.json()['items'] if i.get('task_type') == 'weekly_housekeeping' and i.get('reservation_id') == book.json()['id'])

    r1 = client.post(f"/api/motel/manager/housekeeping/task-runs/{target['task_run_id']}/complete", headers=headers, json={"assignee":"hk1", "outcome":"guest_declined", "notes":"do not disturb"})
    assert r1.status_code == 200
    assert r1.json()['item']['outcome'] == 'guest_declined'
    assert r1.json()['escalated'] is False

    # second miss should escalate
    # pick another run for same reservation
    runs2 = client.get('/api/motel/manager/housekeeping/task-runs', headers=headers).json()['items']
    second = next(i for i in runs2 if i.get('task_type') == 'weekly_housekeeping' and i.get('reservation_id') == book.json()['id'] and i.get('task_run_id') != target['task_run_id'])
    r2 = client.post(f"/api/motel/manager/housekeeping/task-runs/{second['task_run_id']}/complete", headers=headers, json={"assignee":"hk1", "outcome":"no_access"})
    assert r2.status_code == 200
    assert r2.json()['escalated'] is True


def test_housekeeping_reschedule_outcome_audited(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "production")
    headers = {
        "x-manager-token": "testtoken",
        "x-authenticated-user": "m1",
        "x-authenticated-role": "manager",
    }
    seed = client.patch('/api/motel/rooms/ms-room-8', json={"status": "available", "notes": "seed"})
    assert seed.status_code == 200
    book = client.post('/api/motel/kiosk/book', json={
        "guest_name": "Resched Flow",
        "check_in": "2031-12-01",
        "check_out": "2031-12-20",
        "room_id": "ms-room-8",
        "rate_per_night": 129,
        "stay_class": "medium",
        "weekly_housekeeping_cadence_days": 7,
    })
    assert book.status_code == 200
    runs = client.get('/api/motel/manager/housekeeping/task-runs', headers=headers).json()['items']
    target = next(i for i in runs if i.get('task_type') == 'weekly_housekeeping' and i.get('reservation_id') == book.json()['id'])
    rr = client.post(f"/api/motel/manager/housekeeping/task-runs/{target['task_run_id']}/complete", headers=headers, json={"outcome":"rescheduled", "reschedule_for":"2031-12-18", "notes":"guest asked tomorrow"})
    assert rr.status_code == 200
    assert rr.json()['item']['outcome'] == 'rescheduled'
    assert rr.json()['item']['reschedule_for'] == '2031-12-18'
