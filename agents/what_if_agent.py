"""What-if Analysis Agent for extra credit."""

from __future__ import annotations

import re
from typing import Any

from models.what_if_model import simulate_top_negative_seller_intervention


def _extract_top_n(question: str, default: int = 20) -> int:
    match = re.search(r"(?:top|Top|TOP)\s*(\d+)|前\s*(\d+)", question)
    if not match:
        return default
    value = match.group(1) or match.group(2)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 100))


def run_what_if_agent(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question") or "")
    top_n = _extract_top_n(question)
    result = simulate_top_negative_seller_intervention(top_n=top_n)
    return {
        "agent": "what_if_agent",
        "question": question,
        **result,
    }

