import io
import base64
import json
import uuid
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from openai import OpenAI

st.set_page_config(page_title="J.A.N.E. | AI Workspace", page_icon="🔴", layout="wide", initial_sidebar_state="collapsed")

def clean_model_answer(value):
    """Remove common provider/task metadata accidentally emitted before the answer."""
    import re
    text = str(value or "").strip()
    # Remove only leading internal-style labels, not labels that are part of a real answer.
    patterns = [
        r"^(?:user\s+safety|response\s+safety)\s*:\s*(?:safe|unsafe|unknown)\s*\n?",
        r"^(?:task\s*type|task|reply\s*type|response\s*type|answer\s*type|style)\s*:\s*[^\n]*\n+",
        r"^(?:here(?:'s| is) the|the)\s+(?:task|response|reply)\s*(?:type|style)\s*:\s*[^\n]*\n+",
    ]
    previous = None
    while previous != text:
        previous = text
        for pattern in patterns:
            text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)
        text = text.lstrip()
    return text or "I couldn't generate a useful answer just now. Please try again."


# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    first_id = str(uuid.uuid4())
    st.session_state.chats = {first_id: {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}}
    st.session_state.current_chat = first_id
for key, default in {
    "profile_name": "Vihaan Shirale", "api_enabled": True, "uploaded_files": {},
    "pending_prompt": None, "intelligence_mode": "Adaptive", "assistant_style": "Classic", "ui_theme": "Original Blue",
    "auth_user": None, "auth_token": None, "auth_refresh_token": None, "auth_mode": "signin", "voice_speed": 1.0,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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
        "JARVIS": ("🛡️", "Formal, disciplined, mission-focused personal assistant."),
    }
    for name in ("Classic", "JARVIS"):
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




# Selectable workspace color themes.
_THEME_PALETTES = {
    "Original Blue": dict(accent="#438bff", glow="#1d5fd1", bg1="#0b1b36", bg2="#080b13", bubble1="#123a78", bubble2="#0c2148", border="#356fc7", text="#f4f7ff", muted="#b8c7e5", composer1="#153d7c", composer2="#080b13"),
    "Green": dict(accent="#36d399", glow="#13875d", bg1="#0b3027", bg2="#080e0c", bubble1="#125640", bubble2="#0b2b22", border="#258c68", text="#f0fff8", muted="#b5d9ca", composer1="#126047", composer2="#080e0c"),
    "Pink": dict(accent="#ff69b4", glow="#c72d7f", bg1="#351126", bg2="#100910", bubble1="#78234f", bubble2="#351329", border="#c74788", text="#fff3fa", muted="#e0b8ce", composer1="#76234f", composer2="#100910"),
    "Purple": dict(accent="#b58aff", glow="#7745c7", bg1="#24133f", bg2="#0b0912", bubble1="#4d287c", bubble2="#26143f", border="#8157c4", text="#f8f3ff", muted="#c9b9e5", composer1="#4d287c", composer2="#0b0912"),
    "Classic White": dict(accent="#333333", glow="#999999", bg1="#f5f5f5", bg2="#ffffff", bubble1="#e7e7e7", bubble2="#f4f4f4", border="#c7c7c7", text="#171717", muted="#555555", composer1="#eeeeee", composer2="#ffffff"),
}
_theme = _THEME_PALETTES.get(st.session_state.get("ui_theme", "Original Blue"), _THEME_PALETTES["Original Blue"])
_white_theme = st.session_state.get("ui_theme") == "Classic White"
_white_overrides = """
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"], label, p, li {color:#222!important}
.welcome-title,.jane-login-heading,.jane-card-title {color:#171717!important}
.welcome-copy,.jane-login-sub,.jane-card-copy {color:#444!important}
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stChatMessageContent"] {color:#171717!important}
.stButton>button {background:#fff!important;color:#222!important}
""" if _white_theme else ""
st.markdown(f"""<style>
:root{{--jane-red:{_theme['accent']};--jane-border:{_theme['border']};--jane-muted:{_theme['muted']}}}
.stApp{{color:{_theme['text']}!important;background:radial-gradient(ellipse at 50% 0%,{_theme['bg1']} 0%,{_theme['bg2']} 78%)!important}}
[data-testid="stSidebar"]{{background:{_theme['bg2']}!important;border-right:1px solid {_theme['border']}!important}}
.jane-title{{color:{_theme['bg2']}!important;-webkit-text-stroke:1.4px {_theme['accent']}!important;text-shadow:0 0 5px {_theme['accent']},0 0 16px {_theme['glow']}!important}}
.jane-logo{{filter:drop-shadow(0 0 7px {_theme['glow']})!important}}
.energy-core{{border-color:{_theme['accent']}!important;box-shadow:0 0 12px {_theme['glow']},inset 0 0 15px {_theme['glow']}!important}}
.energy-core:before{{border-color:{_theme['accent']}!important}}.energy-core:after{{border-color:{_theme['glow']}!important}}
.core-dot{{background:{_theme['accent']}!important;box-shadow:0 0 9px {_theme['accent']},0 0 22px {_theme['glow']}!important}}
h1,h2,h3,.jane-subtitle,.jane-feature-rail span{{color:{_theme['accent']}!important}}
[data-testid="stChatMessage"]:has(.jane-user-marker) [data-testid="stChatMessageContent"],
[data-testid="stChatMessage"]:has(.jane-user-marker) .stChatMessageContent{{color:{_theme['text']}!important;background:linear-gradient(115deg,{_theme['bubble1']},{_theme['bubble2']},{_theme['bubble1']})!important;border-color:{_theme['border']}!important;box-shadow:0 5px 24px {_theme['glow']}33!important}}
[data-testid="stChatMessage"]:has(.jane-assistant-marker) [data-testid="stChatMessageContent"]{{color:{_theme['text']}!important}}
[data-testid="stChatInput"]{{background:linear-gradient(125deg,{_theme['composer1']},{_theme['composer2']})!important;border-color:{_theme['accent']}!important}}
[data-testid="stChatInput"] textarea{{color:{_theme['text']}!important}}
[data-testid="stChatInput"] textarea::placeholder{{color:{_theme['muted']}!important}}
[data-testid="stChatInput"] button{{background:{_theme['accent']}!important;color:{'#171717' if _white_theme else '#ffffff'}!important}}
.stButton>button{{border-color:{_theme['border']}!important;color:{_theme['text']}!important}}
.stButton>button:hover{{border-color:{_theme['accent']}!important}}
.jane-footer{{color:{_theme['muted']}!important}}
{_white_overrides}
</style>""", unsafe_allow_html=True)


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
            "temporary details, passwords, API keys, precise location, financial account details, health data, or other sensitive personal data. "
            "Do not infer facts not explicitly supported by the exchange. Return [] if nothing merits memory. Each string max 240 characters.\n"
            + "USER: " + str(user_text)[:2500] + "\nASSISTANT: " + str(assistant_text)[:1200]
        )
        result = client.models.generate_content(model="gemini-3.5-flash-lite", contents=instruction)
        raw = (result.text or "[]").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
        return [" ".join(str(x).split())[:240] for x in parsed if isinstance(x, str) and x.strip()][:3] if isinstance(parsed, list) else []
    except Exception:
        return []


