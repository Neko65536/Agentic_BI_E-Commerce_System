"""
Review sentiment and complaint mining utilities.

This module intentionally starts with a deterministic score-based sentiment
baseline. It is stable for demos and easy to explain in the report.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.data_analysis_agent import dataframe_to_rows, execute_sql


STOPWORDS = {
    "que", "com", "para", "uma", "por", "mas", "dos", "das", "foi", "sao",
    "são", "não", "nao", "meu", "minha", "muito", "muita", "mais", "esta",
    "este", "isso", "esse", "essa", "ele", "ela", "sem", "como", "produto",
    "pedido", "entrega", "recebi", "veio", "chegou", "loja", "pra", "pela",
    "pelo", "the", "and", "for", "with", "this", "that", "you", "are",
}

THEME_KEYWORDS: dict[str, set[str]] = {
    "delivery_delay": {
        "atraso", "atrasado", "demora", "demorou", "prazo", "entrega",
        "entregue", "transportadora", "correio", "correios", "chegar",
        "chegou", "recebi", "recebido", "ainda",
    },
    "product_quality": {
        "quebrado", "defeito", "defeituoso", "qualidade", "danificado",
        "ruim", "fragil", "frágil", "peca", "peça", "produto", "material",
    },
    "wrong_or_missing_item": {
        "errado", "diferente", "faltando", "incompleto", "troca", "modelo",
        "cor", "tamanho", "enviado", "veio",
    },
    "customer_service": {
        "atendimento", "resposta", "contato", "suporte", "reclamei",
        "resolver", "solução", "solucao", "email", "telefone",
    },
    "refund_or_cancellation": {
        "cancelado", "cancelamento", "reembolso", "estorno", "dinheiro",
        "devolução", "devolucao", "paguei", "pagamento",
    },
}


def _label(score: int | float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 4:
        return "positive"
    if score <= 2:
        return "negative"
    return "neutral"


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ]{3,}", text.lower())
    return [word for word in words if word not in STOPWORDS]


def _theme_counts(tokens: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    token_set = set(tokens)
    for theme, keywords in THEME_KEYWORDS.items():
        counts[theme] += len(token_set & keywords)
    return counts


def _load_review_rows(limit: int) -> list[dict[str, Any]]:
    sql = """
    SELECT
      review_score,
      COALESCE(review_comment_title, '') AS review_comment_title,
      COALESCE(review_comment_message, '') AS review_comment_message
    FROM order_reviews
    WHERE review_comment_message IS NOT NULL
      AND review_comment_message <> ''
    LIMIT :limit;
    """
    return dataframe_to_rows(execute_sql(sql, {"limit": limit}))


def _load_low_score_sellers() -> list[dict[str, Any]]:
    sql = """
    SELECT
      oi.seller_id,
      s.seller_state,
      COUNT(*) AS review_count,
      ROUND(AVG(r.review_score), 4) AS avg_review_score,
      SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS negative_reviews,
      ROUND(SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*), 4) AS negative_rate
    FROM order_reviews r
    JOIN order_items oi ON oi.order_id = r.order_id
    JOIN sellers s ON s.seller_id = oi.seller_id
    GROUP BY oi.seller_id, s.seller_state
    HAVING review_count >= 5
    ORDER BY negative_rate DESC, negative_reviews DESC, avg_review_score ASC
    LIMIT 10;
    """
    return dataframe_to_rows(execute_sql(sql))


def _load_low_score_categories() -> list[dict[str, Any]]:
    sql = """
    SELECT
      COALESCE(t.product_category_name_english, p.product_category_name, 'UNKNOWN') AS product_category_english,
      COUNT(*) AS review_count,
      ROUND(AVG(r.review_score), 4) AS avg_review_score,
      SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS negative_reviews
    FROM order_reviews r
    JOIN order_items oi ON oi.order_id = r.order_id
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN product_category_name_translation t
      ON t.product_category_name = p.product_category_name
    GROUP BY product_category_english
    HAVING review_count >= 20
    ORDER BY negative_reviews DESC, avg_review_score ASC
    LIMIT 10;
    """
    return dataframe_to_rows(execute_sql(sql))


def analyze_review_sentiment(question: str, limit: int = 5000) -> dict[str, Any]:
    rows = _load_review_rows(limit)
    counts = Counter()
    positive_words: Counter[str] = Counter()
    negative_words: Counter[str] = Counter()
    complaint_themes: Counter[str] = Counter()

    for row in rows:
        score = row.get("review_score")
        try:
            numeric_score = int(score)
        except (TypeError, ValueError):
            numeric_score = None

        label = _label(numeric_score)
        counts[label] += 1
        text = f"{row.get('review_comment_title') or ''} {row.get('review_comment_message') or ''}"
        tokens = _tokenize(text)
        if label == "positive":
            positive_words.update(tokens)
        elif label == "negative":
            negative_words.update(tokens)
            complaint_themes.update(_theme_counts(tokens))

    total = sum(counts.values())
    negative_rate = (counts["negative"] / total) if total else 0.0
    positive_rate = (counts["positive"] / total) if total else 0.0
    negative_keyword_rows = [
        {"keyword": word, "count": count}
        for word, count in negative_words.most_common(30)
    ]
    positive_keyword_rows = [
        {"keyword": word, "count": count}
        for word, count in positive_words.most_common(30)
    ]
    topic_summary = [
        {
            "topic": theme,
            "count": count,
            "business_meaning": {
                "delivery_delay": "配送延迟、承诺时效和末端履约问题",
                "product_quality": "商品质量、破损和描述不符问题",
                "wrong_or_missing_item": "错发、漏发、规格不符问题",
                "customer_service": "客服响应和售后处理问题",
                "refund_or_cancellation": "退款、取消和支付争议问题",
            }.get(theme, "其他问题"),
        }
        for theme, count in complaint_themes.most_common()
        if count > 0
    ]

    return {
        "method": "review_score_rule",
        "sample_size": total,
        "sentiment_counts": {
            "positive": counts["positive"],
            "neutral": counts["neutral"],
            "negative": counts["negative"],
        },
        "positive_rate": round(positive_rate, 4),
        "negative_rate": round(negative_rate, 4),
        "positive_keywords": positive_words.most_common(15),
        "negative_keywords": negative_words.most_common(15),
        "positive_keyword_rows": positive_keyword_rows,
        "negative_keyword_rows": negative_keyword_rows,
        "topic_summary": topic_summary,
        "wordcloud_data": negative_keyword_rows,
        "low_score_sellers": _load_low_score_sellers(),
        "low_score_categories": _load_low_score_categories(),
        "insight": (
            f"按评分规则识别评论情感，样本{total}条，负面评论占比约{negative_rate:.2%}。"
            "差评关键词、主题归因和低评分卖家/品类可作为诊断分析与决策建议输入。"
        ),
    }
