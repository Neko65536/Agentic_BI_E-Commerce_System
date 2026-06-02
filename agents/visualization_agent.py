"""VisualizationAgent for member C.

The agent generates self-contained HTML/SVG artifacts without relying on a
frontend framework. It covers the six chart families required by the course:
line, geographic bubble map, bar, matrix heatmap, scatter/bubble, and word
cloud/topic visualization.
"""

from __future__ import annotations

import html
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "outputs" / "charts"


STATE_COORDS: dict[str, tuple[float, float]] = {
    "AC": (-70.0, -9.0), "AL": (-36.6, -9.6), "AM": (-63.0, -4.5),
    "AP": (-51.8, 1.4), "BA": (-41.7, -12.6), "CE": (-39.6, -5.2),
    "DF": (-47.9, -15.8), "ES": (-40.3, -19.6), "GO": (-49.8, -16.0),
    "MA": (-45.0, -5.0), "MG": (-44.5, -18.5), "MS": (-54.5, -20.5),
    "MT": (-56.0, -13.0), "PA": (-52.0, -3.8), "PB": (-36.8, -7.1),
    "PE": (-37.8, -8.4), "PI": (-42.8, -7.5), "PR": (-51.5, -24.7),
    "RJ": (-43.2, -22.3), "RN": (-36.5, -5.8), "RO": (-63.0, -11.0),
    "RR": (-61.4, 2.0), "RS": (-53.2, -30.0), "SC": (-50.0, -27.2),
    "SE": (-37.4, -10.6), "SP": (-48.0, -22.2), "TO": (-48.3, -10.2),
}


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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


def _safe_filename(text: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_\-]+", "_", text).strip("_")
    return (slug or "chart")[:70]