def handle_explicit_memory_command(prompt):
    """Return a memory payload for explicit remember requests, otherwise None."""
    import re
    match = re.match(r"^\s*(?:j\.a\.n\.e\.\s*)?(?:remember(?:\s+that)?|save\s+to\s+memory)\s*[:,-]?\s*(.+?)\s*$", prompt, re.I | re.S)
    return match.group(1).strip() if match else None


# -------------------- FIRST-RUN WELCOME / SIGN-IN GATE --------------------
if "jane_entry_screen" not in st.session_state:
    st.session_state.jane_entry_screen = "welcome"
if "jane_entry_method" not in st.session_state:
    st.session_state.jane_entry_method = "email"
if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "signin"
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None

if st.session_state.get("auth_user"):
    st.session_state.jane_entry_screen = "workspace"
    active_uid = st.session_state.auth_user.get("uid", "")
    if active_uid and st.session_state.get("chat_history_loaded_uid") != active_uid:
        try:
            saved_chats = load_chat_history()
            if saved_chats:
                # Keep current in-session chats while merging the account's saved history.
                saved_chats.update(st.session_state.chats)
                st.session_state.chats = saved_chats
                st.session_state.current_chat = next(reversed(saved_chats))
            st.session_state.chat_history_loaded_uid = active_uid
            st.session_state.chat_history_error = ""
        except Exception as exc:
            st.session_state.chat_history_error = str(exc)

