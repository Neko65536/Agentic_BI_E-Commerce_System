"""
CoordinatorAgent.

Responsibilities:
1. Parse the user's natural-language BI question.
2. Classify the analysis type.
3. Create a task plan for downstream agents.

This agent does not generate SQL and does not query the database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.llm_client import LLMClient
from agents.schemas import AgentTask, AnalysisType, CoordinatorPlan


ALLOWED_ANALYSIS_TYPES: set[str] = {
    "descriptive",
    "diagnostic",
    "predictive",
    "prescriptive",
}

SYSTEM_PROMPT = """
你是电商 BI 系统中的协调器 Agent。

你的职责：
1. 解析用户自然语言问题。
2. 判断问题属于 descriptive、diagnostic、predictive、prescriptive 哪一种分析类型。
3. 将问题拆成当前阶段可执行的子任务。
4. 当前阶段只允许调度 data_analysis_agent。
5. 如果问题要求预测未来销售额或GMV，任务要求必须写明查询 mv_monthly_sales 全量历史月份，不要使用当前日期过滤。
6. 不要生成 SQL，不要编造查询结果。
7. 可以在任务要求里写明应优先使用的预聚合视图名称，但不要生成具体 SQL 片段或字段级表达式。

分析类型定义：
- descriptive：描述性分析，回答“发生了什么”。例如 GMV、排名、分布、趋势、最低/最高。
- diagnostic：诊断性分析，回答“为什么发生”。例如 延迟原因、评分低的关联因素。
- predictive：预测性分析，回答“未来会怎样”。当前阶段让数据分析 Agent 优先查询 mv_monthly_sales 全量历史月度 GMV 作为预测输入。
- prescriptive：规范性分析，回答“应该怎么做”。当前阶段只能让数据分析 Agent 查询历史数据作为决策依据。

你必须返回 JSON，不要 Markdown，不要解释性正文。
返回格式必须为：
{
  "question": "用户问题",
  "analysis_type": "descriptive|diagnostic|predictive|prescriptive",
  "intent": "snake_case_business_intent",
  "task_plan": [
    {
      "agent": "data_analysis_agent",
      "task": "子任务描述",
      "input": {
        "question": "用户问题",
        "requirements": ["要求1", "要求2"]
      },
      "expected_output": {
        "data": "查询结果JSON",
        "summary": "统计摘要"
      }
    }
  ],
  "reasoning_summary": "简短说明为什么这样分类和拆解"
}
""".strip()


def _normalize_analysis_type(value: Any) -> AnalysisType:
    text = str(value or "descriptive").strip().lower()
    if text not in ALLOWED_ANALYSIS_TYPES:
        return "descriptive"
    return text  # type: ignore[return-value]


def _normalize_task(question: str, raw_task: dict[str, Any]) -> AgentTask:
    input_obj = raw_task.get("input") if isinstance(raw_task.get("input"), dict) else {}
    expected_output = raw_task.get("expected_output") if isinstance(raw_task.get("expected_output"), dict) else {}

    requirements = input_obj.get("requirements", [])
    if not isinstance(requirements, list):
        requirements = [str(requirements)]

    return {
        "agent": "data_analysis_agent",
        "task": str(raw_task.get("task") or "根据用户问题查询数据库并生成统计摘要"),
        "input": {
            "question": str(input_obj.get("question") or question),
            "requirements": [str(item) for item in requirements if str(item).strip()],
        },
        "expected_output": {
            "data": str(expected_output.get("data") or "查询结果JSON"),
            "summary": str(expected_output.get("summary") or "统计摘要"),
        },
    }


def _normalize_plan(question: str, raw: dict[str, Any]) -> CoordinatorPlan:
    raw_tasks = raw.get("task_plan")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raw_tasks = [
            {
                "agent": "data_analysis_agent",
                "task": "根据用户问题查询数据库并生成统计摘要",
                "input": {"question": question, "requirements": ["返回查询结果", "生成统计摘要"]},
                "expected_output": {"data": "查询结果JSON", "summary": "统计摘要"},
            }
        ]

    first_task = raw_tasks[0]
    if not isinstance(first_task, dict):
        first_task = {}

    return {
        "question": str(raw.get("question") or question),
        "analysis_type": _normalize_analysis_type(raw.get("analysis_type")),
        "intent": str(raw.get("intent") or "general_analysis"),
        "task_plan": [_normalize_task(question, first_task)],
        "reasoning_summary": str(raw.get("reasoning_summary") or "协调器已将问题拆解为数据分析子任务。"),
    }


def create_task_plan(
    question: str,
    history_context: list[dict[str, str]] | None = None,
) -> CoordinatorPlan:
    """
    Create a structured CoordinatorAgent plan.

    Current implementation intentionally produces one DataAnalysisAgent task.
    More agents can be added later by expanding this contract.
    """
    history_text = json.dumps(history_context or [], ensure_ascii=False, indent=2)

    user_prompt = f"""
用户问题：
{question}

历史会话上下文：
{history_text}

请生成协调器任务计划。
""".strip()

    client = LLMClient()

    raw = client.chat_json([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])
    print("=========协调器Agent-LLM原始返回：===========")
    print(f"{json.dumps(raw, ensure_ascii=False, indent=2)}")
    print("==========================================")

    return _normalize_plan(question, raw)


if __name__ == "__main__":
    plan = create_task_plan("评价分数最低的卖家有哪些？")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
