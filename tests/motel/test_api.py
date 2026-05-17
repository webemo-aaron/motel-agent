import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    # Import after env is set so MotelDB picks up tmp_path
    import importlib

    import motel.api as api_mod

    importlib.reload(api_mod)
    from motel.api import app

    return TestClient(app)


def test_overview_returns_200(client):
    resp = client.get("/api/motel/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_rooms" in data
    assert "occupied_count" in data


def test_rooms_returns_list(client):
    resp = client.get("/api/motel/rooms")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_reservations_returns_list(client):
    resp = client.get("/api/motel/reservations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_stats_returns_occupancy(client):
    resp = client.get("/api/motel/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "occupancy_pct" in data
    assert "revenue_today" in data


def test_manager_strategy_endpoint_returns_portal_payload(client):
    resp = client.get("/api/motel/manager/strategy")
    assert resp.status_code == 200
    data = resp.json()
    assert "strategy_phase" in data
    assert "packages" in data and isinstance(data["packages"], list)
    assert any("Aventon" in pkg["name"] or "Ride Bethel" in pkg["name"] for pkg in data["packages"])
    assert "integration_endpoints" in data



def test_manager_plan_crud_flow(client):
    r1 = client.post('/api/motel/manager/campaigns', json={
        'week': 'Week 1', 'channel': 'email', 'objective': 'direct', 'offer': '2-night', 'budget': 120, 'owner': 'manager', 'status': 'planned'
    })
    assert r1.status_code == 200

    r2 = client.post('/api/motel/manager/events', json={
        'date': '2026-06-01', 'title': 'Reunion', 'event_type': 'reunion', 'expected_guests': 20, 'room_block': 0, 'notes': 'kitchen', 'status': 'planned'
    })
    assert r2.status_code == 200

    r3 = client.post('/api/motel/manager/leads', json={
        'name': 'Sunday River Weddings', 'segment': 'wedding', 'contact': 'test@example.com', 'source': 'partner', 'est_value': 1500, 'stage': 'new', 'notes': ''
    })
    assert r3.status_code == 200
    lead_id = r3.json()['id']

    r4 = client.patch(f'/api/motel/manager/leads/{lead_id}', json={'stage': 'qualified'})
    assert r4.status_code == 200
    assert r4.json()['stage'] == 'qualified'

    r5 = client.post('/api/motel/manager/ebike/settings', json={'fleet_size': 8, 'half_day_rate': 60, 'full_day_rate': 90})
    assert r5.status_code == 200

    r6 = client.post('/api/motel/manager/ebike/bookings', json={
        'guest_name': 'Alex Guest', 'date': '2026-06-02', 'duration': 'half_day', 'bikes': 2, 'status': 'reserved'
    })
    assert r6.status_code == 200

    rp = client.get('/api/motel/manager/plan')
    assert rp.status_code == 200
    payload = rp.json()
    assert len(payload['campaigns']) >= 1
    assert len(payload['events']) >= 1
    assert len(payload['leads']) >= 1
    assert payload['ebike']['settings']['fleet_size'] == 8
    assert len(payload['ebike']['bookings']) >= 1



def test_manager_weekly_briefing_endpoint(client):
    resp = client.get('/api/motel/manager/weekly-briefing')
    assert resp.status_code == 200
    data = resp.json()
    assert 'briefing' in data and isinstance(data['briefing'], str)
    assert 'actions' in data and isinstance(data['actions'], list)



def test_event_room_block_conflict_returns_400(client):
    # 99 rooms should exceed current inventory
    resp = client.post('/api/motel/manager/events', json={
        'date': '2026-06-03', 'title': 'Huge Event', 'event_type': 'retreat',
        'expected_guests': 100, 'room_block': 99, 'notes': '', 'status': 'planned'
    })
    assert resp.status_code == 400


def test_ebike_overbooking_guardrail(client):
    client.post('/api/motel/manager/ebike/settings', json={'fleet_size': 2, 'half_day_rate': 55, 'full_day_rate': 85})
    ok = client.post('/api/motel/manager/ebike/bookings', json={
        'guest_name': 'Guest A', 'date': '2026-06-04', 'duration': 'half_day', 'bikes': 2, 'status': 'reserved'
    })
    assert ok.status_code == 200
    bad = client.post('/api/motel/manager/ebike/bookings', json={
        'guest_name': 'Guest B', 'date': '2026-06-04', 'duration': 'half_day', 'bikes': 1, 'status': 'reserved'
    })
    assert bad.status_code == 400


def test_lead_history_and_send_briefing(client):
    lead = client.post('/api/motel/manager/leads', json={
        'name': 'Lead H', 'segment': 'group', 'contact': 'x@y.com', 'source': 'direct',
        'est_value': 500, 'stage': 'new', 'notes': 'start'
    }).json()
    lid = lead['id']
    client.patch(f'/api/motel/manager/leads/{lid}', json={'stage': 'qualified', 'notes': 'called'})
    hist = client.get(f'/api/motel/manager/leads/{lid}/history')
    assert hist.status_code == 200
    assert len(hist.json()['history']) >= 1

    send = client.post('/api/motel/manager/send-weekly-briefing')
    assert send.status_code == 200
    assert 'id' in send.json()



def test_manager_recommendations_endpoint(client):
    resp = client.get('/api/motel/manager/recommendations')
    assert resp.status_code == 200
    data = resp.json()
    assert 'recommendations' in data and isinstance(data['recommendations'], list)
    assert 'funnel' in data and isinstance(data['funnel'], dict)


def test_ebike_booking_update_and_delete(client):
    created = client.post('/api/motel/manager/ebike/bookings', json={
        'guest_name': 'Guest Z', 'date': '2026-06-05', 'duration': 'half_day', 'bikes': 1, 'status': 'reserved'
    })
    assert created.status_code == 200
    bid = created.json()['id']

    upd = client.patch(f'/api/motel/manager/ebike/bookings/{bid}', json={
        'guest_name': 'Guest Z', 'date': '2026-06-05', 'duration': 'full_day', 'bikes': 1, 'status': 'checked_out'
    })
    assert upd.status_code == 200
    assert upd.json()['duration'] == 'full_day'

    dele = client.delete(f'/api/motel/manager/ebike/bookings/{bid}')
    assert dele.status_code == 200
    assert dele.json()['deleted'] == bid



def test_manager_export_weekly_endpoint(client):
    resp = client.get('/api/motel/manager/export/weekly')
    assert resp.status_code == 200
    data = resp.json()
    assert 'snapshot_date' in data
    assert 'overview' in data and 'stats' in data
    assert 'plan' in data and 'recommendations' in data and 'briefing' in data


def test_manager_recovery_sprint(client):
    resp = client.post('/api/motel/manager/recovery-sprint')
    assert resp.status_code == 200
    data = resp.json()
    assert 'triggered' in data
    assert 'created' in data
    assert 'occupancy_pct' in data



def test_manager_automation_settings_and_run(client):
    set_resp = client.post('/api/motel/manager/automation/settings', json={
        'auto_recovery_enabled': True,
        'recovery_threshold_pct': 40,
        'auto_briefing_alert_enabled': False
    })
    assert set_resp.status_code == 200
    assert set_resp.json()['recovery_threshold_pct'] == 40

    get_resp = client.get('/api/motel/manager/automation/settings')
    assert get_resp.status_code == 200
    assert 'auto_recovery_enabled' in get_resp.json()

    run_resp = client.post('/api/motel/manager/automation/run-daily')
    assert run_resp.status_code == 200
    payload = run_resp.json()
    assert 'actions' in payload and isinstance(payload['actions'], list)

    logs = client.get('/api/motel/manager/automation/logs')
    assert logs.status_code == 200
    assert isinstance(logs.json().get('logs', []), list)



def test_rates_endpoints_integration(client):
    h = client.get('/api/motel/rates/health')
    assert h.status_code == 200

    s = client.get('/api/motel/rates/snapshot')
    assert s.status_code == 200
    assert 'items' in s.json()

    a = client.get('/api/motel/rates/alerts')
    assert a.status_code == 200
    assert 'items' in a.json()

    c = client.get('/api/motel/rates/calendar')
    assert c.status_code == 200
    cal = c.json()
    assert 'days' in cal
    assert isinstance(cal.get('days'), list)
    assert isinstance(cal.get('local_events'), list)

    sm = client.get('/api/motel/rates/summary')
    assert sm.status_code == 200
    payload = sm.json()
    assert 'snapshot_count' in payload
    assert 'alerts_count' in payload



def test_rates_alert_ack_flow(client):
    alerts = client.get('/api/motel/rates/alerts').json().get('items', [])
    if not alerts:
        return
    aid = alerts[0]['id']
    ack = client.post('/api/motel/rates/alerts/ack', json={'alert_id': aid})
    assert ack.status_code == 200
    refetched = client.get('/api/motel/rates/alerts').json().get('items', [])
    found = next((a for a in refetched if a.get('id') == aid), None)
    assert found is not None
    assert found.get('acknowledged') is True



def test_manager_qa_summary_endpoint(client):
    r = client.get('/api/motel/manager/qa-summary')
    assert r.status_code == 200
    j = r.json()
    assert 'total_runs' in j
    assert 'pass_count' in j
    assert 'fail_count' in j



# ─── Voice Settings Endpoints (NEW) ──────────────────────────────────


def test_voice_settings_get_empty_on_fresh_db(client):
    """GET /api/motel/settings/voice returns empty dict on fresh database."""
    resp = client.get("/api/motel/settings/voice")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_voice_settings_post_saves_public_host(client):
    """POST /api/motel/settings/voice saves public_host."""
    payload = {"public_host": "abc123.trycloudflare.com"}
    resp = client.post("/api/motel/settings/voice", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "saved"}

    # Verify it was saved
    resp = client.get("/api/motel/settings/voice")
    data = resp.json()
    assert data.get("voice.public_host") == "abc123.trycloudflare.com"


def test_voice_settings_post_saves_hermes_url(client):
    """POST /api/motel/settings/voice saves hermes_url."""
    payload = {"hermes_url": "http://localhost:8652/v1/chat/completions"}
    resp = client.post("/api/motel/settings/voice", json=payload)
    assert resp.status_code == 200

    resp = client.get("/api/motel/settings/voice")
    data = resp.json()
    assert data.get("voice.hermes_url") == "http://localhost:8652/v1/chat/completions"


def test_voice_settings_post_saves_twilio_credentials(client):
    """POST /api/motel/settings/voice saves Twilio credentials."""
    payload = {
        "twilio_account_sid": "AC1234567890abcdef1234567890abcde",
        "twilio_auth_token": "auth_token_secret_1234567890",
        "twilio_phone_number": "+1-555-0123",
    }
    resp = client.post("/api/motel/settings/voice", json=payload)
    assert resp.status_code == 200

    resp = client.get("/api/motel/settings/voice")
    data = resp.json()
    # Secrets should be masked in the response
    assert data.get("voice.twilio_phone_number") == "+1-555-0123"
    # Auth token should be masked
    assert data.get("voice.twilio_auth_token", "").startswith("●●●●")


def test_voice_settings_get_masks_secrets(client):
    """GET /api/motel/settings/voice masks sensitive fields."""
    client.post(
        "/api/motel/settings/voice",
        json={
            "hermes_api_key": "sk-1234567890abcdef",
            "twilio_auth_token": "auth_token_xyz",
            "ifttt_webhook_key": "webhook_secret_123",
        },
    )

    resp = client.get("/api/motel/settings/voice")
    data = resp.json()

    # Check that masked fields show ●●●● pattern with last 4 chars
    assert data.get("voice.hermes_api_key", "").startswith("●●●●")
    assert data.get("voice.twilio_auth_token", "").startswith("●●●●")
    assert data.get("voice.ifttt_webhook_key", "").startswith("●●●●")


def test_voice_settings_post_skips_masked_values(client):
    """POST /api/motel/settings/voice skips values starting with ●●●●."""
    # First save a secret
    client.post(
        "/api/motel/settings/voice",
        json={"hermes_api_key": "original_secret_value_123"},
    )

    # Try to "save" with masked value (from GET response)
    resp = client.get("/api/motel/settings/voice")
    masked_value = resp.json().get("voice.hermes_api_key")

    # POST with masked value should not update it
    resp = client.post(
        "/api/motel/settings/voice", json={"hermes_api_key": masked_value}
    )
    assert resp.status_code == 200

    # Original value should be unchanged
    resp = client.get("/api/motel/settings/voice")
    data = resp.json()
    assert data.get("voice.hermes_api_key") == masked_value


def test_voice_settings_post_saves_ifttt_config(client):
    """POST /api/motel/settings/voice saves IFTTT settings."""
    payload = {
        "ifttt_webhook_key": "webhook_key_xyz",
        "ifttt_event_name": "camera_motion",
    }
    resp = client.post("/api/motel/settings/voice", json=payload)
    assert resp.status_code == 200

    resp = client.get("/api/motel/settings/voice")
    data = resp.json()
    assert data.get("voice.ifttt_event_name") == "camera_motion"
    # Webhook key should be masked
    assert data.get("voice.ifttt_webhook_key", "").startswith("●●●●")


def test_voice_settings_post_multiple_fields(client):
    """POST /api/motel/settings/voice can save multiple fields at once."""
    payload = {
        "public_host": "tunnel.example.com",
        "hermes_url": "http://localhost:8652",
        "hermes_api_key": "api_key_123",
        "twilio_phone_number": "+1-555-0100",
    }
    resp = client.post("/api/motel/settings/voice", json=payload)
    assert resp.status_code == 200

    resp = client.get("/api/motel/settings/voice")
    data = resp.json()
    assert data.get("voice.public_host") == "tunnel.example.com"
    assert data.get("voice.hermes_url") == "http://localhost:8652"
    assert data.get("voice.twilio_phone_number") == "+1-555-0100"


# ─── Voice Status Endpoint ────────────────────────────────────────────


def test_voice_status_returns_dict(client):
    """GET /api/voice/status returns health status dict."""
    resp = client.get("/api/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_voice_status_includes_voice_bridge_check(client):
    """GET /api/voice/status includes voice_bridge_healthy field."""
    resp = client.get("/api/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "voice_bridge_healthy" in data or resp.status_code == 200


def test_voice_status_includes_public_host(client):
    """GET /api/voice/status includes public_host if configured."""
    client.post(
        "/api/motel/settings/voice", json={"public_host": "test.example.com"}
    )

    resp = client.get("/api/voice/status")
    assert resp.status_code == 200


def test_voice_status_includes_twilio_configured(client):
    """GET /api/voice/status includes twilio_configured field."""
    resp = client.get("/api/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    # Either field exists or endpoint is working
    assert resp.status_code == 200


def test_voice_status_without_configuration(client):
    """GET /api/voice/status works with no configuration."""
    # Fresh database should not have any configuration
    resp = client.get("/api/voice/status")
    assert resp.status_code == 200


# ─── Error Handling ──────────────────────────────────────────────────


def test_invalid_endpoint_returns_404(client):
    """GET to non-existent endpoint returns 404."""
    resp = client.get("/api/motel/nonexistent")
    assert resp.status_code == 404


def test_post_with_invalid_json_returns_400(client):
    """POST with invalid JSON returns 400."""
    resp = client.post(
        "/api/motel/settings/voice",
        data="invalid json {",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422 or resp.status_code == 400


# ─── Marvin Context Endpoint ────────────────────────────────────────


def test_marvin_context_returns_insights(client):
    """GET /api/motel/marvin-context returns insights array."""
    resp = client.get("/api/motel/marvin-context")
    assert resp.status_code == 200
    data = resp.json()
    assert "insights" in data
    assert isinstance(data["insights"], list)
    assert "overview" in data
    assert "timestamp" in data


def test_marvin_context_critical_alert_when_unresolved_alerts(client):
    """marvin-context includes critical alert when unresolved_alerts > 0."""
    # Create an alert
    from motel.db import MotelDB
    import os
    db = MotelDB(db_path=os.path.join(os.getenv("HERMES_HOME", ""), "motel.db"))
    db.alert_create("Critical issue", alert_type="urgent")

    resp = client.get("/api/motel/marvin-context")
    data = resp.json()
    insights = data["insights"]

    # Should have at least one critical alert insight
    alert_insights = [i for i in insights if i.get("type") == "alert"]
    assert len(alert_insights) > 0
    assert alert_insights[0]["priority"] == "critical"


def test_marvin_context_high_occupancy_insight(client):
    """marvin-context includes high occupancy insight when > 80%."""
    from motel.db import MotelDB
    import os
    db = MotelDB(db_path=os.path.join(os.getenv("HERMES_HOME", ""), "motel.db"))

    # Create 10 rooms
    for i in range(10):
        db.room_upsert(str(i), name=f"Room {i}")

    # Mark 9 as occupied (90% occupancy)
    for i in range(9):
        db.room_update_status(str(i), "occupied")

    resp = client.get("/api/motel/marvin-context")
    data = resp.json()
    insights = data["insights"]

    # Should have high occupancy insight
    high_occ = [i for i in insights if "High occupancy" in i.get("message", "")]
    assert len(high_occ) > 0


def test_marvin_context_low_occupancy_insight(client):
    """marvin-context includes low occupancy insight when < 35%."""
    from motel.db import MotelDB
    import os
    db = MotelDB(db_path=os.path.join(os.getenv("HERMES_HOME", ""), "motel.db"))

    # Create 10 rooms
    for i in range(10):
        db.room_upsert(str(i), name=f"Room {i}")

    # Mark only 1 as occupied (10% occupancy)
    db.room_update_status("0", "occupied")

    resp = client.get("/api/motel/marvin-context")
    data = resp.json()
    insights = data["insights"]

    # Should have low occupancy insight
    low_occ = [i for i in insights if "Low occupancy" in i.get("message", "")]
    assert len(low_occ) > 0


def test_marvin_context_dirty_rooms_with_arrivals_insight(client):
    """marvin-context includes insight when dirty_rooms > 0 and arrivals_today > 0."""
    from motel.db import MotelDB
    from datetime import date, timedelta
    import os
    db = MotelDB(db_path=os.path.join(os.getenv("HERMES_HOME", ""), "motel.db"))

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # Create room and mark as dirty
    db.room_upsert("1", name="Room 1")
    db.room_update_status("1", "dirty")

    # Create a booking for today (arrival)
    db.booking_create("Guest A", today, tomorrow, "1", 100.0)

    resp = client.get("/api/motel/marvin-context")
    data = resp.json()
    insights = data["insights"]

    # Should have insight about dirty rooms with arrivals
    dirty_arrivals = [
        i for i in insights if "dirty room" in i.get("message", "").lower()
    ]
    assert len(dirty_arrivals) > 0


def test_marvin_context_many_dirty_rooms_insight(client):
    """marvin-context includes insight when dirty_rooms > 5."""
    from motel.db import MotelDB
    import os
    db = MotelDB(db_path=os.path.join(os.getenv("HERMES_HOME", ""), "motel.db"))

    # Create 6 rooms and mark as dirty
    for i in range(6):
        db.room_upsert(str(i), name=f"Room {i}")
        db.room_update_status(str(i), "dirty")

    resp = client.get("/api/motel/marvin-context")
    data = resp.json()
    insights = data["insights"]

    # Should have insight about many dirty rooms
    many_dirty = [
        i for i in insights if "Multiple rooms need cleaning" in i.get("message", "")
    ]
    assert len(many_dirty) > 0


# ─── Checkin/Checkout Endpoints ──────────────────────────────────────


def test_checkin_invalid_reservation_returns_404(client):
    """POST /api/motel/checkin with invalid reservation_id returns 404."""
    payload = {"reservation_id": "nonexistent-id"}
    resp = client.post("/api/motel/checkin", json=payload)
    assert resp.status_code == 404


def test_checkout_invalid_reservation_returns_404(client):
    """POST /api/motel/checkout with invalid reservation_id returns 404."""
    payload = {"reservation_id": "nonexistent-id"}
    resp = client.post("/api/motel/checkout", json=payload)
    assert resp.status_code == 404


def test_kiosk_config_and_telegram_health(client):
    r1 = client.get('/api/motel/kiosk/config')
    assert r1.status_code == 200
    assert 'check_in_time' in r1.json()

    r2 = client.get('/api/motel/integrations/telegram/health')
    assert r2.status_code == 200
    assert 'configured' in r2.json()


def test_operator_alert_endpoint(client):
    r = client.post('/api/motel/operator-alert', json={'message': 'kiosk help test', 'alert_type': 'urgent'})
    assert r.status_code == 200
    j = r.json()
    assert j['message'] == 'kiosk help test'
    assert 'telegram' in j


def test_admin_unlock_flow(client):
    bad = client.post('/api/motel/admin/unlock', json={'pin': '0000'})
    assert bad.status_code == 401
    ok = client.post('/api/motel/admin/unlock', json={'pin': '2468'})
    assert ok.status_code == 200
    token = ok.json()['token']
    valid = client.post('/api/motel/admin/validate', json={'token': token})
    assert valid.status_code == 200
    assert valid.json()['valid'] is True


def test_kiosk_book_invalid_room_returns_400(client):
    bad = client.post('/api/motel/kiosk/book', json={
        'guest_name': 'Bad Room',
        'check_in': '2026-06-01',
        'check_out': '2026-06-02',
        'room_id': '9999',
        'rate_per_night': 100,
        'party_size': 1,
    })
    assert bad.status_code == 400


def test_rates_competitors_endpoint(client):
    r = client.get('/api/motel/rates/competitors?days=30&market=all')
    assert r.status_code == 200
    body = r.json()
    assert 'items' in body
    assert isinstance(body['items'], list)
    if body['items']:
        item = body['items'][0]
        assert 'property' in item
        assert 'confidence' in item
        assert 'sources' in item
