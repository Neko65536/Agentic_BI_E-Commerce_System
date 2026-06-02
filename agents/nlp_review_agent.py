"""NLP/ReviewInsightAgent for member C."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.sentiment_model import analyze_review_sentiment


def run_nlp_review_agent(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    question = str(payload.get("question") or "")
    result = analyze_review_sentiment(question=question)
    return {
        "agent": "nlp_review_agent",
        "question": question,
        **result,
    }

