from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass

from backend.support_app.models import Source


@dataclass
class CompactionResult:
    rag_context: str
    local_sources: list[Source]
    web_sources: list[Source]
    metrics: dict[str, object]


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Cheap deterministic estimate: close enough for trend/cost-reduction logging.
    return max(1, len(text) // 4)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def compact_text(text: str, max_chars: int) -> str:
    cleaned = normalize_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    truncated = cleaned[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{truncated} ..."


def compact_sources(sources: list[Source], max_snippet_chars: int) -> list[Source]:
    return [
        Source(
            title=source.title,
            url=source.url,
            snippet=compact_text(source.snippet, max_snippet_chars),
            rank=source.rank,
            source_type=source.source_type,
        )
        for source in sources
    ]


def compact_agent_context(
    rag_context: str,
    local_sources: list[Source],
    web_sources: list[Source],
) -> CompactionResult:
    start = time.perf_counter()
    if os.getenv("ENABLE_CONTEXT_COMPACTION", "true").lower() != "true":
        return CompactionResult(
            rag_context=rag_context,
            local_sources=local_sources,
            web_sources=web_sources,
            metrics={
                "enabled": False,
                "happened": False,
                "duration_ms": 0,
                "estimated_tokens_before": estimate_tokens(
                    rag_context + " ".join(source.snippet for source in local_sources + web_sources)
                ),
                "estimated_tokens_after": estimate_tokens(
                    rag_context + " ".join(source.snippet for source in local_sources + web_sources)
                ),
                "estimated_tokens_reduced": 0,
                "reduction_pct": 0.0,
            },
        )

    max_rag_chars = int(os.getenv("COMPACT_RAG_CONTEXT_CHARS", "2800"))
    max_source_chars = int(os.getenv("COMPACT_SOURCE_SNIPPET_CHARS", "360"))
    before_text = rag_context + " ".join(source.snippet for source in local_sources + web_sources)

    compacted_rag_context = compact_text(rag_context, max_rag_chars)
    compacted_local_sources = compact_sources(local_sources, max_source_chars)
    compacted_web_sources = compact_sources(web_sources, max_source_chars)
    after_text = compacted_rag_context + " ".join(
        source.snippet for source in compacted_local_sources + compacted_web_sources
    )

    before_tokens = estimate_tokens(before_text)
    after_tokens = estimate_tokens(after_text)
    reduced_tokens = max(before_tokens - after_tokens, 0)
    duration_ms = int((time.perf_counter() - start) * 1000)
    metrics = {
        "enabled": True,
        "happened": reduced_tokens > 0,
        "duration_ms": duration_ms,
        "estimated_tokens_before": before_tokens,
        "estimated_tokens_after": after_tokens,
        "estimated_tokens_reduced": reduced_tokens,
        "reduction_pct": round((reduced_tokens / before_tokens * 100), 2) if before_tokens else 0.0,
        "max_rag_context_chars": max_rag_chars,
        "max_source_snippet_chars": max_source_chars,
    }
    return CompactionResult(
        rag_context=compacted_rag_context,
        local_sources=compacted_local_sources,
        web_sources=compacted_web_sources,
        metrics=metrics,
    )


def compaction_metrics_asdict(result: CompactionResult) -> dict[str, object]:
    return dict(asdict(result)["metrics"])

