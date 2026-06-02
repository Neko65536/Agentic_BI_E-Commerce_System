"""
Deterministic sales forecasting utilities for member C.

The first project version keeps forecasting lightweight and explainable:
- prefer monthly GMV rows from mv_monthly_sales;
- convert monthly GMV into weekly scale;
- fit a simple linear trend on the latest months;
- output the next 6 weekly values with a basic uncertainty band.
"""

from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.data_analysis_agent import dataframe_to_rows, execute_sql


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _extract_monthly_series(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return sorted monthly rows containing year_month and total_gmv."""
    if not rows:
        return []

    series: list[dict[str, Any]] = []
    for row in rows:
        year_month = row.get("year_month") or row.get("`year_month`")
        total_gmv = _to_float(row.get("total_gmv"))
        if year_month and total_gmv is not None:
            series.append({"year_month": str(year_month), "total_gmv": total_gmv})

    return sorted(series, key=lambda item: item["year_month"])


def load_monthly_sales() -> list[dict[str, Any]]:
    """Load the canonical monthly GMV series from the pre-aggregated table."""
    sql = """
    SELECT `year_month`, total_gmv
    FROM mv_monthly_sales
    ORDER BY `year_month`;
    """
    return dataframe_to_rows(execute_sql(sql))


def _linear_trend(values: list[float]) -> tuple[float, float]:
    """Return intercept and slope for y=a+b*x."""
    n = len(values)
    if n == 1:
        return values[0], 0.0

    xs = list(range(n))
    x_mean = mean(xs)
    y_mean = mean(values)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return y_mean, 0.0

    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denom
    intercept = y_mean - slope * x_mean
    return intercept, slope


def _month_after(year_month: str) -> date:
    year_text, month_text = year_month.split("-", 1)
    year = int(year_text)
    month = int(month_text)
    if month == 12:
        return date(year + 1, 1, 1)
    return date(year, month + 1, 1)


def _next_week_labels(periods: int, last_year_month: str) -> list[str]:
    start = _month_after(last_year_month)
    return [(start + timedelta(days=7 * i)).isoformat() for i in range(periods)]


def run_forecast_model(
    question: str,
    source_rows: list[dict[str, Any]] | None = None,
    periods: int = 6,
) -> dict[str, Any]:
    """
    Produce a 6-week GMV forecast.

    source_rows is optional because DataAnalysisAgent may have queried a
    different view. If no usable monthly series is present, the function loads
    mv_monthly_sales directly.
    """
    series = _extract_monthly_series(source_rows)
    source = "data_analysis_rows"
    if len(series) < 4:
        series = _extract_monthly_series(load_monthly_sales())
        source = "mv_monthly_sales"

    if len(series) < 2:
        return {
            "forecast_period": f"未来{periods}周",
            "source": source,
            "history_points": len(series),
            "forecast_values": [],
            "confidence_interval": [],
            "trend_summary": "历史月度GMV数据不足，无法生成稳定预测。",
        }

    recent = series[-min(len(series), 12):]
    monthly_values = [_to_float(item["total_gmv"]) or 0.0 for item in recent]
    weekly_values = [value / 4.345 for value in monthly_values]

    intercept, slope = _linear_trend(weekly_values)
    residuals = [
        weekly_values[i] - (intercept + slope * i)
        for i in range(len(weekly_values))
    ]
    residual_std = math.sqrt(mean([r * r for r in residuals])) if residuals else 0.0

    labels = _next_week_labels(periods, recent[-1]["year_month"])
    forecasts: list[dict[str, Any]] = []
    intervals: list[dict[str, Any]] = []
    start_x = len(weekly_values)
    for i, label in enumerate(labels):
        predicted = max(0.0, intercept + slope * (start_x + i))
        lower = max(0.0, predicted - 1.96 * residual_std)
        upper = predicted + 1.96 * residual_std
        forecasts.append({
            "week_start": label,
            "predicted_gmv": round(predicted, 2),
        })
        intervals.append({
            "week_start": label,
            "lower": round(lower, 2),
            "upper": round(upper, 2),
        })

    direction = "上升" if slope > 0 else "下降" if slope < 0 else "平稳"
    trend_summary = (
        f"基于最近{len(recent)}个月GMV折算周度序列，简单线性趋势显示未来{periods}周GMV整体{direction}。"
        f"该结果适合课程演示和运营参考，正式业务预测仍需加入节假日、促销和品类结构变量。"
    )

    return {
        "forecast_period": f"未来{periods}周",
        "source": source,
        "history_points": len(series),
        "history_tail": recent[-6:],
        "forecast_values": forecasts,
        "confidence_interval": intervals,
        "trend_summary": trend_summary,
    }
