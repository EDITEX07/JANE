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

if "profile_name" not in st.session_state:
    st.session_state.profile_name = "Explorer"

if "api_enabled" not in st.session_state:
    st.session_state.api_enabled = False

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = {}

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None


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


# -------------------- STYLING --------------------
st.markdown(
    """
    <style>
    :root {
        --jane-red: #ff465c;
        --jane-bg: #0b0b10;
        --jane-panel: #17151d;
        --jane-border: #402331;
        --jane-muted: #aaa5b2;
    }

    .stApp {
        color: #f4f4f5;
        background:
            repeating-linear-gradient(
                45deg,
                #100d12,
                #100d12 7px,
                #1b1017 7px,
                #1b1017 14px
            );
    }

    [data-testid="stHeader"] {
        background: rgba(11, 11, 16, 0.92);
    }

    [data-testid="stSidebar"] {
        background: #0b0b10;
        border-right: 1px solid var(--jane-border);
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem;
    }

    .jane-header {
        background: #050507;
        border: 1px solid #33202a;
        border-radius: 18px;
        padding: 15px 12px;
        text-align: center;
        margin: 0 0 18px 0;
        box-shadow: 0 8px 28px rgba(0,0,0,.20);
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
        margin: 0 0 10px 0;
    }

    .welcome-copy {
        color: var(--jane-muted);
        font-size: 15px;
        margin: 0 auto 18px auto;
        max-width: 540px;
    }

    [data-testid="stChatMessage"] {
        background: rgba(15, 12, 20, .94);
        border: 1px solid var(--jane-border);
        border-radius: 16px;
        padding: 13px;
        margin-bottom: 10px;
    }

    /* Spacious native Streamlit chat composer */
    [data-testid="stChatInput"] {
        background: #17131d;
        border: 1px solid #853047;
        border-radius: 22px;
        padding: 10px 13px;
        min-height: 112px;
        box-shadow: 0 5px 24px rgba(0,0,0,.24);
    }

    [data-testid="stChatInput"]:focus-within {
        border-color: var(--jane-red);
        box-shadow: 0 0 0 1px var(--jane-red);
    }

    [data-testid="stChatInput"] textarea {
        min-height: 72px !important;
        max-height: 240px !important;
        font-size: 16px !important;
        line-height: 1.5 !important;
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
        color: #fff;
    }

    [data-testid="stFileUploader"] {
        background: rgba(21,19,26,.85);
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
            padding: 0.8rem 0.75rem 2rem 0.75rem;
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
            min-height: 118px;
            border-radius: 20px;
            padding: 10px 12px;
        }

        [data-testid="stChatInput"] textarea {
            min-height: 76px !important;
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
            col_file, col_remove = st.columns([5, 1])
            with col_file:
                st.caption(f"📄 {filename}")
            with col_remove:
                if st.button("✕", key=f"remove_{filename}"):
                    del st.session_state.uploaded_files[filename]
                    st.rerun()

        preview_choice = st.selectbox(
            "Preview a file",
            ["Choose a file"] + list(st.session_state.uploaded_files.keys()),
        )

        if preview_choice != "Choose a file":
            file_data = st.session_state.uploaded_files[preview_choice]["data"]
            extension = preview_choice.rsplit(".", 1)[-1].lower()

            try:
                if extension == "csv":
                    frame = pd.read_csv(io.BytesIO(file_data))
                    st.dataframe(frame.head(30), use_container_width=True)
                elif extension == "xlsx":
                    frame = pd.read_excel(io.BytesIO(file_data))
                    st.dataframe(frame.head(30), use_container_width=True)
                elif extension in ("txt", "md", "json"):
                    content = file_data.decode("utf-8", errors="replace")
                    st.text_area(
                        "File preview",
                        content[:6000],
                        height=170,
                        disabled=True,
                    )
                else:
                    st.info(
                        "PDF is attached. Reading PDF content will be added "
                        "in a later development phase."
                    )
            except Exception:
                st.warning("JANE could not preview this file.")

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

# Welcome state, shown only before the first message
if not chat["messages"]:
    st.markdown(
        """
        <div class="welcome-wrap">
            <div class="welcome-symbol">✦</div>
            <div class="welcome-title">What can I help with?</div>
            <div class="welcome-copy">
                Research, analyze, organize, and think deeper with JANE.
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
    suggestion_cols = st.columns(3)
    for index, suggestion in enumerate(suggestions):
        with suggestion_cols[index]:
            if st.button(
                suggestion,
                key=f"starter_{index}",
                use_container_width=True,
            ):
                st.session_state.pending_prompt = suggestion
                st.rerun()

# Render saved messages
for message in chat["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("attachments"):
            st.caption("📎 " + ", ".join(message["attachments"]))

# Composer attachments indicator
if st.session_state.uploaded_files:
    st.caption(
        "📎 Attached in this session: "
        + ", ".join(st.session_state.uploaded_files.keys())
    )

prompt = st.chat_input(
    "Message JANE...",
    key="jane_chat_input",
)

if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None

if prompt:
    attachment_names = list(st.session_state.uploaded_files.keys())
    chat["messages"].append(
        {
            "role": "user",
            "content": prompt,
            "attachments": attachment_names,
        }
    )

    if chat["title"] == "New conversation":
        chat["title"] = prompt.strip().replace("\n", " ")[:30] or "New conversation"

    with st.chat_message("user"):
        st.markdown(prompt)
        if attachment_names:
            st.caption("📎 " + ", ".join(attachment_names))

    answer = None

    if st.session_state.api_enabled:
        try:
            api_key = st.secrets["GEMINI_API_KEY"]
            client = genai.Client(api_key=api_key)

            system_instruction = (
                "You are JANE (Judicious, Analytical, and Neuroresearch Engine), "
                "a careful assistant for research, business analysis, and "
                "decision support. Separate evidence from assumptions, explain "
                "uncertainty, and never claim to have verified information "
                "or performed actions you have not actually completed. "
                "Uploaded files are not automatically included in this request."
            )
            conversation = [system_instruction, "\nConversation so far:"]
            for item in chat["messages"]:
                speaker = "User" if item["role"] == "user" else "JANE"
                conversation.append(f"{speaker}: {item['content']}")
            conversation.append("JANE:")

            with st.spinner("JANE is thinking..."):
                result = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents="\n\n".join(conversation),
                )

            answer = result.text

        except Exception as error:
            error_text = str(error).lower()
            if (
                "insufficient_quota" in error_text
                or "no credits" in error_text
                or "credit_balance_exhausted" in error_text
            ):
                answer = (
                    "Gemini could not complete the request because of an account quota or billing limit. "
                    "Your message is saved in this session. Check the model and usage limits "
                    "in Google AI Studio before trying again."
                )
            elif "gemini_api_key" in error_text or "secrets" in error_text:
                answer = (
                    "The API secret is missing or not configured. Add "
                    "GEMINI_API_KEY in Streamlit app settings → Secrets. "
                    "Never put the key in this file or commit it to GitHub."
                )
            else:
                answer = (
                    "I couldn't contact Gemini. Check your GEMINI_API_KEY, "
                    "model availability, and Streamlit deployment logs. "
                    "No external action was performed."
                )
    else:
        answer = (
            "JANE is in **UI development mode**. Your message is saved in "
            "this session, but live AI requests are disabled. Open **Account "
            "& preferences** in the sidebar and enable live requests to "
            "send messages to Gemini. API usage may be subject to quotas or charges."
        )

    answer = answer or "No response was returned."
    chat["messages"].append({"role": "assistant", "content": answer})

    with st.chat_message("assistant"):
        st.markdown(answer)

st.markdown(
    """
    <div class="jane-footer">
        JANE 0.4 · Gemini API · Session data is temporary · Verify important decisions
    </div>
    """,
    unsafe_allow_html=True,
)
