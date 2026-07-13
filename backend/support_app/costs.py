from __future__ import annotations

import os

from backend.support_app.models import UsageCost


def estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    serpapi_searches: int,
    embedding_tokens: int = 0,
    image_generation_count: int = 0,
) -> UsageCost:
    input_cost_per_1m = float(os.getenv("OPENAI_INPUT_COST_PER_1M", "0"))
    output_cost_per_1m = float(os.getenv("OPENAI_OUTPUT_COST_PER_1M", "0"))
    embedding_cost_per_1m = float(os.getenv("OPENAI_EMBEDDING_COST_PER_1M", "0"))
    serpapi_cost_per_search = float(os.getenv("SERPAPI_COST_PER_SEARCH", "0"))
    image_cost_per_generation = float(os.getenv("OPENAI_IMAGE_COST_PER_IMAGE", "0"))
    chat_cost = (prompt_tokens / 1_000_000 * input_cost_per_1m) + (
        completion_tokens / 1_000_000 * output_cost_per_1m
    )
    embedding_cost = embedding_tokens / 1_000_000 * embedding_cost_per_1m
    return UsageCost(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        embedding_tokens=embedding_tokens,
        estimated_openai_cost_usd=round(chat_cost + embedding_cost, 8),
        estimated_embedding_cost_usd=round(embedding_cost, 8),
        serpapi_searches=serpapi_searches,
        estimated_serpapi_cost_usd=round(serpapi_searches * serpapi_cost_per_search, 8),
        image_generation_count=image_generation_count,
        estimated_image_cost_usd=round(image_generation_count * image_cost_per_generation, 8),
    )


def aggregate_costs(*costs: UsageCost) -> UsageCost:
    return estimate_cost(
        prompt_tokens=sum(cost.prompt_tokens for cost in costs),
        completion_tokens=sum(cost.completion_tokens for cost in costs),
        serpapi_searches=sum(cost.serpapi_searches for cost in costs),
        embedding_tokens=sum(cost.embedding_tokens for cost in costs),
        image_generation_count=sum(cost.image_generation_count for cost in costs),
    )
