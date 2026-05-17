"""
Codex CLI HTTP wrapper for kiosk agent chat.
Exposes OpenAI-compatible /v1/chat/completions endpoint.
Codex CLI loads motel MCP server for tool access.

Start: python -m motel.codex_server
"""

from __future__ import annotations

import os
import subprocess
import time

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    raise SystemExit(
        "fastapi/uvicorn not installed. Run: uv pip install fastapi uvicorn"
    )

from pydantic import BaseModel

app = FastAPI(title="Codex CLI Wrapper", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{os.environ.get('MOTEL_KIOSK_PORT', '5182')}",
        f"http://localhost:{os.environ.get('MOTEL_API_PORT', '8653')}",
        f"http://localhost:{os.environ.get('MOTEL_CODEX_PORT', '8654')}",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False


class ChatChoice(BaseModel):
    message: ChatMessage
    finish_reason: str = "stop"


class ChatResponse(BaseModel):
    id: str = "codex-motel"
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """
    OpenAI-compatible chat completions endpoint.
    Forwards to Codex CLI with motel MCP context.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages required")

    # Build Codex CLI prompt from message history
    # Last user message is the actual prompt; prior messages are context
    prompt_parts = []
    for msg in request.messages[:-1]:
        prompt_parts.append(f"{msg.role.upper()}:\n{msg.content}\n")

    last_msg = request.messages[-1]
    if last_msg.role != "user":
        raise HTTPException(status_code=400, detail="Last message must be from user")

    prompt_parts.append(f"USER:\n{last_msg.content}")
    full_prompt = "\n".join(prompt_parts)

    try:
        # Call codex CLI with motel MCP config
        # Codex will have HERMES_HOME set so it can find the motel MCP server config
        env = os.environ.copy()
        # Ensure MCP server is available to Codex
        # Note: Codex CLI loads MCPs from ~/.codex/config.toml or via env
        # For now, we assume motel MCP is registered in Codex config

        result = subprocess.run(
            ["codex", "exec", full_prompt],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise HTTPException(status_code=500, detail=f"Codex error: {error_msg}")

        response_text = result.stdout.strip()
        if not response_text:
            response_text = "(Codex returned empty response)"

        return ChatResponse(
            created=int(time.time()),
            model=request.model or "codex",
            choices=[
                ChatChoice(
                    message=ChatMessage(role="assistant", content=response_text),
                    finish_reason="stop",
                )
            ],
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Codex request timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "codex-wrapper"}


if __name__ == "__main__":
    port = int(os.environ.get("MOTEL_CODEX_PORT", "8654"))
    uvicorn.run("motel.codex_server:app", host="0.0.0.0", port=port, reload=False)
