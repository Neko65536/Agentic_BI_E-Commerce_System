"""
query_router.py

作用：
1. 根据用户自然语言问题判断分析意图 intent。
2. 判断是否可以优先使用 mv_* 预聚合表。
3. 返回结构化路由结果，供 data_analysis_agent.py 生成 SQL。

注意：
这里先用“规则匹配”的方式实现，适合课程项目展示：
- 稳定
- 可解释
- 不依赖大模型
- 能体现“优先使用预聚合视图，无法覆盖时回退原始表”
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RouteDecision:
    """一次路由判断的结果。"""

    intent: str
    use_pre_aggregate: bool
    target_table: str | None
    time_grain: str | None
    dimensions: list[str]
    metrics: list[str]
    filters: dict[str, Any]
    fallback_tables: list[str]
    reason: str


def extract_year(question: str) -> int | None:
    """
    从问题中提取年份。

    例子：
    - “2017年GMV是多少？” -> 2017
    - “看一下2018年的支付方式” -> 2018
    """
    match = re.search(r"(20\d{2})\s*年?", question)
    if match:
        return int(match.group(1))
    return None


def detect_intent(question: str) -> str:
    """
    判断用户问题属于哪种分析意图。

    这里先覆盖老师要求的典型问题：
    1. GMV
    2. 按月/各州趋势
    3. 准时交付率
    4. 延迟最严重州
    5. 支付方式偏好
    6. 平均分期数
    """
    q = question.lower()

    if any(word in question for word in ["GMV", "销售额", "成交额", "交易额"]):
        if any(word in question for word in ["州", "省", "地区", "区域", "排名"]):
            return "state_sales_trend"
        return "gmv"

    if any(word in question for word in ["按月", "月度", "趋势"]) and any(
        word in question for word in ["州", "省", "地区", "区域", "排名"]
    ):
        return "state_sales_trend"

    if any(word in question for word in ["准时", "按时", "准时交付", "准时送达"]):
        return "on_time_delivery_rate"

    if any(word in question for word in ["延迟", "延期", "最慢", "最严重"]):
        return "delivery_delay"

    if any(word in question for word in ["支付方式", "付款方式", "最受欢迎", "popular"]):
        return "payment_method_popularity"

    if any(word in question for word in ["分期", "平均分期", "installment"]):
        return "avg_installments"

    return "general_analysis"


def route_question(question: str) -> dict[str, Any]:
    """
    对用户问题进行路由。

    返回 dict 是为了后面方便传给 LangGraph state。
    """
    year = extract_year(question)
    intent = detect_intent(question)

    filters: dict[str, Any] = {}
    if year:
        filters["year"] = year

    if intent == "gmv":
        decision = RouteDecision(
            intent=intent,
            use_pre_aggregate=True,
            target_table="mv_monthly_sales",
            time_grain="year" if year else "month",
            dimensions=["year_month"],
            metrics=["total_gmv", "total_orders", "avg_basket", "total_freight"],
            filters=filters,
            fallback_tables=["orders", "order_items"],
            reason="GMV 可由 mv_monthly_sales 的月度 total_gmv 汇总得到，优先使用预聚合表。",
        )

    elif intent == "state_sales_trend":
        decision = RouteDecision(
            intent=intent,
            use_pre_aggregate=True,
            target_table="mv_state_sales",
            time_grain="month",
            dimensions=["year_month", "customer_state"],
            metrics=["total_gmv", "total_orders", "unique_customers"],
            filters=filters,
            fallback_tables=["orders", "order_items", "customers"],
            reason="按月、按州的销售趋势和排名可直接使用 mv_state_sales。",
        )

    elif intent == "on_time_delivery_rate":
        decision = RouteDecision(
            intent=intent,
            use_pre_aggregate=True,
            target_table="mv_delivery_perf",
            time_grain="month",
            dimensions=["year_month", "customer_state"],
            metrics=["on_time_rate", "avg_delivery_days", "delayed_orders"],
            filters=filters,
            fallback_tables=["orders", "customers"],
            reason="准时交付率已在 mv_delivery_perf 中按月份和州预聚合。",
        )

    elif intent == "delivery_delay":
        decision = RouteDecision(
            intent=intent,
            use_pre_aggregate=True,
            target_table="mv_delivery_perf",
            time_grain="month",
            dimensions=["year_month", "customer_state"],
            metrics=["delayed_orders", "avg_delivery_days", "on_time_rate"],
            filters=filters,
            fallback_tables=["orders", "customers"],
            reason="延迟订单数和平均配送天数已在 mv_delivery_perf 中预聚合。",
        )

    elif intent == "payment_method_popularity":
        decision = RouteDecision(
            intent=intent,
            use_pre_aggregate=True,
            target_table="mv_payment_dist",
            time_grain="month",
            dimensions=["year_month", "payment_type"],
            metrics=["total_transactions", "total_value", "avg_installments"],
            filters=filters,
            fallback_tables=["payments", "orders"],
            reason="支付方式交易次数和支付金额已在 mv_payment_dist 中按月、支付方式预聚合。",
        )

    elif intent == "avg_installments":
        decision = RouteDecision(
            intent=intent,
            use_pre_aggregate=True,
            target_table="mv_payment_dist",
            time_grain="month",
            dimensions=["year_month", "payment_type"],
            metrics=["avg_installments", "total_transactions"],
            filters=filters,
            fallback_tables=["payments", "orders"],
            reason="平均分期数可由 mv_payment_dist 的 avg_installments 和 total_transactions 计算。",
        )

    else:
        decision = RouteDecision(
            intent=intent,
            use_pre_aggregate=False,
            target_table=None,
            time_grain=None,
            dimensions=[],
            metrics=[],
            filters=filters,
            fallback_tables=[
                "orders",
                "order_items",
                "customers",
                "payments",
                "products",
                "sellers",
                "order_reviews",
            ],
            reason="未命中已知预聚合分析场景，需要回退到原始表或交给 LLM 生成 SQL。",
        )

    return asdict(decision)


if __name__ == "__main__":
    test_questions = [
        "2017年GMV是多少？",
        "按月和各州排名的趋势怎样？",
        "平台整体准时交付率是多少？",
        "哪些州延迟最严重？",
        "哪种支付方式最受欢迎？",
        "平均分期数是多少？",
        "评价分数最低的卖家有哪些？",
    ]

    for q in test_questions:
        print("=" * 80)
        print("问题：", q)
        print(route_question(q))
