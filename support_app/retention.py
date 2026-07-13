from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from support_app.config import (
    ANSWERS_FILE,
    AUDIO_DIR,
    CREWAI_STORAGE_DIR,
    IMAGE_OUTPUT_DIR,
    IMAGE_UPLOAD_DIR,
    JSONL_LOG_PATH,
    LOG_DIR,
    SQLITE_PATH,
    TRANSCRIPT_DIR,
    ensure_runtime_dirs,
)


def retention_days(env_name: str, default: int) -> int:
    try:
        return int(os.getenv(env_name, str(default)))
    except ValueError:
        return default


def cutoff_datetime(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max(days, 0))


def cutoff_timestamp(days: int) -> float:
    return time.time() - (max(days, 0) * 24 * 60 * 60)


def iter_files(paths: Iterable[Path], suffixes: tuple[str, ...] | None = None) -> Iterable[Path]:
    for root in paths:
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = [path for path in root.rglob("*") if path.is_file()]
        for path in candidates:
            if path.name == ".gitkeep":
                continue
            if suffixes and path.suffix not in suffixes:
                continue
            yield path


def delete_old_files(paths: Iterable[Path], days: int, suffixes: tuple[str, ...] | None = None) -> int:
    deleted = 0
    cutoff = cutoff_timestamp(days)
    for path in iter_files(paths, suffixes=suffixes):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        except OSError:
            continue
    return deleted


def prune_sqlite(days: int) -> int:
    if not SQLITE_PATH.exists():
        return 0
    cutoff = cutoff_datetime(days).isoformat()
    try:
        with sqlite3.connect(SQLITE_PATH) as conn:
            cursor = conn.execute("DELETE FROM support_runs WHERE created_at < ?", (cutoff,))
            return int(cursor.rowcount or 0)
    except sqlite3.Error:
        return 0


def parse_created_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def prune_jsonl(days: int) -> int:
    if not JSONL_LOG_PATH.exists():
        return 0
    cutoff = cutoff_datetime(days)
    kept_lines: list[str] = []
    deleted = 0
    try:
        lines = JSONL_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue
        created_at = parse_created_at(payload.get("created_at"))
        if created_at is not None and created_at < cutoff:
            deleted += 1
            continue
        kept_lines.append(line)
    try:
        JSONL_LOG_PATH.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
    except OSError:
        return 0
    return deleted


def apply_retention_policy() -> dict[str, int | bool]:
    ensure_runtime_dirs()
    if os.getenv("ENABLE_RETENTION_POLICY", "true").lower() != "true":
        return {"enabled": False}

    run_days = retention_days("RUN_RETENTION_DAYS", 30)
    log_days = retention_days("LOG_RETENTION_DAYS", 30)
    transcript_days = retention_days("TRANSCRIPT_RETENTION_DAYS", 30)
    audio_days = retention_days("AUDIO_RETENTION_DAYS", 7)
    image_upload_days = retention_days("IMAGE_UPLOAD_RETENTION_DAYS", 7)
    image_output_days = retention_days("IMAGE_OUTPUT_RETENTION_DAYS", 14)
    memory_days = retention_days("CREWAI_MEMORY_RETENTION_DAYS", 30)

    sqlite_rows_deleted = prune_sqlite(run_days)
    jsonl_lines_deleted = prune_jsonl(log_days)
    transcript_files_deleted = delete_old_files([TRANSCRIPT_DIR], transcript_days, suffixes=(".txt",))
    audio_files_deleted = delete_old_files([AUDIO_DIR], audio_days, suffixes=(".wav", ".mp3", ".aiff", ".m4a"))
    image_upload_files_deleted = delete_old_files(
        [IMAGE_UPLOAD_DIR],
        image_upload_days,
        suffixes=(".png", ".jpg", ".jpeg", ".webp"),
    )
    image_output_files_deleted = delete_old_files([IMAGE_OUTPUT_DIR], image_output_days, suffixes=(".png",))
    crewai_files_deleted = delete_old_files([CREWAI_STORAGE_DIR], memory_days)

    answers_deleted = 0
    try:
        should_delete_answers = ANSWERS_FILE.exists() and ANSWERS_FILE.stat().st_mtime < cutoff_timestamp(transcript_days)
    except OSError:
        should_delete_answers = False
    if should_delete_answers:
        try:
            ANSWERS_FILE.unlink()
            answers_deleted = 1
        except OSError:
            answers_deleted = 0

    stale_log_files_deleted = delete_old_files([LOG_DIR], log_days, suffixes=(".log",))

    return {
        "enabled": True,
        "run_retention_days": run_days,
        "log_retention_days": log_days,
        "transcript_retention_days": transcript_days,
        "audio_retention_days": audio_days,
        "image_upload_retention_days": image_upload_days,
        "image_output_retention_days": image_output_days,
        "crewai_memory_retention_days": memory_days,
        "sqlite_rows_deleted": sqlite_rows_deleted,
        "jsonl_lines_deleted": jsonl_lines_deleted,
        "transcript_files_deleted": transcript_files_deleted,
        "audio_files_deleted": audio_files_deleted,
        "image_upload_files_deleted": image_upload_files_deleted,
        "image_output_files_deleted": image_output_files_deleted,
        "crewai_memory_files_deleted": crewai_files_deleted,
        "answers_file_deleted": answers_deleted,
        "stale_log_files_deleted": stale_log_files_deleted,
    }
