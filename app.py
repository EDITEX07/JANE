
import io
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="J.A.N.E. | AI Workspace",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- DESIGN ----------
st.markdown("""
<style>
.stApp {
    background:
        repeating-linear-gradient(
            45deg,
            #171014,
            #171014 5px,
            #211217 5px,
            #211217 10px
        );
    color: #f4f4f5;
}
[data-testid="stHeader"] {
    background: transparent;
}
[data-testid="stSidebar"] {
    background: #0b0b10;
    border-right: 1px solid #38212b;
}
.jane-header {
    background: #050507;
    border: 1px solid #29202a;
    border-radius: 18px;
    padding: 12px 18px;
    text-align: center;
    margin-bottom: 22px;
}
.jane-title {
    color: #ff465c;
    font-size: 30px;
    font-weight: 900;
    letter-spacing: 4px;
}
.jane-subtitle {
    color: #a8a8b3;
    font-size: 13px;
}
[data-testid="stChatMessage"] {
    background: rgba(15, 12, 20, 0.94);
    border: 1px solid #35232d;
    border-radius: 15px;
    padding: 12px;
}
[data-testid="stChatInput"] {
    border: 1px solid #a91b46;
    border-radius: 15px;
}
.stButton > button {
    border-radius: 10px;
    border: 1px solid #482532;
}
h1, h2, h3 {
    color: #ff5267;
}
</style>
""", unsafe_allow_html=True)


# ---------- SESSION DATA ----------
if "chats" not in st.session_state:
    first_id = str(uuid.uuid4())
    st.session_state.chats = {
        first_id: {
            "title": "New conversation",
            "messages": [],
            "created": datetime.now().strftime("%d %b, %H:%M"),
        }
    }
    st.session_state.current_chat = first_id

if "profile_name" not in st.session_state:
    st.session_state.profile_name = "Explorer"

if "api_enabled" not in st.session_state:
    st.session_state.api_enabled = False

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = {}


def current_chat():
    return st.session_state.chats[
        st.session_state.current_chat
    ]


def new_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = {
        "title": "New conversation",
        "messages": [],
        "created": datetime.now().strftime("%d %b, %H:%M"),
    }
    st.session_state.current_chat = chat_id


