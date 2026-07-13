from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardrailResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    redacted_text: str = ""


@dataclass
class Source:
    title: str
    url: str
    snippet: str
    rank: int
    source_type: str


@dataclass
class KnowledgeChunk:
    path: str
    chunk_id: int
    text: str


@dataclass
class UsageCost:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    estimated_openai_cost_usd: float = 0.0
    estimated_embedding_cost_usd: float = 0.0
    serpapi_searches: int = 0
    estimated_serpapi_cost_usd: float = 0.0
    image_generation_count: int = 0
    estimated_image_cost_usd: float = 0.0


@dataclass
class ImageInput:
    file_name: str
    mime_type: str
    data: bytes


@dataclass
class ImageArtifact:
    file_name: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    storage_path: str
    source_type: str
    analysis: str = ""
    prompt: str = ""
    error: str | None = None


@dataclass
class VoiceTranscript:
    text: str = ""
    error: str | None = None


@dataclass
class CrewSupportResult:
    direct_answer: str
    web_answer: str
    final_answer: str
    usage_cost: UsageCost
    usage_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunRecord:
    run_id: str
    created_at: str
    query_hash: str
    redacted_query: str
    mode: str
    model: str
    direct_answer: str
    web_answer: str
    final_answer: str
    sources: list[Source]
    guardrails: dict[str, Any]
    usage_cost: UsageCost
    latency_ms: int
    rag_hit: bool
    web_fallback: bool
    langsmith_trace_id: str | None
    status: str
    error: str | None = None
    uploaded_images: list[ImageArtifact] = field(default_factory=list)
    generated_images: list[ImageArtifact] = field(default_factory=list)
