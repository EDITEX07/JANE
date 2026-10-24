import io
import base64
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from openai import OpenAI

st.set_page_config(page_title="J.A.N.E. | AI Workspace", page_icon="🔴", layout="wide", initial_sidebar_state="collapsed")

# -------------------- FINANCIAL PRECISION ENGINE --------------------
# Decimal-based deterministic calculations. Monetary outputs are rounded to paise;
# intermediate values retain high precision. These tools do not replace professional advice.
getcontext().prec = 40
PAISE = Decimal("0.01")

def money(value):
    return Decimal(str(value)).quantize(PAISE, rounding=ROUND_HALF_UP)

def calculate_reducing_emi(principal, annual_rate_percent, months):
    principal = Decimal(str(principal))
    annual_rate_percent = Decimal(str(annual_rate_percent))
    months = int(months)
    if principal <= 0 or annual_rate_percent < 0 or months <= 0:
        raise ValueError("Principal and months must be positive; rate cannot be negative.")
    monthly_rate = annual_rate_percent / Decimal("1200")
    if monthly_rate == 0:
        exact_emi = principal / Decimal(months)
    else:
        growth = (Decimal(1) + monthly_rate) ** months
        exact_emi = principal * monthly_rate * growth / (growth - Decimal(1))
    emi = money(exact_emi)
    # Independently amortize with paise-rounded scheduled payments.
    balance = principal
    total_interest = Decimal(0)
    total_paid = Decimal(0)
    for month in range(1, months + 1):
        interest = money(balance * monthly_rate)
        if month < months:
            payment = emi
            principal_paid = payment - interest
            balance = money(balance - principal_paid)
        else:
            # Settle the remaining principal exactly on the final scheduled payment.
            payment = money(balance + interest)
            principal_paid = balance
            balance = Decimal("0.00")
        total_interest += interest
        total_paid += payment
    return {
        "emi": emi, "total_paid": money(total_paid),
        "total_interest": money(total_interest), "ending_balance": money(balance),
        "monthly_rate_percent": monthly_rate * Decimal(100),
        "months": months, "principal": money(principal),
        "annual_rate_percent": annual_rate_percent,
    }

def calculate_flat_loan(principal, annual_rate_percent, months):
    principal = Decimal(str(principal))
    annual_rate_percent = Decimal(str(annual_rate_percent))
    months = int(months)
    if principal <= 0 or annual_rate_percent < 0 or months <= 0:
        raise ValueError("Principal and months must be positive; rate cannot be negative.")
    years = Decimal(months) / Decimal(12)
    interest = principal * annual_rate_percent / Decimal(100) * years
    total = principal + interest
    return {"emi": money(total / Decimal(months)), "total_paid": money(total),
            "total_interest": money(interest), "months": months,
            "principal": money(principal), "annual_rate_percent": annual_rate_percent}

def fmt_inr(value):
    return f"₹{money(value):,.2f}"

def render_financial_precision_tool():
    with st.expander("🧮 Financial Precision Calculator (verified arithmetic)", expanded=False):
        st.caption("Calculations use Decimal arithmetic. Choose the interest method stated by your lender; fees, insurance and taxes are not included.")
        calc_type = st.radio("Calculation", ["Reducing-balance EMI", "Flat/simple-interest loan"], horizontal=True, key="fp_calc_type")
        c1, c2, c3 = st.columns(3)
        with c1:
            principal = st.number_input("Loan principal (₹)", min_value=0.01, value=100000.0, step=1000.0, format="%.2f", key="fp_principal")
        with c2:
            annual_rate = st.number_input("Annual interest rate (%)", min_value=0.0, value=12.0, step=0.25, format="%.4f", key="fp_rate")
        with c3:
            months = st.number_input("Tenure (months)", min_value=1, max_value=600, value=36, step=1, key="fp_months")
        if st.button("Calculate and verify", key="fp_calculate", type="primary"):
            try:
                result = (calculate_reducing_emi(Decimal(str(principal)), Decimal(str(annual_rate)), int(months))
                          if calc_type == "Reducing-balance EMI"
                          else calculate_flat_loan(Decimal(str(principal)), Decimal(str(annual_rate)), int(months)))
                a, b, c = st.columns(3)
                a.metric("Monthly payment", fmt_inr(result["emi"]))
                b.metric("Total interest", fmt_inr(result["total_interest"]))
                c.metric("Total paid", fmt_inr(result["total_paid"]))
                st.write(f"**Principal:** {fmt_inr(result['principal'])}")
                st.write(f"**Formula method:** {calc_type}; annual rate {Decimal(str(annual_rate))}% over {int(months)} months.")
                st.write(f"**Arithmetic check:** principal + interest = {fmt_inr(Decimal(str(result['principal'])) + Decimal(str(result['total_interest'])))} (minor paise differences may occur in the reducing-balance schedule because each monthly payment is rounded).")
                if calc_type == "Reducing-balance EMI":
                    st.write(f"**Final balance after scheduled payments:** {fmt_inr(result['ending_balance'])}")
                st.caption("Estimate only: actual lender schedules may differ due to payment dates, daily interest, fees, insurance, taxes, and lender-specific rounding. Confirm against the written loan offer.")
            except (ValueError, InvalidOperation, ArithmeticError) as exc:
                st.error(f"Could not calculate these inputs: {exc}")


# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    first_id = str(uuid.uuid4())
    st.session_state.chats = {first_id: {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}}
    st.session_state.current_chat = first_id
for key, default in {
    "profile_name": "Explorer", "api_enabled": True, "uploaded_files": {},
    "pending_prompt": None, "intelligence_mode": "Adaptive", "assistant_style": "Classic",
    "auth_user": None, "auth_token": None, "auth_refresh_token": None, "auth_mode": "signin", "voice_speed": 1.0, "ui_theme": "Red",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Normalize legacy selector values so an older saved "Javis" value cannot crash the app.
if st.session_state.get("assistant_style") in ("Javis", "Jarvis", "JARVIS", "jarvis"):
    st.session_state.assistant_style = "Jarvis"
elif st.session_state.get("assistant_style") != "Classic":
    st.session_state.assistant_style = "Classic"
if st.session_state.get("ui_theme") not in {"Red", "Blue", "Green", "Pink", "Purple", "White"}:
    st.session_state.ui_theme = "Red"

# Live AI requests are always enabled; there is no user-facing on/off switch.
st.session_state.api_enabled = True


def make_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}
    st.session_state.current_chat = chat_id


def active_chat():
    if st.session_state.current_chat not in st.session_state.chats:
        st.session_state.current_chat = next(iter(st.session_state.chats))
    return st.session_state.chats[st.session_state.current_chat]


def suggest_chat_title(prompt):
    """Create a useful, human-readable title from the first substantive message."""
    import re

    text = re.sub(r"\s+", " ", str(prompt or "")).strip(" \t\r\n.,!?;:")
    if not text:
        return None

    # Greetings and conversational openers should never become chat titles.
    normalized = text.lower()
    greeting = re.match(
        r"^(hi|hello|hey|heya|yo|sup|good morning|good afternoon|good evening|how are you|what's up|whats up|thank you|thanks)(\b|[!.?, ]|$)",
        normalized,
    )
    if greeting:
        return None

    # Make common study/learning conversations feel like purposeful sessions.
    study_patterns = [
        (r"^(?:i am |i'm |im )?(?:studying|study|learning|learn|revising|revision of|revise)\s+(?:about\s+|for\s+)?(.+)$", "Studying"),
        (r"^(?:explain|teach me|help me understand)\s+(.+)$", "Understanding"),
        (r"^(?:solve|help me solve)\s+(.+)$", "Solving"),
        (r"^(?:research|researching)\s+(.+)$", "Researching"),
        (r"^(?:plan|planning)\s+(.+)$", "Planning"),
        (r"^(?:build|building|create|creating|develop|developing)\s+(.+)$", "Building"),
    ]
    for pattern, prefix in study_patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            topic = match.group(1).strip(" .!?;:")
            if topic:
                title = f"{prefix} {topic}"
                return title[:56].rstrip(" ,.-")

    # Use the meaningful prompt itself, with enough room to identify its topic.
    text = re.sub(r"^(please\s+)?(can you|could you|would you|i want you to)\s+", "", text, flags=re.IGNORECASE)
    return text[:56].rstrip(" ,.-") or None


def update_chat_title(chat, prompt):
    """Ignore greetings; allow the first meaningful message to name the chat."""
    title = str(chat.get("title", "New conversation")).strip()
    generic_titles = {"", "new conversation", "hi", "hello", "hey", "yo", "sup", "good morning", "good afternoon", "good evening"}
    # Also repair older sessions that were titled from a greeting.
    candidate = suggest_chat_title(prompt)
    if not candidate:
        return
    if title.lower() in generic_titles:
        chat["title"] = candidate


@st.dialog("Choose intelligence")
def intelligence_dialog():
    st.caption("How should J.A.N.E. approach your prompts?")
    descriptions = {
        "General": "Natural, friendly conversation and direct answers.",
        "Adaptive": "Automatically adapts its style to your intent. The default mode.",
        "Thinker": "Deeper analysis for challenging questions and decisions.",
    }
    icons = {"General": "💬", "Adaptive": "🧠", "Thinker": "🔎"}
    for name in ("General", "Adaptive", "Thinker"):
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{icons[name]} {name}**")
                st.caption(descriptions[name])
            with right:
                if st.session_state.intelligence_mode == name:
                    st.markdown("**✓ Active**")
                elif st.button("Select", key=f"mode_select_{name}", use_container_width=True):
                    st.session_state.intelligence_mode = name
                    st.rerun()
    st.caption("Your choice stays active until you change it.")



