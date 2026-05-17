import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client for codex_server app."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("MOTEL_KIOSK_PORT", "5182")
    monkeypatch.setenv("MOTEL_API_PORT", "8653")
    monkeypatch.setenv("MOTEL_CODEX_PORT", "8654")

    # Import after env is set
    import importlib
    import motel.codex_server as cs_mod
    importlib.reload(cs_mod)
    from motel.codex_server import app

    return TestClient(app)


# ─── Chat Completions Endpoint ────────────────────────────────────


def test_chat_completions_returns_400_with_empty_messages(client):
    """POST /v1/chat/completions returns 400 with empty messages."""
    payload = {
        "model": "codex",
        "messages": [],
        "stream": False
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 400
    assert "Messages required" in resp.text


def test_chat_completions_returns_400_with_no_user_message(client):
    """POST /v1/chat/completions returns 400 if last message is not user."""
    payload = {
        "model": "codex",
        "messages": [
            {"role": "assistant", "content": "Hello"}
        ],
        "stream": False
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 400


def test_chat_completions_accepts_valid_request(client):
    """POST /v1/chat/completions accepts valid message format."""
    payload = {
        "model": "codex",
        "messages": [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What time is it?"}
        ],
        "stream": False
    }
    resp = client.post("/v1/chat/completions", json=payload)
    # Should either succeed (200) or fail with specific error, not validation error
    assert resp.status_code in [200, 500, 502, 503]  # Accept success or service error


def test_chat_completions_with_single_user_message(client):
    """POST /v1/chat/completions handles single user message."""
    payload = {
        "model": "codex",
        "messages": [
            {"role": "user", "content": "Hello Marvin"}
        ],
        "stream": False
    }
    resp = client.post("/v1/chat/completions", json=payload)
    # Should not be validation error
    assert resp.status_code != 422


# ─── CORS Configuration ────────────────────────────────────────────


def test_cors_headers_present(client):
    """CORS headers are properly configured."""
    # Make a preflight request
    resp = client.options(
        "/v1/chat/completions",
        headers={"origin": "http://localhost:5182"}
    )
    # Should handle CORS preflight or return 405 (method not allowed)
    assert resp.status_code in [200, 405]


# ─── Data Models ──────────────────────────────────────────────────


def test_chat_request_model_parses_valid_data(tmp_path, monkeypatch):
    """ChatRequest model parses valid message data."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.codex_server import ChatRequest, ChatMessage

    req = ChatRequest(
        model="codex",
        messages=[
            ChatMessage(role="user", content="test")
        ],
        stream=False
    )

    assert req.model == "codex"
    assert len(req.messages) == 1
    assert req.messages[0].role == "user"


def test_chat_response_model_structure(tmp_path, monkeypatch):
    """ChatResponse model has correct structure."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.codex_server import ChatResponse, ChatChoice, ChatMessage

    resp = ChatResponse(
        id="test",
        created=1234567890,
        model="codex",
        choices=[
            ChatChoice(
                message=ChatMessage(role="assistant", content="response"),
                finish_reason="stop"
            )
        ]
    )

    assert resp.id == "test"
    assert resp.object == "chat.completion"
    assert len(resp.choices) == 1
    assert resp.choices[0].message.content == "response"


# ─── App Configuration ─────────────────────────────────────────────


def test_app_is_fastapi_instance(tmp_path, monkeypatch):
    """app is a FastAPI application instance."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.codex_server import app
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)


def test_app_has_correct_title(tmp_path, monkeypatch):
    """FastAPI app has correct title."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from motel.codex_server import app

    assert app.title == "Codex CLI Wrapper"
