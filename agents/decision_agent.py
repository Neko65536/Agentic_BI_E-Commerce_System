"""DecisionIntelligenceAgent for member C."""

from __future__ import annotations

import json
from typing import Any

from agents.llm_client import LLMClient, LLMClientError


def _contains(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _recommendation(priority: str, action: str, evidence: str, expected_impact: str) -> dict[str, str]:
    return {
        "priority": priority,
        "action": action,
        "evidence": evidence,
        "expected_impact": expected_impact,
    }


def _topic_recommendation(topic: dict[str, Any]) -> dict[str, str] | None:
    name = str(topic.get("topic") or "")
    meaning = str(topic.get("business_meaning") or name)
    count = str(topic.get("count") or 0)
    if name == "delivery_delay":
        return _recommendation(
            "P0",
            "针对配送延迟主题建立州级和卖家级SLA看板，对超时线路设置承诺时效修正和承运商复盘机制。",
            f"NLP差评主题识别：{meaning}，命中次数{count}。",
            "降低延迟差评，提升准时率和复购体验。",
        )
    if name == "product_quality":
        return _recommendation(
            "P0",
            "对质量问题高发品类抽检商品描述、包装和售后记录，暂停连续低分SKU的活动流量。",
            f"NLP差评主题识别：{meaning}，命中次数{count}。",
            "减少质量型退款和低分评价。",
        )
    if name == "wrong_or_missing_item":
        return _recommendation(
            "P1",
            "对错发漏发相关卖家增加出库校验，要求高风险卖家提供拣货复核凭证。",
            f"NLP差评主题识别：{meaning}，命中次数{count}。",
            "降低错发漏发导致的客服工单和退货。",
        )
    if name == "customer_service":
        return _recommendation(
            "P1",
            "为高差评卖家设置售后响应时限，并将客服响应质量纳入卖家绩效评分。",
            f"NLP差评主题识别：{meaning}，命中次数{count}。",
            "缩短问题闭环时间，减少二次差评。",
        )
    if name == "refund_or_cancellation":
        return _recommendation(
            "P1",
            "复核退款和取消流程，针对高争议订单增加自动提醒和赔付规则说明。",
            f"NLP差评主题识别：{meaning}，命中次数{count}。",
            "降低支付争议和售后摩擦。",
        )
    return None


def _build_strategy_tiers(recommendations: list[dict[str, str]]) -> dict[str, list[str]]:
    p0 = [item["action"] for item in recommendations if item["priority"] == "P0"]
    p1 = [item["action"] for item in recommendations if item["priority"] == "P1"]
    p2 = [item["action"] for item in recommendations if item["priority"] == "P2"]
    return {
        "next_7_days": p0[:3] or p1[:1] or p2[:1],
        "next_30_days": p1[:3] or p0[:2] or p2[:1],
        "next_90_days": [
            "将GMV、准时率、差评率、低分卖家数纳入固定经营周报。",
            "沉淀预聚合视图和Agent问答截图，用于期末报告和答辩演示。",
        ],
    }


def _compact_json(value: Any, limit: int = 7000) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _build_llm_evidence(
    payload: dict[str, Any],
    visualization_result: dict[str, Any] | None,
    forecast_result: dict[str, Any] | None,
    nlp_result: dict[str, Any] | None,
    what_if_result: dict[str, Any] | None,
    draft_recommendations: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "question": payload.get("question"),
        "analysis_type": payload.get("analysis_type"),
        "intent": payload.get("intent"),
        "summary": payload.get("summary"),
        "view_name": payload.get("view_name"),
        "used_view": payload.get("used_view"),
        "key_findings": payload.get("key_findings"),
        "sql": payload.get("sql"),
        "forecast_result": forecast_result,
        "nlp_result": nlp_result,
        "what_if_result": what_if_result,
        "visualization_charts": (visualization_result or {}).get("charts"),
        "draft_recommendations": draft_recommendations,
    }


def _normalize_llm_recommendations(raw: dict[str, Any]) -> list[dict[str, str]]:
    items = raw.get("recommendations")
    if not isinstance(items, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip()
        if not action:
            continue
        priority = str(item.get("priority") or "P1").strip().upper()
        if priority not in {"P0", "P1", "P2"}:
            priority = "P1"
        normalized.append({
            "priority": priority,
            "action": action,
            "evidence": str(item.get("evidence") or ""),
            "expected_impact": str(item.get("expected_impact") or item.get("impact") or ""),
        })
    return normalized[:6]


def _normalize_strategy_tiers(
    raw: dict[str, Any],
    recommendations: list[dict[str, str]],
) -> dict[str, list[str]]:
    tiers = raw.get("strategy_tiers")
    if not isinstance(tiers, dict):
        return _build_strategy_tiers(recommendations)

    normalized: dict[str, list[str]] = {}
    for key in ("next_7_days", "next_30_days", "next_90_days"):
        value = tiers.get(key)
        if isinstance(value, list):
            normalized[key] = [str(item) for item in value if str(item).strip()][:4]
        elif isinstance(value, str) and value.strip():
            normalized[key] = [value.strip()]
        else:
            normalized[key] = []

    fallback = _build_strategy_tiers(recommendations)
    for key, value in fallback.items():
        if not normalized[key]:
            normalized[key] = value
    return normalized


def _normalize_what_if_answer(
    raw: Any,
    fallback: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Keep structured what-if metrics when LLM returns text or partial JSON."""
    if isinstance(raw, dict):
        merged = dict(fallback or {})
        merged.update({k: v for k, v in raw.items() if v is not None})
        return merged or None

    if isinstance(raw, str) and raw.strip():
        if fallback:
            merged = dict(fallback)
            merged["llm_summary"] = raw.strip()
            return merged
        return {"summary": raw.strip()}

    return fallback


def _generate_llm_strategy(
    payload: dict[str, Any],
    visualization_result: dict[str, Any] | None,
    forecast_result: dict[str, Any] | None,
    nlp_result: dict[str, Any] | None,
    what_if_result: dict[str, Any] | None,
    draft_recommendations: list[dict[str, str]],
) -> dict[str, Any]:
    evidence = _build_llm_evidence(
        payload,
        visualization_result,
        forecast_result,
        nlp_result,
        what_if_result,
        draft_recommendations,
    )

    system_prompt = """
你是Agentic BI系统中的规范性决策Agent。你的任务是基于已给出的SQL查询结果、预测结果、评论NLP结果和What-if结果，生成可执行的运营决策建议。

要求：
1.只能使用输入证据，不要编造不存在的指标或表。
2.建议必须具体到运营动作，例如物流线路、卖家治理、品类质检、支付体验、库存/客服排班。
3.如果输入包含forecast_result，需要把未来6周趋势转化为容量、库存或履约建议。
4.如果输入包含nlp_result，需要把情感/主题结果融入差评原因和改进方案。
5.如果输入包含what_if_result，需要解释模拟假设、预期提升和落地风险。
6.输出必须是合法JSON，不要Markdown。

JSON格式：
{
  "business_problem": "一句话概括业务问题",
  "recommendations": [
    {"priority": "P0/P1/P2", "action": "具体行动", "evidence": "数据证据", "expected_impact": "预期影响"}
  ],
  "strategy_tiers": {
    "next_7_days": ["7天内动作"],
    "next_30_days": ["30天内动作"],
    "next_90_days": ["90天内动作"]
  },
  "what_if_answer": null,
  "priority": "P0/P1/P2",
  "expected_impact": "总体预期影响"
}
""".strip()
    user_prompt = f"请基于以下证据生成规范性决策建议：\n{_compact_json(evidence)}"
    raw = LLMClient().chat_json([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    recommendations = _normalize_llm_recommendations(raw)
    if not recommendations:
        raise LLMClientError("DecisionAgent LLM未返回有效recommendations")

    return {
        "business_problem": str(raw.get("business_problem") or payload.get("question") or payload.get("intent") or "平台经营分析"),
        "recommendations": recommendations,
        "strategy_tiers": _normalize_strategy_tiers(raw, recommendations),
        "what_if_answer": raw.get("what_if_answer"),
        "priority": str(raw.get("priority") or recommendations[0]["priority"]),
        "expected_impact": str(raw.get("expected_impact") or recommendations[0]["expected_impact"]),
    }


def run_decision_agent(
    payload: dict[str, Any],
    visualization_result: dict[str, Any] | None = None,
    forecast_result: dict[str, Any] | None = None,
    nlp_result: dict[str, Any] | None = None,
    what_if_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    question = str(payload.get("question") or "")
    intent = str(payload.get("intent") or "")
    summary = str(payload.get("summary") or "")
    view_name = str(payload.get("view_name") or "")
    analysis_type = str(payload.get("analysis_type") or "")
    evidence_base = summary or "基于数据分析Agent返回的查询结果。"

    is_what_if_q = bool(what_if_result) or _contains(
        question + intent,
        ["what-if", "whatif", "如果", "假如", "下架", "整改", "提升多少", "模拟"],
    )

    recommendations: list[dict[str, str]] = []

    if what_if_result:
        lift = what_if_result.get("estimated_lift")
        baseline = what_if_result.get("baseline_avg_score")
        simulated = what_if_result.get("simulated_avg_score")
        recommendations.append(_recommendation(
            "P0",
            f"优先整改或下架Top高差评卖家：平台均分预计从{baseline}提升至{simulated}（+{lift}分）。",
            str(what_if_result.get("insight", "")),
            f"受影响评论{what_if_result.get('affected_reviews')}条，适合作为高优先级运营实验。",
        ))
        recommendations.append(_recommendation(
            "P1",
            "对模拟识别出的高差评卖家分批整改，并跟踪整改前后评分与差评率变化。",
            f"被干预卖家评论均分{what_if_result.get('affected_avg_score')}，明显低于平台均值。",
            "验证模拟结论，并控制GMV与供给替代风险。",
        ))

    if not is_what_if_q:
        if view_name == "mv_delivery_perf" or _contains(question + intent, ["配送", "延迟", "准时", "delivery"]):
            recommendations.append(_recommendation(
                "P0",
                "优先治理延迟订单集中的州，拆分为干线运输、末端派送和承诺时效三类问题分别跟踪。",
                evidence_base,
                "提升准时率，降低差评和退款风险。",
            ))

        if view_name == "mv_seller_perf" or _contains(question + intent, ["卖家", "差评", "评分", "review"]):
            recommendations.append(_recommendation(
                "P0",
                "建立低评分卖家观察名单，对连续低分且订单量较高的卖家触发整改或流量降权。",
                evidence_base,
                "减少高风险卖家对整体口碑的拖累。",
            ))

        if view_name == "mv_category_sales" or _contains(question + intent, ["品类", "category"]):
            recommendations.append(_recommendation(
                "P1",
                "对高GMV品类做库存和物流优先保障，对下滑品类检查价格、评价和配送体验。",
                evidence_base,
                "稳定核心收入，同时识别品类增长机会。",
            ))

        if view_name == "mv_payment_dist" or _contains(question + intent, ["支付", "分期", "payment"]):
            recommendations.append(_recommendation(
                "P1",
                "围绕主流支付方式优化结算体验，并监控高分期订单的坏账或取消风险。",
                evidence_base,
                "提升支付转化率和资金周转稳定性。",
            ))

        if forecast_result and forecast_result.get("forecast_values"):
            recommendations.append(_recommendation(
                "P1",
                "根据未来6周GMV预测提前调整客服、仓储和物流容量。",
                str(forecast_result.get("trend_summary", "")),
                "降低销售波动期间的履约压力。",
            ))

        if nlp_result and nlp_result.get("negative_rate") is not None:
            recommendations.append(_recommendation(
                "P1",
                "将差评关键词纳入运营周报，针对高频问题制定卖家培训和物流整改清单。",
                str(nlp_result.get("insight", "")),
                "把非结构化评论转化为可追踪的服务质量指标。",
            ))
            for topic in (nlp_result.get("topic_summary") or [])[:3]:
                topic_item = _topic_recommendation(topic)
                if topic_item:
                    recommendations.append(topic_item)

    if not recommendations:
        recommendations.append(_recommendation(
            "P2",
            "继续使用预聚合视图监控GMV、订单量、客单价和区域结构，发现异常后再下钻原始表。",
            evidence_base,
            "保持分析响应速度，并减少无目标的多表JOIN成本。",
        ))

    what_if_answer = None
    if what_if_result:
        what_if_answer = {
            "scenario": what_if_result.get("scenario"),
            "assumption": "、".join(what_if_result.get("assumptions") or []),
            "baseline_avg_score": what_if_result.get("baseline_avg_score"),
            "simulated_avg_score": what_if_result.get("simulated_avg_score"),
            "estimated_lift": what_if_result.get("estimated_lift"),
            "affected_reviews": what_if_result.get("affected_reviews"),
            "evidence": what_if_result.get("insight"),
        }
    elif _contains(question + intent, ["what-if", "如果", "下架", "top20", "top 20"]):
        negative_rate = nlp_result.get("negative_rate") if nlp_result else None
        what_if_answer = {
            "scenario": "下架或整改Top高差评卖家/商品",
            "assumption": "优先处理负面评价集中对象，短期不改变整体需求结构。",
            "expected_direction": "整体评分预计改善，差评率预计下降；实际提升幅度需要基于被处理对象订单占比进一步测算。",
            "evidence": f"当前负面评论占比={negative_rate}" if negative_rate is not None else evidence_base,
        }

    llm_generated = False
    llm_error = None
    business_problem = question or intent or "平台经营分析"
    strategy_tiers = _build_strategy_tiers(recommendations)
    priority = recommendations[0]["priority"]
    expected_impact = recommendations[0]["expected_impact"]

    try:
        llm_strategy = _generate_llm_strategy(
            payload=payload,
            visualization_result=visualization_result,
            forecast_result=forecast_result,
            nlp_result=nlp_result,
            what_if_result=what_if_result,
            draft_recommendations=recommendations,
        )
        recommendations = llm_strategy["recommendations"]
        strategy_tiers = llm_strategy["strategy_tiers"]
        business_problem = llm_strategy["business_problem"]
        llm_what_if = llm_strategy.get("what_if_answer")
        if llm_what_if is not None:
            what_if_answer = _normalize_what_if_answer(llm_what_if, what_if_answer)
        priority = llm_strategy["priority"]
        expected_impact = llm_strategy["expected_impact"]
        llm_generated = True
    except Exception as exc:
        llm_error = str(exc)

    return {
        "agent": "decision_agent",
        "business_problem": business_problem,
        "analysis_type": analysis_type,
        "recommendations": recommendations,
        "strategy_tiers": strategy_tiers,
        "what_if_answer": what_if_answer,
        "priority": priority,
        "expected_impact": expected_impact,
        "llm_generated": llm_generated,
        "llm_error": llm_error,
        "evidence": {
            "summary": summary,
            "view_name": view_name,
            "visualization": visualization_result,
            "forecast_available": bool(forecast_result and forecast_result.get("forecast_values")),
            "nlp_available": bool(nlp_result),
            "what_if_available": bool(what_if_result),
        },
    }
