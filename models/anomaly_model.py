"""Simple anomaly detection helpers for optional extra credit."""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any


def detect_recent_anomalies(rows: list[dict[str, Any]], metric: str = "total_gmv") -> dict[str, Any]:
    values: list[float] = []
    labels: list[str] = []
    for row in rows:
        value = row.get(metric)
        label = row.get("year_month") or row.get("customer_state") or row.get("payment_type") or ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isnan(number):
            labels.append(str(label))
            values.append(number)

    if len(values) < 6:
        return {
            "metric": metric,
            "anomalies": [],
            "summary": "数据点少于6个，暂不执行异常检测。",
        }

    baseline = values[:-1]
    latest = values[-1]
    avg = mean(baseline)
    std = pstdev(baseline) or 0.0
    z_score = 0.0 if std == 0 else (latest - avg) / std
    anomalies = []
    if abs(z_score) >= 2:
        anomalies.append({
            "label": labels[-1],
            "value": latest,
            "z_score": round(z_score, 4),
            "direction": "surge" if z_score > 0 else "drop",
        })

    return {
        "metric": metric,
        "anomalies": anomalies,
        "summary": "最近一期指标存在异常波动。" if anomalies else "最近一期指标未发现显著异常波动。",
    }