# ---------- SIDEBAR ----------
with st.sidebar:
    st.markdown("## 🔴 J.A.N.E.")
    st.caption("Your personal intelligence workspace")

    if st.button("＋  New chat", use_container_width=True):
        new_chat()
        st.rerun()

    st.divider()
    st.markdown("### Your conversations")

    for chat_id, chat in reversed(
        list(st.session_state.chats.items())
    ):
        label = chat["title"][:28]
        if chat_id == st.session_state.current_chat:
            label = "● " + label

        if st.button(
            label,
            key=f"chat_{chat_id}",
            use_container_width=True,
        ):
            st.session_state.current_chat = chat_id
            st.rerun()

    st.divider()
    st.markdown("### 📎 Documents & attachments")

    uploaded = st.file_uploader(
        "Add files to this session",
        type=["txt", "csv", "xlsx", "pdf", "json", "md"],
        accept_multiple_files=True,
        help="Uploads are held in this app session, not permanently stored.",
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
        st.caption("Available in this session")

        for filename, fileinfo in list(
            st.session_state.uploaded_files.items()
        ):
            col1, col2 = st.columns([4, 1])

            with col1:
                st.text(f"📄 {filename}")

            with col2:
                if st.button("×", key=f"remove_{filename}"):
                    del st.session_state.uploaded_files[filename]
                    st.rerun()

        selected_file = st.selectbox(
            "Preview a file",
            ["None"] + list(st.session_state.uploaded_files.keys()),
        )

        if selected_file != "None":
            fileinfo = st.session_state.uploaded_files[selected_file]
            extension = selected_file.rsplit(".", 1)[-1].lower()

            try:
                if extension == "csv":
                    df = pd.read_csv(
                        io.BytesIO(fileinfo["data"])
                    )
                    st.dataframe(df.head(20), use_container_width=True)

                elif extension in ("txt", "md", "json"):
                    text_preview = fileinfo["data"].decode(
                        "utf-8", errors="replace"
                    )
                    st.text_area(
                        "File preview",
                        text_preview[:5000],
                        height=150,
                        disabled=True,
                    )

                elif extension == "xlsx":
                    df = pd.read_excel(
                        io.BytesIO(fileinfo["data"])
                    )
                    st.dataframe(df.head(20), use_container_width=True)

                else:
                    st.info(
                        "File attached. PDF content extraction "
                        "will be added in a later phase."
                    )

            except Exception:
                st.warning("This file could not be previewed.")

    st.divider()

    with st.expander("👤 Account & preferences"):
        st.session_state.profile_name = st.text_input(
            "Display name",
            value=st.session_state.profile_name,
            max_chars=40,
        )

        st.caption(
            "This is a local session profile, not a secure account."
        )

        st.session_state.api_enabled = st.checkbox(
            "Enable live AI requests",
            value=st.session_state.api_enabled,
            help="AI API calls may incur charges.",
        )

        st.caption(
            "Live AI requests are OFF by default to avoid "
            "unexpected API usage."
        )

    if st.button("🗑️ Clear current conversation",
                 use_container_width=True):
        current_chat()["messages"] = []
        current_chat()["title"] = "New conversation"
        st.rerun()


# ---------- MAIN CHAT ----------
st.markdown("""
<div class="jane-header">
    <div class="jane-title">J.A.N.E.</div>
    <div class="jane-subtitle">
        Judicious, Analytical, and Neuroresearch Engine
    </div>
</div>
""", unsafe_allow_html=True)

top_left, top_right = st.columns([4, 1])

with top_left:
    st.caption(
        f"Workspace / {current_chat()['title']}"
    )

with top_right:
    st.markdown(
        f"👤 **{st.session_state.profile_name}**"
    )

chat = current_chat()

if not chat["messages"]:
    st.markdown("## What shall we work on?")
    st.write(
        "Research ideas, understand business data, "
        "or prepare your next decision."
    )

    suggestions = [
        "Help me plan an online business",
        "Explain how to analyse business data",
        "Help me evaluate a business idea",
    ]

    cols = st.columns(len(suggestions))

    for i, suggestion in enumerate(suggestions):
        with cols[i]:
            if st.button(
                suggestion,
                key=f"suggestion_{i}",
                use_container_width=True,
            ):
                st.session_state.pending_prompt = suggestion
                st.rerun()

for message in chat["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message.get("attachments"):
            st.caption(
                "📎 " + ", ".join(message["attachments"])
            )

prompt = st.chat_input("It's JANE. Ask of your mind...")

if "pending_prompt" in st.session_state:
    prompt = st.session_state.pop("pending_prompt")

if prompt:
    attachments = list(st.session_state.uploaded_files.keys())

    chat["messages"].append({
        "role": "user",
        "content": prompt,
        "attachments": attachments,
    })

    if chat["title"] == "New conversation":
        chat["title"] = prompt[:28]

    with st.chat_message("user"):
        st.markdown(prompt)
        if attachments:
            st.caption("📎 " + ", ".join(attachments))

    answer = None

    if st.session_state.api_enabled:
        try:
            api_key = st.secrets["OPENAI_API_KEY"]
            client = OpenAI(api_key=api_key)

            api_messages = [{
                "role": "system",
                "content": (
                    "You are JANE, a careful AI assistant for "
                    "research, business analysis and decision support. "
                    "Distinguish evidence from assumptions, identify "
                    "uncertainty, and never claim to have verified "
                    "something you have not verified."
                ),
            }]

            for item in chat["messages"]:
                api_messages.append({
                    "role": item["role"],
                    "content": item["content"],
                })

            with st.spinner("JANE is thinking..."):
                result = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=api_messages,
                    max_tokens=1200,
                    timeout=45,
                )

            answer = result.choices[0].message.content

        except Exception as error:
            error_text = str(error).lower()

            if (
                "insufficient_quota" in error_text
                or "no credits" in error_text
                or "credit_balance_exhausted" in error_text
            ):
                answer = (
                    "Your OpenAI API account has no available "
                    "credits. Your message is saved in this session, "
                    "but I cannot generate an AI response until "
                    "API access is available."
                )
            else:
                answer = (
                    "I couldn't contact the AI service. Check your "
                    "API configuration and deployment logs. "
                    "No external action was performed."
                )

    else:
        answer = (
            "JANE is currently in **UI development mode**. "
            "Your message has been saved in this session, but "
            "live AI requests are disabled to avoid API charges. "
            "You can continue exploring the interface and "
            "uploading files while we build the next features."
        )

    chat["messages"].append({
        "role": "assistant",
        "content": answer or "No response was returned.",
    })

    with st.chat_message("assistant"):
        st.markdown(answer or "No response was returned.")

st.divider()
st.caption(
    "JANE 0.1 • Development mode • "
    "Session data is temporary and may disappear when the session resets."
)
