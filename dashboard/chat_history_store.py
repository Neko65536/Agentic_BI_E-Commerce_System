"""Persist chat sessions to local JSON files for Streamlit UI history."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CHAT_HISTORY_DIR = ROOT / "outputs" / "chat_sessions"
MAX_STORED_CHATS = 50


def ensure_chat_history_dir() -> Path:
    CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_HISTORY_DIR


def new_chat_id() -> str:
    return uuid4().hex


def _chat_path(chat_id: str) -> Path:
    safe_id = "".join(ch for ch in chat_id if ch.isalnum())
    return ensure_chat_history_dir() / f"{safe_id}.json"


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def list_chats(limit: int = MAX_STORED_CHATS) -> list[dict[str, Any]]:
    ensure_chat_history_dir()
    chats: list[dict[str, Any]] = []
    for path in CHAT_HISTORY_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or not data.get("id"):
            continue
        chats.append(data)
    chats.sort(key=lambda item: _parse_time(item.get("updated_at")), reverse=True)
    return chats[:limit]


def load_chat(chat_id: str) -> dict[str, Any] | None:
    path = _chat_path(chat_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_chat(record: dict[str, Any]) -> str:
    chat_id = str(record.get("id") or new_chat_id())
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        "id": chat_id,
        "title": str(record.get("title") or "未命名对话"),
        "created_at": record.get("created_at") or now,
        "updated_at": now,
        "session_id": record.get("session_id"),
        "messages": record.get("messages") or [],
        "history_context": record.get("history_context") or [],
        "last_result": record.get("last_result"),
    }
    _chat_path(chat_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _trim_old_chats()
    return chat_id


def delete_chat(chat_id: str) -> bool:
    path = _chat_path(chat_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def _trim_old_chats() -> None:
    chats = list_chats(limit=MAX_STORED_CHATS + 20)
    for extra in chats[MAX_STORED_CHATS:]:
        delete_chat(str(extra.get("id", "")))


def title_from_messages(messages: list[dict[str, Any]], max_len: int = 28) -> str:
    for msg in messages:
        if msg.get("is_user") and msg.get("content"):
            text = " ".join(str(msg["content"]).split())
            if len(text) <= max_len:
                return text
            return text[: max_len - 1] + "…"
    return "未命名对话"
