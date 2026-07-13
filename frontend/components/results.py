from __future__ import annotations

import os
from dataclasses import asdict

import streamlit as st

from backend.support_app.config import APP_ROOT
from backend.support_app.models import ImageArtifact, RunRecord
from backend.support_app.voice import synthesize_speech


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
