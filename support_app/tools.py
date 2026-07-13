from __future__ import annotations

from typing import Any

from crewai.tools import tool

from support_app.google_sheets import google_sheets_status_summary
from support_app.rag import retrieve_hybrid_rag, retrieve_local_knowledge
from support_app.search import search_web


def make_rag_retrieval_tool(prefetched_context: str, prefetched_sources: str) -> Any:
    @tool("rag_retrieval", max_usage_count=1)
    def rag_retrieval(query: str) -> str:
        """Retrieve trusted local support knowledge using hybrid RAG before answering."""
        if prefetched_context:
            return (
                f"Trusted local context:\n{prefetched_context}\n\n"
                f"Sources:\n{prefetched_sources or 'No local sources.'}"
            )

        context, sources, rag_hit, _cost = retrieve_hybrid_rag(query)
        if not rag_hit:
            context, sources, rag_hit = retrieve_local_knowledge(query)
        if not rag_hit:
            return "No trusted local RAG context was found."
        source_text = "\n".join(f"- {source.title}: {source.url}" for source in sources)
        return f"Trusted local context:\n{context}\n\nSources:\n{source_text}"

    return rag_retrieval


def make_serpapi_search_tool(prefetched_results: str) -> Any:
    @tool("serpapi_search", max_usage_count=1)
    def serpapi_search(query: str) -> str:
        """Search Google through SerpAPI when web verification is required."""
        if prefetched_results:
            return prefetched_results
        sources = search_web(query)
        if not sources:
            return "No SerpAPI results were available."
        return "\n".join(
            (
                f"{source.rank}. {source.title}\n"
                f"URL: {source.url}\n"
                f"Snippet: {source.snippet}"
            )
            for source in sources
        )

    return serpapi_search


def make_image_analysis_tool(prefetched_analysis: str) -> Any:
    @tool("image_analysis", max_usage_count=1)
    def image_analysis(_query: str = "") -> str:
        """Read sanitized analysis for images attached by the user."""
        return prefetched_analysis or "No image analysis was available."

    return image_analysis


def make_google_sheets_reporting_tool(prefetched_status: str) -> Any:
    @tool("google_sheets_reporting_status", max_usage_count=1)
    def google_sheets_reporting_status(_query: str = "") -> str:
        """Read Google Sheets reporting status without writing logs or exposing secrets."""
        return prefetched_status or google_sheets_status_summary()

    return google_sheets_reporting_status
