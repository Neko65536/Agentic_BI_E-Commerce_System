"""What-if simulation model for seller quality intervention."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.data_analysis_agent import dataframe_to_rows, execute_sql


def simulate_top_negative_seller_intervention(top_n: int = 20) -> dict[str, Any]:
    """
    Estimate score lift if top high-negative-review sellers are delisted or fixed.

    Simulation rule:
    - identify sellers with the highest negative review counts and low average score;
    - compute baseline platform average review score;
    - compute simulated average after excluding those sellers' affected reviews;
    - return lift and affected seller list.
    """
    sql = """
    WITH seller_review AS (
      SELECT
        oi.seller_id,
        COUNT(DISTINCT r.review_id) AS review_count,
        AVG(r.review_score) AS avg_review_score,
        SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS negative_reviews
      FROM order_items oi
      JOIN order_reviews r ON r.order_id = oi.order_id
      GROUP BY oi.seller_id
      HAVING review_count >= 5
    ),
    top_sellers AS (
      SELECT seller_id, review_count, avg_review_score, negative_reviews
      FROM seller_review
      ORDER BY negative_reviews DESC, avg_review_score ASC
      LIMIT :top_n
    ),
    affected_reviews AS (
      SELECT DISTINCT r.review_id, r.review_score
      FROM top_sellers ts
      JOIN order_items oi ON oi.seller_id = ts.seller_id
      JOIN order_reviews r ON r.order_id = oi.order_id
    ),
    baseline AS (
      SELECT COUNT(*) AS total_reviews, SUM(review_score) AS total_score, AVG(review_score) AS avg_score
      FROM order_reviews
    ),
    affected AS (
      SELECT COUNT(*) AS affected_reviews, SUM(review_score) AS affected_score, AVG(review_score) AS affected_avg_score
      FROM affected_reviews
    )
    SELECT
      b.total_reviews,
      b.avg_score AS baseline_avg_score,
      a.affected_reviews,
      a.affected_avg_score,
      (b.total_reviews - a.affected_reviews) AS remaining_reviews,
      (b.total_score - a.affected_score) / NULLIF((b.total_reviews - a.affected_reviews), 0) AS simulated_avg_score
    FROM baseline b
    CROSS JOIN affected a;
    """
    summary_rows = dataframe_to_rows(execute_sql(sql, {"top_n": top_n}))
    summary = summary_rows[0] if summary_rows else {}

    sellers_sql = """
    SELECT
      oi.seller_id,
      COUNT(DISTINCT r.review_id) AS review_count,
      ROUND(AVG(r.review_score), 4) AS avg_review_score,
      SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS negative_reviews
    FROM order_items oi
    JOIN order_reviews r ON r.order_id = oi.order_id
    GROUP BY oi.seller_id
    HAVING review_count >= 5
    ORDER BY negative_reviews DESC, avg_review_score ASC
    LIMIT :top_n;
    """
    affected_sellers = dataframe_to_rows(execute_sql(sellers_sql, {"top_n": top_n}))

    baseline_avg = float(summary.get("baseline_avg_score") or 0)
    simulated_avg = float(summary.get("simulated_avg_score") or baseline_avg)
    lift = simulated_avg - baseline_avg

    return {
        "scenario": f"整改或下架Top{top_n}高差评卖家",
        "baseline_avg_score": round(baseline_avg, 4),
        "simulated_avg_score": round(simulated_avg, 4),
        "estimated_lift": round(lift, 4),
        "affected_reviews": int(summary.get("affected_reviews") or 0),
        "remaining_reviews": int(summary.get("remaining_reviews") or 0),
        "affected_avg_score": round(float(summary.get("affected_avg_score") or 0), 4),
        "affected_sellers": affected_sellers,
        "chart_data": [
            {"scenario": "baseline", "avg_review_score": round(baseline_avg, 4)},
            {"scenario": "after_intervention", "avg_review_score": round(simulated_avg, 4)},
            {"scenario": "affected_sellers", "avg_review_score": round(float(summary.get("affected_avg_score") or 0), 4)},
        ],
        "assumptions": [
            "该模拟基于历史评论评分，不代表真实因果实验。",
            "Top高差评卖家的历史评论被视为可整改或可替换订单体验。",
            "模拟结果用于运营优先级判断，正式决策需结合卖家GMV和品类供给替代性。",
        ],
        "insight": (
            f"若优先整改或下架Top{top_n}高差评卖家，平台平均评分预计从"
            f"{baseline_avg:.4f}提升到{simulated_avg:.4f}，提升约{lift:.4f}分。"
        ),
    }

