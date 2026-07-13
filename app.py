from __future__ import annotations

from support_app.costs import aggregate_costs
from support_app.guardrails import redact_text, validate_query
from support_app.models import UsageCost
from support_app.rag import chunk_text
from support_app.ui import main


if __name__ == "__main__":
    main()
