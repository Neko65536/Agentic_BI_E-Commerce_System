"""Safety guard for LLM-generated SQL."""

from __future__ import annotations

import re


FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "LOAD_FILE",
    "INTO OUTFILE",
    "INTO DUMPFILE",
]


def validate_readonly_sql(sql: str) -> str:
    """
    Only allow a single read-only MySQL query.

    Allowed entry points:
    - SELECT
    - WITH
    """
    cleaned = sql.strip()
    if not cleaned:
        raise ValueError("SQL 为空。")

    cleaned = cleaned.rstrip(";").strip()

    if ";" in cleaned:
        raise ValueError("不允许执行多条 SQL 语句。")

    if not re.match(r"^(SELECT|WITH)\b", cleaned, flags=re.IGNORECASE | re.DOTALL):
        raise ValueError("只允许 SELECT 或 WITH 查询。")

    upper_sql = re.sub(r"\s+", " ", cleaned.upper())
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in upper_sql:
            raise ValueError(f"SQL 包含禁止关键字：{keyword}")

    return cleaned + ";"
