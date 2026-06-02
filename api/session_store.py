"""In-memory session memory for multi-turn AgenticBI analysis.

This is intentionally lightweight for course demo purposes. It keeps recent
turns in process memory and exposes compact history_context to the coordinator.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4


MAX_TURNS_PER_SESSION = 8
_SESSIONS: dict[str, list[dict[str, Any]]] = {}


def create_session_id() -> str:
    return uuid4().hex


def ensure_session(session_id: str | None = None) -> str:
    sid = session_id or create_session_id()
    _SESSIONS.setdefault(sid, [])
    return sid


def _compact_text(value: str, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _extract_entities(result: dict[str, Any]) -> dict[str, Any]:
    rows = result.get("rows") or []
    seller_ids = []
    states = []
    categories = []
    def collect_from_obj(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("seller_id") and obj["seller_id"] not in seller_ids:
                seller_ids.append(obj["seller_id"])
            if obj.get("customer_state") and obj["customer_state"] not in states:
                states.append(obj["customer_state"])
            if obj.get("seller_state") and obj["seller_state"] not in states:
                states.append(obj["seller_state"])
            category = obj.get("product_category_english") or obj.get("product_category_name_english")
            if category and category not in categories:
                categories.append(category)
            for value in obj.values():
                collect_from_obj(value)
        elif isinstance(obj, list):
            for item in obj:
                collect_from_obj(item)
        elif isinstance(obj, str) and ("seller_id" in obj or "customer_state" in obj):
            try:
                collect_from_obj(json.loads(obj))
            except json.JSONDecodeError:
                return

    for row in rows[:20]:
        if isinstance(row, dict):
            collect_from_obj(row)

    return {
        "view_name": (result.get("data_analysis") or {}).get("view_name"),
        "seller_ids": seller_ids[:10],
        "states": states[:10],
        "categories": categories[:10],
    }


def load_history_context(session_id: str, limit: int = 4) -> list[dict[str, str]]:
    turns = _SESSIONS.get(session_id, [])[-limit:]
    context: list[dict[str, str]] = []
    for turn in turns:
        entities = turn.get("entities") or {}
        entity_text = ""
        if entities:
            entity_text = f"\n关联实体：{entities}"
        context.append({
            "role": "user",
            "content": _compact_text(turn.get("question", "")),
        })
        context.append({
            "role": "assistant",
            "content": _compact_text(
                f"摘要：{turn.get('summary', '')}\nSQL：{turn.get('sql', '')}{entity_text}",
                limit=900,
            ),
        })
    return context


def save_turn(session_id: str, question: str, result: dict[str, Any]) -> None:
    sid = ensure_session(session_id)
    turns = _SESSIONS[sid]
    turns.append({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "summary": result.get("summary", ""),
        "sql": result.get("sql", ""),
        "final_answer": result.get("final_answer", ""),
        "analysis_type": (result.get("coordinator_plan") or {}).get("analysis_type", ""),
        "intent": (result.get("coordinator_plan") or {}).get("intent", ""),
        "entities": _extract_entities(result),
    })
    if len(turns) > MAX_TURNS_PER_SESSION:
        del turns[:-MAX_TURNS_PER_SESSION]


def get_session_snapshot(session_id: str) -> dict[str, Any]:
    sid = ensure_session(session_id)
    return {
        "session_id": sid,
        "turn_count": len(_SESSIONS.get(sid, [])),
        "turns": _SESSIONS.get(sid, []),
    }
