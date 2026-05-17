"""
Twilio ConversationRelay WebSocket bridge for Agent Marvin.

Converts Twilio's text-in/text-out ConversationRelay protocol to Hermes gateway
/v1/chat/completions calls. Handles TwiML webhook for incoming calls.

Runs on port 8655 (exposed via cloudflared tunnel for Twilio callback).

Environment variables:
  VOICE_BRIDGE_PORT: port to listen on (default 8655)
  PUBLIC_HOST: tunnel hostname (e.g., xxxx.trycloudflare.com)
  HERMES_API_KEY: bearer token for gateway access
"""

import json
import logging
import os
from typing import Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response

try:
    from twilio.twiml.voice_response import VoiceResponse, Connect
except ImportError:
    raise SystemExit("twilio not installed. Run: pip install twilio")

logger = logging.getLogger(__name__)

app = FastAPI(title="Marvin Voice Bridge", version="1.0.0")

# Configuration defaults (env vars)
VOICE_BRIDGE_PORT = int(os.getenv("VOICE_BRIDGE_PORT", "8655"))
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost:8655")  # e.g., xxxx.trycloudflare.com
HERMES_URL = os.getenv("HERMES_URL", "http://localhost:8652/v1/chat/completions")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "test-key-for-local-development")


def _get_config() -> dict:
    """Read voice config from DB, falling back to env vars."""
    try:
        from motel.db import MotelDB

        db = MotelDB()
        return {
            "public_host": db.config_get("voice.public_host") or PUBLIC_HOST,
            "hermes_url": db.config_get("voice.hermes_url") or HERMES_URL,
            "hermes_api_key": db.config_get("voice.hermes_api_key") or HERMES_API_KEY,
        }
    except Exception:
        return {"public_host": PUBLIC_HOST, "hermes_url": HERMES_URL, "hermes_api_key": HERMES_API_KEY}

# System message for phone calls — teaches Marvin to be brief and clear for voice
MARVIN_PHONE_SYSTEM = """You are answering the front desk phone at West Bethel Motel.

Rules:
- Be brief and clear. Maximum 2-3 sentences per response.
- No markdown, no bullet points, no lists.
- Speak in natural conversational sentences.
- When retrieving information (reservations, room status, etc.), say "Let me check that for you" to fill the silence while processing.
- Always end with a clear question or offer: "How can I help?" or "Would you like me to...?"
- If the caller is angry or wants to speak with a human, say "Let me connect you with the front desk" and call send_operator_alert() with their request.
- For emergencies (medical, fire, police, safety hazards), immediately say "I'm calling emergency services" and escalate to send_operator_alert(alert_type="safety")."""


def parse_sse_chunk(line: str) -> Optional[dict]:
    """Parse a single SSE 'data:' line into JSON."""
    if not line.startswith("data:"):
        return None
    data_str = line[5:].strip()
    if data_str == "[DONE]":
        return None
    try:
        return json.loads(data_str)
    except json.JSONDecodeError:
        return None


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "voice_bridge"}


@app.post("/twilio/voice")
async def twilio_voice_webhook(request: Request):
    """
    TwiML webhook for incoming Twilio calls.

    Twilio calls this endpoint when a guest calls the motel's phone number.
    We return TwiML that instructs Twilio to start a ConversationRelay session.
    """
    config = _get_config()
    resp = VoiceResponse()

    # Start ConversationRelay: Twilio will send transcripts to our WebSocket endpoint
    # ConversationRelay handles STT (via Deepgram Nova-2 for phone) and TTS
    connect = Connect()
    connect.conversation_relay(
        url=f"wss://{config['public_host']}/twilio/relay",
        welcome_greeting="Thank you for calling West Bethel Motel. I'm Marvin, how can I help you today?",
        tts_provider="google",  # Google's TTS (good quality, natural-sounding)
        voice="en-US-Journey-D",  # Warm, professional voice
        transcription_provider="deepgram",
        speech_model="nova-2-phonecall",  # Optimized for phone audio
        language="en-US",
    )
    resp.append(connect)

    logger.info(f"Incoming call from {request.client.host if request.client else 'unknown'}")
    return Response(content=str(resp), media_type="text/xml")


@app.websocket("/twilio/relay")
async def twilio_relay(ws: WebSocket):
    """
    ConversationRelay WebSocket endpoint.

    Twilio sends transcripts, we call Hermes gateway, stream tokens back to Twilio.
    ConversationRelay protocol:
    - Server → Client: {type:"prompt", voicePrompt:"guest's speech"}
    - Client → Server: {type:"text", token:"...", last:True/False}
    """
    await ws.accept()
    logger.info("WebSocket connection established with Twilio ConversationRelay")

    config = _get_config()
    conversation = [
        {"role": "system", "content": MARVIN_PHONE_SYSTEM},
    ]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                try:
                    message = await ws.receive_json()
                except WebSocketDisconnect:
                    logger.info("ConversationRelay disconnected (call ended)")
                    break

                msg_type = message.get("type")

                if msg_type == "prompt":
                    # Guest has spoken — Twilio sends us the transcript
                    transcript = message.get("voicePrompt", "")
                    logger.info(f"Guest: {transcript}")

                    if not transcript.strip():
                        continue

                    # Add guest's message to conversation history
                    conversation.append({"role": "user", "content": transcript})

                    # Call Hermes gateway with streaming enabled
                    try:
                        async with client.stream(
                            "POST",
                            config["hermes_url"],
                            json={
                                "model": "hermes",
                                "messages": conversation,
                                "stream": True,
                            },
                            headers={"Authorization": f"Bearer {config['hermes_api_key']}"},
                        ) as resp:
                            full_reply = ""

                            # Stream SSE chunks back to Twilio as tokens
                            async for line in resp.aiter_lines():
                                chunk = parse_sse_chunk(line)
                                if not chunk:
                                    continue

                                # Extract token from SSE chunk
                                token = (
                                    chunk.get("choices", [{}])[0]
                                    .get("delta", {})
                                    .get("content", "")
                                )

                                if token:
                                    full_reply += token
                                    # Send token to Twilio for TTS playback
                                    await ws.send_json({
                                        "type": "text",
                                        "token": token,
                                        "last": False,
                                    })

                            # Signal end of response to Twilio
                            await ws.send_json({
                                "type": "text",
                                "token": "",
                                "last": True,
                            })

                            # Store assistant's reply in conversation history
                            if full_reply.strip():
                                conversation.append({
                                    "role": "assistant",
                                    "content": full_reply.strip(),
                                })
                                logger.info(f"Marvin: {full_reply.strip()}")

                    except Exception as e:
                        logger.error(f"Error calling Hermes gateway: {e}")
                        await ws.send_json({
                            "type": "text",
                            "token": "I'm having trouble understanding. Could you repeat that?",
                            "last": True,
                        })

                elif msg_type == "interrupt":
                    # Guest started speaking while Marvin was replying
                    # ConversationRelay handles this automatically; we just reset
                    logger.info("Guest interrupted response")

                elif msg_type == "started":
                    logger.info("ConversationRelay stream started")

                elif msg_type == "stopped":
                    logger.info("ConversationRelay stream stopped")

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        try:
            await ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print(f"Starting voice bridge on 0.0.0.0:{VOICE_BRIDGE_PORT}")
    print(f"Public endpoint: wss://{PUBLIC_HOST}/twilio/relay")

    uvicorn.run(
        "motel.voice_bridge:app",
        host="0.0.0.0",
        port=VOICE_BRIDGE_PORT,
        reload=False,
    )