@st.dialog("Choose assistant style")
def assistant_style_dialog():
    st.caption("Choose how J.A.N.E. speaks to you.")
    options = {
        "Classic": ("💬", "Natural, friendly, everyday J.A.N.E."),
        "Jarvis": ("🛡️", "Formal, disciplined, mission-focused personal assistant."),
    }
    for name in ("Classic", "Jarvis"):
        icon, description = options[name]
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{icon} {name}**")
                st.caption(description)
            with right:
                if st.session_state.assistant_style == name:
                    st.markdown("**✓ Active**")
                elif st.button("Select", key=f"style_select_{name}", use_container_width=True):
                    st.session_state.assistant_style = name
                    st.rerun()
    st.caption("This changes J.A.N.E.'s response style, not its intelligence mode.")

def render_message_content(message):
    content = message.get("content", "")
    if message.get("role") == "user":
        lines = content.splitlines() or [content]
        if len(lines) > 7:
            st.markdown("\n".join(lines[:7]).rstrip() + "…")
            with st.expander("See more"):
                st.markdown(content)
        else:
            st.markdown(content)
    else:
        st.markdown(content)


def render_copy_answer(content, key):
    payload = json.dumps(content, ensure_ascii=False).replace("</", "<\\/")
    components.html(f'''<div style="background:transparent;padding:2px 0 6px"><button id="copy-{key}" style="background:#171217;color:#e9e5eb;border:1px solid #49303b;border-radius:8px;padding:6px 11px;font-size:12px;cursor:pointer">⧉ Copy answer</button><span id="status-{key}" style="margin-left:9px;color:#aaa5b2;font:12px Arial,sans-serif"></span></div>
<script>
const answer={payload};const button=document.getElementById("copy-{key}");const status=document.getElementById("status-{key}");
button.addEventListener("click",async()=>{{try{{await navigator.clipboard.writeText(answer);status.textContent="Copied!";}}catch(err){{const area=document.createElement("textarea");area.value=answer;document.body.appendChild(area);area.select();try{{document.execCommand("copy");status.textContent="Copied!";}}catch(e){{status.textContent="Copy unavailable";}}area.remove();}}}});
</script>''', height=42, scrolling=False)


def render_speak_controls(content, key):
    """Read replies with browser/device speech synthesis, without a TTS API call."""
    safe_key = "voice_" + "".join(ch if ch.isalnum() else "_" for ch in str(key))
    text_payload = json.dumps(str(content or "").strip()[:12000], ensure_ascii=False).replace("</", "<\\/")
    speed = float(st.session_state.get("voice_speed", 1.0))
    components.html(f'''<div style="font-family:Arial,sans-serif;display:flex;gap:8px;align-items:center;background:transparent">
<button id="speak-{safe_key}" style="background:#a10f2b;color:white;border:0;border-radius:18px;padding:8px 13px;cursor:pointer">🔊 Read aloud</button>
<button id="stop-{safe_key}" style="background:#171217;color:#eee;border:1px solid #49303b;border-radius:18px;padding:8px 13px;cursor:pointer">■ Stop</button>
</div>
<script>
(()=>{{
 const text={text_payload};
 const rate={speed};
 const speak=document.getElementById("speak-{safe_key}");
 const stop=document.getElementById("stop-{safe_key}");
 speak.addEventListener("click",()=>{{
   if(!text)return;
   if(!("speechSynthesis" in window)||!("SpeechSynthesisUtterance" in window))return;
   window.speechSynthesis.cancel();
   const utterance=new SpeechSynthesisUtterance(text);
   utterance.rate=Math.max(0.5,Math.min(3,rate));
   window.speechSynthesis.speak(utterance);
 }});
 stop.addEventListener("click",()=>{{if("speechSynthesis" in window)window.speechSynthesis.cancel();}});
}})();
</script>''', height=52, scrolling=False)

