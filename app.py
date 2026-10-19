import io
import re
import base64
import json
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from openai import OpenAI  # still used for the text-chat quota fallback only

st.set_page_config(page_title="J.A.N.E. | AI Workspace", page_icon="🔴", layout="wide", initial_sidebar_state="collapsed")

# -------------------- LOGIN PORTRAIT --------------------
# Paste your ORIGINAL base64 portrait string between the quotes below (the long
# text that used to sit after "data:image/jpeg;base64," in the <img> tag).
# Alternatively, save the picture as "jane_portrait.jpg" next to app.py.
# If neither exists, the login screen simply skips the portrait.
JANE_PORTRAIT_B64 = ""


def portrait_html():
    b64 = JANE_PORTRAIT_B64.strip()
    if not b64:
        portrait_file = Path(__file__).with_name("jane_portrait.jpg")
        if portrait_file.exists():
            b64 = base64.b64encode(portrait_file.read_bytes()).decode("ascii")
    if not b64:
        return ""
    return ('<div class="jane-portrait-frame"><img class="jane-portrait" src="data:image/jpeg;base64,'
            + b64 + '" alt="J.A.N.E. male character portrait"></div>')


# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    first_id = str(uuid.uuid4())
    st.session_state.chats = {first_id: {"title": "New conversation", "messages": [], "created": datetime.now().strftime("%d %b %Y, %H:%M")}}
    st.session_state.current_chat = first_id
for key, default in {
    "profile_name": "Explorer", "api_enabled": True, "uploaded_files": {},
    "pending_prompt": None, "intelligence_mode": "Adaptive",
    "auth_user": None, "auth_token": None, "auth_mode": "signin",
    "voice_speed": 1.0,
}.items():
    if key not in st.session_state:
        }
        raise ValueError(friendly.get(code, f"Firebase authentication failed: {code}")) from None


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
    with st.expander("🔊 Voice settings", expanded=False):
        st.session_state.voice_speed = st.slider(
            "Reading speed",
            min_value=0.5, max_value=3.0,
            value=float(st.session_state.voice_speed),
            step=0.1, format="%.1f×",
            help="How fast J.A.N.E. reads aloud (0.5× slow to 3× fast)",
        )
        st.caption("Uses your device's built-in voice. Tap 🔊 under a reply to listen, tap ⏹ to stop. Speed applies the next time you tap 🔊.")
    with st.expander("👤 Account & preferences"):
        st.session_state.profile_name = st.text_input("Display name", value=st.session_state.profile_name, max_chars=40)
        st.caption("This is a session profile, not a login account.")
        st.caption("Live AI requests are always enabled. API usage may be subject to quotas or charges.")
        st.caption("Read-aloud uses your device's system voice from the 🔊 button below each reply.")
    if st.button("🗑️ Clear current conversation", use_container_width=True):
        active_chat()["messages"] = []; active_chat()["title"] = "New conversation"; st.rerun()

                            "is not configured yet. Add OPENAI_API_KEY in Streamlit app settings → Secrets."
                        )
                    else:
                        system_instruction = build_system_instruction(mode)
                        history = []
                        for item in chat["messages"]:
                            role = "user" if item.get("role") == "user" else "assistant"
                            history.append({"role": role, "content": item.get("content", "")})
                        with st.spinner("Gemini hit a limit. J.A.N.E. is switching to OpenAI..."):
                            openai_client = OpenAI(api_key=openai_key)
                            response = openai_client.responses.create(
                                model=st.secrets.get("OPENAI_MODEL", "gpt-4.1-mini"),
                                instructions=system_instruction,
                                input=history,
                            )
                        answer = response.output_text or "OpenAI returned an empty response. Please try again."
                        st.caption("↪ Answered by OpenAI because Gemini reached its quota/rate limit.")
                except Exception as fallback_error:
                    fallback_text = str(fallback_error).lower()
                    if "401" in fallback_text or "api key" in fallback_text or "authentication" in fallback_text:
                        answer = "Gemini reached its quota, but OpenAI fallback authentication failed. Check OPENAI_API_KEY in Streamlit Secrets."
                    elif "429" in fallback_text or "quota" in fallback_text or "rate limit" in fallback_text:
                        answer = "Both Gemini and OpenAI appear to be limited right now. Check both providers' usage limits and try again later."
                    else:
                        answer = f"Gemini hit its quota and OpenAI fallback failed ({type(fallback_error).__name__}). Check Streamlit logs; API keys are not shown."
            elif is_key_error:
                answer = "The Gemini API secret is missing or invalid. Check GEMINI_API_KEY in Streamlit app settings → Secrets. Never put keys in this file or commit them to GitHub."
            elif is_quota_error:
                answer = "Gemini image generation reached a quota/rate limit. Automatic OpenAI fallback currently applies to text chat only; check Gemini usage or try image generation later."
            else:
                answer = f"I couldn't complete that request ({type(error).__name__}). Check Streamlit logs for the full error; your API key is not displayed here."
    assistant_message = {"role": "assistant", "content": answer, "intelligence_mode": mode}
    if generated_image_bytes:
        assistant_message["image_bytes"] = generated_image_bytes
        assistant_message["image_filename"] = "jane_generated_image.png"
    chat["messages"].append(assistant_message)
    with st.chat_message("assistant", avatar="assistant"):
        st.markdown(answer)
        if generated_image_bytes:
            st.image(generated_image_bytes, caption="Generated by J.A.N.E.", use_container_width=True)
            st.download_button("⬇ Download image", data=generated_image_bytes, file_name="jane_generated_image.png", mime="image/png", key=f"download_latest_image_{len(chat['messages'])}")
        else:
            render_copy_answer(answer, f"latest-{len(chat['messages'])}")
            render_speak_controls(answer, f"latest-{len(chat['messages'])}")

st.markdown("<div class='jane-footer'>J.A.N.E. 0.92 · OCR · Gemini + OpenAI fallback · System voice read-aloud · Guest data is temporary · Verify important decisions</div>", unsafe_allow_html=True)