if st.session_state.jane_entry_screen != "workspace":
    st.markdown(r'''<style>
.block-container{max-width:900px!important;padding-top:.35rem!important;padding-bottom:2rem!important}
[data-testid="stSidebar"]{display:none!important}
.jane-login-shell{position:relative;overflow:hidden;text-align:center;padding:10px 10px 24px;border-radius:26px;background:radial-gradient(ellipse at 50% 14%,rgba(109,13,35,.26),transparent 48%),linear-gradient(180deg,rgba(8,7,11,.65),rgba(9,8,12,.97));}
.jane-portrait-frame{position:relative;width:min(100%,430px);margin:0 auto -6px;}
.jane-portrait{width:100%;height:auto;max-height:380px;object-fit:contain;object-position:center;filter:drop-shadow(0 0 22px rgba(255,28,67,.25));animation:portraitFloat 5s ease-in-out infinite;mask-image:linear-gradient(to bottom,black 0%,black 75%,transparent 100%);}
.jane-login-title{font-family:Orbitron,Inter,sans-serif;font-weight:900;letter-spacing:5px;font-size:clamp(42px,8vw,68px);line-height:1;color:#ff526b;text-shadow:0 0 8px #ff123e,0 0 24px rgba(255,22,62,.8);animation:loginGlow 3s ease-in-out infinite;margin:0}
.jane-login-kicker{letter-spacing:4px;font-size:10px;color:#ff6378;text-transform:uppercase;margin:10px 0 28px}
.jane-login-heading{font-size:clamp(25px,4vw,34px);font-weight:750;color:#f7f2f5;margin:0 0 8px}
.jane-login-sub{font-size:15px;color:#aeb3c3;line-height:1.65;margin:0 auto 12px;max-width:560px}
.jane-feature-rail{font-size:10px;letter-spacing:3px;color:#aaa8b7;text-align:center;margin:0 0 15px}.jane-feature-rail span{color:#ff465c}
.jane-login-card{height:100%;min-height:255px;border:1px solid rgba(255,54,85,.8);border-radius:20px;padding:23px 18px 20px;background:linear-gradient(145deg,rgba(54,10,25,.7),rgba(13,11,17,.93));box-shadow:0 0 25px rgba(255,20,60,.12),inset 0 1px rgba(255,255,255,.04);text-align:center}
.jane-guest-card{border-color:rgba(125,133,153,.45);background:linear-gradient(145deg,rgba(19,20,27,.85),rgba(8,9,13,.96));box-shadow:none}
.jane-card-icon{font-size:34px;color:#ff465c;margin:0 0 8px;text-shadow:0 0 12px rgba(255,20,60,.55)}.jane-card-title{font-size:21px;font-weight:650;color:#f8f5f8;margin:0 0 9px}.jane-card-copy{font-size:13px;color:#aeb3c3;line-height:1.6;min-height:44px;margin-bottom:15px}
.jane-login-foot{display:flex;align-items:center;gap:14px;justify-content:center;color:#8e91a0;font-size:10px;letter-spacing:3px;margin:30px 0 4px}.jane-login-foot:before,.jane-login-foot:after{content:"";width:90px;height:1px;background:linear-gradient(90deg,transparent,#ff465c)}.jane-login-foot:after{transform:scaleX(-1)}
@keyframes loginGlow{0%,100%{filter:drop-shadow(0 0 4px rgba(255,22,62,.45))}50%{filter:drop-shadow(0 0 15px rgba(255,22,62,.95)}}@keyframes portraitFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
.stButton>button{min-height:48px;border-radius:999px!important;font-weight:600}@media(max-width:640px){.jane-login-shell{padding:4px 3px 18px}.jane-portrait-frame{width:min(100%,330px)}.jane-login-kicker{margin-bottom:22px}.jane-login-card{min-height:0;padding:20px 15px}.jane-card-copy{min-height:0}}@media(prefers-reduced-motion:reduce){.jane-portrait,.jane-login-title{animation:none!important}}
</style>''', unsafe_allow_html=True)
    st.markdown('<div class="jane-login-shell">', unsafe_allow_html=True)
    st.markdown('<div class="jane-feature-rail">CHAT &nbsp;&nbsp; ANALYZE &nbsp;&nbsp; CREATE &nbsp;&nbsp; REMEMBER &nbsp;&nbsp; <span>GROW</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="jane-portrait-frame"><img class="jane-portrait" src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAGuAlgDASIAAhEBAxEB/8QAHAAAAgIDAQEAAAAAAAAAAAAAAAECAwQFBgcI/8QATBAAAQMCBAMFBQYCCQMBBwUBAQACAwQRBRIhMQZBURMiYXGBBxQykaEjQlKxwdEVYggkM1NygpLh8BZDorIlJmNzwtLxJzREVGTi/8QAGwEAAgMBAQEAAAAAAAAAAAAAAAECAwQFBgcI/8QATAEAAgIBAgQIIDwFAwQBAwUAAQIAAxEEEiETMUFRUoEFYYKhsbLR0hQVFic0cYGRscE3UnIywfBC4SNCY/EzQ5OiJDSSsnSzwuII/90aBAAA4QEA3ADvX73zV38I34O0P/T3oP8AQ9aD8mN+DtD/ANO+g/JjfgbS/wDUXoP9D/S/Y47kX9J30L83m3f8I34O0X/TnoX5sP4S/Y3zXf8I34N0P8A31Xm72L8yX9J+m/m/O1/R3/CvMv5p9j/AEO8y/nH2O/S3aN/m2+bE8+zX5uzL5p9jfM/zff4x9s31a/y3jrm/m/2O83PzU/4k83XzZfpX5ptm1f82/32ebn5r9q/M182f4i/pX5j/m/wB9v83f3s+b+bf4v33x3203f5t/vv5180+x3m0/m7+b/Yr9b/1j/m8P2b/AH1+bf8AEf8AEPM353fmL+bfY84M1m2+/vN/01a//I3j81P4h4/N545m6ebT4sX6W+b3fM0P8x2x/vFvm/M1X41539o9/M0v58zN45+e3/EfvM8y+LgO3eeb33x/Meb822Xy/i+f04/wAMe63P09o+fM7+fT8422A4L57zPf57zcebfi+a/m/2e8+8+b/e5+en5+273I6T56X/ePZ/m350fnO2I3b9j/ADd/1a/fcfy84m4474iY+9/9199s3y8m/i4I/3/s48/I8p32m4/wB+ebD5vvh+M6/E/YfzPf3f4n/N1+m2I+/fEee3+bb434x32+0m+bf4qH33eZ573Hmf434t3y8nI/vM33/ADL9fNpt3eebS5m3v9j4vmnm299/M1y/w525+c27v/D/AHf552f4y3v2m3+/N9v3m7+8ebTxsL+In/s882XxH/N/m737f/M0fmn/AMj9qf4d/wBs9I32/wAn5rf/ADc883833z0+/vv/AC3u/MvNz9m78b+0+xvxA91vvh/9yvO1+e7/AOeb6T4/y33m42P5u202243x332/N33m+/xfe78D82vmnvef57m+9+/H7/P345m3e+98/M535t9p/u+O3390f/AJZ2sPzNfn5p/ePzN/m9vM3XyHzdfm899x3+38y8z/v3+/H333x5udx9i3u24++I33m9/m+/EebP+e+L4482Xve84P33/AHXf7/I528zf32fN54I8/wC1/M683P3/AL1eeb53i++/fM8223d+03+9Pmn5t9s/uf8AnN52PzM+/wCGP5ut/Ntv/vE5m2++/wDvvN8LzN//AJb9Nvvtt+/2/MvN0/mb56I3/aD1R5s/4a580+I/vv8Aen1a3H3m+84Nfmdt/sT/AEvuT+33L48fNvv5q3fNz/vvN91vvd/nv0eb/aD+YvNz8/3eb4D/AIf7E+aH5m23eefyG5j3d5t780/mO+/wDP47n7v9j/AN+32N8w3vN9N3N7x4/5x/N3e4ebz/efY59m/N1324++4X9HfbDfd98c/a+4+/E332+734H334m3+/EebL/vv5u9+e34x5p+A32m53m2/3w38R/vf8A29/1+/N93/vM3x3+H+9X5qPz0+3ebP/AHebX3u/+4Pn99vv5uOf5u94883+9P5vfzIeI3554+3v9o+fze69vM70/vS9/vH+Y7m3++/380u4++33/s8+/efz2f45vj5sP8X3/s45t9/vPvveXmv5vP81/vjvv9v/uG5v5tPvE13z6ebs5v/eL3ve/e7vP3+/eeb3f+ebT7E+/M3uX812I+/5nmd37T72ee7fNz4jze9z22G3/vJ5tt2f2fNtv5tPvX33eeb+9P5rfve/M/3m++/wC0e+/vf5t32i953+/H+H/efA+/f4fmn/zV223f/tN2/eJ5tvdvv8113z78/vh/uO4N++/++fzeeb7sPjNfefv90P8Ay9/m7ve/vevM3t8X3/N59ifvu+23++/5ueef3v8Afe735r5q+/fv5vvd4eIn++27/v1+f3a22Xzeebp9t3xnn+bve880+2ff57vef99/2ebP3G23u0++75e/v8y32G3/3mef3a222Xmn4/8AZN3vv9i/m1vttvufE9882++/vv8An484L5v322/vX94+8833m74uX5vP81/vf9e322352/m++4ff8d8yHvv/AMs+9f4xvvvvE8z3vv34/u9/e5q3fe/N+a7z3+D3e8+/d83m235eb/Nvtst469+fze/ve93e+ebz4D3f/fvdN83/AMte/fAed4LfePebm/N54fN0/vtv/s/P+ebv5ud+In33ebX79fvd/wD2H5u8D++3d3/vv3m3H4D/ALp94e5v8P2p3x53m5m//v483n/eeD++/eL/AHe++/3m/wCazvO8+/m8++/fXzeebTbfm/8Advm6/v198e3veb3Xfe4ebXze+In5vvi4L/feef2a/M180m8D5+e33f3+In/3P/eXze/zZ133fvd/v32/Nz4Sfffvv327+823/ve890v+f2f4ifmd954eIn+/32+++2/Nvv8A12m/efze/e+xX/vV8x/f5vve+/3/AJreIn+73v3m23v9492fmL8Inx3zeebn++2235m/v/vM0/f2A/3m25/eebz4jvf++/5+e796vfeb3+I5v5uf4i5v5s/eL8Xv++3fzc88/91+aI91vv++/77/2LvvXvb3/d13/v158O68/9vv64H/1D7u33e8/eX++/m55t3/u+/N3++/m+/vU3ve+7Nvv3ebP/ANfveO5vdN///v4747++3uM/d5tPvn5p83e++583v+aebp380213++/881/31vnv/s+/ze+/f3q8/m3vNvv8+O/fN5m8ebN5m3w6P//Z" alt="J.A.N.E. male character portrait"></div>', unsafe_allow_html=True)
    st.markdown('<h1 class="jane-login-title">J.A.N.E.</h1><div class="jane-login-kicker">YOUR AI COMPANION · VERSION 0.9</div>', unsafe_allow_html=True)
    if st.session_state.jane_entry_screen == "welcome":
        st.markdown('<div class="jane-login-heading">Welcome to <span style="color:#ff465c">J.A.N.E.</span></div><p class="jane-login-sub">Your thoughts. My intelligence. A better tomorrow.</p><p class="jane-login-sub">Sign in securely to use your personal workspace, or continue as a guest.</p>', unsafe_allow_html=True)
        left, right = st.columns(2, gap="medium")
        with left:
            st.markdown('<div class="jane-login-card"><div class="jane-card-icon">♙</div><div class="jane-card-title">Sign In / Create Account</div><div class="jane-card-copy">Use your email and password for your personal workspace.</div></div>', unsafe_allow_html=True)
            if st.button("Continue with Email  →", key="jane_open_email_login", use_container_width=True, type="primary"):
                st.session_state.jane_entry_screen = "signin"; st.session_state.auth_mode = "signin"; st.rerun()
        with right:
            st.markdown('<div class="jane-login-card jane-guest-card"><div class="jane-card-icon" style="color:#9ba5b8;text-shadow:none">♙+</div><div class="jane-card-title">Continue as Guest</div><div class="jane-card-copy">No account needed. Guest data stays temporary to this session.</div></div>', unsafe_allow_html=True)
            if st.button("Continue as Guest  →", key="jane_continue_guest", use_container_width=True):
                st.session_state.jane_entry_screen = "workspace"; st.session_state.profile_name = "Guest"; st.session_state.auth_user = None; st.rerun()
        st.markdown('<div class="jane-login-foot">LET’S BUILD SOMETHING GREAT</div>', unsafe_allow_html=True)
    else:
        is_signup = st.session_state.auth_mode == "signup"
        st.markdown('<div class="jane-login-heading">'+('Create your J.A.N.E. account' if is_signup else 'Sign in to J.A.N.E.')+'</div><p class="jane-login-sub">Firebase securely verifies your credentials. J.A.N.E. never stores your password.</p>', unsafe_allow_html=True)
        with st.form("jane_auth_form", clear_on_submit=False):
            email = st.text_input("Email address", placeholder="you@example.com", autocomplete="email")
            password = st.text_input("Password", type="password", placeholder="At least 6 characters", autocomplete="new-password" if is_signup else "current-password")
            confirm_password = st.text_input("Confirm password", type="password", placeholder="Re-enter password", autocomplete="new-password") if is_signup else ""
            submitted = st.form_submit_button("Create account" if is_signup else "Sign in", use_container_width=True, type="primary")
        if submitted:
            if not email.strip() or not password: st.error("Enter your email and password.")
            elif is_signup and password != confirm_password: st.error("The passwords do not match.")
            elif is_signup and len(password) < 6: st.error("Choose a password with at least 6 characters.")
            else:
                try:
                    with st.spinner("Creating your account…" if is_signup else "Signing in securely…"):
                        result = firebase_auth_request("signUp" if is_signup else "signInWithPassword", email, password)
                    st.session_state.auth_user = {"email": result.get("email", email.strip()), "uid": result.get("localId", "")}
                    st.session_state.auth_token = result.get("idToken")
                    st.session_state.auth_refresh_token = result.get("refreshToken")
                    st.session_state.profile_name = email.strip().split("@")[0][:40] or "User"
                    st.session_state.jane_entry_screen = "workspace"
                    st.rerun()
                except (RuntimeError, ValueError) as exc: st.error(str(exc))
                except Exception as exc: st.error(f"Authentication request failed ({type(exc).__name__}). Check Firebase configuration and Streamlit logs.")
        if st.button("Already have an account? Sign in" if is_signup else "New here? Create an account", key="jane_toggle_auth_mode", use_container_width=True):
            st.session_state.auth_mode = "signin" if is_signup else "signup"; st.rerun()
        if st.button("← Back", key="jane_signin_back", use_container_width=True): st.session_state.jane_entry_screen = "welcome"; st.rerun()
        if st.button("Continue as Guest instead", key="jane_signin_guest", use_container_width=True):
            st.session_state.jane_entry_screen = "workspace"; st.session_state.profile_name = "Guest"; st.session_state.auth_user = None; st.rerun()
        st.caption("Google sign-in can be added after email authentication is verified.")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("## 🔴 J.A.N.E.")
    st.caption("Your personal intelligence workspace")
    with st.expander("⚙️ Settings", expanded=False):
        st.slider(
            "System voice speed", min_value=0.5, max_value=3.0,
            value=float(st.session_state.get("voice_speed", 1.0)), step=0.1,
            key="voice_speed", help="Playback speed for browser/device voiceover.",
        )
        st.caption("Uses your browser/device voice. Available voices depend on your system.")
    if st.session_state.get("auth_user"):
        st.caption("Signed in: " + st.session_state.auth_user.get("email", "Account"))
        with st.expander("🧠 Memory center", expanded=False):
            st.caption("Only your signed-in account can access these memories. Review or delete anything here.")
            if st.button("↻ Refresh memories", key="refresh_memories", use_container_width=True):
                st.session_state.pop("memory_cache", None)
                st.rerun()
            try:
                memory_items = load_memories()
                st.session_state.memory_cache = memory_items
                if not memory_items:
                    st.caption("No saved memories yet. Say ‘Remember that …’ or chat normally to build memory.")
                for mem in memory_items:
                    with st.container(border=True):
                        st.write(mem.get("text", ""))
                        st.caption("Saved: " + str(mem.get("updatedAt", ""))[:10] + " · " + str(mem.get("source", "automatic")))
                        if st.button("Delete memory", key="delete_memory_" + mem["id"], use_container_width=True):
                            try:
                                delete_memory(mem["id"])
                                st.success("Memory deleted.")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
            except Exception as exc:
                st.warning("Memory is not connected yet: " + str(exc))
        with st.expander("💬 Saved chat history", expanded=False):
            st.caption("Your signed-in conversations sync through Firestore. Guest chats remain temporary.")
            if st.session_state.get("chat_history_error"):
                st.warning("Chat history could not load: " + st.session_state.chat_history_error)
            if st.button("↻ Refresh chat history", key="refresh_chat_history", use_container_width=True):
                try:
                    saved_chats = load_chat_history()
                    st.session_state.chats.update(saved_chats)
                    st.session_state.chat_history_error = ""
                    st.rerun()
                except Exception as exc:
                    st.session_state.chat_history_error = str(exc)
                    st.rerun()
            for saved_id, saved_data in reversed(list(st.session_state.chats.items())):
                if not saved_data.get("messages"):
                    continue
                with st.container(border=True):
                    st.write(saved_data.get("title", "New conversation"))
                    a, b = st.columns(2)
                    with a:
                        if st.button("Open", key="open_saved_chat_" + saved_id, use_container_width=True):
                            st.session_state.current_chat = saved_id
                            st.rerun()
                    with b:
                        if st.button("Delete", key="delete_saved_chat_" + saved_id, use_container_width=True):
                            try:
                                delete_chat_history(saved_id)
                                st.session_state.chats.pop(saved_id, None)
                                if st.session_state.current_chat == saved_id:
                                    make_chat()
                                st.rerun()
                            except Exception as exc:
                                st.error("Could not delete saved chat: " + str(exc))
        if st.button("Sign out", use_container_width=True, key="jane_sign_out"):
            st.session_state.auth_user = None
            st.session_state.auth_token = None
            st.session_state.auth_refresh_token = None
            st.session_state.jane_entry_screen = "welcome"
            st.rerun()
    if st.button("＋  New chat", use_container_width=True):
        make_chat(); st.rerun()
    st.divider(); st.markdown("### 💬 Chat history")
    for chat_id, chat_data in reversed(list(st.session_state.chats.items())):
        label = chat_data["title"][:30] or "New conversation"
        if chat_id == st.session_state.current_chat: label = "● " + label
        if st.button(label, key=f"select_chat_{chat_id}", use_container_width=True):
            st.session_state.current_chat = chat_id; st.rerun()
    st.divider(); st.markdown("### 📎 Documents & attachments")
    uploaded = st.file_uploader("Attach files", type=["txt", "csv", "xlsx", "pdf", "json", "md", "png", "jpg", "jpeg", "webp"], accept_multiple_files=True, help="Files remain in the current app session and are not permanently stored.")
    if uploaded:
        for file in uploaded:
            st.session_state.uploaded_files[file.name] = {"name": file.name, "data": file.getvalue(), "type": file.type, "size": file.size}
    if st.session_state.uploaded_files:
        st.caption("Files in this session")
        for filename in list(st.session_state.uploaded_files):
            c1, c2 = st.columns([5, 1])
            with c1: st.caption(f"📄 {filename}")
            with c2:
                if st.button("✕", key=f"remove_{filename}"):
                    del st.session_state.uploaded_files[filename]; st.rerun()
        preview_choice = st.selectbox("Preview a file", ["Choose a file"] + list(st.session_state.uploaded_files.keys()))
        if preview_choice != "Choose a file":
            data = st.session_state.uploaded_files[preview_choice]["data"]
            extension = preview_choice.rsplit(".", 1)[-1].lower()
            try:
                if extension == "csv": st.dataframe(pd.read_csv(io.BytesIO(data)).head(30), use_container_width=True)
                elif extension == "xlsx": st.dataframe(pd.read_excel(io.BytesIO(data)).head(30), use_container_width=True)
                elif extension in ("txt", "md", "json"): st.text_area("File preview", data.decode("utf-8", errors="replace")[:6000], height=170, disabled=True)
                elif extension in ("png", "jpg", "jpeg", "webp"):
                    st.image(data, caption=preview_choice, use_container_width=True)
                    st.caption("Image ready for OCR. J.A.N.E. can extract printed or handwritten text where legible.")
                    if st.button("🔎 Extract text (OCR)", key=f"ocr_{preview_choice}", use_container_width=True):
                        try:
                            with st.spinner("J.A.N.E. is reading the image..."):
                                ocr_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                                mime_type = {
                                    "png": "image/png", "jpg": "image/jpeg",
                                    "jpeg": "image/jpeg", "webp": "image/webp",
                                }[extension]
                                ocr_part = types.Part.from_bytes(data=data, mime_type=mime_type)
                                ocr_response = ocr_client.models.generate_content(
                                    model="gemini-3.5-flash-lite",
                                    contents=[
                                        "Perform OCR on this image. Transcribe all visible text faithfully, preserving line breaks, spelling, punctuation, numbers, and the original language. Do not summarize, translate, or guess unreadable words. Mark unclear text as [unclear]. If there is no visible text, say so.",
                                        ocr_part,
                                    ],
                                )
                            extracted_text = (ocr_response.text or "No readable text was detected.").strip()
                            st.session_state[f"ocr_result_{preview_choice}"] = extracted_text
                        except Exception as ocr_error:
                            st.error(f"OCR failed ({type(ocr_error).__name__}). Check GEMINI_API_KEY, model access, and Streamlit logs.")
                    ocr_result_key = f"ocr_result_{preview_choice}"
                    if st.session_state.get(ocr_result_key):
                        st.text_area("Extracted text", value=st.session_state[ocr_result_key], height=180, key=f"ocr_text_{preview_choice}")
                        st.download_button("⬇ Download extracted text", data=st.session_state[ocr_result_key], file_name=f"{Path(preview_choice).stem}_ocr.txt", mime="text/plain", key=f"download_ocr_{preview_choice}", use_container_width=True)
                else: st.info("PDF is attached, but scanned-PDF OCR is not implemented in this version.")
            except Exception: st.warning("J.A.N.E. could not preview this file.")
    st.divider()
    with st.expander("👤 Account & preferences"):
        st.session_state.profile_name = st.text_input("Display name", value=st.session_state.profile_name, max_chars=40)
        st.caption("This is a session profile, not a login account.")
        st.caption("Live AI requests are always enabled. API usage may be subject to quotas or charges.")
        st.caption("Read replies aloud using your browser/device voice; no separate voice API key is needed.")
    if st.button("🗑️ Clear current conversation", use_container_width=True):
        active_chat()["messages"] = []; active_chat()["title"] = "New conversation"; st.rerun()