# -------------------- STYLING --------------------
st.markdown(r'''<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Inter:wght@400;500;600;700&display=swap');
:root{--jane-red:#ff465c;--jane-border:#402331;--jane-muted:#aaa5b2}
html,body,[class*="css"]{font-family:Inter,system-ui,sans-serif}
.stApp{color:#f4f4f5;background:radial-gradient(ellipse at 50% 0%,#29101b 0%,#130d14 40%,#09090d 100%)}
[data-testid="stHeader"]{background:rgba(11,11,16,.88)}[data-testid="stSidebar"]{background:#0b0b10;border-right:1px solid var(--jane-border)}
.block-container{max-width:1040px;padding-top:1rem;padding-bottom:135px}
.jane-logo-wrap{display:flex;justify-content:center;align-items:center;width:100%;padding:5px 0 8px}
.jane-logo{width:160px;max-width:44vw;height:auto;object-fit:contain;filter:drop-shadow(0 0 7px rgba(255,36,61,.75));animation:janePulse 3s ease-in-out infinite}
.jane-title{font-family:Orbitron,Arial,sans-serif;text-align:center;font-size:clamp(32px,7vw,54px);font-weight:900;letter-spacing:3px;color:#1b080e;-webkit-text-stroke:1.4px #ff465c;text-shadow:0 0 5px #ff243d,0 0 16px rgba(255,36,61,.8);animation:janePulse 3s ease-in-out infinite}
.jane-subtitle{font-size:10px;letter-spacing:3px;text-transform:uppercase;text-align:center;color:#b8a6b0;margin-top:-3px}
.core-wrap{display:flex;justify-content:center;align-items:center;margin:14px auto 23px;height:92px}
.energy-core{position:relative;width:70px;height:70px;border-radius:50%;border:1px solid rgba(255,70,92,.85);box-shadow:0 0 12px #ff243d,inset 0 0 15px rgba(255,36,61,.4);animation:corePulse 2.6s ease-in-out infinite}
.energy-core:before,.energy-core:after{content:"";position:absolute;inset:7px;border:1px solid rgba(255,105,125,.85);border-radius:50%;transform:rotateX(64deg);animation:coreSpin 5s linear infinite}
.energy-core:after{inset:-7px;border-color:rgba(255,36,61,.65);transform:rotateY(68deg);animation:coreSpin 7s linear infinite reverse}
.core-dot{position:absolute;inset:23px;border-radius:50%;background:#ff465c;box-shadow:0 0 9px #ff243d,0 0 22px #ff243d;animation:dotPulse 1.7s ease-in-out infinite}
@keyframes janePulse{0%,100%{opacity:.86;filter:drop-shadow(0 0 4px rgba(255,36,61,.55))}50%{opacity:1;filter:drop-shadow(0 0 13px rgba(255,36,61,.95))}}
@keyframes corePulse{0%,100%{transform:scale(.94);opacity:.78}50%{transform:scale(1.04);opacity:1}}
@keyframes coreSpin{to{transform:rotate(360deg) rotateX(64deg)}}@keyframes dotPulse{0%,100%{transform:scale(.85);opacity:.75}50%{transform:scale(1.12);opacity:1}}
.welcome-wrap{text-align:center;padding:clamp(15px,4vh,42px) 8px 20px}.welcome-title{color:#f5f2f6;font-size:clamp(25px,5vw,35px);font-weight:750;margin:0 0 10px}.welcome-copy{color:var(--jane-muted);font-size:14px;margin:0 auto 18px;max-width:540px}
[data-testid="stChatMessage"]{display:flex!important;align-items:flex-start!important;gap:0!important;width:100%!important;max-width:100%!important;box-sizing:border-box!important;background:transparent!important;border:0!important;padding:0!important;margin:0 0 14px!important}
[data-testid="stChatMessage"] [data-testid^="chatAvatarIcon"],[data-testid="stChatMessage"] [data-testid*="Avatar"]{display:none!important}
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"],[data-testid="stChatMessage"] [data-testid="stChatMessageContent"]>div,[data-testid="stChatMessage"] .stChatMessageContent{box-sizing:border-box!important;flex:0 1 auto!important;min-width:0!important;width:auto!important;overflow-wrap:anywhere!important}
/* Explicit role markers make styling independent of Streamlit avatar test IDs. */
.jane-user-marker,.jane-assistant-marker{display:none!important}
[data-testid="stChatMessage"]{min-width:0!important}
[data-testid="stChatMessage"]:has(.jane-user-marker){justify-content:flex-end!important}
[data-testid="stChatMessage"]:has(.jane-user-marker) [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has(.jane-user-marker) .stChatMessageContent{display:block!important;flex:0 1 auto!important;width:fit-content!important;max-width:min(88%,760px)!important;margin:0 0 0 auto!important;padding:9px 16px 9px!important;color:#fff!important;background:linear-gradient(115deg,rgba(103,15,37,.84),rgba(52,13,29,.94),rgba(125,20,43,.84),rgba(42,11,24,.94))!important;background-size:320% 320%!important;animation:userGradientFlow 10s ease-in-out infinite, userBubbleGlow 5s ease-in-out infinite!important;border:1px solid rgba(255,70,92,.48)!important;border-radius:20px 20px 6px 20px!important;box-shadow:0 5px 24px rgba(255,35,70,.12),inset 0 1px rgba(255,255,255,.055)!important;overflow-wrap:anywhere!important;position:relative!important}
@keyframes userGradientFlow{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
@keyframes userBubbleGlow{0%,100%{border-color:rgba(255,70,92,.38);box-shadow:0 4px 18px rgba(255,35,70,.09),inset 0 1px rgba(255,255,255,.04)}50%{border-color:rgba(255,95,118,.7);box-shadow:0 5px 25px rgba(255,35,70,.17),inset 0 1px rgba(255,255,255,.08)}}
/* Assistant replies stay unboxed. */
[data-testid="stChatMessage"]:has(.jane-assistant-marker){justify-content:flex-start!important}
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has(.jane-assistant-marker) .stChatMessageContent{display:block!important;flex:1 1 auto!important;width:100%!important;max-width:100%!important;margin:0 auto 0 0!important;padding:4px 0 8px!important;color:#f5f2f6!important;background:transparent!important;border:0!important;border-radius:0!important;box-shadow:none!important;overflow-wrap:anywhere!important;text-align:left!important}
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stMarkdownContainer"] *{text-align:left!important}
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stMarkdownContainer"] ul,
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stMarkdownContainer"] ol{padding-left:1.5rem!important;margin-left:0!important}
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stMarkdownContainer"] table{margin-left:0!important;margin-right:auto!important}
[data-testid="stChatMessage"]:has(.jane-user-marker) [data-testid="stMarkdownContainer"]{transform:none!important;margin:0!important;padding:0!important}
[data-testid="stChatMessage"]:has(.jane-user-marker) [data-testid="stChatMessageContent"]>div{min-width:0!important;max-width:100%!important}
[data-testid="stChatMessage"]:has(.jane-user-marker) [data-testid="stMarkdownContainer"] p{margin-top:0!important;margin-bottom:0!important;line-height:1.5!important}
[data-testid="stChatMessage"]:has(.jane-user-marker){overflow:visible!important}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"]{color:inherit!important;overflow-wrap:anywhere!important}[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p:first-child{margin-top:0!important}[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p:last-child{margin-bottom:0!important}
[data-testid="stChatInput"]{position:relative!important;background:linear-gradient(125deg,#a10f2b 0%,#5a1023 32%,#1b0e16 67%,#08080b 100%)!important;border:1px solid #ff465c!important;border-radius:22px!important;padding:38px 13px 8px!important;min-height:112px!important;max-height:156px!important;overflow:visible!important;box-shadow:0 5px 24px rgba(0,0,0,.45)!important}
div[class*="st-key-open_intelligence_dialog"]{position:fixed!important;z-index:10002!important;left:max(18px,calc((100vw - 900px)/2 + 16px))!important;bottom:169px!important;width:auto!important;max-width:190px!important;margin:0!important}
div[class*="st-key-open_intelligence_dialog"] button{min-height:28px!important;height:28px!important;width:auto!important;padding:2px 10px!important;border-radius:999px!important;background:rgba(12,8,13,.92)!important;border:1px solid rgba(255,150,165,.55)!important;color:#fff!important;font-size:12px!important;white-space:nowrap!important}
div[class*="st-key-open_assistant_style_dialog"]{position:fixed!important;z-index:10002!important;left:max(205px,calc((100vw - 900px)/2 + 205px))!important;bottom:169px!important;width:auto!important;max-width:160px!important;margin:0!important}
div[class*="st-key-open_assistant_style_dialog"] button{min-height:28px!important;height:28px!important;width:auto!important;padding:2px 10px!important;border-radius:999px!important;background:rgba(12,8,13,.92)!important;border:1px solid rgba(255,150,165,.55)!important;color:#fff!important;font-size:12px!important;white-space:nowrap!important}
[data-testid="stChatInput"]:focus-within{border-color:#ff7182!important;box-shadow:0 0 0 1px #ff465c,0 5px 24px rgba(0,0,0,.38)!important}[data-testid="stChatInput"] textarea{box-sizing:border-box!important;width:100%!important;color:#fff!important;background:transparent!important;font-size:16px!important;line-height:1.5!important;min-height:42px!important;max-height:7.2em!important;overflow-y:auto!important;resize:none!important;padding-right:3.2rem!important}
[data-testid="stChatInput"] button{position:absolute!important;right:10px!important;bottom:10px!important;z-index:5!important;flex:0 0 auto!important;min-width:38px!important;width:38px!important;height:38px!important;display:flex!important;align-items:center!important;justify-content:center!important}
[data-testid="stChatInput"] form,[data-testid="stChatInput"]>div{position:relative!important;min-width:0!important;box-sizing:border-box!important}[data-testid="stChatInput"] textarea::placeholder{color:#d0c5cc!important;opacity:1!important}[data-testid="stChatInput"] button{background:#ff465c!important;color:#fff!important;border:0!important;border-radius:50%!important}
.stButton>button{min-height:42px;border-radius:12px;border:1px solid var(--jane-border);background:#211923;color:#f4f4f5;transition:border-color .2s ease}.stButton>button:hover{border-color:var(--jane-red);color:#fff}[data-testid="stFileUploader"]{background:rgba(21,19,26,.85);border-radius:14px}h1,h2,h3{color:#ff5267}p,label,li{overflow-wrap:anywhere}.jane-footer{color:#898491;font-size:11px;text-align:center;padding:12px 4px 5px}
@media(max-width:768px){.block-container{padding:.7rem .65rem 130px!important;max-width:100%}.jane-logo{width:130px}.jane-subtitle{font-size:9px;letter-spacing:2px}.core-wrap{height:75px;margin:8px auto 15px}.energy-core{width:58px;height:58px}[data-testid="stChatInput"]{border-radius:20px!important;padding:38px 12px 8px!important;min-height:112px!important;max-height:156px!important}div[class*="st-key-open_intelligence_dialog"]{left:24px!important;bottom:169px!important;max-width:180px!important}div[class*="st-key-open_assistant_style_dialog"]{left:190px!important;bottom:169px!important;max-width:145px!important}.stButton>button{min-height:44px;font-size:14px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important}}
</style>''', unsafe_allow_html=True)


