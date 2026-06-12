"""
Sales forecasting utilities for the predictive analysis workflow.

The model intentionally stays dependency-light for course deployment:
- load the canonical monthly GMV sequence from mv_monthly_sales;
- remove startup months and the final incomplete month when detected;
- fit Holt linear exponential smoothing on monthly GMV;
- convert monthly forecasts to the next 6 weekly GMV values with intervals.
"""

from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median
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


def _month_date(year_month: str) -> date:
    year_text, month_text = year_month.split("-", 1)
    return date(int(year_text), int(month_text), 1)


def _add_months(month_start: date, months: int) -> date:
    month_index = month_start.year * 12 + month_start.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def _extract_monthly_series(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return sorted one-row-per-month GMV records."""
    if not rows:
        return []

    scoped_rows: dict[str, dict[str, Any]] = {}
    fallback_totals: dict[str, float] = {}
    for row in rows:
        year_month = row.get("year_month") or row.get("`year_month`")
        total_gmv = _to_float(row.get("total_gmv"))
        if not year_month or total_gmv is None:
            continue

        year_month_text = str(year_month)
        if not len(year_month_text) >= 7 or year_month_text.upper().endswith("TOTAL"):
            continue

        try:
            _month_date(year_month_text[:7])
        except ValueError:
            continue

        customer_state = row.get("customer_state")
        if customer_state in (None, "", "None"):
            scoped_rows[year_month_text[:7]] = {
                "year_month": year_month_text[:7],
                "total_gmv": total_gmv,
            }
        else:
            fallback_totals[year_month_text[:7]] = fallback_totals.get(year_month_text[:7], 0.0) + total_gmv

    if scoped_rows:
        series = list(scoped_rows.values())
    else:
        series = [
            {"year_month": year_month, "total_gmv": total_gmv}
            for year_month, total_gmv in fallback_totals.items()
        ]

    return sorted(series, key=lambda item: item["year_month"])


def load_monthly_sales() -> list[dict[str, Any]]:
    """Load the canonical monthly GMV series from the pre-aggregated view."""
    sql = """
    SELECT `year_month`, total_gmv
    FROM mv_monthly_sales
    ORDER BY `year_month`;
    """
    return dataframe_to_rows(execute_sql(sql))


def _prepare_model_series(series: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Trim obvious startup and incomplete-month outliers before modeling."""
    prepared = [dict(item) for item in series]
    adjustments: list[str] = []

    values = [_to_float(item.get("total_gmv")) or 0.0 for item in prepared]
    if len(values) >= 12:
        tail_reference = median(values[-12:])
        startup_threshold = max(1000.0, tail_reference * 0.10)
        removed = 0
        while len(prepared) > 12 and (_to_float(prepared[0].get("total_gmv")) or 0.0) < startup_threshold:
            prepared.pop(0)
            removed += 1
        if removed:
            adjustments.append(f"剔除开头{removed}个低GMV启动月份")

    values = [_to_float(item.get("total_gmv")) or 0.0 for item in prepared]
    if len(values) >= 8:
        recent_reference = median(values[-7:-1])
        last_value = values[-1]
        if recent_reference > 0 and last_value < recent_reference * 0.45:
            removed_month = prepared.pop()["year_month"]
            adjustments.append(f"剔除结尾不完整月份{removed_month}")

    return prepared, adjustments


def _rmse(actual: list[float], fitted: list[float]) -> float:
    if not actual or not fitted:
        return 0.0
    pairs = list(zip(actual, fitted))
    return math.sqrt(mean([(a - f) ** 2 for a, f in pairs]))


def _holt_linear(
    values: list[float],
    periods: int,
    alpha: float,
    beta: float,
) -> tuple[list[float], list[float], float, float]:
    """Return fitted values, future monthly forecasts, level, and trend."""
    if not values:
        return [], [], 0.0, 0.0
    if len(values) == 1:
        return [values[0]], [values[0]] * periods, values[0], 0.0

    level = values[0]
    trend = values[1] - values[0]
    fitted = [values[0]]

    for actual in values[1:]:
        forecast = level + trend
        fitted.append(max(0.0, forecast))
        previous_level = level
        level = alpha * actual + (1.0 - alpha) * forecast
        trend = beta * (level - previous_level) + (1.0 - beta) * trend

    future = [max(0.0, level + (step + 1) * trend) for step in range(periods)]
    return fitted, future, level, trend


def _best_holt_linear(values: list[float], periods: int) -> dict[str, Any]:
    """Small grid search keeps the model deterministic and explainable."""
    best: dict[str, Any] | None = None
    for alpha in (0.2, 0.35, 0.5, 0.65, 0.8):
        for beta in (0.05, 0.15, 0.25, 0.35):
            fitted, future, level, trend = _holt_linear(values, periods, alpha, beta)
            score = _rmse(values[1:], fitted[1:]) if len(values) > 1 else 0.0
            candidate = {
                "alpha": alpha,
                "beta": beta,
                "fitted": fitted,
                "future": future,
                "level": level,
                "trend": trend,
                "rmse": score,
            }
            if best is None or score < best["rmse"]:
                best = candidate
    return best or {
        "alpha": 0.5,
        "beta": 0.15,
        "fitted": values,
        "future": values[-1:] * periods,
        "level": values[-1] if values else 0.0,
        "trend": 0.0,
        "rmse": 0.0,
    }


def _month_index_for_week(first_forecast_month: date, week_start: date) -> int:
    return (week_start.year - first_forecast_month.year) * 12 + week_start.month - first_forecast_month.month


def run_forecast_model(
    question: str,
    source_rows: list[dict[str, Any]] | None = None,
    periods: int = 6,
) -> dict[str, Any]:
    """
    Produce a 6-week GMV forecast from the monthly pre-aggregated view.

    source_rows is optional because DataAnalysisAgent may have already queried
    mv_monthly_sales. If not, the model loads mv_monthly_sales directly.
    """
    raw_series = _extract_monthly_series(source_rows)
    source = "data_analysis_rows"
    if len(raw_series) < 4:
        raw_series = _extract_monthly_series(load_monthly_sales())
        source = "mv_monthly_sales"

    model_series, adjustments = _prepare_model_series(raw_series)
    if len(model_series) < 2:
        return {
            "forecast_period": f"未来{periods}周",
            "source": source,
            "model": "holt_linear_exponential_smoothing",
            "history_points": len(model_series),
            "raw_history_points": len(raw_series),
            "history_adjustments": adjustments,
            "forecast_values": [],
            "confidence_interval": [],
            "trend_summary": "历史月度GMV数据不足，无法生成稳定预测。",
        }

    monthly_values = [_to_float(item["total_gmv"]) or 0.0 for item in model_series]
    last_month = _month_date(model_series[-1]["year_month"])
    first_forecast_month = _add_months(last_month, 1)
    last_week = first_forecast_month + timedelta(days=7 * max(periods - 1, 0))
    monthly_horizon = max(1, _month_index_for_week(first_forecast_month, last_week) + 1)

    model = _best_holt_linear(monthly_values, monthly_horizon)
    fitted = model["fitted"]
    monthly_forecasts = model["future"]
    monthly_rmse = _rmse(monthly_values[1:], fitted[1:]) if len(monthly_values) > 1 else 0.0
    weekly_rmse = monthly_rmse / 4.345

    forecasts: list[dict[str, Any]] = []
    intervals: list[dict[str, Any]] = []
    for index in range(periods):
        week_start = first_forecast_month + timedelta(days=7 * index)
        month_index = _month_index_for_week(first_forecast_month, week_start)
        month_value = monthly_forecasts[min(month_index, len(monthly_forecasts) - 1)]
        predicted = max(0.0, month_value / 4.345)
        lower = max(0.0, predicted - 1.96 * weekly_rmse)
        upper = predicted + 1.96 * weekly_rmse
        label = week_start.isoformat()
        forecasts.append({
            "week_start": label,
            "predicted_gmv": round(predicted, 2),
        })
        intervals.append({
            "week_start": label,
            "lower": round(lower, 2),
            "upper": round(upper, 2),
        })

    trend = float(model["trend"])
    direction = "上升" if trend > 0 else "下降" if trend < 0 else "平稳"
    trend_summary = (
        f"基于mv_monthly_sales的{len(model_series)}个月有效历史GMV，"
        f"采用Holt线性指数平滑模型预测未来{periods}周销售额。"
        f"模型月度趋势项为{trend:.2f}，未来短期GMV整体呈{direction}趋势；"
        "区间宽度由历史拟合误差估计，用于展示预测不确定性。"
    )

    return {
        "forecast_period": f"未来{periods}周",
        "source": source,
        "model": "holt_linear_exponential_smoothing",
        "model_params": {
            "alpha": model["alpha"],
            "beta": model["beta"],
            "monthly_rmse": round(monthly_rmse, 2),
        },
        "history_points": len(model_series),
        "raw_history_points": len(raw_series),
        "history_adjustments": adjustments,
        "model_history_range": {
            "start": model_series[0]["year_month"],
            "end": model_series[-1]["year_month"],
        },
        "history_tail": model_series[-6:],
        "monthly_forecast_values": [
            {
                "year_month": _add_months(first_forecast_month, index).strftime("%Y-%m"),
                "predicted_gmv": round(value, 2),
            }
            for index, value in enumerate(monthly_forecasts)
        ],
        "forecast_values": forecasts,
        "confidence_interval": intervals,
        "trend_summary": trend_summary,
    }
