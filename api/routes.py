"""
API 路由处理函数。
"""

from __future__ import annotations

import asyncio
import functools
import sys
from pathlib import Path

from fastapi import APIRouter

from api.schemas import (
    AskRequest,
    AskResponse,
    AskResponseData,
    HealthResponse,
    ParseRequest,
    ParseResponse,
    ParseResponseData,
)
from api.session_store import ensure_session, get_session_snapshot, load_history_context, save_turn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.coordinator_agent import create_task_plan
from agents.orchestrator_agent import run_orchestrator

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
async def health():
    """健康检查。"""
    return HealthResponse(status="ok", version="1.0.0")


@router.post("/ask", response_model=AskResponse)
async def ask_question(body: AskRequest):
    """
    完整分析链路：协调器 → 数据分析 → 最终答案。
    """
    try:
        session_id = ensure_session(body.session_id)
        history_context = body.history_context
        if history_context is None:
            history_context = load_history_context(session_id)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(
                run_orchestrator,
                question=body.question,
                history_context=history_context or [],
            ),
        )
        save_turn(session_id, body.question, result)
        return AskResponse(
            success=True,
            data=AskResponseData(
                session_id=session_id,
                question=result.get("question", body.question),
                analysis_type=result.get("coordinator_plan", {}).get("analysis_type", ""),
                intent=result.get("coordinator_plan", {}).get("intent", ""),
                sql=result.get("sql", ""),
                row_count=result.get("row_count", 0),
                summary=result.get("summary", ""),
                final_answer=result.get("final_answer", ""),
                downstream_payload=result.get("downstream_payload"),
                visualization_result=result.get("visualization_result"),
                forecast_result=result.get("forecast_result"),
                nlp_result=result.get("nlp_result"),
                what_if_result=result.get("what_if_result"),
                decision_result=result.get("decision_result"),
                recommendations=(
                    (result.get("decision_result") or {}).get("recommendations")
                    if result.get("decision_result") else None
                ),
                errors=result.get("errors", []),
            ),
        )
    except Exception as e:
        return AskResponse(success=False, error=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """查看内存会话历史，便于多轮关联分析演示。"""
    return get_session_snapshot(session_id)


@router.post("/parse", response_model=ParseResponse)
async def parse_question(body: ParseRequest):
    """
    仅协调器解析（不执行 SQL），用于快速预览分析类型和意图。
    """
    try:
        loop = asyncio.get_event_loop()
        plan = await loop.run_in_executor(
            None,
            functools.partial(
                create_task_plan,
                question=body.question,
                history_context=body.history_context or [],
            ),
        )
        return ParseResponse(
            success=True,
            data=ParseResponseData(
                analysis_type=plan["analysis_type"],
                intent=plan["intent"],
                reasoning_summary=plan["reasoning_summary"],
            ),
        )
    except Exception as e:
        return ParseResponse(success=False, error=str(e))