# -------------------- UI COLOR THEMES --------------------
THEMES = {
    "Red":    {"accent": "#ff465c", "bright": "#ff7182", "glow": "255,70,92", "deep": "#5a1023", "bubble": "103,15,37"},
    "Blue":   {"accent": "#4da3ff", "bright": "#83c0ff", "glow": "77,163,255", "deep": "#102b52", "bubble": "15,43,83"},
    "Green":  {"accent": "#35d07f", "bright": "#7af0ae", "glow": "53,208,127", "deep": "#0e422d", "bubble": "12,66,44"},
    "Pink":   {"accent": "#ff5fc8", "bright": "#ff9cde", "glow": "255,95,200", "deep": "#55103f", "bubble": "83,16,63"},
    "Purple": {"accent": "#a879ff", "bright": "#c5a6ff", "glow": "168,121,255", "deep": "#30154f", "bubble": "48,21,79"},
    "White":  {"accent": "#f4f4f7", "bright": "#ffffff", "glow": "220,220,235", "deep": "#3a3a46", "bubble": "55,55,68"},
}
theme = THEMES.get(st.session_state.get("ui_theme", "Red"), THEMES["Red"])
st.markdown(f'''<style>
:root{{--jane-red:{theme["accent"]};--jane-border:rgba({theme["glow"]},.42);--jane-accent:{theme["accent"]};}}
.jane-title{{-webkit-text-stroke-color:{theme["accent"]}!important;text-shadow:0 0 5px {theme["accent"]},0 0 16px rgba({theme["glow"]},.8)!important;}}
.jane-logo{{filter:drop-shadow(0 0 7px rgba({theme["glow"]},.75))!important;}}
.energy-core{{border-color:rgba({theme["glow"]},.85)!important;box-shadow:0 0 12px {theme["accent"]},inset 0 0 15px rgba({theme["glow"]},.4)!important;}}
.energy-core:before{{border-color:rgba({theme["glow"]},.85)!important;}}
.energy-core:after{{border-color:rgba({theme["glow"]},.65)!important;}}
.core-dot{{background:{theme["accent"]}!important;box-shadow:0 0 9px {theme["accent"]},0 0 22px {theme["accent"]}!important;}}
[data-testid="stChatMessage"]:has(.jane-user-marker) [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has(.jane-user-marker) .stChatMessageContent{{
 background:linear-gradient(115deg,rgba({theme["bubble"]},.9),rgba({theme["glow"]},.10),rgba({theme["bubble"]},.94))!important;
 border-color:rgba({theme["glow"]},.55)!important;
 box-shadow:0 5px 24px rgba({theme["glow"]},.12),inset 0 1px rgba(255,255,255,.055)!important;
}}
[data-testid="stChatInput"]{{border-color:{theme["accent"]}!important;background:linear-gradient(125deg,{theme["accent"]} 0%,{theme["deep"]} 32%,#1b0e16 67%,#08080b 100%)!important;}}
[data-testid="stChatInput"]:focus-within{{border-color:{theme["bright"]}!important;box-shadow:0 0 0 1px {theme["accent"]},0 5px 24px rgba(0,0,0,.38)!important;}}
[data-testid="stChatInput"] button{{background:{theme["accent"]}!important;color:{"#17121a" if st.session_state.get("ui_theme")=="White" else "#fff"}!important;}}
.stButton>button:hover{{border-color:{theme["accent"]}!important;}}
h1,h2,h3{{color:{theme["accent"]}!important;}}
.jane-login-title,.jane-card-icon{{color:{theme["accent"]}!important;text-shadow:0 0 8px {theme["accent"]},0 0 24px rgba({theme["glow"]},.65)!important;}}
.jane-login-kicker,.jane-feature-rail span{{color:{theme["accent"]}!important;}}
.jane-login-card{{border-color:rgba({theme["glow"]},.7)!important;}}
.jane-login-foot:before,.jane-login-foot:after{{background:linear-gradient(90deg,transparent,{theme["accent"]})!important;}}
</style>''', unsafe_allow_html=True)

