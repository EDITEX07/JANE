"""J.A.N.E. 1.1 private API gateway.

Secrets are supplied through the hosting provider's environment variables.
Never commit API keys to the repository.
"""

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

try:
    from google import genai
except ImportError:
    genai = None

API_KEY_SHA256 = os.getenv("JANE_API_KEY_SHA256", "").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
REQUESTS_PER_MINUTE = max(1, int(os.getenv("JANE_REQUESTS_PER_MINUTE", "12")))
MAX_PROMPT_CHARS = 4000
MAX_HISTORY_MESSAGES = 12
_recent_requests = defaultdict(deque)

app = FastAPI(
    title="J.A.N.E. Private API",
    version="1.1.1",
    description="Private API gateway for the J.A.N.E. assistant.",
)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    mode: Literal["General", "Adaptive", "Thinker"] = "Adaptive"
    style: Literal["Classic", "JARVIS"] = "Classic"
    history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)


def require_api_key(x_jane_api_key: str | None = Header(default=None, alias="X-JANE-API-Key")):
    if not API_KEY_SHA256:
        raise HTTPException(status_code=503, detail="API authentication is not configured.")
    if not x_jane_api_key:
        raise HTTPException(status_code=401, detail="Missing API key.")
    supplied_hash = hashlib.sha256(x_jane_api_key.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied_hash, API_KEY_SHA256):
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return supplied_hash[:12]


def apply_soft_rate_limit(key_fingerprint: str):
    now = time.time()
    events = _recent_requests[key_fingerprint]
    while events and now - events[0] > 60:
        events.popleft()
    if len(events) >= REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit reached. Try again shortly.")
    events.append(now)


def build_system_instruction(mode: str, style: str) -> str:
    """Give the model a consistent voice without forcing a template on every answer."""
    mode_instructions = {
        "General": (
            "Keep the exchange relaxed and direct. Answer the actual question first. "
            "Use a conversational amount of detail and avoid formal report structure unless requested."
        ),
        "Adaptive": (
            "Read the user's intent and context before choosing how to answer. "
            "For a simple question, be brief; for a difficult task, explain enough to make the answer useful. "
            "Ask a follow-up only when a missing detail genuinely prevents progress."
        ),
        "Thinker": (
            "Handle difficult questions with extra care. Check assumptions, consider meaningful alternatives, "
            "and explain the key reasons, trade-offs, and uncertainties when useful. "
            "Give a concise explanation of the result, not private hidden chain-of-thought."
        ),
    }
    style_instructions = {
        "Classic": (
            "Sound like a thoughtful, capable person in a real conversation: warm when appropriate, "
            "clear, grounded, and comfortable. Do not sound like a corporate help desk, a scripted chatbot, "
            "or a formal report generator. Match the user's level of formality without copying every quirk."
        ),
        "JARVIS": (
            "Sound composed, perceptive, polished, and quietly confident, while remaining natural. "
            "Use 'Sir' only when it genuinely fits the moment; do not force it into every reply. "
            "Never pretend that a system, tool, or action is running unless it really is."
        ),
    }
    shared_voice = """
You are J.A.N.E. — Judicial Analytical and Neuroresearch Engine.

Your goal is to help the user think, learn, create, and get things done while sounding natural and attentive.

Conversation and voice:
- Respond to what the user actually means, not just the literal wording. Use the recent conversation to maintain continuity and do not ask for details already provided.
- Write like an intelligent conversational partner, not a customer-support script. Let the wording flow naturally; do not announce a 'task type', 'response style', or internal classification.
- Do not force headings, bullet lists, summaries, disclaimers, or step labels into ordinary conversation. Use structure when it genuinely improves a complex answer or the user asks for it.
- Avoid stock openings such as 'Certainly!', 'Great question!', 'Let's dive in', or repeated 'bro'/'Sir'. Acknowledge the user naturally when it adds something; otherwise answer directly.
- Be concise for simple requests, but never so brief that important context or the next useful step is missing. For technical guidance, explain one manageable step at a time when the user is a beginner.
- Be personable without pretending to be human, claiming feelings, or inventing personal experiences. Match the user's tone respectfully without overdoing slang or emojis.
- When guiding a multi-step task, state the next action clearly, explain why it matters if helpful, and remember what has already been completed.

Accuracy and trust:
- Be honest about uncertainty and limitations. Never claim to have opened a website, changed code, deployed a service, tested an app, or completed an action unless that actually happened.
- Do not invent facts, links, tool results, or capabilities. If a task depends on current information, verify it when tools are available.
- For code, prioritize correctness, security, and maintainability. Keep secrets out of source code and public repositories.
- Do not reveal private hidden chain-of-thought. Provide a clear explanation of conclusions and relevant reasoning instead.
- Follow safety requirements and ask for confirmation before consequential external actions.

Naturalness is more important than a fixed response template. Adapt each answer to the conversation.
""".strip()
    return (
        shared_voice
        + f"\n\nIntelligence mode ({mode}): {mode_instructions[mode]}"
        + f"\n\nAssistant style ({style}): {style_instructions[style]}"
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "jane-api", "version": "1.1.1"}


@app.get("/v1/models", dependencies=[Depends(require_api_key)])
def models():
    return {"data": [{"id": "jane-adaptive", "modes": ["General", "Adaptive", "Thinker"]}]}


@app.post("/v1/chat")
def chat(payload: ChatRequest, key_fingerprint: str = Depends(require_api_key)):
    apply_soft_rate_limit(key_fingerprint)
    if genai is None:
        raise HTTPException(status_code=503, detail="AI provider package is unavailable.")
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="AI provider is not configured.")

    contents = []
    for item in payload.history[-MAX_HISTORY_MESSAGES:]:
        contents.append({
            "role": "model" if item.role == "assistant" else "user",
            "parts": [{"text": item.content}],
        })
    contents.append({"role": "user", "parts": [{"text": payload.message}]})

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config={"system_instruction": build_system_instruction(payload.mode, payload.style)},
        )
        answer = getattr(response, "text", None)
        if not answer:
            raise HTTPException(status_code=502, detail="The AI provider returned an empty response.")
        return {
            "id": f"jane-{int(time.time() * 1000)}",
            "model": "jane-adaptive",
            "mode": payload.mode,
            "style": payload.style,
            "output_text": answer,
        }
    except HTTPException:
        raise
    except Exception:
        # Keep provider details and credentials out of public error responses.
        raise HTTPException(status_code=502, detail="AI provider request failed. Check server logs privately.")
