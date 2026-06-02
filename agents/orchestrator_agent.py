"""
OrchestratorAgent.

Current workflow:
User question
  -> parse_question_node
  -> coordinator_plan_node
  -> data_analysis_node
  -> package_downstream_node
  -> forecast_node
  -> nlp_review_node
  -> what_if_node
  -> visualization_node
  -> decision_node
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
from agents.decision_agent import run_decision_agent
from agents.nlp_review_agent import run_nlp_review_agent
from agents.schemas import CoordinatorPlan, DataAnalysisResult
from agents.visualization_agent import run_visualization_agent
from agents.what_if_agent import run_what_if_agent
from models.forecast_model import run_forecast_model


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
    visualization_result: dict[str, Any] | None
    forecast_result: dict[str, Any] | None
    nlp_result: dict[str, Any] | None
    what_if_result: dict[str, Any] | None
    decision_result: dict[str, Any] | None
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
        "forecast_model_input": {
            "question": state["question"],
            "analysis_type": plan["analysis_type"],
            "data": data_analysis["data"],
        },
        "nlp_review_agent_input": {
            "question": state["question"],
            "analysis_type": plan["analysis_type"],
            "intent": plan["intent"],
        },
        "what_if_agent_input": {
            "question": state["question"],
            "analysis_type": plan["analysis_type"],
            "intent": plan["intent"],
            "summary": data_analysis["summary"],
        },
    }

    return {"downstream_payload": downstream_payload}


def visualization_node(state: BIAnalysisState) -> BIAnalysisState:
    """Call VisualizationAgent and save chart artifact metadata."""
    try:
        payload = dict(state["downstream_payload"]["visualization_agent_input"])
        payload["forecast_result"] = state.get("forecast_result")
        payload["nlp_result"] = state.get("nlp_result")
        payload["what_if_result"] = state.get("what_if_result")
        return {"visualization_result": run_visualization_agent(payload)}
    except Exception as exc:
        errors = state.get("errors", []) + [f"VisualizationAgent失败：{exc}"]
        return {"visualization_result": None, "errors": errors}


def _needs_forecast(state: BIAnalysisState) -> bool:
    plan = state["coordinator_plan"]
    question = state["question"]
    text = f"{question} {plan['intent']} {plan['analysis_type']}".lower()
    keywords = ["预测", "未来", "forecast", "predict", "next"]
    return plan["analysis_type"] == "predictive" or any(keyword in text for keyword in keywords)


def forecast_node(state: BIAnalysisState) -> BIAnalysisState:
    """Run the deterministic 6-week GMV forecast when the question needs it."""
    if not _needs_forecast(state):
        return {"forecast_result": None}

    try:
        payload = state["downstream_payload"]["forecast_model_input"]
        result = run_forecast_model(
            question=payload["question"],
            source_rows=payload.get("data") or [],
        )
        return {"forecast_result": result}
    except Exception as exc:
        errors = state.get("errors", []) + [f"ForecastModel失败：{exc}"]
        return {"forecast_result": None, "errors": errors}


def _needs_nlp(state: BIAnalysisState) -> bool:
    plan = state["coordinator_plan"]
    question = state["question"]
    text = f"{question} {plan['intent']} {plan['analysis_type']}".lower()
    keywords = ["评论", "评价", "评分", "差评", "好评", "review", "sentiment", "seller", "卖家"]
    return plan["analysis_type"] in {"diagnostic", "prescriptive"} or any(keyword in text for keyword in keywords)


def nlp_review_node(state: BIAnalysisState) -> BIAnalysisState:
    """Run review sentiment mining when useful for diagnosis or decisions."""
    if not _needs_nlp(state):
        return {"nlp_result": None}

    try:
        payload = state["downstream_payload"]["nlp_review_agent_input"]
        return {"nlp_result": run_nlp_review_agent(payload)}
    except Exception as exc:
        errors = state.get("errors", []) + [f"NLPReviewAgent失败：{exc}"]
        return {"nlp_result": None, "errors": errors}


def _needs_what_if(state: BIAnalysisState) -> bool:
    plan = state["coordinator_plan"]
    question = state["question"]
    text = f"{question} {plan['intent']} {plan['analysis_type']}".lower()
    keywords = ["what-if", "what if", "如果", "假如", "下架", "整改", "提升多少", "模拟"]
    return any(keyword in text for keyword in keywords)


def what_if_node(state: BIAnalysisState) -> BIAnalysisState:
    """Run What-if simulation when the user asks an intervention question."""
    if not _needs_what_if(state):
        return {"what_if_result": None}

    try:
        payload = state["downstream_payload"]["what_if_agent_input"]
        return {"what_if_result": run_what_if_agent(payload)}
    except Exception as exc:
        errors = state.get("errors", []) + [f"WhatIfAgent失败：{exc}"]
        return {"what_if_result": None, "errors": errors}


def decision_node(state: BIAnalysisState) -> BIAnalysisState:
    """Call DecisionIntelligenceAgent for operational recommendations."""
    try:
        payload = state["downstream_payload"]["decision_agent_input"]
        result = run_decision_agent(
            payload=payload,
            visualization_result=state.get("visualization_result"),
            forecast_result=state.get("forecast_result"),
            nlp_result=state.get("nlp_result"),
            what_if_result=state.get("what_if_result"),
        )
        return {"decision_result": result}
    except Exception as exc:
        errors = state.get("errors", []) + [f"DecisionAgent失败：{exc}"]
        return {"decision_result": None, "errors": errors}


def final_answer_node(state: BIAnalysisState) -> BIAnalysisState:
    """Build user-facing answer."""
    plan = state["coordinator_plan"]
    data_analysis = state["data_analysis"]
    visualization_result = state.get("visualization_result")
    forecast_result = state.get("forecast_result")
    nlp_result = state.get("nlp_result")
    what_if_result = state.get("what_if_result")
    decision_result = state.get("decision_result")

    used_view_text = "是" if data_analysis["used_view"] else "否"
    view_name_text = data_analysis["view_name"] or "无"
    chart_text = ""
    if visualization_result:
        charts = visualization_result.get("charts") or [visualization_result]
        chart_lines = []
        for item in charts[:4]:
            chart_lines.append(
                f"- {item.get('chart_type')}：{item.get('chart_path')}"
            )
        chart_text = (
            f"\n\n可视化结果：\n"
            f"已生成{len(charts)}张图表。\n"
            + "\n".join(chart_lines)
            + f"\n图表洞察：{visualization_result.get('chart_insight')}"
        )

    forecast_text = ""
    if forecast_result and forecast_result.get("forecast_values"):
        first_forecast = forecast_result["forecast_values"][0]
        forecast_text = (
            f"\n\n预测结果：\n"
            f"{forecast_result.get('trend_summary')}\n"
            f"首周预测GMV：{first_forecast.get('predicted_gmv')}（week_start={first_forecast.get('week_start')}）"
        )

    nlp_text = ""
    if nlp_result:
        topics = nlp_result.get("topic_summary") or []
        topic_text = ""
        if topics:
            topic_text = "；主要主题：" + "、".join(
                f"{item.get('business_meaning')}({item.get('count')})"
                for item in topics[:3]
            )
        nlp_text = (
            f"\n\n评论洞察：\n"
            f"{nlp_result.get('insight')}\n"
            f"负面评论占比：{nlp_result.get('negative_rate')}"
            f"{topic_text}"
        )

    decision_text = ""
    if decision_result:
        recommendations = decision_result.get("recommendations") or []
        lines = []
        for item in recommendations[:3]:
            lines.append(
                f"- [{item.get('priority')}] {item.get('action')} 预期影响：{item.get('expected_impact')}"
            )
        if lines:
            decision_text = "\n\n决策建议：\n" + "\n".join(lines)

    what_if_text = ""
    if what_if_result:
        what_if_text = (
            f"\n\nWhat-if模拟：\n"
            f"{what_if_result.get('insight')}\n"
            f"受影响评论数：{what_if_result.get('affected_reviews')}，"
            f"预估评分提升：{what_if_result.get('estimated_lift')}"
        )

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
{chart_text}
{forecast_text}
{nlp_text}
{what_if_text}
{decision_text}
""".strip()

    return {"final_answer": final_answer}


def build_graph():
    workflow = StateGraph(BIAnalysisState)

    workflow.add_node("parse_question", parse_question_node)
    workflow.add_node("coordinator_plan", coordinator_plan_node)
    workflow.add_node("data_analysis", data_analysis_node)
    workflow.add_node("package_downstream", package_downstream_node)
    workflow.add_node("visualization", visualization_node)
    workflow.add_node("forecast", forecast_node)
    workflow.add_node("nlp_review", nlp_review_node)
    workflow.add_node("what_if", what_if_node)
    workflow.add_node("decision", decision_node)
    workflow.add_node("final_answer", final_answer_node)

    workflow.set_entry_point("parse_question")

    workflow.add_edge("parse_question", "coordinator_plan")
    workflow.add_edge("coordinator_plan", "data_analysis")
    workflow.add_edge("data_analysis", "package_downstream")
    workflow.add_edge("package_downstream", "forecast")
    workflow.add_edge("forecast", "nlp_review")
    workflow.add_edge("nlp_review", "what_if")
    workflow.add_edge("what_if", "visualization")
    workflow.add_edge("visualization", "decision")
    workflow.add_edge("decision", "final_answer")
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