# -------------------- FIREBASE AUTHENTICATION --------------------
def firebase_auth_request(endpoint, email, password):
    # Firebase Authentication REST API helper; API key stays in Streamlit Secrets.
    try:
        api_key = st.secrets.get("FIREBASE_API_KEY", "")
    except Exception:
        api_key = ""
    if not api_key:
        raise RuntimeError("Firebase is not configured. Add FIREBASE_API_KEY to Streamlit Secrets.")
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={api_key}"
    body = json.dumps({"email": email.strip(), "password": password, "returnSecureToken": True}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            code = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "Authentication failed")
        except Exception:
            code = "Authentication failed"
        friendly = {
            "EMAIL_EXISTS": "An account with this email already exists. Try signing in.",
            "OPERATION_NOT_ALLOWED": "Email/password sign-in is disabled in Firebase Console → Authentication → Sign-in method.",
            "WEAK_PASSWORD": "Choose a stronger password with at least 6 characters.",
            "EMAIL_NOT_FOUND": "No account was found for this email. Create an account first.",
            "INVALID_PASSWORD": "That password doesn't match this account.",
            "INVALID_LOGIN_CREDENTIALS": "Email or password is incorrect.",
            "USER_DISABLED": "This account has been disabled.",
            "INVALID_EMAIL": "Enter a valid email address.",
            "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please wait a while and try again.",
            "API_KEY_INVALID": "The Firebase API key is invalid. Check Streamlit Secrets.",
        }
        raise ValueError(friendly.get(code, f"Firebase authentication failed: {code}")) from None


