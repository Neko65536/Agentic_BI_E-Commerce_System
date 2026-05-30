"""
Shared Agent interface schemas.

These TypedDicts define the boundary between:
- CoordinatorAgent
- DataAnalysisAgent
- OrchestratorAgent

Keep this file free of business logic.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


AnalysisType = Literal[
    "descriptive",
    "diagnostic",
    "predictive",
    "prescriptive",
]


class TaskInput(TypedDict):
    question: str
    requirements: list[str]


class ExpectedOutput(TypedDict):
    data: str
    summary: str


class AgentTask(TypedDict):
    agent: str
    task: str
    input: TaskInput
    expected_output: ExpectedOutput


class CoordinatorPlan(TypedDict):
    question: str
    analysis_type: AnalysisType
    intent: str
    task_plan: list[AgentTask]
    reasoning_summary: str


class DataAnalysisResult(TypedDict):
    question: str
    sql: str
    used_view: bool
    view_name: str | None
    data: list[dict[str, Any]]
    summary: str
