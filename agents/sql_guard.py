# agents/sql_guard.py

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
    校验 LLM 生成的 SQL 是否只读。

    允许：
    - SELECT
    - WITH ... SELECT

    禁止：
    - DDL
    - DML
    - 多语句
    - 文件读写
    """
    cleaned = sql.strip()

    if not cleaned:
        raise ValueError("SQL 为空")

    cleaned_no_tail = cleaned.rstrip(";").strip()

    if ";" in cleaned_no_tail:
        raise ValueError("不允许多条 SQL 语句")

    if not re.match(r"^(SELECT|WITH)\b", cleaned_no_tail, flags=re.IGNORECASE | re.DOTALL):
        raise ValueError("只允许 SELECT 或 WITH 查询")

    upper_sql = cleaned_no_tail.upper()

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in upper_sql:
            raise ValueError(f"SQL 包含禁止关键字：{keyword}")

    return cleaned_no_tail + ";"