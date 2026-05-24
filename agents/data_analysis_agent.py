"""
DataAnalysisAgent.

Responsibilities:
1. Receive the user question and CoordinatorAgent task.
2. Generate read-only SQL using data dictionary and pre-aggregation policy.
3. Validate SQL safety.
4. Execute SQL.
5. Return a stable JSON-friendly result:
   {
     "question": "用户问题",
     "sql": "执行的SQL语句",
     "used_view": true/false,
     "view_name": "mv_xxx" or None,
     "data": [..records..],
     "summary": "统计摘要"
   }
"""

from __future__ import annotations

import json
import math
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.llm_client import LLMClient
from agents.schemas import AgentTask, DataAnalysisResult
from agents.sql_guard import validate_readonly_sql
from config.settings import sqlalchemy_url


DATA_DICTIONARY_PATH = ROOT / "config" / "data_dictionary.yaml"
PROMPTS_PATH = ROOT / "config" / "prompts.yaml"


def get_engine():
    """Create database connection engine."""
    return create_engine(sqlalchemy_url(), pool_pre_ping=True)


def load_yaml_context(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    return loaded if isinstance(loaded, dict) else {}


def load_data_dictionary_context() -> str:
    """Return compact YAML context for SQL generation."""
    data = load_yaml_context(DATA_DICTIONARY_PATH)
    useful_context = {
        "meta": data.get("meta", {}),
        "tables": data.get("tables", {}),
        "materialized_aggregates": data.get("materialized_aggregates", {}),
    }
    return yaml.safe_dump(useful_context, allow_unicode=True, sort_keys=False)


def load_pre_aggregate_policy_context() -> str:
    """Return the pre-aggregation policy from prompts.yaml if available."""
    prompts = load_yaml_context(PROMPTS_PATH)
    useful_context = {
        "system_principles": prompts.get("system", {}).get("principles", []),
        "pre_aggregate_policy": prompts.get("pre_aggregate_policy", {}),
    }
    return yaml.safe_dump(useful_context, allow_unicode=True, sort_keys=False)


def _to_jsonable(value: Any) -> Any:
    """Convert pandas / Decimal / NaN values to JSON-friendly values."""
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, float) and math.isnan(value):
        return None

    if pd.isna(value):
        return None

    return value


def execute_sql(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Execute SQL and return DataFrame."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def dataframe_to_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert DataFrame to JSON-friendly records."""
    rows = df.to_dict(orient="records")
    return [
        {key: _to_jsonable(value) for key, value in row.items()}
        for row in rows
    ]


def detect_view_name(sql: str) -> str | None:
    """Detect first mv_* table referenced in generated SQL."""
    match = re.search(r"\b(?:FROM|JOIN)\s+`?(mv_[a-zA-Z0-9_]+)`?\b", sql, flags=re.IGNORECASE)
    return match.group(1) if match else None


def generate_sql_plan(question: str, task: AgentTask) -> dict[str, Any]:
    """
    Ask the DataAnalysisAgent LLM to produce SQL and metadata.
    """
    data_dictionary = load_data_dictionary_context()
    pre_aggregate_policy = load_pre_aggregate_policy_context()

    system_prompt = f"""
你是电商 BI 系统中的数据分析 Agent。

你的职责：
1. 将业务问题转换为 MySQL SQL。
2. 判断是否命中预聚合视图 mv_*。
3. 如果预聚合视图可以准确回答问题，必须优先查询视图。
4. 如果预聚合视图无法准确回答问题，才查询原始表。
5. 只生成 SELECT 或 WITH 查询。
6. 禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE。
7. 不要编造不存在的表或字段。
8. 涉及 `year_month` 字段时必须使用反引号。
9. 默认加 LIMIT，除非查询是单行聚合指标。

数据字典：
{data_dictionary}

预聚合视图策略：
{pre_aggregate_policy}

你必须返回 JSON，不要 Markdown，不要解释性正文。
返回格式必须为：
{{
  "sql": "SELECT ...",
  "used_view": true,
  "view_name": "mv_xxx 或 null",
  "summary_intent": "说明这个 SQL 计划如何回答问题"
}}
""".strip()

    user_prompt = f"""
用户问题：
{question}

协调器分配的子任务：
{json.dumps(task, ensure_ascii=False, indent=2)}

请生成可执行 SQL。
""".strip()

    client = LLMClient()

    raw = client.chat_json([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    sql = validate_readonly_sql(str(raw.get("sql", "")))
    view_name = raw.get("view_name")
    if view_name in ("", "null", "None"):
        view_name = None
    if not view_name:
        view_name = detect_view_name(sql)

    used_view = bool(raw.get("used_view")) or bool(view_name)

    res = {
        "sql": sql,
        "used_view": used_view,
        "view_name": str(view_name) if view_name else None,
        "summary_intent": str(raw.get("summary_intent") or "已生成 SQL 查询计划。"),
    }
    print("=========数据分析Agent-LLM返回：============")
    print(res)
    print("==========================================")
    return res


def summarize_rows(
    question: str,
    sql_plan: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    """Generate a compact deterministic summary from returned rows."""
    if not rows:
        return "没有查询到符合条件的数据。"

    used_view_text = "使用了预聚合视图" if sql_plan["used_view"] else "未使用预聚合视图"
    view_text = f"，命中视图 {sql_plan['view_name']}" if sql_plan.get("view_name") else ""
    first_row = rows[0]
    sample_fields = "，".join(f"{key}={value}" for key, value in list(first_row.items())[:4])

    return (
        f"查询返回 {len(rows)} 行结果，{used_view_text}{view_text}。"
        f"首行关键字段：{sample_fields}。"
    )


def run_data_analysis(question: str, task: AgentTask) -> DataAnalysisResult:
    """
    Public entry point for DataAnalysisAgent.
    """
    sql_plan = generate_sql_plan(question, task)
    df = execute_sql(sql_plan["sql"])
    rows = dataframe_to_rows(df)
    summary = summarize_rows(question, sql_plan, rows)

    return {
        "question": question,
        "sql": sql_plan["sql"].strip(),
        "used_view": bool(sql_plan["used_view"]),
        "view_name": sql_plan["view_name"],
        "data": rows,
        "summary": summary,
    }


def recommend_chart(analysis_type: str, data_analysis: DataAnalysisResult) -> str | None:
    """Lightweight chart suggestion for downstream visualization agent."""
    data = data_analysis.get("data", [])
    if not data:
        return None

    first = data[0]
    numeric_fields = [key for key, value in first.items() if isinstance(value, (int, float))]
    categorical_fields = [key for key, value in first.items() if not isinstance(value, (int, float))]

    if len(data) == 1 and numeric_fields:
        return "big_number_card"
    if any("month" in key or "date" in key or "time" in key for key in first):
        return "line_chart"
    if categorical_fields and numeric_fields:
        return "bar_chart"
    if analysis_type in {"diagnostic", "prescriptive"}:
        return "table_with_highlights"
    return "table"


if __name__ == "__main__":
    from agents.coordinator_agent import create_task_plan

    q = "评价分数最低的卖家有哪些？"
    plan = create_task_plan(q)
    result = run_data_analysis(q, plan["task_plan"][0])
    print(json.dumps(result, ensure_ascii=False, indent=2))