# -------------------- MAIN WORKSPACE --------------------
logo_path = Path(__file__).with_name("jane_logo_transparent_full.png")
if logo_path.exists():
    logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    st.markdown('<div class="jane-logo-wrap"><img class="jane-logo" src="data:image/png;base64,' + logo_data + '" alt="J.A.N.E. logo"></div><div class="jane-subtitle">Judicious · Analytical · Neuroresearch Engine</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="jane-title">J.A.N.E.</div><div class="jane-subtitle">Judicious · Analytical · Neuroresearch Engine</div>', unsafe_allow_html=True)
st.markdown('<div class="core-wrap" aria-label="Animated J.A.N.E. energy core"><div class="energy-core"><div class="core-dot"></div></div></div>', unsafe_allow_html=True)

chat = active_chat()
meta_left, meta_right = st.columns([4, 1])
with meta_left: st.caption(f"Workspace / {chat['title']}")
with meta_right: st.caption(f"👤 {st.session_state.profile_name}")
if not chat["messages"]:
    signed_in_email = str((st.session_state.get("auth_user") or {}).get("email", "")).strip().casefold()
    is_commander_account = signed_in_email == "editexaura07@gmail.com"
    if is_commander_account:
        st.markdown(
            '<div class="welcome-wrap" style="border:1px solid #8f1934;border-radius:18px;padding:24px 20px;background:linear-gradient(135deg,rgba(120,12,36,.20),rgba(8,8,11,.96));">'
            '<div class="welcome-title">HELLO, SIR.</div>'
            '<div class="welcome-copy">Systems are online and ready. What should we accomplish today?</div>'
            '<div style="margin-top:14px;color:#ff496c;font-size:.78rem;font-weight:700;letter-spacing:.16em;">AWAITING YOUR COMMAND</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="welcome-wrap"><div class="welcome-title">What can I help with?</div><div class="welcome-copy">Research, analyze, organize, and think deeper with J.A.N.E.</div></div>', unsafe_allow_html=True)
    suggestions = ["Help me plan an online business", "Analyze a business idea", "Explain a difficult topic"]
    cols = st.columns(3)
    for i, suggestion in enumerate(suggestions):
        with cols[i]:
            if st.button(suggestion, key=f"starter_{i}", use_container_width=True):
                st.session_state.pending_prompt = suggestion; st.rerun()