def _format_value(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return str(value)
    if abs(number) >= 1000:
        return f"{number:,.2f}"
    return f"{number:.4g}"


def _numeric_fields(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    fields: list[str] = []
    for key in rows[0]:
        if any(_to_float(row.get(key)) is not None for row in rows):
            fields.append(key)
    return fields


def _label_fields(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    numeric = set(_numeric_fields(rows))
    return [key for key in rows[0] if key not in numeric]


def _pick_metric(rows: list[dict[str, Any]]) -> str | None:
    preferred = [
        "total_gmv", "gmv_total", "total_orders", "total_transactions", "total_value",
        "avg_basket", "avg_delivery_days", "on_time_rate", "delayed_orders",
        "avg_review_score", "avg_rating", "negative_reviews", "review_count",
        "predicted_gmv", "freight_value", "price", "count",
    ]
    numeric = _numeric_fields(rows)
    for key in preferred:
        if key in numeric:
            return key
    return numeric[0] if numeric else None


def _pick_label(rows: list[dict[str, Any]]) -> str | None:
    preferred = [
        "year_month", "week_start", "customer_state", "seller_state",
        "product_category_english", "payment_type", "seller_id", "reason", "keyword",
    ]
    labels = _label_fields(rows)
    for key in preferred:
        if rows and key in rows[0]:
            return key
    return labels[0] if labels else None


def _first_existing(rows: list[dict[str, Any]], candidates: list[str]) -> str | None:
    if not rows:
        return None
    keys = set(rows[0])
    for candidate in candidates:
        if candidate in keys:
            return candidate
    return None


def _scale(value: float, low: float, high: float, out_low: float, out_high: float) -> float:
    span = high - low
    if span == 0:
        return (out_low + out_high) / 2
    return out_low + (value - low) / span * (out_high - out_low)


def _svg_bar(rows: list[dict[str, Any]], label_key: str, metric_key: str) -> str:
    data = rows[:20]
    values = [_to_float(row.get(metric_key)) or 0.0 for row in data]
    max_value = max(values) if values else 0.0
    width = 900
    row_height = 34
    height = max(120, 44 + row_height * len(data))
    bars = []
    for idx, row in enumerate(data):
        value = values[idx]
        y = 32 + idx * row_height
        bar_width = 0 if max_value == 0 else int((value / max_value) * 580)
        label = html.escape(str(row.get(label_key, ""))[:34])
        bars.append(
            f'<text x="12" y="{y + 17}" font-size="13">{label}</text>'
            f'<rect x="250" y="{y}" width="{bar_width}" height="22" fill="#2563eb"></rect>'
            f'<text x="{260 + bar_width}" y="{y + 17}" font-size="12">{html.escape(_format_value(value))}</text>'
        )
    return f'<svg viewBox="0 0 {width} {height}" width="100%" role="img">{"".join(bars)}</svg>'


def _svg_line(rows: list[dict[str, Any]], label_key: str, metric_key: str) -> str:
    data = rows[-36:]
    values = [_to_float(row.get(metric_key)) or 0.0 for row in data]
    if not values:
        return "<p>没有可绘制的数值数据。</p>"

    width = 900
    height = 360
    pad = 52
    max_value = max(values)
    min_value = min(values)
    span = max(max_value - min_value, 1.0)
    step = (width - pad * 2) / max(len(values) - 1, 1)

    points = []
    for idx, value in enumerate(values):
        x = pad + idx * step
        y = height - pad - ((value - min_value) / span) * (height - pad * 2)
        points.append((x, y))

    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#0f766e"></circle>'
        for x, y in points
    )
    start_label = html.escape(str(data[0].get(label_key, "")))
    end_label = html.escape(str(data[-1].get(label_key, "")))
    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" role="img">
      <line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#9ca3af"></line>
      <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#9ca3af"></line>
      <polyline points="{polyline}" fill="none" stroke="#0f766e" stroke-width="3"></polyline>
      {circles}
      <text x="{pad}" y="{height-14}" font-size="12">{start_label}</text>
      <text x="{width-pad-90}" y="{height-14}" font-size="12">{end_label}</text>
      <text x="{pad+4}" y="{pad-14}" font-size="12">{html.escape(_format_value(max_value))}</text>
      <text x="{pad+4}" y="{height-pad+20}" font-size="12">{html.escape(_format_value(min_value))}</text>
    </svg>
    """


def _svg_geo_bubble(rows: list[dict[str, Any]], state_key: str, metric_key: str) -> str:
    data = [row for row in rows if str(row.get(state_key, "")).upper() in STATE_COORDS][:27]
    if not data:
        return _html_table(rows)

    width = 760
    height = 620
    values = [_to_float(row.get(metric_key)) or 0.0 for row in data]
    max_value = max(values) if values else 1.0
    circles = []
    for row, value in zip(data, values):
        state = str(row.get(state_key, "")).upper()
        lng, lat = STATE_COORDS[state]
        x = _scale(lng, -74.0, -34.0, 70.0, width - 70.0)
        y = _scale(lat, 5.0, -34.0, 50.0, height - 70.0)
        radius = 7 + 34 * math.sqrt(value / max_value) if max_value else 7
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="#dc2626" fill-opacity="0.45" stroke="#991b1b"></circle>'
            f'<text x="{x + radius + 3:.1f}" y="{y + 4:.1f}" font-size="12">{html.escape(state)} {html.escape(_format_value(value))}</text>'
        )
    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" role="img">
      <rect x="1" y="1" width="{width-2}" height="{height-2}" fill="#f8fafc" stroke="#cbd5e1"></rect>
      <text x="24" y="32" font-size="16" font-weight="700">Brazil states bubble map</text>
      <text x="24" y="54" font-size="12" fill="#64748b">气泡位置使用州近似中心点，大小表示{html.escape(metric_key)}</text>
      {"".join(circles)}
    </svg>
    """


def _svg_heatmap(rows: list[dict[str, Any]], x_key: str, y_key: str, metric_key: str) -> str:
    x_values = list(dict.fromkeys(str(row.get(x_key, "")) for row in rows if row.get(x_key) is not None))[:16]
    y_values = list(dict.fromkeys(str(row.get(y_key, "")) for row in rows if row.get(y_key) is not None))[:16]
    matrix = {(str(row.get(x_key, "")), str(row.get(y_key, ""))): _to_float(row.get(metric_key)) or 0.0 for row in rows}
    values = list(matrix.values())
    max_value = max(values) if values else 1.0
    cell = 34
    left = 170
    top = 70
    width = left + cell * len(x_values) + 40
    height = top + cell * len(y_values) + 70
    cells = []
    for yi, y_value in enumerate(y_values):
        cells.append(f'<text x="8" y="{top + yi * cell + 22}" font-size="12">{html.escape(y_value[:22])}</text>')
        for xi, x_value in enumerate(x_values):
            value = matrix.get((x_value, y_value), 0.0)
            opacity = 0.08 + 0.82 * (value / max_value) if max_value else 0.08
            cells.append(
                f'<rect x="{left + xi * cell}" y="{top + yi * cell}" width="{cell-2}" height="{cell-2}" fill="#7c3aed" fill-opacity="{opacity:.3f}"></rect>'
            )
    headers = "".join(
        f'<text transform="translate({left + xi * cell + 18},{top - 8}) rotate(-45)" font-size="11">{html.escape(x_value[:12])}</text>'
        for xi, x_value in enumerate(x_values)
    )
    return f'<svg viewBox="0 0 {width} {height}" width="100%" role="img">{headers}{"".join(cells)}</svg>'


def _svg_scatter(rows: list[dict[str, Any]], x_key: str, y_key: str, size_key: str | None = None, color_key: str | None = None) -> str:
    points = []
    for row in rows[:300]:
        x = _to_float(row.get(x_key))
        y = _to_float(row.get(y_key))
        if x is not None and y is not None:
            points.append((row, x, y))
    if not points:
        return _html_table(rows)

    width = 900
    height = 420
    pad = 58
    xs = [item[1] for item in points]
    ys = [item[2] for item in points]
    sizes = [_to_float(item[0].get(size_key)) or 1.0 for item in points] if size_key else [1.0 for _ in points]
    max_size = max(sizes) if sizes else 1.0
    palette = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
    color_map: dict[str, str] = {}
    circles = []
    for idx, (row, x_value, y_value) in enumerate(points):
        x = _scale(x_value, min(xs), max(xs), pad, width - pad)
        y = _scale(y_value, min(ys), max(ys), height - pad, pad)
        size_value = sizes[idx]
        radius = 4 + 16 * math.sqrt(size_value / max_size) if max_size else 4
        color_value = str(row.get(color_key, "")) if color_key else "default"
        if color_value not in color_map:
            color_map[color_value] = palette[len(color_map) % len(palette)]
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color_map[color_value]}" fill-opacity="0.55"></circle>'
        )
    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" role="img">
      <line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#9ca3af"></line>
      <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#9ca3af"></line>
      <text x="{width/2 - 60}" y="{height - 12}" font-size="12">{html.escape(x_key)}</text>
      <text x="8" y="{pad - 18}" font-size="12">{html.escape(y_key)}</text>
      {"".join(circles)}
    </svg>
    """


def _svg_word_cloud(words: list[tuple[str, int | float]]) -> str:
    data = [(str(word), _to_float(count) or 0.0) for word, count in words if str(word).strip()][:50]
    if not data:
        return "<p>没有可展示的关键词。</p>"
    max_count = max(count for _, count in data) or 1.0
    width = 900
    height = 430
    x, y = 24, 52
    pieces = []
    colors = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
    for idx, (word, count) in enumerate(data):
        size = 13 + 30 * math.sqrt(count / max_count)
        token_width = max(54, len(word) * size * 0.58)
        if x + token_width > width - 30:
            x = 24
            y += 52
        if y > height - 24:
            break
        pieces.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}" fill="{colors[idx % len(colors)]}">{html.escape(word)}</text>'
        )
        x += token_width + 18
    return f'<svg viewBox="0 0 {width} {height}" width="100%" role="img">{"".join(pieces)}</svg>'


def _html_table(rows: list[dict[str, Any]]) -> str:
    data = rows[:30]
    if not data:
        return "<p>没有可展示的数据。</p>"
    headers = list(data[0].keys())
    th = "".join(f"<th>{html.escape(str(key))}</th>" for key in headers)
    body = []
    for row in data:
        cells = "".join(f"<td>{html.escape(_format_value(row.get(key)))}</td>" for key in headers)
        body.append(f"<tr>{cells}</tr>")
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def _write_html(title: str, body: str, metadata: dict[str, Any]) -> Path:
    _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = OUTPUT_DIR / f"{timestamp}_{_safe_filename(title)}.html"
    payload = html.escape(json.dumps(metadata, ensure_ascii=False, indent=2))
    content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #111827; }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    .meta {{ color: #64748b; margin-bottom: 18px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; }}
    th {{ background: #f3f4f6; }}
    .card {{ border: 1px solid #e5e7eb; padding: 18px; max-width: 420px; }}
    .value {{ font-size: 34px; font-weight: 700; color: #2563eb; }}
    pre {{ background: #f9fafb; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="meta">AgenticBI自动生成图表</div>
  {body}
  <h2>metadata</h2>
  <pre>{payload}</pre>
</body>
</html>"""
    path.write_text(content, encoding="utf-8")
    return path


