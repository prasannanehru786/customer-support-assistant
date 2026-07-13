from __future__ import annotations

import os
from typing import Any

try:
    import langsmith as ls
except ImportError:  # pragma: no cover - optional observability
    ls = None


def trace_with_langsmith(name: str, inputs: dict[str, Any], outputs: dict[str, Any]) -> str | None:
    if ls is None or os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        return None
    try:
        client = ls.Client()
        run = client.create_run(
            name=name,
            run_type="chain",
            inputs=inputs,
            outputs=outputs,
            project_name=os.getenv("LANGSMITH_PROJECT", "crewai-support-mvp"),
        )
        return str(getattr(run, "id", "")) or None
    except Exception:
        return None

