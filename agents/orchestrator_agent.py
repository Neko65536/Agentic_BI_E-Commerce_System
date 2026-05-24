"""
OrchestratorAgent.

Current workflow:
User question
  -> parse_question_node
  -> coordinator_plan_node
  -> data_analysis_node
  -> package_downstream_node
  -> final_answer_node

This file coordinates agents. It does not generate SQL directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.coordinator_agent import create_task_plan
from agents.data_analysis_agent import recommend_chart, run_data_analysis
from agents.schemas import CoordinatorPlan, DataAnalysisResult


class BIAnalysisState(TypedDict, total=False):
    """LangGraph shared state."""

    question: str
    history_context: list[dict[str, str]]
    normalized_question: str
    coordinator_plan: CoordinatorPlan
    data_analysis: DataAnalysisResult
    sql: str
    rows: list[dict[str, Any]]
    row_count: int
    summary: str
    downstream_payload: dict[str, Any]
    final_answer: str
    errors: list[str]


def parse_question_node(state: BIAnalysisState) -> BIAnalysisState:
    question = state["question"].strip()
    return {
        "normalized_question": question,
        "history_context": state.get("history_context", []),
        "errors": [],
    }


def coordinator_plan_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    CoordinatorAgent call.

    It classifies the analysis type and creates one DataAnalysisAgent subtask.
    """
    question = state["normalized_question"]
    plan = create_task_plan(
        question=question,
        history_context=state.get("history_context", []),
    )
    return {"coordinator_plan": plan}


def data_analysis_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    DataAnalysisAgent call.

    It generates SQL, executes the query, and returns the required output format.
    """
    question = state["normalized_question"]
    coordinator_plan = state["coordinator_plan"]
    task = coordinator_plan["task_plan"][0]

    data_result = run_data_analysis(question=question, task=task)

    return {
        "data_analysis": data_result,
        "sql": data_result["sql"],
        "rows": data_result["data"],
        "row_count": len(data_result["data"]),
        "summary": data_result["summary"],
    }


def package_downstream_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    Package structured output for future VisualizationAgent and DecisionAgent.
    """
    plan = state["coordinator_plan"]
    data_analysis = state["data_analysis"]
    recommended_chart = recommend_chart(plan["analysis_type"], data_analysis)

    downstream_payload = {
        "visualization_agent_input": {
            "question": state["question"],
            "analysis_type": plan["analysis_type"],
            "intent": plan["intent"],
            "recommended_chart": recommended_chart,
            "data": data_analysis["data"],
            "row_count": len(data_analysis["data"]),
        },
        "decision_agent_input": {
            "question": state["question"],
            "analysis_type": plan["analysis_type"],
            "intent": plan["intent"],
            "task_plan": plan["task_plan"],
            "reasoning_summary": plan["reasoning_summary"],
            "summary": data_analysis["summary"],
            "key_findings": data_analysis["data"][:5],
            "sql": data_analysis["sql"],
            "used_view": data_analysis["used_view"],
            "view_name": data_analysis["view_name"],
        },
    }

    return {"downstream_payload": downstream_payload}


def final_answer_node(state: BIAnalysisState) -> BIAnalysisState:
    """Build user-facing answer."""
    plan = state["coordinator_plan"]
    data_analysis = state["data_analysis"]

    used_view_text = "是" if data_analysis["used_view"] else "否"
    view_name_text = data_analysis["view_name"] or "无"

    final_answer = f"""
分析完成。

问题：{state["question"]}

分析类型：{plan["analysis_type"]}
业务意图：{plan["intent"]}
协调器说明：{plan["reasoning_summary"]}

是否使用预聚合视图：{used_view_text}
命中视图：{view_name_text}
返回行数：{len(data_analysis["data"])}

统计摘要：
{data_analysis["summary"]}
""".strip()

    return {"final_answer": final_answer}


def build_graph():
    workflow = StateGraph(BIAnalysisState)

    workflow.add_node("parse_question", parse_question_node)
    workflow.add_node("coordinator_plan", coordinator_plan_node)
    workflow.add_node("data_analysis", data_analysis_node)
    workflow.add_node("package_downstream", package_downstream_node)
    workflow.add_node("final_answer", final_answer_node)

    workflow.set_entry_point("parse_question")

    workflow.add_edge("parse_question", "coordinator_plan")
    workflow.add_edge("coordinator_plan", "data_analysis")
    workflow.add_edge("data_analysis", "package_downstream")
    workflow.add_edge("package_downstream", "final_answer")
    workflow.add_edge("final_answer", END)

    return workflow.compile()


def run_orchestrator(
    question: str,
    history_context: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    graph = build_graph()
    return graph.invoke({
        "question": question,
        "history_context": history_context or [],
    })


if __name__ == "__main__":
    test_questions = [
        "2017年GMV是多少？",
        "按月和各州排名的趋势怎样？",
        "平台整体准时交付率是多少？",
        "评价分数最低的卖家有哪些？",
    ]

    for question in test_questions:
        print("=" * 100)
        result = run_orchestrator(question)
        print(result["final_answer"])
        print()
        print("SQL:")
        print(result["sql"])
        print()
        print("DataAnalysisAgent 输出:")
        print(json.dumps(result["data_analysis"], ensure_ascii=False, indent=2)[:1500])
        print()