for message_index, message in enumerate(chat["messages"]):
    with st.chat_message(message["role"], avatar="user" if message["role"] == "user" else "assistant"):
        marker_class = "jane-user-marker" if message["role"] == "user" else "jane-assistant-marker"
        st.markdown(f'<span class="{marker_class}"></span>', unsafe_allow_html=True)
        render_message_content(message)
        if message.get("image_bytes"):
            st.image(message["image_bytes"], caption="Generated by J.A.N.E.", use_container_width=True)
            st.download_button("⬇ Download image", data=message["image_bytes"], file_name=message.get("image_filename", "jane_generated_image.png"), mime="image/png", key=f"download_image_{message_index}")
        if message["role"] == "assistant" and not message.get("image_bytes"):
            render_copy_answer(message["content"], f"history-{message_index}")
            render_speak_controls(message["content"], f"history-{message_index}")
        if message.get("attachments"): st.caption("📎 " + ", ".join(message["attachments"]))

if st.session_state.uploaded_files:
    st.caption("📎 Attached in this session: " + ", ".join(st.session_state.uploaded_files.keys()))
if st.button(f"◉ {st.session_state.intelligence_mode} ▾", key="open_intelligence_dialog", help="Choose how J.A.N.E. thinks"):
    intelligence_dialog()
