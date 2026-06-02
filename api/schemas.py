"""
API 请求/响应 Pydantic 模型。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    session_id: str | None = None
    history_context: list[dict[str, str]] | None = None


class AskResponseData(BaseModel):
    session_id: str
    question: str
    analysis_type: str
    intent: str
    sql: str
    row_count: int
    summary: str
    final_answer: str
    downstream_payload: dict[str, Any] | None = None
    visualization_result: dict[str, Any] | None = None
    forecast_result: dict[str, Any] | None = None
    nlp_result: dict[str, Any] | None = None
    what_if_result: dict[str, Any] | None = None
    decision_result: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] | None = None
    errors: list[str]


class AskResponse(BaseModel):
    success: bool
    data: AskResponseData | None = None
    error: str | None = None


class ParseRequest(BaseModel):
    question: str
    history_context: list[dict[str, str]] | None = None


class ParseResponseData(BaseModel):
    analysis_type: str
    intent: str
    reasoning_summary: str


class ParseResponse(BaseModel):
    success: bool
    data: ParseResponseData | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
