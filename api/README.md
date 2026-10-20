J.A.N.E. 1.1 — Stage 1 private API
This is an initial private API gateway prototype. It does not modify the existing Streamlit app.
Endpoints
GET /health — public liveness check; does not reveal secrets.
GET /v1/models — requires the X-JANE-API-Key header.
POST /v1/chat — requires the X-JANE-API-Key header.
Required backend environment variables
JANE_API_KEY_SHA256 — SHA-256 hash of the private J.A.N.E. API key, not the raw key.
GEMINI_API_KEY — Gemini provider key, only on the backend.
GEMINI_MODEL — optional model name; defaults to gemini-2.5-flash.
JANE_REQUESTS_PER_MINUTE — optional soft limit; defaults to 12.
Never commit real secrets to GitHub. Configure them in the backend host's secret/environment settings.
Generate a private API key and hash
Run this on a trusted device with Python:
import hashlib, secrets
key = "jane_live_" + secrets.token_urlsafe(32)
print("Save this key securely; it is shown only now:", key)
print("Put this hash in JANE_API_KEY_SHA256:", hashlib.sha256(key.encode()).hexdigest())
Keep the raw key private. Store only the hash as JANE_API_KEY_SHA256. Add the raw key to Streamlit Community Cloud secrets later, when we integrate the app.
Local test
Install dependencies, set environment variables locally (never commit them), then run:
uvicorn main:app --reload
Open /docs for interactive testing. GET /health does not require a key. The other endpoints require X-JANE-API-Key.
Example JSON for POST /v1/chat:
{
  "message": "Explain photosynthesis simply.",
  "mode": "Adaptive",
  "style": "Classic",
  "history": []
}
Stage 1 limitations
The rate limiter is process-local and resets on restart; it is a prototype safeguard, not production-grade quota enforcement.
This version uses one shared private key. It does not yet support per-user keys, an admin dashboard, Firebase ID-token verification, or shared usage metering.
Keep deployment private and use HTTPS. Before exposing this to other apps/users, add durable rate limiting, key rotation/revocation, Firebase identity checks, and stronger usage monitoring.
