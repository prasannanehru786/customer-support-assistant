from __future__ import annotations

from backend.support_app.costs import aggregate_costs
from backend.support_app.guardrails import redact_text, validate_query
from backend.support_app.models import UsageCost
from backend.support_app.rag import chunk_text
from frontend.app import main


if __name__ == "__main__":
    main()
