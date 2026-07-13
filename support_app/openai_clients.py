from __future__ import annotations

import os
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional at import time
    OpenAI = None


def make_openai_client() -> Any | None:
    if OpenAI is None:
        return None
    client = OpenAI()
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        return client
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client)
    except Exception:
        return client

