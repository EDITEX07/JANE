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
REQUESTS_PER_MINUTE = int(os.getenv("JANE_REQUESTS_PER_MINUTE", "12"))
MAX_PROMPT_CHARS = 4000
MAX_HISTORY_MESSAGES = 12
_recent_requests = defaultdict(deque)

app = FastAPI(title="J.A.N.E. Private API", version="1.1.0",
              description="Private API gateway for the J.A.N.E. assistant.")


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


@app.get("/health")
def health():
    return {"status": "ok", "service": "jane-api", "version": "1.1.0"}


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

    mode_instructions = {
        "General": "Answer naturally, clearly, and directly. Avoid unnecessary headings.",
        "Adaptive": "Identify the user's task and adapt the structure and depth to it. Be natural and clear.",
        "Thinker": "Give a careful, deeper answer with assumptions, alternatives, trade-offs, and uncertainty when relevant. Do not reveal private chain-of-thought; provide concise reasoning summaries instead.",
    }
    style_instructions = {
        "Classic": "Use a natural, friendly, conversational style.",
        "JARVIS": "Use a composed, polished, concise assistant style. Address the user as Sir only when natural. Never claim a system or action is running unless it actually is.",
    }
    system_instruction = (
        "You are J.A.N.E., the Judicial Analytical and Neuroresearch Engine. "
        "Be helpful, accurate, honest about uncertainty, and safety-conscious. "
        f"Intelligence mode: {payload.mode}. {mode_instructions[payload.mode]} "
        f"Assistant style: {payload.style}. {style_instructions[payload.style]}"
    )
    contents = []
    for item in payload.history[-MAX_HISTORY_MESSAGES:]:
        contents.append({"role": "model" if item.role == "assistant" else "user",
                         "parts": [{"text": item.content}]})
    contents.append({"role": "user", "parts": [{"text": payload.message}]})
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config={"system_instruction": system_instruction},
        )
        answer = getattr(response, "text", None)
        if not answer:
            raise HTTPException(status_code=502, detail="The AI provider returned an empty response.")
        return {"id": f"jane-{int(time.time() * 1000)}", "model": "jane-adaptive",
                "mode": payload.mode, "style": payload.style, "output_text": answer}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="AI provider request failed. Check server logs privately.")
