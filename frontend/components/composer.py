from __future__ import annotations

import hashlib
import html
import os

import streamlit as st

from backend.support_app.image_service import image_feature_enabled
from backend.support_app.models import ImageInput
from backend.support_app.voice import transcribe_audio


def render_support_request_form(mode: str) -> tuple[bool, str, list[ImageInput]]:
    with st.container(border=True):
        st.markdown(
            '<div class="composer-heading">'
            '<div><div class="section-title">Support request</div>'
            '<div class="section-note">Type, record, or attach an image. Voice is transcribed automatically.</div></div>'
            f'<div class="mode-chip">{html.escape(mode)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        input_col, tools_col = st.columns([0.72, 0.28], gap="large", vertical_alignment="top")

        with tools_col:
            st.markdown('<div class="section-title">Voice</div>', unsafe_allow_html=True)
            if os.getenv("ENABLE_VOICE", "false").lower() == "true":
                if hasattr(st, "audio_input"):
                    audio_value = st.audio_input(
                        "Record customer question",
                        sample_rate=16000,
                        label_visibility="collapsed",
                    )
                    if audio_value:
                        audio_bytes = audio_value.getvalue()
                        audio_hash = hashlib.sha256(audio_bytes).hexdigest()
                    else:
                        audio_hash = ""
                    if audio_value and audio_hash != st.session_state.get("voice_audio_hash"):
                        st.session_state["voice_audio_hash"] = audio_hash
                        with st.spinner("Transcribing locally..."):
                            transcript = transcribe_audio(audio_value)
                        if transcript.error:
                            st.session_state["voice_error"] = transcript.error
                            st.session_state["voice_success"] = ""
                        else:
                            st.session_state["query_text"] = transcript.text
                            st.session_state["voice_error"] = ""
                            st.session_state["voice_success"] = "Transcript added."
                    if st.session_state.get("voice_error"):
                        st.warning(st.session_state["voice_error"])
                    if st.session_state.get("voice_success"):
                        st.success(st.session_state["voice_success"])
                else:
                    st.warning("Voice is enabled, but this Streamlit version does not include st.audio_input.")
            else:
                st.info("Voice is disabled.")

            st.markdown('<div class="section-title">Image</div>', unsafe_allow_html=True)
            uploaded_image_files = []
            if image_feature_enabled():
                uploaded_image_files = st.file_uploader(
                    "Attach support image",
                    type=["png", "jpg", "jpeg", "webp"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                )
                for uploaded_image in uploaded_image_files or []:
                    st.image(uploaded_image, caption=uploaded_image.name, width=180)
            else:
                st.info("Image support is disabled.")

        with input_col:
            query = st.text_area(
                "Customer query",
                key="query_text",
                height=245,
                placeholder="Type the customer question here.",
            )

        _action_spacer, action_col = st.columns([0.76, 0.24])
        with action_col:
            run_requested = st.button("Run support crew", type="primary", use_container_width=True)

    image_inputs = [
        ImageInput(
            file_name=uploaded_image.name,
            mime_type=uploaded_image.type or "application/octet-stream",
            data=uploaded_image.getvalue(),
        )
        for uploaded_image in uploaded_image_files or []
    ]
    return run_requested, query, image_inputs