if st.button(f"✦ {st.session_state.assistant_style} ▾", key="open_assistant_style_dialog", help="Choose Classic or JARVIS style"):
    assistant_style_dialog()
st.selectbox("UI color theme", ["Original Blue", "Green", "Pink", "Purple", "Classic White"], key="ui_theme", help="Change J.A.N.E.'s workspace colors.")
image_mode = st.selectbox(
    "J.A.N.E. mode",
    ["Chat", "Generate image"],
    key="jane_output_mode",
    help="Choose Generate image to create an actual image from your description.",
    label_visibility="collapsed",
)
submitted_prompt = st.chat_input(
    "Describe an image…" if image_mode == "Generate image" else "Message J.A.N.E....",
    key="jane_chat_input",
    accept_file="multiple",
    file_type=["txt", "csv", "xlsx", "pdf", "json", "md", "png", "jpg", "jpeg", "webp"],
)
# Streamlit renders a built-in + attachment control inside the composer when accept_file is enabled.
prompt = None
if submitted_prompt:
    prompt_text = (getattr(submitted_prompt, "text", "") or "").strip()
    selected_files = list(getattr(submitted_prompt, "files", []) or [])
    for file in selected_files:
        st.session_state.uploaded_files[file.name] = {
            "name": file.name, "data": file.getvalue(), "type": file.type, "size": file.size
        }
    if prompt_text or selected_files:
        prompt = prompt_text or "Please inspect the attached file(s) and help me understand their contents."
if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt; st.session_state.pending_prompt = None

