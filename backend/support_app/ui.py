from __future__ import annotations

import hashlib
import html
import os
from dataclasses import asdict

import streamlit as st

from backend.support_app.auth import require_authentication, render_auth_sidebar
from backend.support_app.config import APP_ROOT, DEFAULT_MODEL, ensure_runtime_dirs, get_serpapi_key
from backend.support_app.crewai_flow import crewai_dependency_status
from backend.support_app.google_sheets import ensure_google_reporting_destination, google_sheets_enabled
from backend.support_app.image_service import image_feature_enabled
from backend.support_app.models import ImageArtifact, ImageInput, RunRecord
from backend.support_app.retention import apply_retention_policy
from backend.support_app.storage import init_db
from backend.support_app.voice import synthesize_speech, transcribe_audio
from backend.support_app.workflow import run_support_flow


def render_app_chrome() -> None:
    st.markdown(
        """
        <style>
        :root {
            --surface: #ffffff;
            --page: #f7f8fb;
            --ink: #20232d;
            --muted: #667085;
            --line: #d9dee8;
            --soft-line: #e8ebf2;
            --accent: #d92d3a;
            --accent-dark: #bb2430;
            --ok: #17803d;
            --warn: #b54708;
        }
        html, body, [data-testid="stAppViewContainer"] {
            background: var(--page);
        }
        .main .block-container {
            max-width: 1240px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }
        [data-testid="stSidebar"] {
            background: #eef2f7;
            border-right: 1px solid #d7dde8;
        }
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--ink);
            letter-spacing: 0 !important;
        }
        [data-testid="stSidebar"] [role="radiogroup"] {
            gap: 0.35rem;
        }
        h1 {
            font-size: 2.25rem !important;
            line-height: 1.12 !important;
            letter-spacing: 0 !important;
            margin-bottom: 0.35rem !important;
            color: var(--ink);
        }
        h2, h3 {
            letter-spacing: 0 !important;
        }
        .app-eyebrow {
            color: #8a3441;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0 !important;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }
        .app-kicker,
        .section-note {
            color: var(--muted);
            font-size: 0.98rem;
        }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
            margin-top: 0.2rem;
        }
        [data-testid="stSidebar"] .status-grid {
            grid-template-columns: 1fr;
        }
        .status-pill {
            background: var(--surface);
            border: 1px solid var(--soft-line);
            border-radius: 8px;
            padding: 0.58rem 0.68rem;
        }
        .status-pill .label {
            color: var(--muted);
            display: block;
            font-size: 0.72rem;
            line-height: 1.1;
        }
        .status-pill .value {
            color: var(--ink);
            display: block;
            font-size: 0.88rem;
            font-weight: 700;
            line-height: 1.35;
            margin-top: 0.15rem;
            overflow-wrap: anywhere;
        }
        .status-pill.good .value {
            color: var(--ok);
        }
        .status-pill.warn .value {
            color: var(--warn);
        }
        .section-title {
            color: var(--ink);
            font-size: 1rem;
            font-weight: 750;
            line-height: 1.25;
            margin-bottom: 0.1rem;
        }
        .composer-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.75rem;
        }
        .mode-chip {
            border: 1px solid #f1b4bb;
            border-radius: 999px;
            color: #a61b29;
            font-size: 0.78rem;
            font-weight: 700;
            padding: 0.22rem 0.58rem;
            white-space: nowrap;
        }
        div[data-testid="stTextArea"] textarea {
            min-height: 245px;
            border-radius: 8px;
            border: 1px solid #d9dee8;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
            font-size: 0.96rem;
            line-height: 1.5;
        }
        div[data-testid="stTextArea"] textarea:focus {
            border-color: #475467;
            box-shadow: 0 0 0 3px rgba(71, 84, 103, 0.12);
        }
        div[data-testid="stAudioInput"] {
            border: 1px solid #d9dee8;
            border-radius: 8px;
            background: #ffffff;
            padding: 0.75rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }
        div[data-testid="stTextArea"] label,
        div[data-testid="stAudioInput"] label {
            color: var(--ink) !important;
            font-weight: 700 !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.3rem;
            border-bottom: 1px solid var(--soft-line);
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            font-weight: 700;
            padding-left: 0.85rem;
            padding-right: 0.85rem;
        }
        div[data-testid="stExpander"] {
            border: 1px solid var(--soft-line);
            border-radius: 8px;
            background: var(--surface);
        }
        div.stButton > button {
            border-radius: 8px;
            min-height: 2.65rem;
            font-weight: 600;
        }
        div.stButton > button[kind="primary"] {
            background: var(--accent);
            border-color: var(--accent);
        }
        div.stButton > button[kind="primary"]:hover {
            background: var(--accent-dark);
            border-color: var(--accent-dark);
        }
        .result-divider {
            height: 1px;
            background: var(--soft-line);
            margin: 1.25rem 0 1rem;
        }
        div[data-testid="stStatusWidget"] {
            visibility: hidden;
            height: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_status_grid(items: list[tuple[str, str, str]]) -> None:
    cells = "".join(
        (
            f'<div class="status-pill {html.escape(tone)}">'
            f'<span class="label">{html.escape(label)}</span>'
            f'<span class="value">{html.escape(value)}</span>'
            "</div>"
        )
        for label, value, tone in items
    )
    st.markdown(f'<div class="status-grid">{cells}</div>', unsafe_allow_html=True)


def render_header(mode: str) -> None:
    crewai_status = crewai_dependency_status()
    header_col, status_col = st.columns([0.62, 0.38], gap="large", vertical_alignment="center")
    with header_col:
        st.markdown(
            '<div class="app-eyebrow">AI support workspace</div>'
            "<h1>Customer Support Assistant</h1>"
            '<div class="app-kicker">One production answer with traceable retrieval, web fallback, voice input, and cost logs.</div>',
            unsafe_allow_html=True,
        )
    with status_col:
        render_status_grid(
            [
                ("Mode", mode, "warn" if mode == "buildathon" else "good"),
                ("CrewAI", crewai_status, "good" if crewai_status == "ready" else "warn"),
                ("Voice", os.getenv("ENABLE_VOICE", "false").lower(), "good"),
                ("Image", str(image_feature_enabled()).lower(), "good" if image_feature_enabled() else "warn"),
                ("LangSmith", os.getenv("LANGSMITH_TRACING", "false").lower(), "good"),
                ("SerpAPI", "ready" if get_serpapi_key() else "missing", "good" if get_serpapi_key() else "warn"),
            ]
        )


def render_sidebar(mode_options: list[str]) -> str:
    crewai_status = crewai_dependency_status()
    with st.sidebar:
        render_auth_sidebar()
        st.markdown("### Control")
        mode = st.radio("Mode", mode_options, index=0)
        st.markdown("### Runtime")
        render_status_grid(
            [
                ("Model", DEFAULT_MODEL, "good"),
                ("CrewAI", crewai_status, "good" if crewai_status == "ready" else "warn"),
                ("Voice", os.getenv("ENABLE_VOICE", "false").lower(), "good"),
                ("Image", str(image_feature_enabled()).lower(), "good" if image_feature_enabled() else "warn"),
                ("LangSmith", os.getenv("LANGSMITH_TRACING", "false").lower(), "good"),
                ("SerpAPI", "ready" if get_serpapi_key() else "missing", "good" if get_serpapi_key() else "warn"),
            ]
        )
    return mode


def render_final_answer(record: RunRecord) -> None:
    st.subheader("Final Answer")
    st.write(record.final_answer)
    render_generated_images(record.generated_images)
    audio_path = synthesize_speech(record.final_answer, record.run_id)
    if audio_path:
        st.caption("Audio response")
        st.audio(str(audio_path))
    elif os.getenv("ENABLE_VOICE", "false").lower() == "true":
        st.warning(
            "Audio response could not be generated. Install Piper/eSpeak, or use Docker where eSpeakNG is installed."
        )


def artifact_path(image: ImageArtifact) -> str:
    if image.storage_path.startswith(("http://", "https://")):
        return image.storage_path
    return str(APP_ROOT / image.storage_path)


def render_generated_images(images: list[ImageArtifact]) -> None:
    generated = [image for image in images if image.source_type == "generated"]
    if not generated:
        return
    st.caption("Generated image output")
    for image in generated:
        if image.error:
            st.warning(image.error)
            continue
        if image.storage_path:
            st.image(artifact_path(image), caption=image.file_name or "Generated image")


def render_image_trace(record: RunRecord) -> None:
    if not record.uploaded_images and not record.generated_images:
        st.info("No images were attached or generated.")
        return

    for image in record.uploaded_images:
        st.markdown(f"**Uploaded:** `{image.file_name}`")
        st.caption(f"{image.mime_type} | {image.width}x{image.height}px | sha256 `{image.sha256[:12]}`")
        if image.storage_path:
            st.image(artifact_path(image), width=220)
        if image.analysis:
            st.write(image.analysis)
        if image.error:
            st.warning(image.error)

    for image in record.generated_images:
        st.markdown(f"**Generated:** `{image.file_name or 'image output'}`")
        if image.storage_path and not image.error:
            st.image(artifact_path(image), width=320)
        if image.error:
            st.warning(image.error)


def render_buildathon_tabs(record: RunRecord | None = None) -> None:
    final_tab, direct_tab, web_tab = st.tabs(
        ["Final Answer", "Direct Assistant", "Web Search Assistant"]
    )
    if record is None:
        with final_tab:
            st.info("Run the support crew to generate the synthesized final answer.")
        with direct_tab:
            st.info("The local-knowledge assistant answer will appear here.")
        with web_tab:
            st.info("The SerpAPI web-search assistant answer will appear here.")
        return

    with final_tab:
        render_final_answer(record)
    with direct_tab:
        st.write(record.direct_answer)
    with web_tab:
        st.write(record.web_answer)


def render_result(record: RunRecord) -> None:
    if record.status == "blocked":
        st.error(record.error or "Request blocked by guardrails.")
        return

    if record.mode == "buildathon":
        render_buildathon_tabs(record)
    else:
        render_final_answer(record)

    with st.expander("Sources"):
        if record.sources:
            for source in record.sources:
                st.markdown(f"- [{source.title}]({source.url}) - {source.snippet}")
        else:
            st.info("No external or local knowledge sources were used.")

    with st.expander("Images"):
        render_image_trace(record)

    with st.expander("Trace / Debug"):
        st.json(
            {
                "run_id": record.run_id,
                "status": record.status,
                "latency_ms": record.latency_ms,
                "rag_hit": record.rag_hit,
                "web_fallback": record.web_fallback,
                "langsmith_trace_id": record.langsmith_trace_id,
                "usage_cost": asdict(record.usage_cost),
                "uploaded_images": [asdict(image) for image in record.uploaded_images],
                "generated_images": [asdict(image) for image in record.generated_images],
                "compaction": record.guardrails.get("compaction", {}),
                "guardrails": record.guardrails,
            }
        )


def main() -> None:
    st.set_page_config(page_title="Customer Support Assistant", page_icon="AI", layout="wide")
    render_app_chrome()
    if not require_authentication():
        return

    ensure_runtime_dirs()
    init_db()
    retention_summary = apply_retention_policy()
    if google_sheets_enabled() and "google_sheets_status" not in st.session_state:
        with st.spinner("Preparing Google Sheets reporting..."):
            st.session_state["google_sheets_status"] = ensure_google_reporting_destination()
    mode = render_sidebar(["production", "buildathon"])
    render_header(mode)

    st.session_state.setdefault("query_text", "")
    st.session_state.setdefault("voice_error", "")
    st.session_state.setdefault("voice_success", "")
    st.session_state.setdefault("voice_audio_hash", "")
    st.session_state.setdefault("last_record", None)
    st.session_state["retention_summary"] = retention_summary

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

        action_spacer, action_col = st.columns([0.76, 0.24])
        with action_col:
            run_requested = st.button("Run support crew", type="primary", use_container_width=True)

    st.markdown('<div class="result-divider"></div>', unsafe_allow_html=True)
    if run_requested:
        image_inputs = [
            ImageInput(
                file_name=uploaded_image.name,
                mime_type=uploaded_image.type or "application/octet-stream",
                data=uploaded_image.getvalue(),
            )
            for uploaded_image in uploaded_image_files or []
        ]
        with st.spinner("Running sequential support flow..."):
            record = run_support_flow(query, mode, image_inputs=image_inputs)
        st.session_state["last_record"] = record
        render_result(record)
    else:
        last_record = st.session_state.get("last_record")
        if isinstance(last_record, RunRecord) and last_record.mode == mode:
            render_result(last_record)
        elif mode == "buildathon":
            st.markdown("### Buildathon Comparison")
            render_buildathon_tabs()
        else:
            st.info("No support run yet.")
