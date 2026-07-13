from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from backend.support_app.config import ANSWERS_FILE, JSONL_LOG_PATH, SQLITE_PATH, TRANSCRIPT_DIR, ensure_runtime_dirs
from backend.support_app.models import RunRecord


def support_run_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(support_runs)")}


def init_db() -> None:
    ensure_runtime_dirs()
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS support_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                query_hash TEXT NOT NULL,
                redacted_query TEXT NOT NULL,
                mode TEXT NOT NULL,
                model TEXT NOT NULL,
                final_answer TEXT NOT NULL,
                direct_answer TEXT NOT NULL,
                web_answer TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                guardrails_json TEXT NOT NULL,
                usage_cost_json TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                rag_hit INTEGER NOT NULL,
                web_fallback INTEGER NOT NULL,
                langsmith_trace_id TEXT,
                status TEXT NOT NULL,
                error TEXT,
                uploaded_images_json TEXT NOT NULL DEFAULT '[]',
                generated_images_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        existing_columns = support_run_columns(conn)
        if "uploaded_images_json" not in existing_columns:
            try:
                conn.execute("ALTER TABLE support_runs ADD COLUMN uploaded_images_json TEXT NOT NULL DEFAULT '[]'")
            except sqlite3.OperationalError:
                pass
        if "generated_images_json" not in existing_columns:
            try:
                conn.execute("ALTER TABLE support_runs ADD COLUMN generated_images_json TEXT NOT NULL DEFAULT '[]'")
            except sqlite3.OperationalError:
                pass


def append_jsonl(record: RunRecord) -> None:
    ensure_runtime_dirs()
    payload = asdict(record)
    payload["sources"] = [asdict(source) for source in record.sources]
    payload["usage_cost"] = asdict(record.usage_cost)
    payload["compaction"] = record.guardrails.get("compaction", {})
    with JSONL_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=True) + "\n")


def save_run(record: RunRecord) -> None:
    init_db()
    append_jsonl(record)
    with sqlite3.connect(SQLITE_PATH) as conn:
        columns = support_run_columns(conn)
        base_values = (
            record.run_id,
            record.created_at,
            record.query_hash,
            record.redacted_query,
            record.mode,
            record.model,
            record.final_answer,
            record.direct_answer,
            record.web_answer,
            json.dumps([asdict(source) for source in record.sources]),
            json.dumps(record.guardrails),
            json.dumps(asdict(record.usage_cost)),
            record.latency_ms,
            int(record.rag_hit),
            int(record.web_fallback),
            record.langsmith_trace_id,
            record.status,
            record.error,
        )
        if {"uploaded_images_json", "generated_images_json"}.issubset(columns):
            conn.execute(
                """
                INSERT OR REPLACE INTO support_runs (
                    run_id, created_at, query_hash, redacted_query, mode, model,
                    final_answer, direct_answer, web_answer, sources_json,
                    guardrails_json, usage_cost_json, latency_ms, rag_hit,
                    web_fallback, langsmith_trace_id, status, error,
                    uploaded_images_json, generated_images_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                base_values
                + (
                    json.dumps([asdict(image) for image in record.uploaded_images]),
                    json.dumps([asdict(image) for image in record.generated_images]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT OR REPLACE INTO support_runs (
                    run_id, created_at, query_hash, redacted_query, mode, model,
                    final_answer, direct_answer, web_answer, sources_json,
                    guardrails_json, usage_cost_json, latency_ms, rag_hit,
                    web_fallback, langsmith_trace_id, status, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                base_values,
            )


def save_transcripts(record: RunRecord) -> Path:
    ensure_runtime_dirs()
    transcript = (
        f"Run ID: {record.run_id}\n"
        f"Created At: {record.created_at}\n"
        f"Mode: {record.mode}\n"
        f"Model: {record.model}\n\n"
        f"Query:\n{record.redacted_query}\n\n"
        f"Direct Assistant Answer:\n{record.direct_answer}\n\n"
        f"Web Search Answer:\n{record.web_answer}\n\n"
        f"Final Answer:\n{record.final_answer}\n\n"
        f"Sources:\n"
        + "\n".join(f"- {source.title}: {source.url}" for source in record.sources)
        + "\n\n"
        + "Uploaded Images:\n"
        + "\n".join(
            f"- {image.file_name} ({image.width}x{image.height}): {image.analysis or image.error or 'No analysis'}"
            for image in record.uploaded_images
        )
        + "\n\n"
        + "Generated Images:\n"
        + "\n".join(
            f"- {image.file_name}: {image.storage_path or image.error or 'No image generated'}"
            for image in record.generated_images
        )
        + "\n"
    )
    transcript_path = TRANSCRIPT_DIR / f"{record.run_id}.txt"
    transcript_path.write_text(transcript, encoding="utf-8")
    with ANSWERS_FILE.open("a", encoding="utf-8") as file:
        file.write("\n" + "=" * 80 + "\n" + transcript)
    return transcript_path
