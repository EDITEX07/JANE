import io
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
from google import genai

st.set_page_config(
    page_title="J.A.N.E. | AI Workspace",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    chat_id = str(uuid.uuid4())
    st.session_state.chats = {
        chat_id: {
            "title": "New conversation",
            "messages": [],
            "created": datetime.now().strftime("%d %b %Y, %H:%M"),
        }
    }
    st.session_state.current_chat = chat_id

for key, default in {
    "profile_name": "Explorer",
    "api_enabled": False,
    "uploaded_files": {},
    "pending_prompt": None,
    "intelligence_mode": "Adaptive",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def make_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = {
        "title": "New conversation",
        "messages": [],
        "created": datetime.now().strftime("%d %b %Y, %H:%M"),
    }
    st.session_state.current_chat = chat_id


def active_chat():
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
                elif st.button(
                    "Select",
                    key=f"mode_select_{name}",
                    use_container_width=True,
                ):
                    st.session_state.intelligence_mode = name
                    st.rerun()

    st.caption("Your choice stays active until you change it.")


# -------------------- STYLING --------------------
st.markdown(
    """
<style>
:root {
    --jane-red: #ff465c;
    --jane-border: #402331;
    --jane-muted: #aaa5b2;
}

.stApp {
    color: #f4f4f5;
    background: repeating-linear-gradient(
        45deg,
        #100d12, #100d12 7px,
        #1b1017 7px, #1b1017 14px
    );
}

[data-testid="stHeader"] {
    background: rgba(11, 11, 16, .92);
}

[data-testid="stSidebar"] {
    background: #0b0b10;
    border-right: 1px solid var(--jane-border);
}

.jane-header {
    background: #050507;
    border: 1px solid #33202a;
    border-radius: 18px;
    padding: 15px 12px;
    text-align: center;
    margin: 0 0 18px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, .2);
}

.jane-title {
    color: var(--jane-red);
    font-size: clamp(25px, 5vw, 34px);
    font-weight: 900;
    letter-spacing: 4px;
    line-height: 1.2;
}

.jane-subtitle {
    color: var(--jane-muted);
    font-size: 12px;
    margin-top: 6px;
}

.welcome-wrap {
    text-align: center;
    padding: clamp(22px, 7vh, 76px) 8px 20px;
}

.welcome-symbol {
    display: inline-block;
    background: #25121b;
    border: 1px solid #592437;
    border-radius: 22px;
    padding: 15px 22px;
    margin-bottom: 16px;
    font-size: 30px;
}

.welcome-title {
    color: #f5f2f6;
    font-size: clamp(25px, 5vw, 36px);
    font-weight: 750;
    margin: 0 0 10px;
}

.welcome-copy {
    color: var(--jane-muted);
    font-size: 15px;
    margin: 0 auto 18px;
    max-width: 540px;
}

[data-testid="stChatMessage"] {
    background: rgba(15, 12, 20, .94);
    border: 1px solid var(--jane-border);
    border-radius: 16px;
    padding: 13px;
    margin-bottom: 10px;
}

/* Native Streamlit chat input stays anchored at the bottom of the page.
   Extra top padding makes room for the overlaid intelligence selector. */
[data-testid="stChatInput"] {
    position: relative !important;
    background: linear-gradient(
        125deg,
        #a10f2b 0%,
        #5a1023 32%,
        #1b0e16 67%,
        #08080b 100%
    ) !important;
    background-color: #210d16 !important;
    border: 1px solid #ff465c !important;
    border-radius: 22px !important;
    padding: 42px 13px 8px !important;
    min-height: 112px !important;
    opacity: 1 !important;
    box-shadow: 0 5px 24px rgba(0, 0, 0, .45) !important;
}

/* Place the real, clickable mode-selector button visually inside the input. */
div[class*="st-key-open_intelligence_dialog"] {
    position: fixed !important;
    z-index: 10002 !important;
    left: max(18px, calc((100vw - 900px) / 2 + 16px)) !important;
    bottom: 112px !important;
    width: auto !important;
    max-width: 190px !important;
    margin: 0 !important;
}

div[class*="st-key-open_intelligence_dialog"] button {
    min-height: 28px !important;
    height: 28px !important;
    width: auto !important;
    padding: 2px 10px !important;
    border-radius: 999px !important;
    background: rgba(12, 8, 13, .92) !important;
    border: 1px solid rgba(255, 150, 165, .55) !important;
    color: #ffffff !important;
    font-size: 12px !important;
    white-space: nowrap !important;
}

div[class*="st-key-open_intelligence_dialog"] button:hover {
    background: #35121f !important;
    border-color: #ff7182 !important;
}

[data-testid="stChatInput"]:focus-within {
    border-color: #ff7182 !important;
    box-shadow: 0 0 0 1px #ff465c, 0 5px 24px rgba(0, 0, 0, .38) !important;
}

[data-testid="stChatInput"] textarea {
    color: #ffffff !important;
    background: transparent !important;
    font-size: 16px !important;
    line-height: 1.5 !important;
    min-height: 42px !important;
    opacity: 1 !important;
}

[data-testid="stChatInput"] textarea::placeholder {
    color: #d0c5cc !important;
    opacity: 1 !important;
}

/* Style Streamlit's native submit control where the installed version exposes it. */
[data-testid="stChatInput"] button {
    background: #ff465c !important;
    color: #ffffff !important;
    border: 0 !important;
    border-radius: 50% !important;
}

[data-testid="stChatInput"] button:hover {
    background: #e9344b !important;
    color: #ffffff !important;
}

/* Keep the chat content from being obscured by the bottom composer. */
.block-container {
    padding-bottom: 120px !important;
}

.stButton > button {
    min-height: 42px;
    border-radius: 12px;
    border: 1px solid var(--jane-border);
    background: #211923;
    color: #f4f4f5;
    transition: border-color .2s ease;
}

.stButton > button:hover {
    border-color: var(--jane-red);
    color: #ffffff;
}

[data-testid="stFileUploader"] {
    background: rgba(21, 19, 26, .85);
    border-radius: 14px;
}

h1, h2, h3 {
    color: #ff5267;
}

p, label, li {
    overflow-wrap: anywhere;
}

.jane-footer {
    color: #898491;
    font-size: 11px;
    text-align: center;
    padding: 12px 4px 5px;
}

@media (max-width: 768px) {
    .block-container {
        padding: .8rem .75rem 130px !important;
        max-width: 100%;
    }

    .jane-header {
        padding: 13px 8px;
        border-radius: 15px;
        margin-bottom: 12px;
    }

    .jane-title {
        font-size: 27px;
        letter-spacing: 3px;
    }

    .jane-subtitle {
        font-size: 11px;
    }

    .welcome-wrap {
        padding-top: 28px;
    }

    [data-testid="stChatMessage"] {
        padding: 10px;
        border-radius: 13px;
    }

    [data-testid="stChatInput"] {
        border-radius: 20px !important;
        padding: 42px 12px 8px !important;
        min-height: 112px !important;
    }

    div[class*="st-key-open_intelligence_dialog"] {
        left: 24px !important;
        bottom: 100px !important;
        max-width: 180px !important;
    }

    [data-testid="stChatInput"] textarea {
        font-size: 16px !important;
    }

    .stButton > button {
        min-height: 44px;
        font-size: 14px;
    }
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        transition: none !important;
        animation: none !important;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("## 🔴 J.A.N.E.")
    st.caption("Your personal intelligence workspace")

    if st.button("＋  New chat", use_container_width=True):
        make_chat()
        st.rerun()

    st.divider()
    st.markdown("### 💬 Chat history")

    for chat_id, chat_data in reversed(list(st.session_state.chats.items())):
        label = chat_data["title"][:30] or "New conversation"
        if chat_id == st.session_state.current_chat:
            label = "● " + label

        if st.button(label, key=f"select_chat_{chat_id}", use_container_width=True):
            st.session_state.current_chat = chat_id
            st.rerun()

    st.divider()
    st.markdown("### 📎 Documents & attachments")

    uploaded = st.file_uploader(
        "Attach files",
        type=["txt", "csv", "xlsx", "pdf", "json", "md"],
        accept_multiple_files=True,
        help="Files remain in the current app session and are not permanently stored.",
    )

    if uploaded:
        for file in uploaded:
            st.session_state.uploaded_files[file.name] = {
                "name": file.name,
                "data": file.getvalue(),
                "type": file.type,
                "size": file.size,
            }

    if st.session_state.uploaded_files:
        st.caption("Files in this session")

        for filename in list(st.session_state.uploaded_files):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.caption(f"📄 {filename}")
            with c2:
                if st.button("✕", key=f"remove_{filename}"):
                    del st.session_state.uploaded_files[filename]
                    st.rerun()

        preview_choice = st.selectbox(
            "Preview a file",
            ["Choose a file"] + list(st.session_state.uploaded_files.keys()),
        )

        if preview_choice != "Choose a file":
            data = st.session_state.uploaded_files[preview_choice]["data"]
            extension = preview_choice.rsplit(".", 1)[-1].lower()

            try:
                if extension == "csv":
                    st.dataframe(
                        pd.read_csv(io.BytesIO(data)).head(30),
                        use_container_width=True,
                    )
                elif extension == "xlsx":
                    st.dataframe(
                        pd.read_excel(io.BytesIO(data)).head(30),
                        use_container_width=True,
                    )
                elif extension in ("txt", "md", "json"):
                    st.text_area(
                        "File preview",
                        data.decode("utf-8", errors="replace")[:6000],
                        height=170,
                        disabled=True,
                    )
                else:
                    st.info("PDF is attached. Reading PDF content is not implemented yet.")
            except Exception:
                st.warning("J.A.N.E. could not preview this file.")

    st.divider()

    with st.expander("👤 Account & preferences"):
        st.session_state.profile_name = st.text_input(
            "Display name",
            value=st.session_state.profile_name,
            max_chars=40,
        )
        st.caption("This is a session profile, not a login account.")

        st.session_state.api_enabled = st.toggle(
            "Enable live AI requests",
            value=st.session_state.api_enabled,
            help="Gemini API usage may be subject to quotas or charges. Disabled by default.",
        )

    if st.button("🗑️ Clear current conversation", use_container_width=True):
        active_chat()["messages"] = []
        active_chat()["title"] = "New conversation"
        st.rerun()


# -------------------- MAIN WORKSPACE --------------------
st.markdown(
    """
<div class="jane-header">
  <div class="jane-title">J.A.N.E.</div>
  <div class="jane-subtitle">
    Judicious, Analytical, and Neuroresearch Engine
  </div>
</div>
""",
    unsafe_allow_html=True,
)

chat = active_chat()
meta_left, meta_right = st.columns([4, 1])

with meta_left:
    st.caption(f"Workspace / {chat['title']}")

with meta_right:
    st.caption(f"👤 {st.session_state.profile_name}")

if not chat["messages"]:
    st.markdown(
        """
<div class="welcome-wrap">
  <div class="welcome-symbol">✦</div>
  <div class="welcome-title">What can I help with?</div>
  <div class="welcome-copy">
    Research, analyze, organize, and think deeper with J.A.N.E.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    suggestions = [
        "Help me plan an online business",
        "Analyze a business idea",
        "Explain a difficult topic",
    ]
    cols = st.columns(3)

    for i, suggestion in enumerate(suggestions):
        with cols[i]:
            if st.button(suggestion, key=f"starter_{i}", use_container_width=True):
                st.session_state.pending_prompt = suggestion
                st.rerun()

for message in chat["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("attachments"):
            st.caption("📎 " + ", ".join(message["attachments"]))

# -------------------- CHAT COMPOSER --------------------
if st.session_state.uploaded_files:
    st.caption(
        "📎 Attached in this session: "
        + ", ".join(st.session_state.uploaded_files.keys())
    )

# This real Streamlit button is visually positioned inside the native composer
# using CSS above. It remains clickable and opens the same mode-selection dialog.
if st.button(
    f"◉ {st.session_state.intelligence_mode} ▾",
    key="open_intelligence_dialog",
    help="Choose how J.A.N.E. responds",
):
    intelligence_dialog()

# Streamlit's native chat input is anchored to the bottom of the page.
submitted_prompt = st.chat_input(
    "Message J.A.N.E....",
    key="jane_chat_input",
)

prompt = submitted_prompt.strip() if submitted_prompt else None

if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None


# -------------------- PROCESS PROMPT --------------------
if prompt:
    attachment_names = list(st.session_state.uploaded_files.keys())
    mode = st.session_state.intelligence_mode

    chat["messages"].append(
        {
            "role": "user",
            "content": prompt,
            "attachments": attachment_names,
            "intelligence_mode": mode,
        }
    )

    if chat["title"] == "New conversation":
        chat["title"] = prompt.strip().replace("\n", " ")[:30] or "New conversation"

    with st.chat_message("user"):
        st.markdown(prompt)
        if attachment_names:
            st.caption("📎 " + ", ".join(attachment_names))

    if st.session_state.api_enabled:
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

            mode_instructions = {
                "General": (
                    "Respond naturally, warmly, and directly, like a helpful "
                    "conversational assistant. Do not force headings such as "
                    "Evidence, Uncertainty, or Transparency. Use lists only when "
                    "they improve clarity. Be accurate and honest."
                ),
                "Adaptive": (
                    "Infer the user's intent and adapt response style and depth. "
                    "For casual chat, be natural and friendly. For practical "
                    "questions, be clear and useful. For analysis, compare options "
                    "and explain important assumptions. For research, be careful "
                    "about evidence and uncertainty. Do not force research-report "
                    "headings when they do not fit."
                ),
                "Thinker": (
                    "Approach challenging prompts deliberately and in depth. "
                    "Consider relevant alternatives, assumptions, trade-offs, edge "
                    "cases, and gaps before giving a clear conclusion. Be thorough "
                    "when the problem warrants it but concise for simple prompts. "
                    "Explain useful reasoning without revealing private "
                    "chain-of-thought. Avoid unnecessary boilerplate headings."
                ),
            }

            system_instruction = (
                "You are J.A.N.E. (Judicious, Analytical, and Neuroresearch Engine), "
                "a careful and helpful assistant. Never claim to have verified "
                "information or performed actions you have not completed. Uploaded "
                "files are not automatically included in this request. "
                f"Active intelligence mode: {mode}. "
                f"Mode instructions: {mode_instructions[mode]}"
            )

            conversation = [system_instruction, "Conversation so far:"]

            for item in chat["messages"]:
                speaker = "User" if item["role"] == "user" else "J.A.N.E."
                conversation.append(f"{speaker}: {item['content']}")

            conversation.append("J.A.N.E.:")

            with st.spinner("J.A.N.E. is thinking..."):
                result = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents="\n\n".join(conversation),
                )

            answer = result.text or "I didn't receive a text response. Please try again."

        except Exception as error:
            error_text = str(error).lower()

            if any(
                term in error_text
                for term in (
                    "insufficient_quota",
                    "no credits",
                    "credit_balance_exhausted",
                )
            ):
                answer = (
                    "Gemini could not complete the request because of an account "
                    "quota or billing limit. Check your usage limits in Google AI Studio."
                )
            elif "gemini_api_key" in error_text or "secrets" in error_text:
                answer = (
                    "The API secret is missing or not configured. Add GEMINI_API_KEY "
                    "in Streamlit app settings → Secrets. Never put the key in this "
                    "file or commit it to GitHub."
                )
            else:
                answer = (
                    "I couldn't contact Gemini. Check your GEMINI_API_KEY, model "
                    "availability, and Streamlit deployment logs. No external action "
                    "was performed."
                )
    else:
        answer = (
            "J.A.N.E. is in **UI development mode**. Your message is saved in this "
            "session, but live AI requests are disabled. Open **Account & preferences** "
            "in the sidebar and enable live requests to send messages to Gemini. "
            "API usage may be subject to quotas or charges."
        )

    chat["messages"].append(
        {
            "role": "assistant",
            "content": answer,
            "intelligence_mode": mode,
        }
    )

    with st.chat_message("assistant"):
        st.markdown(answer)

st.markdown(
    "<div class='jane-footer'>J.A.N.E. 0.3 · Gemini API · "
    "Session data is temporary · Verify important decisions</div>",
    unsafe_allow_html=True,
)