# -------------------- FIRESTORE MEMORY 2.0 --------------------
def _firebase_project_id():
    try:
        return str(st.secrets.get("FIREBASE_PROJECT_ID", "")).strip()
    except Exception:
        return ""


def _refresh_firebase_id_token():
    """Refresh the short-lived Firebase ID token using the sign-in refresh token."""
    refresh_token = st.session_state.get("auth_refresh_token")
    if not refresh_token:
        raise RuntimeError("Your sign-in session has expired. Sign out and sign in again, then retry chat history.")
    try:
        api_key = str(st.secrets.get("FIREBASE_API_KEY", "")).strip()
    except Exception:
        api_key = ""
    if not api_key:
        raise RuntimeError("Add FIREBASE_API_KEY to Streamlit Secrets.")
    url = f"https://securetoken.googleapis.com/v1/token?key={api_key}"
    body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise RuntimeError("Your Firebase session could not be refreshed. Sign out and sign in again.") from None
    st.session_state.auth_token = result.get("id_token")
    if result.get("refresh_token"):
        st.session_state.auth_refresh_token = result["refresh_token"]
    if not st.session_state.auth_token:
        raise RuntimeError("Firebase did not return a refreshed sign-in token. Sign in again.")
    return st.session_state.auth_token


def _firestore_request(method, path, payload=None):
    """Call Firestore REST using the user's Firebase ID token, refreshing once if expired."""
    user = st.session_state.get("auth_user") or {}
    token = st.session_state.get("auth_token")
    project_id = _firebase_project_id()
    if not user.get("uid") or not token:
        raise RuntimeError("Sign in to use personal memory and saved chat history.")
    if not project_id:
        raise RuntimeError("Add FIREBASE_PROJECT_ID to Streamlit Secrets to enable memory and chat history.")
    url = "https://firestore.googleapis.com/v1/" + path.lstrip("/")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def send(current_token):
        request = urllib.request.Request(url, data=data, headers={
            "Authorization": "Bearer " + current_token,
            "Content-Type": "application/json; charset=utf-8",
        }, method=method)
        return urllib.request.urlopen(request, timeout=12)

    try:
        try:
            response = send(token)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                token = _refresh_firebase_id_token()
                response = send(token)
            else:
                raise
        with response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:350]
        if exc.code == 401:
            raise RuntimeError("Firebase rejected the sign-in token. Sign out and sign in again.") from None
        if exc.code == 403:
            raise RuntimeError("Firestore returned PERMISSION_DENIED. Check that FIREBASE_PROJECT_ID is the correct project and publish rules allowing /users/{userId}/chats/{chatId} and /users/{userId}/memories/{memoryId} only when request.auth.uid == userId. Firebase detail: " + detail) from None
        raise RuntimeError(f"Firestore request failed ({exc.code}). {detail}") from None


def _memory_collection_path():
    uid = (st.session_state.get("auth_user") or {}).get("uid", "")
    if not uid or "/" in uid:
        raise RuntimeError("A valid signed-in user is required.")
    return f"projects/{_firebase_project_id()}/databases/(default)/documents/users/{uid}/memories"


def _chat_collection_path():
    uid = (st.session_state.get("auth_user") or {}).get("uid", "")
    if not uid or "/" in uid:
        raise RuntimeError("A valid signed-in user is required.")
    return f"projects/{_firebase_project_id()}/databases/(default)/documents/users/{uid}/chats"


def _firestore_string(value):
    return {"stringValue": str(value)}


