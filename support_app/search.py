from __future__ import annotations

import os

import requests

from support_app.config import SERPAPI_ENDPOINT, get_serpapi_key
from support_app.models import Source


def search_web(query: str) -> list[Source]:
    key = get_serpapi_key()
    if not key:
        return []
    timeout_seconds = float(os.getenv("SERPAPI_TIMEOUT_SECONDS", "12"))
    params = {
        "engine": "google",
        "q": query,
        "api_key": key,
        "num": int(os.getenv("SERPAPI_RESULTS", "5")),
    }
    response = requests.get(SERPAPI_ENDPOINT, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    results = payload.get("organic_results", []) or []
    sources: list[Source] = []
    for idx, item in enumerate(results[: int(os.getenv("SERPAPI_RESULTS", "5"))], start=1):
        link = item.get("link") or item.get("redirect_link") or ""
        if not link:
            continue
        sources.append(
            Source(
                title=str(item.get("title") or "Search result"),
                url=link,
                snippet=str(item.get("snippet") or ""),
                rank=idx,
                source_type="web",
            )
        )
    return sources

