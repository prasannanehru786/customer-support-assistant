from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from support_app.config import DEFAULT_MODEL, get_serpapi_key
from support_app.compaction import compact_agent_context, compaction_metrics_asdict
from support_app.costs import aggregate_costs, estimate_cost
from support_app.crewai_flow import run_crewai_support_crew
import os

from support_app.guardrails import pii_findings, redact_sources, redact_text, validate_answer, validate_query
from support_app.google_sheets import append_run_to_google_sheet
from support_app.image_service import (
    analyze_uploaded_images,
    generate_image_output,
    image_feature_enabled,
    wants_image_output,
    save_uploaded_images,
)
from support_app.models import ImageInput, RunRecord, Source, UsageCost
from support_app.observability import trace_with_langsmith
from support_app.rag import retrieve_hybrid_rag, retrieve_local_knowledge
from support_app.search import search_web
from support_app.storage import save_run, save_transcripts
from support_app.utils import sha256_text


def run_support_flow(query: str, mode: str, image_inputs: list[ImageInput] | None = None) -> RunRecord:
    start = time.perf_counter()
    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    uploaded_images = save_uploaded_images(image_inputs or [], run_id)
    image_output_requested = wants_image_output(query)
    input_guardrail = validate_query(query)
    pii_redaction_enabled = os.getenv("ENABLE_PII_REDACTION_FOR_LLM", "true").lower() == "true"
    safe_query = input_guardrail.redacted_text if pii_redaction_enabled else query.strip()
    guardrails: dict[str, object] = {
        "input": asdict(input_guardrail),
        "privacy": {
            "pii_redaction_for_llm": pii_redaction_enabled,
            "pii_findings": pii_findings(query),
            "query_redacted_before_llm": safe_query != query.strip(),
        },
        "images": {
            "enabled": image_feature_enabled(),
            "uploaded_count": len(uploaded_images),
            "accepted_count": len([image for image in uploaded_images if not image.error]),
            "rejected_count": len([image for image in uploaded_images if image.error]),
            "output_requested": image_output_requested,
        },
    }
    if not input_guardrail.passed:
        record = RunRecord(
            run_id=run_id,
            created_at=created_at,
            query_hash=sha256_text(query),
            redacted_query=input_guardrail.redacted_text,
            mode=mode,
            model=DEFAULT_MODEL,
            direct_answer="",
            web_answer="",
            final_answer="",
            sources=[],
            guardrails=guardrails,
            usage_cost=UsageCost(),
            latency_ms=int((time.perf_counter() - start) * 1000),
            rag_hit=False,
            web_fallback=False,
            langsmith_trace_id=None,
            status="blocked",
            error="; ".join(input_guardrail.reasons),
            uploaded_images=uploaded_images,
        )
        record.guardrails["google_sheets"] = append_run_to_google_sheet(record)
        save_run(record)
        return record

    image_context, image_analysis_cost = analyze_uploaded_images(uploaded_images)
    guardrails["images"]["analysis_available"] = any(image.analysis for image in uploaded_images)

    rag_context, local_sources, rag_hit, rag_cost = retrieve_hybrid_rag(safe_query)
    rag_mode = "hybrid_qdrant_bm25"
    if not rag_hit:
        rag_context, local_sources, rag_hit = retrieve_local_knowledge(safe_query)
        rag_mode = "keyword_file_fallback" if rag_hit else "none"

    rag_context = redact_text(rag_context)
    local_sources = redact_sources(local_sources)
    guardrails["rag"] = {"mode": rag_mode, "source_count": len(local_sources)}

    web_sources: list[Source] = []
    web_error: str | None = None
    web_fallback = mode == "buildathon" or not rag_hit
    serpapi_searches = 0
    if web_fallback:
        serpapi_searches = 1 if get_serpapi_key() else 0
        try:
            web_sources = search_web(safe_query)
            web_sources = redact_sources(web_sources)
        except Exception as exc:
            web_error = f"Web search failed: {exc}"

    compaction_result = compact_agent_context(rag_context, local_sources, web_sources)
    rag_context = compaction_result.rag_context
    local_sources = compaction_result.local_sources
    web_sources = compaction_result.web_sources
    guardrails["compaction"] = compaction_metrics_asdict(compaction_result)

    crew_error: str | None = None
    try:
        crew_result = run_crewai_support_crew(
            query=safe_query,
            rag_context=rag_context,
            local_sources=local_sources,
            web_sources=web_sources,
            image_context=image_context,
            web_error=web_error,
            mode=mode,
            web_fallback=web_fallback,
            serpapi_searches=serpapi_searches,
        )
        direct_answer = crew_result.direct_answer
        web_answer = crew_result.web_answer
        final_answer = crew_result.final_answer
        crew_cost = crew_result.usage_cost
        crew_usage_metrics = crew_result.usage_metrics
    except Exception as exc:
        crew_error = f"CrewAI execution failed: {exc}"
        direct_answer = ""
        web_answer = web_error or ""
        final_answer = crew_error
        crew_cost = estimate_cost(0, 0, serpapi_searches)
        crew_usage_metrics = {}

    guardrails["crewai"] = {
        "framework": "crewai",
        "process": "sequential",
        "error": crew_error,
        "usage_metrics": crew_usage_metrics,
    }

    generated_images: list = []
    image_output_cost = UsageCost()
    if crew_error is None:
        generated_images, image_output_cost = generate_image_output(
            query=safe_query,
            final_answer=final_answer,
            image_context=image_context,
            run_id=run_id,
        )
    guardrails["images"]["generated_count"] = len(
        [image for image in generated_images if image.storage_path and not image.error]
    )
    guardrails["images"]["generation_errors"] = [
        image.error for image in generated_images if image.error
    ]

    direct_guardrail = validate_answer(direct_answer, needs_citation=False, sources=local_sources)
    guardrails["direct_answer"] = asdict(direct_guardrail)

    all_sources = local_sources + web_sources
    web_guardrail = validate_answer(web_answer, needs_citation=bool(web_sources), sources=web_sources)
    guardrails["web_answer"] = asdict(web_guardrail)

    final_guardrail = validate_answer(final_answer, needs_citation=bool(all_sources), sources=all_sources)
    guardrails["final_answer"] = asdict(final_guardrail)

    usage_cost = aggregate_costs(rag_cost, crew_cost, image_analysis_cost, image_output_cost)

    langsmith_trace_id = trace_with_langsmith(
        "support_flow",
        {
            "query_hash": sha256_text(query),
            "mode": mode,
            "rag_hit": rag_hit,
            "rag_mode": rag_mode,
            "uploaded_image_count": len(uploaded_images),
            "image_output_requested": image_output_requested,
        },
        {
            "run_id": run_id,
            "status": "ok",
            "web_fallback": web_fallback,
            "crewai_usage_metrics": crew_usage_metrics,
            "compaction": guardrails["compaction"],
            "images": guardrails["images"],
            "estimated_cost": usage_cost.estimated_openai_cost_usd
            + usage_cost.estimated_serpapi_cost_usd
            + usage_cost.estimated_image_cost_usd,
        },
    )

    status = "ok" if final_guardrail.passed and crew_error is None else "needs_review"
    record = RunRecord(
        run_id=run_id,
        created_at=created_at,
        query_hash=sha256_text(query),
        redacted_query=input_guardrail.redacted_text,
        mode=mode,
        model=DEFAULT_MODEL,
        direct_answer=redact_text(direct_answer),
        web_answer=redact_text(web_answer),
        final_answer=redact_text(final_answer),
        sources=all_sources,
        guardrails=guardrails,
        usage_cost=usage_cost,
        latency_ms=int((time.perf_counter() - start) * 1000),
        rag_hit=rag_hit,
        web_fallback=web_fallback,
        langsmith_trace_id=langsmith_trace_id,
        status=status,
        error=None if status == "ok" else crew_error or "; ".join(final_guardrail.reasons),
        uploaded_images=uploaded_images,
        generated_images=generated_images,
    )
    record.guardrails["google_sheets"] = append_run_to_google_sheet(record)
    save_run(record)
    save_transcripts(record)
    return record
