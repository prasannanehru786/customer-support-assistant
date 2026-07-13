from __future__ import annotations

import html
import os

import streamlit as st

from backend.support_app.config import DEFAULT_MODEL, get_serpapi_key
from backend.support_app.crewai_flow import crewai_dependency_status
from backend.support_app.image_service import image_feature_enabled
from frontend.components.auth import render_auth_sidebar


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
