from __future__ import annotations

import streamlit as st

from backend.support_app.config import ensure_runtime_dirs
from backend.support_app.google_sheets import ensure_google_reporting_destination, google_sheets_enabled
from backend.support_app.models import RunRecord
from backend.support_app.retention import apply_retention_policy
from backend.support_app.storage import init_db
from backend.support_app.workflow import run_support_flow
from frontend.components.auth import require_authentication
from frontend.components.chrome import render_app_chrome, render_header, render_sidebar
from frontend.components.composer import render_support_request_form
from frontend.components.results import render_buildathon_tabs, render_result


def init_session_state() -> None:
    st.session_state.setdefault("query_text", "")
    st.session_state.setdefault("voice_error", "")
    st.session_state.setdefault("voice_success", "")
    st.session_state.setdefault("voice_audio_hash", "")
    st.session_state.setdefault("last_record", None)


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
    init_session_state()
    st.session_state["retention_summary"] = retention_summary

    run_requested, query, image_inputs = render_support_request_form(mode)

    st.markdown('<div class="result-divider"></div>', unsafe_allow_html=True)
    if run_requested:
        with st.spinner("Running sequential support flow..."):
            record = run_support_flow(query, mode, image_inputs=image_inputs)
        st.session_state["last_record"] = record
        render_result(record)
        return

    last_record = st.session_state.get("last_record")
    if isinstance(last_record, RunRecord) and last_record.mode == mode:
        render_result(last_record)
    elif mode == "buildathon":
        st.markdown("### Buildathon Comparison")
        render_buildathon_tabs()
    else:
        st.info("No support run yet.")
