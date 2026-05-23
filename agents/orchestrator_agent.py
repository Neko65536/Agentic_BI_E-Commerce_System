"""
orchestrator_agent.py

成员 B：Agent 编排与数据分析负责人

作用：
1. 用 LangGraph 设计整体 Agent 工作流。
2. 协调 query_router 和 data_analysis_agent。
3. 解析用户问题、拆分任务、调度数据分析 Agent、整合答案。
4. 输出结构化结果，供可视化 Agent 和决策 Agent 使用。

当前工作流：
用户问题
  -> parse_question_node
  -> route_query_node
  -> data_analysis_node
  -> package_downstream_node
  -> final_answer_node

为什么用 LangGraph？
LangGraph 可以把每一步封装成节点，每个节点读写同一个 state。
你可以把它理解为“有状态的流程图”。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph


# 允许直接运行：python agents/orchestrator_agent.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.data_analysis_agent import (
    dataframe_to_rows,
    execute_sql,
    generate_sql,
    recommend_chart,
    summarize_result,
)
from agents.query_router import route_question


class BIAnalysisState(TypedDict, total=False):
    """
    LangGraph 的共享状态。

    每个节点接收 state，返回要更新的字段。
    total=False 表示字段可以逐步补齐。
    """

    question: str
    normalized_question: str
    route: dict[str, Any]
    sql: str | None
    params: dict[str, Any]
    source_tables: list[str]
    used_pre_aggregate: bool
    strategy: str
    rows: list[dict[str, Any]]
    row_count: int
    summary: str
    downstream_payload: dict[str, Any]
    final_answer: str
    errors: list[str]


def parse_question_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    节点 1：解析用户问题。

    目前先做最小处理：
    - 去掉前后空白
    - 保留原始中文问题
    后续如果要支持复杂问题拆分，可以在这里扩展。
    """
    question = state["question"].strip()

    return {
        "normalized_question": question,
        "errors": [],
    }


def route_query_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    节点 2：查询路由。

    调用 query_router.py，判断：
    - intent 是什么
    - 是否使用预聚合表
    - 目标表是哪张
    - 回退表有哪些
    """
    question = state["normalized_question"]
    route = route_question(question)

    return {
        "route": route,
    }


def data_analysis_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    节点 3：数据分析。

    根据 route 生成 SQL，执行 SQL，并生成摘要。
    """
    question = state["normalized_question"]
    route = state["route"]
    plan = generate_sql(route)

    if plan.sql is None:
        return {
            "sql": None,
            "params": plan.params,
            "source_tables": plan.source_tables,
            "used_pre_aggregate": plan.used_pre_aggregate,
            "strategy": plan.strategy,
            "rows": [],
            "row_count": 0,
            "summary": plan.note,
        }

    df = execute_sql(plan.sql, plan.params)
    rows = dataframe_to_rows(df)
    summary = summarize_result(question, route, plan, rows)

    return {
        "sql": plan.sql.strip(),
        "params": plan.params,
        "source_tables": plan.source_tables,
        "used_pre_aggregate": plan.used_pre_aggregate,
        "strategy": plan.strategy,
        "rows": rows,
        "row_count": len(rows),
        "summary": summary,
    }


def package_downstream_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    节点 4：打包给下游 Agent。

    这一步非常重要，因为你的任务要求：
    “将 SQL、查询结果和分析摘要以结构化形式传给可视化 Agent 和决策 Agent。”

    所以这里明确输出两个包：
    - visualization_agent_input
    - decision_agent_input
    """
    route = state["route"]
    intent = route["intent"]

    downstream_payload = {
        "visualization_agent_input": {
            "analysis_type": intent,
            "recommended_chart": recommend_chart(intent),
            "data": state["rows"],
            "row_count": state["row_count"],
            "x_fields": route.get("dimensions", []),
            "y_fields": route.get("metrics", []),
        },
        "decision_agent_input": {
            "question": state["question"],
            "intent": intent,
            "summary": state["summary"],
            "key_findings": state["rows"][:5],
            "sql": state["sql"],
            "source_tables": state["source_tables"],
            "used_pre_aggregate": state["used_pre_aggregate"],
            "strategy": state["strategy"],
            "route_reason": route.get("reason"),
        },
    }

    return {
        "downstream_payload": downstream_payload,
    }


def final_answer_node(state: BIAnalysisState) -> BIAnalysisState:
    """
    节点 5：整合最终回答。

    面向用户的答案要简洁；
    面向其他 Agent 的结构化数据放在 downstream_payload。
    """
    route = state["route"]

    preagg_text = "是" if state["used_pre_aggregate"] else "否"

    final_answer = f"""
分析完成。

问题：{state["question"]}

意图识别：{route["intent"]}
查询策略：{state["strategy"]}
是否使用预聚合表：{preagg_text}
使用数据源：{", ".join(state["source_tables"])}

结论：
{state["summary"]}
""".strip()

    return {
        "final_answer": final_answer,
    }


def build_graph():
    """
    构建 LangGraph 工作流。
    """
    workflow = StateGraph(BIAnalysisState)

    workflow.add_node("parse_question", parse_question_node)
    workflow.add_node("route_query", route_query_node)
    workflow.add_node("data_analysis", data_analysis_node)
    workflow.add_node("package_downstream", package_downstream_node)
    workflow.add_node("final_answer", final_answer_node)

    workflow.set_entry_point("parse_question")

    workflow.add_edge("parse_question", "route_query")
    workflow.add_edge("route_query", "data_analysis")
    workflow.add_edge("data_analysis", "package_downstream")
    workflow.add_edge("package_downstream", "final_answer")
    workflow.add_edge("final_answer", END)

    return workflow.compile()


def run_orchestrator(question: str) -> dict[str, Any]:
    """
    对外主函数。

    输入：
        自然语言问题

    输出：
        包含 final_answer、sql、rows、downstream_payload 的完整结构化结果
    """
    graph = build_graph()
    result = graph.invoke({"question": question})
    return result


if __name__ == "__main__":
    test_questions = [
        "2017年GMV是多少？",
        "按月和各州排名的趋势怎样？",
        "平台整体准时交付率是多少？",
        "哪些州延迟最严重？",
        "哪种支付方式最受欢迎？",
        "平均分期数是多少？",
    ]

    for question in test_questions:
        print("=" * 100)
        result = run_orchestrator(question)
        print(result["final_answer"])
        print()
        print("SQL:")
        print(result["sql"])
        print()
        print("下游 Agent 输入示例:")
        print(json.dumps(result["downstream_payload"], ensure_ascii=False, indent=2)[:1500])
        print()
