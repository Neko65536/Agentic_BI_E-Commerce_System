"""
data_analysis_agent.py

作用：
1. 接收用户问题或 query_router 的路由结果。
2. 生成 SQL。
3. 执行 SQL。
4. 返回结构化结果：
   - question: 原始问题
   - route: 路由结果
   - sql: 执行的 SQL
   - params: SQL 参数
   - rows: 查询结果
   - summary: 文字摘要
   - downstream_payload: 给可视化 Agent / 决策 Agent 使用的数据包

当前版本特点：
- 不依赖大模型，先用规则覆盖课程要求的典型问题。
- 优先使用 mv_* 预聚合表。
- 如果预聚合表不能精确回答，就回退原始表。
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from agents.llm_sql_generator import generate_sql_with_llm

import pandas as pd
from sqlalchemy import create_engine, text


# 允许直接运行：python agents/data_analysis_agent.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import sqlalchemy_url
from agents.query_router import route_question


@dataclass
class SQLPlan:
    """SQL 生成计划。"""

    sql: str | None
    params: dict[str, Any]
    source_tables: list[str]
    used_pre_aggregate: bool
    strategy: str
    note: str


def get_engine():
    """创建数据库连接。"""
    return create_engine(sqlalchemy_url(), pool_pre_ping=True)


def _year_month_where(route: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    为 mv_* 表构造 year_month 过滤条件。

    例如：
    filters.year = 2017
    -> WHERE `year_month` LIKE :year_prefix
    -> {"year_prefix": "2017-%"}
    """
    year = route.get("filters", {}).get("year")
    if year:
        return "WHERE `year_month` LIKE :year_prefix", {"year_prefix": f"{year}-%"}
    return "", {}


