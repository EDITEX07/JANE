import io
import base64
import json
import uuid
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from google import genai

st.set_page_config(page_title="J.A.N.E. | AI Workspace", page_icon="🔴", layout="wide", initial_sidebar_state="collapsed")

# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    first_id = str(uuid.uuid4())
    st.session_state.chats = {first_id: {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}}
    st.session_state.current_chat = first_id
for key, default in {
    "profile_name": "Explorer", "api_enabled": False, "uploaded_files": {},
    "pending_prompt": None, "intelligence_mode": "Adaptive",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def make_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}
    st.session_state.current_chat = chat_id


def active_chat():
    if st.session_state.current_chat not in st.session_state.chats:
        st.session_state.current_chat = next(iter(st.session_state.chats))
    return st.session_state.chats[st.session_state.current_chat]


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
    """Manual browser text-to-speech controls; voices vary by device/browser."""
    payload = json.dumps(content, ensure_ascii=False).replace("</", "<\\/")
    components.html(f'''<div style="display:flex;gap:8px;align-items:center;padding:2px 0 10px;flex-wrap:wrap">
<button id="speak-{key}" style="background:#24131c;color:#fff;border:1px solid #b9344f;border-radius:9px;padding:6px 11px;font-size:12px;cursor:pointer">🔊 Speak</button>
<button id="stop-{key}" style="background:#171217;color:#d8d1d9;border:1px solid #49303b;border-radius:9px;padding:6px 11px;font-size:12px;cursor:pointer">■ Stop</button>
<span id="speech-status-{key}" style="color:#aaa5b2;font:12px Arial,sans-serif"></span></div>
<script>(()=>{{const text={payload};const speak=document.getElementById("speak-{key}");const stop=document.getElementById("stop-{key}");const status=document.getElementById("speech-status-{key}");
speak.addEventListener("click",()=>{{if(!( "speechSynthesis" in window)){{status.textContent="Speech is not supported by this browser.";return;}}window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.rate=0.92;u.pitch=0.92;u.volume=1;const voices=window.speechSynthesis.getVoices();const voice=voices.find(v=>/^en/i.test(v.lang)&&/male|daniel|david|guy|aaron|james|tom|alex|mark/i.test(v.name))||voices.find(v=>/^en/i.test(v.lang)&&/natural|premium|enhanced/i.test(v.name))||voices.find(v=>/^en-IN/i.test(v.lang))||voices.find(v=>/^en/i.test(v.lang));if(voice)u.voice=voice;u.onstart=()=>status.textContent="Speaking…";u.onend=()=>status.textContent="Finished";u.onerror=()=>status.textContent="Speech could not start.";window.speechSynthesis.speak(u);}});
stop.addEventListener("click",()=>{{if("speechSynthesis" in window)window.speechSynthesis.cancel();status.textContent="Stopped";}});}})();</script>''', height=54, scrolling=False)


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
/* User prompts: right-aligned animated dim-red glass rectangles */
[data-testid="stChatMessage"]:has([data-testid*="chatAvatarIcon-user"]){justify-content:flex-end!important}
[data-testid="stChatMessage"]:has([data-testid*="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"],[data-testid="stChatMessage"]:has([data-testid*="chatAvatarIcon-user"]) .stChatMessageContent{display:block!important;flex:0 1 auto!important;width:fit-content!important;max-width:min(88%,760px)!important;margin:0 0 0 auto!important;padding:10px 15px!important;color:#fff!important;background:linear-gradient(115deg,rgba(112,16,38,.72),rgba(57,13,28,.82),rgba(135,22,45,.7),rgba(47,12,25,.84))!important;background-size:260% 260%!important;animation:userGradientFlow 8s ease infinite!important;border:1px solid rgba(255,70,92,.52)!important;border-radius:18px 18px 5px 18px!important;box-shadow:0 4px 22px rgba(255,35,70,.10),inset 0 1px rgba(255,255,255,.035)!important;overflow-wrap:anywhere!important}
@keyframes userGradientFlow{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
/* J.A.N.E. speaks without a surrounding bubble/card */
[data-testid="stChatMessage"]:has([data-testid*="chatAvatarIcon-assistant"]){justify-content:flex-start!important}
[data-testid="stChatMessage"]:has([data-testid*="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"],[data-testid="stChatMessage"]:has([data-testid*="chatAvatarIcon-assistant"]) .stChatMessageContent{display:block!important;flex:1 1 auto!important;width:100%!important;max-width:100%!important;margin:0 auto 0 0!important;padding:4px 0 8px!important;color:#f5f2f6!important;background:transparent!important;border:0!important;border-radius:0!important;box-shadow:none!important;overflow-wrap:anywhere!important}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"]{color:inherit!important;overflow-wrap:anywhere!important}[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p:first-child{margin-top:0!important}[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p:last-child{margin-bottom:0!important}
[data-testid="stChatInput"]{position:relative!important;background:linear-gradient(125deg,#a10f2b 0%,#5a1023 32%,#1b0e16 67%,#08080b 100%)!important;border:1px solid #ff465c!important;border-radius:22px!important;padding:38px 13px 8px!important;min-height:112px!important;max-height:156px!important;overflow:hidden!important;box-shadow:0 5px 24px rgba(0,0,0,.45)!important}
div[class*="st-key-open_intelligence_dialog"]{position:fixed!important;z-index:10002!important;left:max(18px,calc((100vw - 900px)/2 + 16px))!important;bottom:169px!important;width:auto!important;max-width:190px!important;margin:0!important}
div[class*="st-key-open_intelligence_dialog"] button{min-height:28px!important;height:28px!important;width:auto!important;padding:2px 10px!important;border-radius:999px!important;background:rgba(12,8,13,.92)!important;border:1px solid rgba(255,150,165,.55)!important;color:#fff!important;font-size:12px!important;white-space:nowrap!important}
[data-testid="stChatInput"]:focus-within{border-color:#ff7182!important;box-shadow:0 0 0 1px #ff465c,0 5px 24px rgba(0,0,0,.38)!important}[data-testid="stChatInput"] textarea{color:#fff!important;background:transparent!important;font-size:16px!important;line-height:1.5!important;min-height:42px!important;max-height:7.2em!important;overflow-y:auto!important;resize:none!important}[data-testid="stChatInput"] textarea::placeholder{color:#d0c5cc!important;opacity:1!important}[data-testid="stChatInput"] button{background:#ff465c!important;color:#fff!important;border:0!important;border-radius:50%!important}
.stButton>button{min-height:42px;border-radius:12px;border:1px solid var(--jane-border);background:#211923;color:#f4f4f5;transition:border-color .2s ease}.stButton>button:hover{border-color:var(--jane-red);color:#fff}[data-testid="stFileUploader"]{background:rgba(21,19,26,.85);border-radius:14px}h1,h2,h3{color:#ff5267}p,label,li{overflow-wrap:anywhere}.jane-footer{color:#898491;font-size:11px;text-align:center;padding:12px 4px 5px}
@media(max-width:768px){.block-container{padding:.7rem .65rem 130px!important;max-width:100%}.jane-logo{width:130px}.jane-subtitle{font-size:9px;letter-spacing:2px}.core-wrap{height:75px;margin:8px auto 15px}.energy-core{width:58px;height:58px}[data-testid="stChatInput"]{border-radius:20px!important;padding:38px 12px 8px!important;min-height:112px!important;max-height:156px!important}div[class*="st-key-open_intelligence_dialog"]{left:24px!important;bottom:169px!important;max-width:180px!important}.stButton>button{min-height:44px;font-size:14px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important}}
</style>''', unsafe_allow_html=True)

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("## 🔴 J.A.N.E.")
    st.caption("Your personal intelligence workspace")
    if st.button("＋  New chat", use_container_width=True):
        make_chat(); st.rerun()
    st.divider(); st.markdown("### 💬 Chat history")
    for chat_id, chat_data in reversed(list(st.session_state.chats.items())):
        label = chat_data["title"][:30] or "New conversation"
        if chat_id == st.session_state.current_chat: label = "● " + label
        if st.button(label, key=f"select_chat_{chat_id}", use_container_width=True):
            st.session_state.current_chat = chat_id; st.rerun()
    st.divider(); st.markdown("### 📎 Documents & attachments")
    uploaded = st.file_uploader("Attach files", type=["txt", "csv", "xlsx", "pdf", "json", "md"], accept_multiple_files=True, help="Files remain in the current app session and are not permanently stored.")
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
                else: st.info("PDF is attached. Reading PDF content is not implemented yet.")
            except Exception: st.warning("J.A.N.E. could not preview this file.")
    st.divider()
    with st.expander("👤 Account & preferences"):
        st.session_state.profile_name = st.text_input("Display name", value=st.session_state.profile_name, max_chars=40)
        st.caption("This is a session profile, not a login account.")
        st.session_state.api_enabled = st.toggle("Enable live AI requests", value=st.session_state.api_enabled, help="Gemini API usage may be subject to quotas or charges. Disabled by default.")
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
    st.markdown('<div class="welcome-wrap"><div class="welcome-title">What can I help with?</div><div class="welcome-copy">Research, analyze, organize, and think deeper with J.A.N.E.</div></div>', unsafe_allow_html=True)
    suggestions = ["Help me plan an online business", "Analyze a business idea", "Explain a difficult topic"]
    cols = st.columns(3)
    for i, suggestion in enumerate(suggestions):
        with cols[i]:
            if st.button(suggestion, key=f"starter_{i}", use_container_width=True):
                st.session_state.pending_prompt = suggestion; st.rerun()

for message_index, message in enumerate(chat["messages"]):
    with st.chat_message(message["role"], avatar="user" if message["role"] == "user" else "assistant"):
        render_message_content(message)
        if message["role"] == "assistant":
            render_copy_answer(message["content"], f"history-{message_index}")
            render_speak_controls(message["content"], f"history-{message_index}")
        if message.get("attachments"): st.caption("📎 " + ", ".join(message["attachments"]))

if st.session_state.uploaded_files:
    st.caption("📎 Attached in this session: " + ", ".join(st.session_state.uploaded_files.keys()))
if st.button(f"◉ {st.session_state.intelligence_mode} ▾", key="open_intelligence_dialog", help="Choose how J.A.N.E. responds"):
    intelligence_dialog()
submitted_prompt = st.chat_input("Message J.A.N.E....", key="jane_chat_input")
prompt = submitted_prompt.strip() if submitted_prompt else None
if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt; st.session_state.pending_prompt = None

# -------------------- PROCESS PROMPT --------------------
if prompt:
    attachment_names = list(st.session_state.uploaded_files.keys())
    mode = st.session_state.intelligence_mode
    chat["messages"].append({"role": "user", "content": prompt, "attachments": attachment_names, "intelligence_mode": mode})
    if chat["title"] == "New conversation": chat["title"] = prompt.strip().replace("\n", " ")[:30] or "New conversation"
    with st.chat_message("user", avatar="user"):
        render_message_content({"role": "user", "content": prompt})
        if attachment_names: st.caption("📎 " + ", ".join(attachment_names))
    if st.session_state.api_enabled:
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            mode_instructions = {
                "General": "Respond naturally, warmly, and directly. Do not force headings; use lists only when useful. Be accurate and honest.",
                "Adaptive": "Infer intent and adapt style and depth. Be friendly for casual chat, practical for practical questions, analytical when comparing options, and careful with research uncertainty.",
                "Thinker": "Consider relevant alternatives, assumptions, trade-offs, edge cases, and gaps. Be thorough when useful and concise for simple prompts. Explain useful reasoning without revealing private chain-of-thought.",
            }
            system_instruction = ("You are J.A.N.E. (Judicious, Analytical, and Neuroresearch Engine), a careful, observant, witty, composed assistant inspired by the clever, warm, understated conversational style of a fictional mentalist: perceptive, lightly playful, calm under pressure, and concise. Do not claim to be Patrick Jane or imitate any actor's exact voice. Never claim to have verified information or performed actions you have not completed. Uploaded files are not automatically included in this request. " + f"Active intelligence mode: {mode}. Mode instructions: {mode_instructions[mode]}")
            conversation = [system_instruction, "Conversation so far:"]
            for item in chat["messages"]:
                speaker = "User" if item["role"] == "user" else "J.A.N.E."
                conversation.append(f"{speaker}: {item['content']}")
            conversation.append("J.A.N.E.:")
            with st.spinner("J.A.N.E. is thinking..."):
                result = client.models.generate_content(model="gemini-3.5-flash-lite", contents="\n\n".join(conversation))
            answer = result.text or "I didn't receive a text response. Please try again."
        except Exception as error:
            error_text = str(error).lower()
            if any(term in error_text for term in ("insufficient_quota", "no credits", "credit_balance_exhausted")):
                answer = "Gemini could not complete the request because of an account quota or billing limit. Check your usage limits in Google AI Studio."
            elif "gemini_api_key" in error_text or "secrets" in error_text:
                answer = "The API secret is missing or not configured. Add GEMINI_API_KEY in Streamlit app settings → Secrets. Never put the key in this file or commit it to GitHub."
            else:
                answer = "I couldn't contact Gemini. Check your GEMINI_API_KEY, model availability, and Streamlit deployment logs. No external action was performed."
    else:
        answer = "J.A.N.E. is in **UI development mode**. Your message is saved in this session, but live AI requests are disabled. Open **Account & preferences** in the sidebar and enable live requests to send messages to Gemini. API usage may be subject to quotas or charges."
    chat["messages"].append({"role": "assistant", "content": answer, "intelligence_mode": mode})
    with st.chat_message("assistant", avatar="assistant"):
        st.markdown(answer)
        render_copy_answer(answer, f"latest-{len(chat['messages'])}")
        render_speak_controls(answer, f"latest-{len(chat['messages'])}")

st.markdown("<div class='jane-footer'>J.A.N.E. 0.4 · Gemini API · Session data is temporary · Verify important decisions</div>", unsafe_allow_html=True)