def _decode_firestore_value(value):
    if "stringValue" in value: return value["stringValue"]
    if "booleanValue" in value: return value["booleanValue"]
    if "integerValue" in value:
        try: return int(value["integerValue"])
        except Exception: return value["integerValue"]
    if "timestampValue" in value: return value["timestampValue"]
    return None


def save_chat_history(chat_id, chat_data):
    """Persist a user's conversation as a JSON string in their own Firestore chat document."""
    if not st.session_state.get("auth_user"):
        return False
    if not chat_id or "/" in str(chat_id) or ".." in str(chat_id):
        raise RuntimeError("Invalid chat ID.")
    # Binary image data and uploaded file bytes are deliberately not stored in chat history.
    safe_messages = []
    for message in chat_data.get("messages", []):
        safe = {k: v for k, v in message.items() if k not in ("image_bytes",)}
        if isinstance(safe.get("attachments"), list):
            safe["attachments"] = [str(name) for name in safe["attachments"]]
        safe_messages.append(safe)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    payload = {
        "id": str(chat_id),
        "title": str(chat_data.get("title", "New conversation"))[:160],
        "created": str(chat_data.get("created", now)),
        "updatedAt": now,
        "messages": safe_messages,
    }
    document = {"fields": {
        "payload": {"stringValue": json.dumps(payload, ensure_ascii=False)},
        "title": {"stringValue": payload["title"]},
        "created": {"stringValue": payload["created"]},
        "updatedAt": {"timestampValue": now},
    }}
    path = _chat_collection_path() + "/" + str(chat_id)
    try:
        _firestore_request("PATCH", path + "?updateMask.fieldPaths=payload&updateMask.fieldPaths=title&updateMask.fieldPaths=created&updateMask.fieldPaths=updatedAt", document)
    except RuntimeError as exc:
        if "(404)" not in str(exc):
            raise
        _firestore_request("POST", _chat_collection_path() + "?documentId=" + str(chat_id), document)
    return True


def load_chat_history():
    """Load persisted conversations for the currently authenticated account."""
    if not st.session_state.get("auth_user"):
        return {}
    result = _firestore_request("GET", _chat_collection_path())
    chats = {}
    for document in result.get("documents", []):
        fields = {k: _decode_firestore_value(v) for k, v in document.get("fields", {}).items()}
        try:
            payload = json.loads(fields.get("payload", "{}"))
            chat_id = str(payload.get("id") or document.get("name", "").rsplit("/", 1)[-1])
            messages = payload.get("messages", [])
            if not isinstance(messages, list):
                messages = []
            chats[chat_id] = {
                "title": str(payload.get("title", "New conversation")),
                "created": str(payload.get("created", "")),
                "messages": messages,
            }
        except (TypeError, ValueError):
            continue
    return chats


def delete_chat_history(chat_id):
    if not chat_id or "/" in str(chat_id) or ".." in str(chat_id):
        raise RuntimeError("Invalid chat ID.")
    _firestore_request("DELETE", _chat_collection_path() + "/" + str(chat_id))


def load_memories():
    if not st.session_state.get("auth_user"):
        return []
    result = _firestore_request("GET", _memory_collection_path())
    memories = []
    for doc in result.get("documents", []):
        fields = {k: _decode_firestore_value(v) for k, v in doc.get("fields", {}).items()}
        memories.append({"id": doc.get("name", "").rsplit("/", 1)[-1], **fields})
    memories.sort(key=lambda item: str(item.get("updatedAt", "")), reverse=True)
    return memories


def save_memory(text, source="automatic"):
    text = " ".join(str(text or "").split()).strip()
    if not text or len(text) > 600:
        return False
    # Do not save duplicates; compare normalized memory text.
    memories = load_memories()
    normalized = text.casefold().rstrip(".! ")
    for item in memories:
        if str(item.get("text", "")).casefold().rstrip(".! ") == normalized:
            return False
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    fields = {
        "text": {"stringValue": text},
        "source": {"stringValue": source},
        "createdAt": {"timestampValue": now},
        "updatedAt": {"timestampValue": now},
    }
    doc_id = "m_" + uuid.uuid4().hex
    _firestore_request("POST", _memory_collection_path() + "?documentId=" + doc_id, {"fields": fields})
    return True


def delete_memory(memory_id):
    if not memory_id or "/" in memory_id or ".." in memory_id:
        raise RuntimeError("Invalid memory ID.")
    _firestore_request("DELETE", _memory_collection_path() + "/" + memory_id)


def extract_memories(user_text, assistant_text):
    """Use Gemini to extract a few durable, non-sensitive facts; never for Guest sessions."""
    if not st.session_state.get("auth_user"):
        return []
    # Explicit remember commands are handled locally without an extraction call.
    try:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        instruction = (
            "Extract up to 3 durable, useful user memories from the exchange. Return ONLY a JSON array of short strings. "
            "Save preferences, long-running projects, goals, and stable workflow choices. Do not save one-off questions, "
            "temporary details, passwords, API keys, precise location, financial account details, health data, or other sensitive personal