def _infer_chart_type(recommended: str | None, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "table"
    if len(rows) == 1 and _numeric_fields(rows):
        return "big_number_card"

    keys = set(rows[0])
    if "customer_state" in keys or "seller_state" in keys:
        return "geographic_bubble_map"
    if {"product_weight_g", "freight_value"}.issubset(keys) or {"product_weight_g", "price"}.issubset(keys):
        return "scatter_bubble_chart"
    if "payment_type" in keys and {"payment_installments", "installments", "payment_sequential"} & keys:
        return "matrix_heatmap"

    numeric = _numeric_fields(rows)
    labels = _label_fields(rows)
    label_key = _pick_label(rows) or ""
    if len(labels) >= 2 and numeric:
        return "matrix_heatmap"
    if recommended in {"line_chart", "bar_chart", "table", "big_number_card"}:
        return recommended
    if "month" in label_key or "date" in label_key or "week" in label_key:
        return "line_chart"
    if labels and numeric:
        return "bar_chart"
    return "table"


def _build_body(chart_type: str, rows: list[dict[str, Any]]) -> tuple[str, str | None, str | None]:
    label_key = _pick_label(rows)
    metric_key = _pick_metric(rows)

    if not rows:
        return "<p>没有可展示的数据。</p>", label_key, metric_key
    if chart_type == "big_number_card" and metric_key:
        value = rows[0].get(metric_key)
        body = f'<div class="card"><div>{html.escape(metric_key)}</div><div class="value">{html.escape(_format_value(value))}</div></div>'
        return body, label_key, metric_key
    if chart_type == "line_chart" and label_key and metric_key:
        return _svg_line(rows, label_key, metric_key), label_key, metric_key
    if chart_type == "bar_chart" and label_key and metric_key:
        return _svg_bar(rows, label_key, metric_key), label_key, metric_key
    if chart_type == "geographic_bubble_map" and metric_key:
        state_key = _first_existing(rows, ["customer_state", "seller_state", "geolocation_state"]) or label_key
        if state_key:
            return _svg_geo_bubble(rows, state_key, metric_key), state_key, metric_key
    if chart_type == "matrix_heatmap" and metric_key:
        payment_dim = _first_existing(rows, ["payment_installments", "installments", "payment_sequential"])
        if "payment_type" in rows[0] and payment_dim:
            return _svg_heatmap(rows, payment_dim, "payment_type", metric_key), f"{payment_dim} x payment_type", metric_key
        labels = _label_fields(rows)
        if len(labels) >= 2:
            return _svg_heatmap(rows, labels[0], labels[1], metric_key), f"{labels[0]} x {labels[1]}", metric_key
    if chart_type == "scatter_bubble_chart":
        x_key = _first_existing(rows, ["product_weight_g", "product_length_cm", "price"])
        y_key = _first_existing(rows, ["freight_value", "avg_price", "payment_value"])
        size_key = _first_existing(rows, ["total_orders", "order_count", "review_count"])
        color_key = _first_existing(rows, ["order_status", "product_category_english"])
        if x_key and y_key:
            return _svg_scatter(rows, x_key, y_key, size_key, color_key), x_key, y_key

    return _html_table(rows), label_key, metric_key


def _build_insight(chart_type: str, rows: list[dict[str, Any]], label_key: str | None, metric_key: str | None) -> str:
    if not rows:
        return "没有可视化数据。"
    if metric_key:
        numeric_rows = [
            (row, _to_float(row.get(metric_key)))
            for row in rows
            if _to_float(row.get(metric_key)) is not None
        ]
        if numeric_rows:
            top_row, top_value = max(numeric_rows, key=lambda item: item[1] or 0)
            label = top_row.get(label_key) if label_key else "首要对象"
            return f"{chart_type}展示{len(rows)}行结果，最高{metric_key}为{_format_value(top_value)}，对应{label_key or 'label'}={label}。"
    return f"{chart_type}展示{len(rows)}行结果，可用于报告截图和前端展示。"


def _create_chart(question: str, chart_type: str, rows: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    body, label_key, metric_key = _build_body(chart_type, rows)
    title = f"{question[:36]}-{suffix}-{chart_type}"
    metadata = {
        "question": question,
        "chart_type": chart_type,
        "label_key": label_key,
        "metric_key": metric_key,
        "row_count": len(rows),
    }
    path = _write_html(title, body, metadata)
    return {
        "chart_type": chart_type,
        "chart_title": title,
        "chart_path": str(path),
        "chart_insight": _build_insight(chart_type, rows, label_key, metric_key),
        "label_key": label_key,
        "metric_key": metric_key,
        "row_count": len(rows),
    }


def _forecast_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    forecast = payload.get("forecast_result") or {}
    values = forecast.get("forecast_values") or []
    return values if isinstance(values, list) else []


def _what_if_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    what_if = payload.get("what_if_result") or {}
    rows = what_if.get("chart_data") or []
    return rows if isinstance(rows, list) else []


def _keyword_rows(payload: dict[str, Any]) -> list[tuple[str, int | float]]:
    nlp = payload.get("nlp_result") or {}
    words = nlp.get("wordcloud_data") or nlp.get("negative_keywords") or nlp.get("positive_keywords") or []
    result: list[tuple[str, int | float]] = []
    for item in words:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            result.append((str(item[0]), item[1]))
        elif isinstance(item, dict):
            result.append((str(item.get("keyword") or item.get("word") or ""), item.get("count") or 0))
    return result


def _create_word_cloud(question: str, words: list[tuple[str, int | float]]) -> dict[str, Any]:
    title = f"{question[:36]}-word_cloud"
    body = _svg_word_cloud(words)
    metadata = {
        "question": question,
        "chart_type": "word_cloud",
        "row_count": len(words),
    }
    path = _write_html(title, body, metadata)
    top_word = words[0][0] if words else "无"
    return {
        "chart_type": "word_cloud",
        "chart_title": title,
        "chart_path": str(path),
        "chart_insight": f"词云展示{len(words)}个评论关键词，最高频关键词为{top_word}。",
        "label_key": "keyword",
        "metric_key": "count",
        "row_count": len(words),
    }


def run_visualization_agent(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        rows = []

    question = str(payload.get("question") or "BI分析结果")
    primary_type = _infer_chart_type(payload.get("recommended_chart"), rows)
    charts = [_create_chart(question, primary_type, rows, "primary")]

    forecast_rows = _forecast_rows(payload)
    if forecast_rows:
        charts.append(_create_chart(question, "line_chart", forecast_rows, "forecast"))

    what_if_rows = _what_if_rows(payload)
    if what_if_rows:
        charts.append(_create_chart(question, "bar_chart", what_if_rows, "what_if"))

    keyword_rows = _keyword_rows(payload)
    if keyword_rows:
        charts.append(_create_word_cloud(question, keyword_rows))

    primary = charts[0]
    return {
        **primary,
        "charts": charts,
        "supported_chart_types": [
            "line_chart",
            "geographic_bubble_map",
            "bar_chart",
            "matrix_heatmap",
            "scatter_bubble_chart",
            "word_cloud",
            "big_number_card",
            "table",
        ],
    }
