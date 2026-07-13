from __future__ import annotations

import os
import re

from support_app.models import GuardrailResult, Source

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(the\s+)?(system|developer)\s+instructions",
    r"reveal\s+(your\s+)?(system|developer)\s+prompt",
    r"print\s+(your\s+)?(hidden\s+)?instructions",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+",
]

PII_PATTERNS = [
    (r"\b[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}\b", "[redacted-email]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[redacted-ssn]"),
    (r"\b(?:\d[ -]*?){13,19}\b", "[redacted-card]"),
    (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[redacted-ip]"),
    (r"(?<!\w)\+?\d[\d\-\s()]{8,}\d\b", "[redacted-phone]"),
]


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = re.sub(pattern, "[redacted-secret]", redacted)
    for pattern, replacement in PII_PATTERNS:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def count_pattern_matches(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text))


def pii_findings(text: str) -> dict[str, int]:
    labels = {
        "[redacted-email]": "email",
        "[redacted-phone]": "phone",
        "[redacted-ssn]": "ssn",
        "[redacted-card]": "payment_card",
        "[redacted-ip]": "ip_address",
    }
    findings: dict[str, int] = {}
    remaining = text
    for pattern, replacement in PII_PATTERNS:
        count = count_pattern_matches(remaining, pattern)
        if count:
            findings[labels.get(replacement, replacement)] = count
            remaining = re.sub(pattern, replacement, remaining)
    secret_count = sum(count_pattern_matches(remaining, pattern) for pattern in SECRET_PATTERNS)
    if secret_count:
        findings["secret"] = secret_count
    return findings


def redact_sources(sources: list[Source]) -> list[Source]:
    return [
        Source(
            title=redact_text(source.title),
            url=source.url,
            snippet=redact_text(source.snippet),
            rank=source.rank,
            source_type=source.source_type,
        )
        for source in sources
    ]


def validate_query(query: str) -> GuardrailResult:
    reasons: list[str] = []
    cleaned = query.strip()
    if not cleaned:
        reasons.append("Query is empty.")
    if len(cleaned) > int(os.getenv("MAX_QUERY_CHARS", "4000")):
        reasons.append("Query is too long.")
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            reasons.append("Query contains prompt-injection language.")
            break
    return GuardrailResult(
        passed=not reasons,
        reasons=reasons,
        redacted_text=redact_text(cleaned),
    )


def validate_answer(answer: str, needs_citation: bool, sources: list[Source]) -> GuardrailResult:
    reasons: list[str] = []
    if not answer.strip():
        reasons.append("Answer is empty.")
    if needs_citation and not sources:
        reasons.append("Answer requires at least one source citation.")
    return GuardrailResult(passed=not reasons, reasons=reasons, redacted_text=redact_text(answer))
