
import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="JANE AI",
    page_icon="🧠",
    layout="centered"
)

st.title("🧠 JANE AI")
st.caption("Judicious, Analytical, and Neuroresearch Engine")

st.markdown(
    "Your AI assistant for research, analysis, "
    "problem-solving, and business decisions."
)

# Load the API key securely from Streamlit Secrets
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    api_key = None

if not api_key:
    st.warning(
        "JANE needs an OpenAI API key. "
        "We will configure it during deployment."
    )
    st.stop()

client = OpenAI(api_key=api_key)

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are JANE, the Judicious, Analytical, "
                "and Neuroresearch Engine. "
                "Explain things clearly, reason carefully, "
                "distinguish facts from assumptions, "
                "identify uncertainty and risks, and "
                "support recommendations with evidence "
                "when available. Never claim to have "
                "verified information or performed actions "
                "that you have not actually verified. "
                "Ask for clarification when necessary. "
                "Require human approval before consequential "
                "external actions."
            )
        }
    ]

# Display the conversation
for message in st.session_state.messages:
    if message["role"] == "system":
        continue

    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
prompt = st.chat_input("Ask JANE anything...")

if prompt:
    st.session_state.messages.append(
        {"role": "user", "content": prompt}
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("JANE is thinking..."):
                response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=st.session_state.messages,
                    max_tokens=1200,
                    timeout=60
                )

                answer = response.choices[0].message.content
                answer = answer or "I couldn't generate a response."

            st.markdown(answer)

            st.session_state.messages.append(
                {"role": "assistant", "content": answer}
            )

        except Exception as error:
            st.error(
                "JANE couldn't complete that request. "
                "Check the API configuration and try again."
            )
            st.caption(f"Technical details: {error}")

if st.button("Clear conversation"):
    st.session_state.messages = [
        st.session_state.messages[0]
    ]
    st.rerun()