def _orders_year_where(route: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    为 orders 原始表构造年份过滤条件。
    """
    year = route.get("filters", {}).get("year")
    base = """
WHERE order_purchase_timestamp IS NOT NULL
  AND order_delivered_customer_date IS NOT NULL
  AND order_estimated_delivery_date IS NOT NULL
"""
    params: dict[str, Any] = {}

    if year:
        base += """
  AND order_purchase_timestamp >= :start_date
  AND order_purchase_timestamp < :end_date
"""
        params["start_date"] = f"{year}-01-01"
        params["end_date"] = f"{year + 1}-01-01"

    return base, params


def generate_sql(route: dict[str, Any], question: str | None = None) -> SQLPlan:
    """
    根据路由结果生成 SQL。

    注意：
    这里不拼接用户原文，只拼接我们自己控制的 SQL 模板。
    年份等变量用参数绑定，避免 SQL 注入。
    """
    intent = route["intent"]

    if intent == "gmv":
        where_sql, params = _year_month_where(route)
        sql = f"""
SELECT
  ROUND(SUM(total_gmv), 2) AS gmv,
  SUM(total_orders) AS total_orders,
  ROUND(SUM(total_gmv) / NULLIF(SUM(total_orders), 0), 2) AS avg_basket,
  ROUND(SUM(total_freight), 2) AS total_freight
FROM mv_monthly_sales
{where_sql};
"""
        return SQLPlan(
            sql=sql,
            params=params,
            source_tables=["mv_monthly_sales"],
            used_pre_aggregate=True,
            strategy="pre_aggregate",
            note="GMV 使用 mv_monthly_sales 汇总，避免实时 JOIN orders 和 order_items。",
        )

    if intent == "state_sales_trend":
        where_sql, params = _year_month_where(route)
        sql = f"""
WITH ranked AS (
  SELECT
    `year_month`,
    customer_state,
    total_gmv,
    total_orders,
    unique_customers,
    RANK() OVER (
      PARTITION BY `year_month`
      ORDER BY total_gmv DESC
    ) AS state_rank
  FROM mv_state_sales
  {where_sql}
)
SELECT
  `year_month`,
  customer_state,
  state_rank,
  ROUND(total_gmv, 2) AS total_gmv,
  total_orders,
  unique_customers
FROM ranked
WHERE state_rank <= 5
ORDER BY `year_month`, state_rank
LIMIT 120;
"""
        return SQLPlan(
            sql=sql,
            params=params,
            source_tables=["mv_state_sales"],
            used_pre_aggregate=True,
            strategy="pre_aggregate",
            note="按月、按州排名直接使用 mv_state_sales，并用窗口函数计算每月州排名。",
        )

    if intent == "on_time_delivery_rate":
        where_sql, params = _orders_year_where(route)
        sql = f"""
SELECT
  COUNT(*) AS valid_delivery_orders,
  SUM(
    CASE
      WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 1
      ELSE 0
    END
  ) AS on_time_orders,
  SUM(
    CASE
      WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 1
      ELSE 0
    END
  ) AS delayed_orders,
  ROUND(
    AVG(
      CASE
        WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 1
        ELSE 0
      END
    ),
    4
  ) AS on_time_rate
FROM orders
{where_sql};
"""
        return SQLPlan(
            sql=sql,
            params=params,
            source_tables=["orders"],
            used_pre_aggregate=False,
            strategy="fallback_raw_table",
            note=(
                "平台整体准时率需要订单级分母。当前 mv_delivery_perf 没有 total_orders 字段，"
                "为保证口径准确，回退 orders 原始表计算。"
            ),
        )

    if intent == "delivery_delay":
        where_sql, params = _year_month_where(route)
        sql = f"""
SELECT
  customer_state,
  SUM(delayed_orders) AS delayed_orders,
  ROUND(AVG(avg_delivery_days), 2) AS avg_delivery_days,
  ROUND(AVG(on_time_rate), 4) AS avg_on_time_rate
FROM mv_delivery_perf
{where_sql}
GROUP BY customer_state
ORDER BY delayed_orders DESC, avg_delivery_days DESC
LIMIT 10;
"""
        return SQLPlan(
            sql=sql,
            params=params,
            source_tables=["mv_delivery_perf"],
            used_pre_aggregate=True,
            strategy="pre_aggregate",
            note="延迟严重州使用 mv_delivery_perf，按州汇总 delayed_orders 并排序。",
        )

    if intent == "payment_method_popularity":
        where_sql, params = _year_month_where(route)
        sql = f"""
SELECT
  payment_type,
  SUM(total_transactions) AS total_transactions,
  ROUND(SUM(total_value), 2) AS total_value,
  ROUND(
    SUM(avg_installments * total_transactions) / NULLIF(SUM(total_transactions), 0),
    4
  ) AS weighted_avg_installments
FROM mv_payment_dist
{where_sql}
GROUP BY payment_type
ORDER BY total_transactions DESC;
"""
        return SQLPlan(
            sql=sql,
            params=params,
            source_tables=["mv_payment_dist"],
            used_pre_aggregate=True,
            strategy="pre_aggregate",
            note="支付方式偏好使用 mv_payment_dist，按交易次数判断最受欢迎支付方式。",
        )

    if intent == "avg_installments":
        where_sql, params = _year_month_where(route)
        sql = f"""
SELECT
  ROUND(
    SUM(avg_installments * total_transactions) / NULLIF(SUM(total_transactions), 0),
    4
  ) AS overall_avg_installments,
  SUM(total_transactions) AS total_transactions
FROM mv_payment_dist
{where_sql};
"""
        return SQLPlan(
            sql=sql,
            params=params,
            source_tables=["mv_payment_dist"],
            used_pre_aggregate=True,
            strategy="pre_aggregate",
            note=(
                "平均分期数使用加权平均："
                "SUM(avg_installments * total_transactions) / SUM(total_transactions)。"
            ),
        )

    if question:
        llm_plan = generate_sql_with_llm(question, route)

        return SQLPlan(
            sql=llm_plan["sql"],
            params={},
            source_tables=llm_plan["source_tables"],
            used_pre_aggregate=llm_plan["used_pre_aggregate"],
            strategy=llm_plan["strategy"],
            note=llm_plan["note"],
        )

    return SQLPlan(
        sql=None,
        params={},
        source_tables=route.get("fallback_tables", []),
        used_pre_aggregate=False,
        strategy="needs_llm_or_manual_sql",
        note="该问题暂未命中规则模板，且未提供 question，无法调用 LLM 生成 SQL。",
    )


def _to_jsonable(value: Any) -> Any:
    """把 Decimal、NaN 等对象转成适合 JSON 输出的值。"""
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, float) and math.isnan(value):
        return None

    if pd.isna(value):
        return None

    return value


def execute_sql(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """执行 SQL，返回 DataFrame。"""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def dataframe_to_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame 转成 JSON 友好的 rows。"""
    rows = df.to_dict(orient="records")
    return [
        {key: _to_jsonable(value) for key, value in row.items()}
        for row in rows
    ]


def summarize_result(question: str, route: dict[str, Any], plan: SQLPlan, rows: list[dict[str, Any]]) -> str:
    """根据不同 intent 生成简短统计摘要。"""
    intent = route["intent"]

    if not rows:
        return "没有查询到符合条件的数据。"

    if intent == "gmv":
        row = rows[0]
        return (
            f"查询结果显示，GMV 为 {row.get('gmv')}，"
            f"订单数为 {row.get('total_orders')}，"
            f"平均客单价约为 {row.get('avg_basket')}。"
        )

    if intent == "state_sales_trend":
        top = rows[0]
        return (
            f"已按月份计算各州 GMV 排名。样例结果中，"
            f"{top.get('year_month')} 排名第 {top.get('state_rank')} 的州是 "
            f"{top.get('customer_state')}，GMV 为 {top.get('total_gmv')}。"
        )

    if intent == "on_time_delivery_rate":
        row = rows[0]
        rate = row.get("on_time_rate")
        percent = round(rate * 100, 2) if rate is not None else None
        return (
            f"平台整体准时交付率约为 {percent}%。"
            f"有效配送订单数为 {row.get('valid_delivery_orders')}，"
            f"其中准时订单 {row.get('on_time_orders')}，"
            f"延迟订单 {row.get('delayed_orders')}。"
            f"说明：{plan.note}"
        )

    if intent == "delivery_delay":
        top = rows[0]
        return (
            f"延迟最严重的州是 {top.get('customer_state')}，"
            f"延迟订单数为 {top.get('delayed_orders')}，"
            f"平均配送天数约为 {top.get('avg_delivery_days')} 天，"
            f"平均准时率为 {top.get('avg_on_time_rate')}。"
        )

    if intent == "payment_method_popularity":
        top = rows[0]
        return (
            f"最受欢迎的支付方式是 {top.get('payment_type')}，"
            f"交易次数为 {top.get('total_transactions')}，"
            f"支付总额为 {top.get('total_value')}。"
        )

    if intent == "avg_installments":
        row = rows[0]
        return (
            f"平台整体平均分期数约为 {row.get('overall_avg_installments')}，"
            f"统计交易次数为 {row.get('total_transactions')}。"
        )

    return "已完成查询并返回结构化结果。"


def analyze_question(question: str) -> dict[str, Any]:
    """
    对外主函数：
    输入自然语言问题，输出结构化分析结果。
    """
    route = route_question(question)
    plan = generate_sql(route, question)

    if plan.sql is None:
        return {
            "question": question,
            "route": route,
            "sql": None,
            "params": plan.params,
            "source_tables": plan.source_tables,
            "used_pre_aggregate": plan.used_pre_aggregate,
            "strategy": plan.strategy,
            "rows": [],
            "row_count": 0,
            "summary": plan.note,
            "downstream_payload": {
                "analysis_type": route["intent"],
                "data": [],
                "recommended_chart": None,
                "note": plan.note,
            },
        }

    df = execute_sql(plan.sql, plan.params)
    rows = dataframe_to_rows(df)
    summary = summarize_result(question, route, plan, rows)

    return {
        "question": question,
        "route": route,
        "sql": plan.sql.strip(),
        "params": plan.params,
        "source_tables": plan.source_tables,
        "used_pre_aggregate": plan.used_pre_aggregate,
        "strategy": plan.strategy,
        "rows": rows,
        "row_count": len(rows),
        "summary": summary,
        "downstream_payload": {
            "analysis_type": route["intent"],
            "data": rows,
            "recommended_chart": recommend_chart(route["intent"]),
            "note": plan.note,
        },
    }


def recommend_chart(intent: str) -> str | None:
    """给可视化 Agent 的简单建议。"""
    mapping = {
        "gmv": "big_number_card",
        "state_sales_trend": "monthly_ranked_bar_or_map",
        "on_time_delivery_rate": "kpi_card",
        "delivery_delay": "horizontal_bar_chart",
        "payment_method_popularity": "bar_or_pie_chart",
        "avg_installments": "big_number_card",
    }
    return mapping.get(intent)


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
        result = analyze_question(question)
        print("问题：", question)
        print("策略：", result["strategy"])
        print("数据源：", result["source_tables"])
        print("摘要：", result["summary"])
        print("SQL：")
        print(result["sql"])
        print("前 3 行结果：")
        print(json.dumps(result["rows"][:3], ensure_ascii=False, indent=2))
