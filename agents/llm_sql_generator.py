# agents/llm_sql_generator.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from agents.llm_client import LLMClient
from agents.sql_guard import validate_readonly_sql


ROOT = Path(__file__).resolve().parents[1]
DATA_DICTIONARY_PATH = ROOT / "config" / "data_dictionary.yaml"


def load_data_dictionary_context() -> str:
    """
    读取数据字典，给 LLM 作为 schema 上下文。

    作用：
    - 告诉 LLM 有哪些表
    - 哪些 mv_* 可以优先使用
    - 每张表的字段含义是什么
    """
    data = yaml.safe_load(DATA_DICTIONARY_PATH.read_text(encoding="utf-8"))

    useful_context = {
        "meta": data.get("meta", {}),
        "tables": data.get("tables", {}),
        "materialized_aggregates": data.get("materialized_aggregates", {}),
    }

    return yaml.safe_dump(
        useful_context,
        allow_unicode=True,
        sort_keys=False,
    )


def generate_sql_with_llm(question: str, route: dict[str, Any]) -> dict[str, Any]:
    """
    让 LLM 为规则未覆盖的问题生成 SQL 计划。

    返回结构：
    {
      "sql": "...",
      "source_tables": ["..."],
      "used_pre_aggregate": true/false,
      "strategy": "llm_pre_aggregate" / "llm_fallback_raw_table",
      "note": "..."
    }
    """
    schema_context = load_data_dictionary_context()

    system_prompt = f"""
        你是电商 BI 系统中的 NL2SQL Agent。

        你必须遵守：

        1. 只能生成 MySQL SELECT 或 WITH 查询。
        2. 禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE。
        3. 优先使用 mv_* 预聚合表。
        4. 只有当 mv_* 无法准确回答问题时，才回退原始表。
        5. 不要编造不存在的表或字段。
        6. 涉及 year_month 字段时必须写成 `year_month`。
        7. 返回必须是 JSON，不要 Markdown，不要解释性正文。

        数据字典如下：

        {schema_context}

        返回 JSON 格式必须为：

        {{
        "sql": "SELECT ...",
        "source_tables": ["table_name"],
        "used_pre_aggregate": true,
        "strategy": "llm_pre_aggregate",
        "note": "简短说明为什么这样查"
        }}
    """.strip()

    user_prompt = f"""
        用户问题：
        {question}

        规则路由结果：
        {json.dumps(route, ensure_ascii=False, indent=2)}

        请生成 SQL 查询计划。
    """.strip()

    llm_client = LLMClient()
    result = llm_client.chat_json([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    sql = validate_readonly_sql(str(result.get("sql", "")))

    return {
        "sql": sql,
        "source_tables": result.get("source_tables", []),
        "used_pre_aggregate": bool(result.get("used_pre_aggregate", False)),
        "strategy": result.get("strategy", "llm_generated_sql"),
        "note": result.get("note", "LLM 生成 SQL。"),
    }