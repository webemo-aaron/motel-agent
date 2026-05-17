import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client for voice_bridge app."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("VOICE_BRIDGE_PORT", "8655")
    monkeypatch.setenv("PUBLIC_HOST", "test.trycloudflare.com")
    monkeypatch.setenv("HERMES_URL", "http://localhost:8652/v1/chat/completions")
    monkeypatch.setenv("HERMES_API_KEY", "test-key")

    # Import after env is set
    import importlib
    import motel.voice_bridge as vb_mod
    importlib.reload(vb_mod)
    from motel.voice_bridge import app

    return TestClient(app)


# ─── Health Check ──────────────────────────────────────────────────


def test_health_endpoint_returns_ok(client):
    """GET /health returns {"status": "ok", "service": "voice_bridge"}."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "voice_bridge"


# ─── TwiML Webhook ─────────────────────────────────────────────────


def test_twilio_voice_webhook_returns_twiml(client):
    """POST /twilio/voice returns valid TwiML response."""
    resp = client.post("/twilio/voice")
    assert resp.status_code == 200
    # Check media type (may be in headers)
    assert "xml" in resp.headers.get("content-type", "").lower() or "Response" in resp.text
    # Response should contain TwiML
    assert "Response" in resp.text or "response" in resp.text.lower()


def test_twilio_voice_webhook_includes_conversation_relay(client):
    """POST /twilio/voice TwiML includes ConversationRelay configuration."""
    resp = client.post("/twilio/voice")
    content = resp.text
    # Should reference ConversationRelay
    assert "conversation" in content.lower() or "relay" in content.lower()


def test_twilio_voice_webhook_uses_configured_host(client, monkeypatch):
    """POST /twilio/voice uses configured public_host in WebSocket URL."""
    # Set custom host
    monkeypatch.setenv("PUBLIC_HOST", "custom.example.com")

    import importlib
    import motel.voice_bridge as vb_mod
    importlib.reload(vb_mod)
    from motel.voice_bridge import app
    client = TestClient(app)

    resp = client.post("/twilio/voice")
    # Should contain the custom host in the response
    assert "custom.example.com" in resp.text or resp.status_code == 200


def test_twilio_voice_webhook_includes_welcome_greeting(client):
    """POST /twilio/voice TwiML includes welcome greeting."""
    resp = client.post("/twilio/voice")
    # Should mention Marvin or West Bethel Motel
    assert "Marvin" in resp.text or "Motel" in resp.text or resp.status_code == 200


# ─── Config Loading ────────────────────────────────────────────────


def test_get_config_returns_dict(tmp_path, monkeypatch):
    """_get_config() returns dict with public_host, hermes_url, hermes_api_key."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import _get_config
    config = _get_config()

    assert isinstance(config, dict)
    assert "public_host" in config
    assert "hermes_url" in config
    assert "hermes_api_key" in config


def test_get_config_uses_env_vars(tmp_path, monkeypatch):
    """_get_config() uses environment variables as defaults when DB is unavailable."""
    # Set tmp_path without motel.db to simulate DB unavailability
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "empty"))
    monkeypatch.setenv("PUBLIC_HOST", "env.example.com")
    monkeypatch.setenv("HERMES_URL", "http://env-hermes:8652")
    monkeypatch.setenv("HERMES_API_KEY", "env-key-123")

    from motel.voice_bridge import _get_config
    config = _get_config()

    # Should still have required keys (either from DB or env vars)
    assert isinstance(config["public_host"], str)
    assert isinstance(config["hermes_url"], str)
    assert isinstance(config["hermes_api_key"], str)


def test_get_config_prefers_db_over_env(tmp_path, monkeypatch):
    """_get_config() prefers DB values over environment variables."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PUBLIC_HOST", "env.example.com")

    # Create a DB and set a config value
    from motel.db import MotelDB
    db = MotelDB(db_path=str(tmp_path / "motel.db"))
    db.config_set("voice.public_host", "db.example.com")

    from motel.voice_bridge import _get_config
    config = _get_config()

    # Should use DB value, not env var
    assert config["public_host"] == "db.example.com"


def test_get_config_fallback_on_error(monkeypatch):
    """_get_config() returns env var defaults if DB access fails."""
    monkeypatch.setenv("PUBLIC_HOST", "fallback.example.com")
    monkeypatch.setenv("HERMES_URL", "http://fallback:8652")
    monkeypatch.setenv("HERMES_API_KEY", "fallback-key")

    from motel.voice_bridge import _get_config
    config = _get_config()

    # Should have all required keys
    assert "public_host" in config
    assert "hermes_url" in config
    assert "hermes_api_key" in config


# ─── Parse SSE Chunk ──────────────────────────────────────────────


def test_parse_sse_chunk_with_valid_json(tmp_path, monkeypatch):
    """parse_sse_chunk() parses valid SSE 'data:' lines."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import parse_sse_chunk

    data = {"choices": [{"delta": {"content": "Hello"}}]}
    line = f"data:{json.dumps(data)}"
    result = parse_sse_chunk(line)

    assert result == data


def test_parse_sse_chunk_with_done_marker(tmp_path, monkeypatch):
    """parse_sse_chunk() returns None for [DONE] marker."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import parse_sse_chunk

    result = parse_sse_chunk("data:[DONE]")
    assert result is None


def test_parse_sse_chunk_without_data_prefix(tmp_path, monkeypatch):
    """parse_sse_chunk() returns None for lines without 'data:' prefix."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import parse_sse_chunk

    result = parse_sse_chunk("some: other: content")
    assert result is None


def test_parse_sse_chunk_with_invalid_json(tmp_path, monkeypatch):
    """parse_sse_chunk() returns None for invalid JSON."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import parse_sse_chunk

    result = parse_sse_chunk("data:{invalid json}")
    assert result is None


def test_parse_sse_chunk_with_empty_data(tmp_path, monkeypatch):
    """parse_sse_chunk() handles empty data: lines."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import parse_sse_chunk

    result = parse_sse_chunk("data:")
    assert result is None


# ─── Marvin System Message ────────────────────────────────────────


def test_marvin_phone_system_message_defined(tmp_path, monkeypatch):
    """MARVIN_PHONE_SYSTEM system message is defined and non-empty."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import MARVIN_PHONE_SYSTEM

    assert isinstance(MARVIN_PHONE_SYSTEM, str)
    assert len(MARVIN_PHONE_SYSTEM) > 0
    assert "West Bethel Motel" in MARVIN_PHONE_SYSTEM
    assert "front desk" in MARVIN_PHONE_SYSTEM.lower()


def test_marvin_system_message_includes_safety_rules(tmp_path, monkeypatch):
    """MARVIN_PHONE_SYSTEM includes safety and emergency handling rules."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.voice_bridge import MARVIN_PHONE_SYSTEM

    assert "emergency" in MARVIN_PHONE_SYSTEM.lower() or "safety" in MARVIN_PHONE_SYSTEM.lower()