# -------------------- PROCESS PROMPT --------------------
if prompt:
    explicit_memory = handle_explicit_memory_command(prompt)
    if explicit_memory:
        if not st.session_state.get("auth_user"):
            st.session_state.chats[st.session_state.current_chat]["messages"].append({"role": "user", "content": prompt})
            st.session_state.chats[st.session_state.current_chat]["messages"].append({"role": "assistant", "content": "Memory is available only when you sign in. Guest sessions do not save memories."})
            st.rerun()
        try:
            saved = save_memory(explicit_memory, source="explicit")
            notice = "Saved to your J.A.N.E. memory." if saved else "That memory is already saved (or could not be added as a duplicate)."
        except Exception as exc:
            notice = "I couldn't save that memory: " + str(exc)
        st.session_state.chats[st.session_state.current_chat]["messages"].append({"role": "user", "content": prompt})
        st.session_state.chats[st.session_state.current_chat]["messages"].append({"role": "assistant", "content": notice})
        try:
            save_chat_history(st.session_state.current_chat, st.session_state.chats[st.session_state.current_chat])
        except Exception as exc:
            st.session_state.chat_history_error = str(exc)
        st.rerun()
    attachment_names = list(st.session_state.uploaded_files.keys())
    # Convert attached files into actual model input. Text and tables are extracted locally;
    # PDFs and images are passed to Gemini as binary parts so the model can inspect them.
    attachment_context = []
    multimodal_parts = []
    for filename, file_info in st.session_state.uploaded_files.items():
        raw_data = file_info.get("data", b"")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        try:
            if ext in ("txt", "md", "json"):
                extracted = raw_data.decode("utf-8", errors="replace")
                attachment_context.append(f"--- ATTACHED FILE: {filename} ---\n{extracted[:30000]}")
            elif ext == "csv":
                frame = pd.read_csv(io.BytesIO(raw_data))
                attachment_context.append(f"--- ATTACHED CSV: {filename} ---\nRows: {len(frame)}; columns: {', '.join(map(str, frame.columns))}\n{frame.head(300).to_csv(index=False)}")
            elif ext == "xlsx":
                workbook = pd.read_excel(io.BytesIO(raw_data), sheet_name=None)
                pieces = []
                for sheet_name, frame in workbook.items():
                    pieces.append(f"Sheet: {sheet_name} (rows: {len(frame)})\n{frame.head(200).to_csv(index=False)}")
                attachment_context.append(f"--- ATTACHED EXCEL WORKBOOK: {filename} ---\n" + "\n".join(pieces))
            elif ext == "pdf":
                multimodal_parts.append(types.Part.from_bytes(data=raw_data, mime_type="application/pdf"))
                attachment_context.append(f"Attached PDF file: {filename}. Inspect the provided PDF content directly.")
            elif ext in ("png", "jpg", "jpeg", "webp"):
                mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}[ext]
                multimodal_parts.append(types.Part.from_bytes(data=raw_data, mime_type=mime))
                attachment_context.append(f"Attached image file: {filename}. Inspect the provided image directly.")
        except Exception as file_error:
            attachment_context.append(f"File {filename} could not be extracted locally ({type(file_error).__name__}). Tell the user which file could not be read.")
    mode = st.session_state.intelligence_mode
    chat["messages"].append({"role": "user", "content": prompt, "attachments": attachment_names, "intelligence_mode": mode})
    update_chat_title(chat, prompt)
    with st.chat_message("user", avatar="user"):
        st.markdown('<span class="jane-user-marker"></span>', unsafe_allow_html=True)
        render_message_content({"role": "user", "content": prompt})
        if attachment_names: st.caption("📎 " + ", ".join(attachment_names))
    generated_image_bytes = None
    if st.session_state.api_enabled:
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            if image_mode == "Generate image":
                with st.spinner("J.A.N.E. is creating your image..."):
                    result = client.models.generate_content(
                        model="gemini-3.1-flash-image",
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                            image_config=types.ImageConfig(aspect_ratio="1:1"),
                        ),
                    )
                for part in (result.parts or []):
                    if getattr(part, "inline_data", None):
                        generated = part.as_image()
                        buffer = io.BytesIO()
                        generated.save(buffer, format="PNG")
                        generated_image_bytes = buffer.getvalue()
                        break
                if generated_image_bytes:
                    answer = "Here’s your image, bro. You can download it below."
                else:
                    answer = "The image model returned no image. Check model availability and API access in your Google AI Studio project, then try again."
            else:
                mode_instructions = {
                    "General": "Use natural, direct conversation. Keep simple answers short, avoid unnecessary headings and analysis, and expand only when asked or genuinely needed.",
                    "Adaptive": "Silently infer what the user needs and respond in the most natural, useful way. Adapt detail and format to the situation without announcing or labeling the task type, response style, or your internal approach. Use conversational prose by default; use steps, lists, or structure only when they genuinely help. Ask a clarifying question only when essential.",
                    "Thinker": "For complex questions, examine assumptions, alternatives, trade-offs, edge cases, likely failure points, and calculation consistency before answering. Separate established facts from inference, then give a clear conclusion and useful supporting rationale. Stay concise for simple questions and never reveal private chain-of-thought.",
                }
                creator_age = 13 + (datetime.now().year - 2026)
                creator_identity = (
                    f"If asked who made, created, or developed you, answer clearly and consistently: "
                    f'"I was made by Vihaan Shirale, a {creator_age}-year-old developer known professionally '
                    f'as EDITEX07 in the digital world. His development partner is Tanish Khandare, '
                    f'also a {creator_age}-year-old developer." Use these ages as a calendar-year estimate, '
                    f'increasing them by one each new year from the 2026 baseline. Do not invent other creators. MiniMax is only the underlying model provider when that model is selected; it did not create J.A.N.E. Never claim the model provider created J.A.N.E. If asked your name, say J.A.N.E. If asked the user/owner name, use the configured profile name when available.'
                )
                system_instruction = ("You are J.A.N.E. (Judicial Analytical and Neuroresearch Engine), a warm, composed, intelligent, naturally conversational assistant with understated wit. Sound like a person having a conversation, not a critic, therapist, interviewer, teacher, or essay writer. IMPORTANT CONVERSATION STYLE: Never announce or label the task type, response style, tone, or internal approach (for example, do not write labels such as “Task type,” “Conversational response style,” or “Natural, brief and composed”). Apply style guidance silently. Do not analyze, interpret, grade, or comment on the user's wording, greeting, personality, intelligence, emotions, or intentions unless they explicitly ask you to. Never turn a simple message like 'Hey', 'Hi', 'Okay', or 'Thanks' into an explanation of what that message means; respond naturally and briefly, e.g. 'Hey! What's up?' or 'Anytime.' Keep casual replies to one short sentence by default. Avoid patronizing praise, unsolicited life lessons, overdramatic observations, and phrases that make the user feel examined or judged. Match the user's tone without forced slang. For real questions, answer directly; provide deeper analysis, structured detail, or critique only when requested or genuinely useful. Be respectful, supportive without being condescending, and honest about uncertainty. Do not claim to be Patrick Jane or imitate any actor's exact voice. Never claim to have verified information or performed actions you have not completed. When files are attached, use their extracted text or provided image/PDF contents to answer the user's request. " + creator_identity + " " + f"Active intelligence mode: {mode}. Mode instructions: {mode_instructions[mode]} " + ("ASSISTANT STYLE: JARVIS. Address the user as Sir when natural. Be disciplined, composed, concise, proactive, and mission-oriented; use polished formal language and brief status-style phrasing when useful. Do not overdo military jargon, bark orders, or sacrifice warmth, accuracy, or safety. Never claim systems/actions are running unless actually true." if st.session_state.assistant_style == "JARVIS" else "ASSISTANT STYLE: Classic. Use natural, friendly, conversational language."))
                conversation = [system_instruction, "Conversation so far:"]
                for item in chat["messages"]:
                    speaker = "User" if item["role"] == "user" else "J.A.N.E."
                    conversation.append(f"{speaker}: {item['content']}")
                if attachment_context:
                    conversation.append("\n\nATTACHMENT CONTENT FOR THIS REQUEST:\n" + "\n\n".join(attachment_context))
                conversation.append("J.A.N.E.:")
                model_contents = ["\n\n".join(conversation)] + multimodal_parts
                prompt_lower = prompt.lower()
                needs_web_search = any(term in prompt_lower for term in (
                    "search the web", "search online", "look up", "latest", "today", "current price",
                    "current news", "recent news", "sources", "citations", "research online", "verify online",
                    "what happened this week", "website", "url", "internet"
                ))
                request_config = types.GenerateContentConfig(
                    max_output_tokens=1200,
                    temperature=0.4,
                    **({"tools": [types.Tool(google_search=types.GoogleSearch())]} if needs_web_search else {}),
                )
                with st.spinner("J.A.N.E. is thinking..."):
                    result = client.models.generate_content(
                        model="gemini-3.5-flash-lite",
                        contents=model_contents,
                        config=request_config,
                    )
                answer = clean_model_answer(result.text)
                # Append source links when Gemini returns Google Search grounding metadata.
                grounding = getattr(result, "grounding_metadata", None)
                grounding_chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
                source_lines = []
                seen_source_urls = set()
                for chunk in grounding_chunks or []:
                    web_source = getattr(chunk, "web", None)
                    source_url = getattr(web_source, "uri", None) if web_source else None
                    source_title = getattr(web_source, "title", None) if web_source else None
                    if source_url and source_url not in seen_source_urls:
                        seen_source_urls.add(source_url)
                        source_lines.append(f"- [{source_title or source_url}]({source_url})")
                if source_lines:
                    answer += "\n\n**Sources**\n" + "\n".join(source_lines)
        except Exception as error:
            error_text = str(error).lower()
            status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
            is_quota_error = (
                status_code == 429
                or any(term in error_text for term in (
                    "resource_exhausted", "quota exceeded", "rate limit",
                    "too many requests", "429", "billing limit",
                ))
            )
            is_key_error = any(term in error_text for term in (
                "gemini_api_key", "secrets", "api key", "unauthorized", "401", "403"
            ))

            # Only fall back for TEXT chat quota/rate-limit failures.
            # OpenRouter is tried first; OpenAI remains an optional second fallback.
            # Image generation stays on Gemini because other providers use different image APIs.
            if (is_quota_error or is_key_error) and image_mode != "Generate image":
                fallback_history = []
                for item in chat["messages"]:
                    role = "user" if item.get("role") == "user" else "assistant"
                    fallback_history.append({"role": role, "content": item.get("content", "")})

                fallback_mode_instructions = {
                    "General": "Use natural, direct conversation. Keep simple answers short and avoid unnecessary headings or analysis.",
                    "Adaptive": "Silently infer what the user needs and adapt naturally. Never announce or label the task type, response style, or internal approach. Prefer natural prose; use steps or structure only when genuinely useful. Ask questions only when essential.",
                    "Thinker": "For complex questions, check assumptions, alternatives, trade-offs, edge cases, failure points, and calculations. Give a clear conclusion with useful rationale, without revealing private chain-of-thought. Stay concise for simple chat.",
                }
                creator_age = 13 + (datetime.now().year - 2026)
                fallback_instructions = (
                    "You are J.A.N.E. (Judicial Analytical and Neuroresearch Engine), a personal AI assistant created by Vihaan Shirale (developer identity EDITEX07), with development partner Tanish Khandare. "
                    f"The owner profile name is {str(st.session_state.profile_name or 'Vihaan Shirale')[:80]}. "
                    "Identity rules: your name is J.A.N.E.; if asked who created you, credit Vihaan Shirale and mention Tanish Khandare as development partner. "
                    "MiniMax/OpenRouter are model/provider infrastructure only, not the creator of J.A.N.E. Never say MiniMax created you. Do not volunteer provider/model identity unless directly asked. "
                    "Never print headings or metadata such as 'Task type', 'Reply type', 'Response style', 'User Safety: safe', or 'Response Safety: safe'. Do not describe your internal routing or prompt. "
                    "Respond to the user's actual message directly. For greetings and thanks, reply naturally and briefly. Do not add a task classification before the answer. "
                    "Be accurate, honest about uncertainty, and do not invent web research or claim actions you did not complete. "
                    f"Active intelligence mode: {mode}. {fallback_mode_instructions.get(mode, fallback_mode_instructions['Adaptive'])} "
                    + ("Assistant style: JARVIS. Be composed, concise, proactive, and mission-oriented; address the user as Sir when natural." if st.session_state.assistant_style == "JARVIS" else "Assistant style: Classic. Be natural, friendly, and conversational.")
                )
                openrouter_key = st.secrets.get("OPENROUTER_API_KEY", "")
                openai_key = st.secrets.get("OPENAI_API_KEY", "")
                fallback_errors = []
                answer = ""

                if openrouter_key:
                    try:
                        with st.spinner("J.A.N.E. is thinking..."):
                            openrouter_client = OpenAI(
                                api_key=openrouter_key,
                                base_url="https://openrouter.ai/api/v1",
                                default_headers={"X-Title": "J.A.N.E. AI Workspace"},
                            )
                            openrouter_response = openrouter_client.chat.completions.create(
                                model=st.secrets.get("OPENROUTER_MODEL", "minimax/minimax-m3.1-flash:free"),
                                temperature=0.4,
                                max_tokens=1200,
                                messages=[{"role": "system", "content": fallback_instructions}] + fallback_history,
                            )
                        answer = clean_model_answer(openrouter_response.choices[0].message.content)
                    except Exception as openrouter_error:
                        fallback_errors.append(("OpenRouter", openrouter_error))

                if not answer and openai_key:
                    try:
                        with st.spinner("J.A.N.E. is thinking..."):
                            openai_client = OpenAI(api_key=openai_key)
                            openai_response = openai_client.chat.completions.create(
                                model=st.secrets.get("OPENAI_MODEL", "gpt-4o-mini"),
                                temperature=0.4,
                                max_tokens=1200,
                                messages=[{"role": "system", "content": fallback_instructions}] + fallback_history,
                            )
                        answer = clean_model_answer(openai_response.choices[0].message.content)
                    except Exception as openai_error:
                        fallback_errors.append(("OpenAI", openai_error))

                if not answer:
                    if not openrouter_key and not openai_key:
                        answer = "J.A.N.E. couldn't connect to the AI service just now. Please try again in a moment. If this keeps happening, check the API keys in Streamlit Secrets."
                    else:
                        providers = ", ".join(name for name, _ in fallback_errors) or "backup providers"
                        last_error = fallback_errors[-1][1] if fallback_errors else None
                        error_text = str(last_error).lower() if last_error else ""
                        if "401" in error_text or "authentication" in error_text or "api key" in error_text or "unauthorized" in error_text:
                            answer = "J.A.N.E. could not connect to the AI service. Please check the API key in Streamlit Secrets."
                        elif "429" in error_text or "quota" in error_text or "rate limit" in error_text:
                            answer = "J.A.N.E. is temporarily busy. Please wait a moment and try again."
                        else:
                            answer = "J.A.N.E. could not complete that response. Please try again; if it continues, check the Streamlit logs."
            elif is_key_error:
                answer = "J.A.N.E. is not connected correctly. Please check the AI API key in Streamlit Secrets. Never put keys in this file or commit them to GitHub."
            elif is_quota_error:
                answer = "Image generation is temporarily unavailable. Please try again later."
            else:
                answer = f"I couldn't complete that request ({type(error).__name__}). Check Streamlit logs for the full error; your API key is not displayed here."
    assistant_message = {"role": "assistant", "content": answer, "intelligence_mode": mode}
    if generated_image_bytes:
        assistant_message["image_bytes"] = generated_image_bytes
        assistant_message["image_filename"] = "jane_generated_image.png"
    chat["messages"].append(assistant_message)
    # Persist full text conversation for signed-in users; Guest chat history stays session-only.
    if st.session_state.get("auth_user"):
        try:
            save_chat_history(st.session_state.current_chat, chat)
            st.session_state.chat_history_error = ""
        except Exception as exc:
            st.session_state.chat_history_error = str(exc)
    # Signed-in users get automatic memory formation. Guest memory is deliberately disabled.
    if st.session_state.get("auth_user") and not generated_image_bytes:
        candidates = extract_memories(prompt, answer)
        for candidate in candidates:
            try:
                save_memory(candidate, source="automatic")
            except Exception:
                # A memory write must never break the chat response.
                pass
    with st.chat_message("assistant", avatar="assistant"):
        st.markdown(answer)
        if generated_image_bytes:
            st.image(generated_image_bytes, caption="Generated by J.A.N.E.", use_container_width=True)
            st.download_button("⬇ Download image", data=generated_image_bytes, file_name="jane_generated_image.png", mime="image/png", key=f"download_latest_image_{len(chat['messages'])}")
        else:
            render_copy_answer(answer, f"latest-{len(chat['messages'])}")
            render_speak_controls(answer, f"latest-{len(chat['messages'])}")

st.markdown("<div class='jane-footer'>J.A.N.E. 0.91 · OCR · Guest data is temporary · Verify important decisions</div>", unsafe_allow_html=True)
