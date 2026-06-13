"""
Streamlit Web UI for Agentic BI E-Commerce System.

成员D负责：Web前端界面、图表展示、多轮问答
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 从环境变量读取后端端口，默认 3000
BACKEND_PORT = os.getenv("PORT", "3000")
API_BASE_URL = f"http://localhost:{BACKEND_PORT}/api"
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", "180"))


def init_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "history_context" not in st.session_state:
        st.session_state.history_context = []
    if "expanded_sections" not in st.session_state:
        st.session_state.expanded_sections = {
            "summary": True,
            "sql": True,
            "visualization": True,
            "what_if": True,
            "nlp": True,
            "forecast": True,
            "decision": True
        }
    if "is_typing" not in st.session_state:
        st.session_state.is_typing = False
    if "last_send_status" not in st.session_state:
        st.session_state.last_send_status = None
    if "last_error_message" not in st.session_state:
        st.session_state.last_error_message = ""


def split_questions(raw_text: str) -> list[str]:
    """Split pasted multi-line questions into independent user questions."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return [raw_text.strip()] if raw_text.strip() else []

    questions: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.、)]|[（(]\d+[）)])\s*", "", line)
        cleaned = cleaned.strip().strip("“”\"'`")
        if cleaned:
            questions.append(cleaned)
    return questions


def call_api(endpoint: str, method: str = "GET", **kwargs):
    """Call the backend API."""
    url = f"{API_BASE_URL}/{endpoint}"
    try:
        if method == "POST":
            response = requests.post(url, json=kwargs, timeout=API_TIMEOUT_SECONDS)
        else:
            response = requests.get(url, params=kwargs, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "连接失败，请检查后端服务是否启动"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "请求超时，请稍后重试"}
    except Exception as e:
        return {"success": False, "error": f"API调用失败: {str(e)}"}


def ask_question(question: str) -> dict | None:
    """Send question to backend and get response."""
    st.session_state.is_typing = True
    
    data = {
        "question": question,
        "session_id": st.session_state.session_id,
        "history_context": st.session_state.history_context
    }
    result = call_api("ask", method="POST", **data)
    
    st.session_state.is_typing = False
    
    if result and result.get("success"):
        st.session_state.last_send_status = "success"
        st.session_state.last_error_message = ""
        
        if st.session_state.session_id is None:
            st.session_state.session_id = result["data"]["session_id"]
        
        history_item = {
            "question": question,
            "answer": result["data"].get("final_answer", ""),
            "timestamp": datetime.now().isoformat()
        }
        st.session_state.history_context.append(history_item)
        
        return result["data"]
    else:
        st.session_state.last_send_status = "error"
        st.session_state.last_error_message = (result or {}).get("error", "未知错误")
        return None


def toggle_section(section_name: str):
    """Toggle section expansion state."""
    st.session_state.expanded_sections[section_name] = not st.session_state.expanded_sections.get(section_name, True)


def get_chart_rows(result: dict, chart: dict | None = None) -> list:
    """Return chart-scoped rows before falling back to the full analysis rows."""
    if chart:
        chart_data = chart.get("data")
        if isinstance(chart_data, dict) and isinstance(chart_data.get("data"), list):
            return chart_data["data"]
        if isinstance(chart_data, list):
            return chart_data
    return result.get("downstream_payload", {}).get("data", [])


def display_visualization(result: dict):
    """Display visualization results with collapsible sections."""
    viz_result = result.get("visualization_result")
    if viz_result:
        charts = viz_result.get("charts", [])
        
        for chart in charts:
            chart_type = chart.get("chart_type", "")
            chart_title = chart.get("chart_title", "")
            chart_insight = chart.get("chart_insight", "")
            chart_path = chart.get("chart_path", "")
            
            with st.expander(f"📊 {chart_title}", expanded=True):
                if chart_type == "line_chart":
                    display_line_chart(result, chart)
                elif chart_type == "bar_chart":
                    display_bar_chart(result, chart)
                elif chart_type == "geographic_bubble_map":
                    display_geo_chart(result, chart)
                elif chart_type == "word_cloud":
                    display_word_cloud(result, chart)
                elif chart_type == "matrix_heatmap":
                    display_heatmap(result, chart)
                elif chart_type == "scatter_bubble_chart":
                    display_scatter_chart(result, chart)
                elif chart_type == "big_number_card":
                    display_big_number(result, chart)
                elif chart_type == "table":
                    display_data_table(result, chart)
                
                if chart_path:
                    try:
                        with open(chart_path, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                            st.components.v1.html(html_content, height=400, scrolling=True)
                    except Exception as e:
                        pass
                
                if chart_insight:
                    st.markdown(f"💡 **图表洞察:** {chart_insight}")


def display_line_chart(result: dict, chart: dict = None):
    """Display line chart for time series data with Plotly."""
    try:
        import pandas as pd
        import plotly.express as px
        
        data = get_chart_rows(result, chart)
        
        if data:
            df = pd.DataFrame(data)
            time_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ["month", "date", "week", "time"])]
            
            if time_cols:
                time_col = time_cols[0]
                numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
                
                if numeric_cols:
                    fig = px.line(df, x=time_col, y=numeric_cols[:3], 
                                  title=chart.get("chart_title", "时间序列趋势"),
                                  labels={time_col: "时间"},
                                  template="plotly_white")
                    fig.update_layout(height=350)
                    st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"图表渲染失败: {str(e)}")


def display_bar_chart(result: dict, chart: dict = None):
    """Display bar chart with Plotly."""
    try:
        import pandas as pd
        import plotly.express as px
        
        data = get_chart_rows(result, chart)
        
        if data:
            df = pd.DataFrame(data)
            cat_cols = [col for col in df.columns if df[col].dtype not in ["int64", "float64", "datetime64"]]
            numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
            
            if cat_cols and numeric_cols:
                preferred_labels = [
                    "category",
                    "product_category_name_english",
                    "product_category_english",
                    "payment_type",
                    "customer_state",
                    "route_label",
                    "seller_label",
                    "seller_id",
                ]
                preferred_metrics = [
                    "cancellation_rate",
                    "return_rate",
                    "cancel_rate",
                    "delivery_diff",
                    "negative_rate",
                    "avg_delivery_days",
                    "negative_review_count",
                    "negative_reviews",
                    "negative_count",
                    "bad_review_count",
                    "bad_reviews",
                    "bad_count",
                    "complaint_count",
                    "review_count",
                    "total_negative_reviews",
                    "cnt",
                    "count",
                ]
                chart_label = chart.get("label_key") if chart else None
                chart_metric = chart.get("metric_key") if chart else None
                x_col = chart_label if chart_label in df.columns else next(
                    (col for col in preferred_labels if col in df.columns),
                    cat_cols[0],
                )
                metric_col = chart_metric if chart_metric in df.columns else next(
                    (col for col in preferred_metrics if col in df.columns),
                    numeric_cols[0],
                )
                y_cols = [metric_col]
                df = df[df[x_col].notna() & df[metric_col].notna()]

                if df[x_col].duplicated().any():
                    df = (
                        df.groupby(x_col, as_index=False)[y_cols]
                        .max()
                        .sort_values(y_cols[0], ascending=False)
                        .head(20)
                    )

                if not df.empty:
                    df = df.sort_values(metric_col, ascending=False).head(20)
                    y_label = metric_col
                    if metric_col.endswith("_rate"):
                        df = df.copy()
                        df["_plot_rate"] = df[metric_col] * 100
                        y_cols = ["_plot_rate"]
                        y_label = f"{metric_col} (%)"
                    fig = px.bar(
                        df,
                        x=x_col,
                        y=y_cols,
                        title=chart.get("chart_title", "数据对比"),
                        labels={x_col: x_col, "_plot_rate": y_label},
                        template="plotly_white",
                    )
                    fig.update_layout(height=350)
                    st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"图表渲染失败: {str(e)}")


def display_geo_chart(result: dict, chart: dict = None):
    """Display geographic bubble map."""
    try:
        import pandas as pd
        import plotly.express as px

        data = get_chart_rows(result, chart)

        if data:
            df = pd.DataFrame(data)

            state_col = None
            for col in ["customer_state", "seller_state", "geolocation_state", "state"]:
                if col in df.columns:
                    state_col = col
                    break

            if state_col:
                chart_metric = chart.get("metric_key") if chart else None
                numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
                rate_cols = [col for col in numeric_cols if col.endswith("_rate")]
                metric_col = chart_metric if chart_metric in df.columns else (
                    rate_cols[0] if rate_cols else numeric_cols[0] if numeric_cols else None
                )

                if metric_col:
                    state_coords = {
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

                    grouped = (
                        df.groupby(state_col, as_index=False)[metric_col]
                        .sum()
                        .rename(columns={metric_col: "metric_value"})
                    )
                    grouped["state"] = grouped[state_col].astype(str).str.upper()
                    grouped = grouped[grouped["state"].isin(state_coords)]
                    grouped["longitude"] = grouped["state"].map(lambda s: state_coords[s][0])
                    grouped["latitude"] = grouped["state"].map(lambda s: state_coords[s][1])

                    if not grouped.empty:
                        fig = px.scatter(
                            grouped,
                            x="longitude",
                            y="latitude",
                            size="metric_value",
                            color="state",
                            hover_name="state",
                            hover_data={"metric_value": True, "longitude": False, "latitude": False},
                            title=chart.get("chart_title", "巴西各州地理分布"),
                            labels={"metric_value": metric_col},
                            template="plotly_white",
                        )
                        fig.update_layout(height=350, xaxis_title="经度", yaxis_title="纬度")
                        st.plotly_chart(fig, use_container_width=True)

                        st.markdown("📍 **巴西各州数据分布**")
                        st.dataframe(grouped[[state_col, "metric_value"]])
    except Exception as e:
        st.warning(f"地理图表渲染失败: {str(e)}")


def display_word_cloud(result: dict, chart: dict = None):
    """Display word cloud visualization."""
    try:
        from wordcloud import WordCloud
        import matplotlib.pyplot as plt
        
        nlp_result = result.get("nlp_result", {})
        words = []
        
        for key in ["positive_keywords", "negative_keywords", "wordcloud_data"]:
            if key in nlp_result:
                for item in nlp_result[key]:
                    if isinstance(item, dict):
                        word = item.get("keyword", item.get("word", ""))
                        count = item.get("count", 1)
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        word, count = item[0], item[1]
                    else:
                        word, count = str(item), 1
                    words.append((str(word), count))
        
        if words:
            wordcloud = WordCloud(
                width=800,
                height=400,
                background_color='white',
                colormap='viridis',
                font_path='simhei.ttf' if os.path.exists('simhei.ttf') else None
            ).generate_from_frequencies(dict(words))
            
            plt.figure(figsize=(10, 5))
            plt.imshow(wordcloud, interpolation='bilinear')
            plt.axis('off')
            st.pyplot(plt)
            plt.close()
    except Exception as e:
        display_html_word_cloud(result, chart)


def display_html_word_cloud(result: dict, chart: dict = None):
    """Display word cloud as HTML tags."""
    nlp_result = result.get("nlp_result", {})
    keywords = []
    
    for key in ["positive_keywords", "negative_keywords", "wordcloud_data"]:
        if key in nlp_result:
            keywords.extend(nlp_result[key])
    
    if keywords:
        word_items = []
        for item in keywords[:30]:
            if isinstance(item, dict):
                word = item.get("keyword", item.get("word", ""))
                count = item.get("count", 1)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                word, count = item[0], item[1]
            else:
                continue
            word_items.append((str(word), count))
        
        if word_items:
            max_count = max([w[1] for w in word_items])
            html_content = '<div style="display: flex; flex-wrap: wrap; gap: 10px; padding: 20px; background: #f8fafc; border-radius: 12px; min-height: 150px;">'
            for word, count in word_items:
                size = max(16, min(56, 16 + (count / max_count) * 40))
                html_content += f'<span style="font-size: {size}px; padding: 6px 16px; background: linear-gradient(135deg, #2563eb, #6366f1); color: white; border-radius: 25px; font-weight: 500; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);">{word}</span>'
            html_content += '</div>'
            st.markdown(html_content, unsafe_allow_html=True)


def display_heatmap(result: dict, chart: dict = None):
    """Display matrix heatmap with Plotly."""
    try:
        import pandas as pd
        import plotly.express as px
        
        data = get_chart_rows(result, chart)
        
        if data:
            df = pd.DataFrame(data)
            cat_cols = [col for col in df.columns if df[col].dtype not in ["int64", "float64"]]
            numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
            
            if len(cat_cols) >= 2 and numeric_cols:
                pivot_df = df.pivot(index=cat_cols[0], columns=cat_cols[1], values=numeric_cols[0]).fillna(0)
                fig = px.imshow(pivot_df, 
                                labels=dict(x=cat_cols[1], y=cat_cols[0], color=numeric_cols[0]),
                                x=pivot_df.columns,
                                y=pivot_df.index,
                                title=chart.get("chart_title", "矩阵热力图"),
                                template="plotly_white")
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"热力图渲染失败: {str(e)}")


def display_scatter_chart(result: dict, chart: dict = None):
    """Display scatter/bubble chart with Plotly."""
    try:
        import pandas as pd
        import plotly.express as px
        
        data = get_chart_rows(result, chart)
        
        if data:
            df = pd.DataFrame(data)
            numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
            cat_cols = [col for col in df.columns if df[col].dtype not in ["int64", "float64"]]
            
            if len(numeric_cols) >= 2:
                size_col = numeric_cols[2] if len(numeric_cols) >= 3 else None
                color_col = cat_cols[0] if cat_cols else None
                
                fig = px.scatter(df, 
                                 x=numeric_cols[0], 
                                 y=numeric_cols[1],
                                 size=size_col,
                                 color=color_col,
                                 title=chart.get("chart_title", "散点图"),
                                 labels={numeric_cols[0]: numeric_cols[0], numeric_cols[1]: numeric_cols[1]},
                                 template="plotly_white")
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"散点图渲染失败: {str(e)}")


def display_big_number(result: dict, chart: dict = None):
    """Display big number card."""
    data = get_chart_rows(result, chart)
    
    if data and len(data) >= 1:
        first_row = data[0] if isinstance(data[0], dict) else data[0]
        
        numeric_items = []
        for key, value in (first_row.items() if isinstance(first_row, dict) else enumerate(first_row)):
            if isinstance(value, (int, float)):
                numeric_items.append((str(key), value))
        
        if numeric_items:
            cols = st.columns(len(numeric_items))
            for i, (label, value) in enumerate(numeric_items):
                with cols[i]:
                    st.metric(label=label, value=f"{value:,.2f}")


def display_data_table(result: dict, chart: dict = None):
    """Display data table."""
    data = get_chart_rows(result, chart)
    
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)


def display_nlp_result(result: dict):
    """Display NLP analysis results with collapsible section."""
    if result.get("what_if_result"):
        return
    nlp_result = result.get("nlp_result")
    if nlp_result:
        with st.expander("💬 NLP分析结果", expanded=st.session_state.expanded_sections.get("nlp", True)):
            col1, col2 = st.columns(2)
            
            with col1:
                if "sentiment_score" in nlp_result:
                    sentiment = float(nlp_result["sentiment_score"])
                    color = "green" if sentiment > 0.5 else "red" if sentiment < 0.3 else "yellow"
                    st.markdown(f"<div style='text-align: center; padding: 16px; background: #f8fafc; border-radius: 12px;'>"
                                f"<div style='font-size: 14px; color: #64748b;'>情感得分</div>"
                                f"<div style='font-size: 48px; font-weight: bold; color: {color};'>{sentiment:.2f}</div>"
                                f"</div>", unsafe_allow_html=True)
            
            with col2:
                if "positive_keywords" in nlp_result:
                    st.markdown("**👍 好评关键词:**")
                    keywords = [str(k) for k in nlp_result["positive_keywords"][:8]]
                    st.write(", ".join(keywords))
            
            if "negative_keywords" in nlp_result:
                st.markdown("**👎 差评关键词:**")
                keywords = [str(k) for k in nlp_result["negative_keywords"][:8]]
                st.write(", ".join(keywords))
            
            if "main_complaints" in nlp_result:
                st.markdown("**⚠️ 主要差评原因:**")
                for i, complaint in enumerate(nlp_result["main_complaints"][:5], 1):
                    st.write(f"{i}. {complaint}")


def display_forecast_result(result: dict):
    """Display forecast results with collapsible section."""
    if result.get("what_if_result"):
        return
    forecast_result = result.get("forecast_result")
    if forecast_result:
        with st.expander("📈 预测结果", expanded=st.session_state.expanded_sections.get("forecast", True)):
            if "forecast_period" in forecast_result:
                st.markdown(f"**预测周期:** {forecast_result['forecast_period']}")
            
            if "forecast_values" in forecast_result:
                try:
                    import pandas as pd
                    import plotly.express as px
                    
                    values = forecast_result["forecast_values"]
                    if isinstance(values, list) and values:
                        df = pd.DataFrame(values)
                        time_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ["month", "date", "week"])]
                        numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
                        
                        if time_cols and numeric_cols:
                            fig = px.line(df, x=time_cols[0], y=numeric_cols,
                                          title="预测趋势",
                                          template="plotly_white")
                            fig.update_layout(height=300)
                            st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.dataframe(forecast_result["forecast_values"])
            
            if "trend_summary" in forecast_result:
                st.markdown(f"**趋势解释:** {forecast_result['trend_summary']}")
            
            if "confidence_interval" in forecast_result:
                st.markdown(f"**置信区间:** {forecast_result['confidence_interval']}")


def display_what_if_result(result: dict):
    """Display What-if simulation results."""
    what_if = result.get("what_if_result")
    if not what_if:
        return

    with st.expander("🔮 What-if 模拟", expanded=st.session_state.expanded_sections.get("what_if", True)):
        st.markdown(f"**场景:** {what_if.get('scenario', '卖家干预模拟')}")

        col1, col2, col3 = st.columns(3)
        col1.metric("干预前均分", what_if.get("baseline_avg_score"))
        col2.metric("干预后均分", what_if.get("simulated_avg_score"))
        col3.metric("预估提升", what_if.get("estimated_lift"))

        if what_if.get("insight"):
            st.markdown(f"**结论:** {what_if.get('insight')}")

        st.markdown(
            f"受影响评论 **{what_if.get('affected_reviews')}** 条 · "
            f"剩余评论 **{what_if.get('remaining_reviews')}** 条 · "
            f"被干预卖家均分 **{what_if.get('affected_avg_score')}**"
        )

        chart_data = what_if.get("chart_data") or []
        if chart_data:
            try:
                import pandas as pd
                import plotly.express as px

                df = pd.DataFrame(chart_data)
                label_map = {
                    "baseline": "干预前",
                    "after_intervention": "干预后",
                    "affected_sellers": "被干预卖家",
                }
                if "scenario" in df.columns:
                    df["scenario_label"] = df["scenario"].map(label_map).fillna(df["scenario"])
                    fig = px.bar(
                        df,
                        x="scenario_label",
                        y="avg_review_score",
                        title="平台评分干预前后对比",
                        labels={"scenario_label": "场景", "avg_review_score": "平均评分"},
                        template="plotly_white",
                    )
                    fig.update_layout(height=320)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.dataframe(chart_data)

        assumptions = what_if.get("assumptions") or []
        if assumptions:
            st.markdown("**假设说明:**")
            for item in assumptions:
                st.write(f"- {item}")


def display_decision_result(result: dict):
    """Display decision/recommendation results with collapsible section."""
    decision_result = result.get("decision_result")
    if decision_result:
        with st.expander("🎯 决策建议", expanded=st.session_state.expanded_sections.get("decision", True)):
            if "business_problem" in decision_result:
                st.markdown(
                    f'<div class="decision-card"><div class="decision-action">'
                    f'📌 {_esc(decision_result["business_problem"])}</div></div>',
                    unsafe_allow_html=True,
                )

            if "recommendations" in decision_result:
                st.markdown("**运营建议**")
                for i, rec in enumerate(decision_result["recommendations"][:5], 1):
                    if isinstance(rec, dict):
                        action = rec.get("action") or rec.get("suggestion") or rec.get("recommendation", str(rec))
                        priority = rec.get("priority", "P1")
                        evidence = rec.get("evidence", "")
                        impact = rec.get("expected_impact", "")
                        badge = _priority_badge(priority)
                        meta_parts = []
                        if evidence:
                            meta_parts.append(f"依据：{_esc(evidence)}")
                        if impact:
                            meta_parts.append(f"预期影响：{_esc(impact)}")
                        meta_html = "<br>".join(meta_parts)
                        st.markdown(
                            f'<div class="decision-card">'
                            f'<div class="decision-action">{badge}{i}. {_esc(action)}</div>'
                            f'{"<div class=\"decision-meta\">" + meta_html + "</div>" if meta_html else ""}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.write(f"{i}. {rec}")

            what_if_answer = decision_result.get("what_if_answer")
            if what_if_answer and what_if_answer.get("estimated_lift") is not None:
                st.markdown("**What-if 量化答案**")
                st.write(
                    f"评分 {what_if_answer.get('baseline_avg_score')} → "
                    f"{what_if_answer.get('simulated_avg_score')} "
                    f"(+{what_if_answer.get('estimated_lift')})"
                )

            col_a, col_b = st.columns(2)
            with col_a:
                if "priority" in decision_result:
                    st.metric("整体优先级", decision_result["priority"])
            with col_b:
                if decision_result.get("llm_generated"):
                    st.success("LLM 决策已生成")
                elif decision_result.get("llm_error"):
                    st.caption(f"规则兜底：{decision_result['llm_error'][:80]}")


def display_sql_result(result: dict):
    """Display SQL execution results with collapsible section."""
    with st.expander("🔍 查询详情", expanded=st.session_state.expanded_sections.get("sql", True)):
        if result.get("sql"):
            st.markdown("**执行的SQL语句:**")
            st.code(result["sql"], language="sql")
        
        if result.get("used_view"):
            st.success(f"✅ 使用预聚合视图: {result.get('view_name', '未知')}")
        else:
            st.info("🔄 未使用预聚合视图")
        
        if result.get("row_count"):
            st.markdown(f"**返回行数:** {result['row_count']}")


def format_time(timestamp_str):
    """Format timestamp to readable time."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime("%H:%M")
    except:
        return ""


# 六项业务能力（四类分析 + NLP + What-if）
ALL_CAPABILITY_CHIPS = [
    ("descriptive", "描述性", "#2563eb"),
    ("diagnostic", "诊断性", "#7c3aed"),
    ("predictive", "预测性", "#0891b2"),
    ("prescriptive", "规范性", "#059669"),
    ("nlp", "NLP 评论洞察", "#db2777"),
    ("what_if", "What-if 模拟", "#ea580c"),
]

ANALYSIS_TYPE_LABELS = {k: (label, color) for k, label, color in ALL_CAPABILITY_CHIPS if k in {
    "descriptive", "diagnostic", "predictive", "prescriptive",
}}

EXTENSION_CAPABILITY_LABELS = {
    "nlp": ("NLP 评论洞察", "#db2777"),
    "what_if": ("What-if 模拟", "#ea580c"),
    "forecast": ("GMV 预测", "#0891b2"),
}

CHART_TYPE_LABELS = {
    "line_chart": "折线图",
    "bar_chart": "柱状图",
    "geographic_bubble_map": "地理气泡图",
    "matrix_heatmap": "矩阵热力图",
    "scatter_bubble_chart": "散点/气泡图",
    "word_cloud": "词云",
}

PRIORITY_STYLES = {
    "P0": ("#dc2626", "#fef2f2", "#fecaca"),
    "P1": ("#d97706", "#fffbeb", "#fde68a"),
    "P2": ("#2563eb", "#eff6ff", "#bfdbfe"),
}


def _esc(text: str) -> str:
    return html.escape(str(text or "")).replace("\n", "<br>")


def check_backend_health() -> tuple[bool, str]:
    result = call_api("health")
    if result.get("status") == "ok":
        return True, result.get("version", "1.0.0")
    return False, ""


def _capability_chips_html(chip_keys: list[str] | None = None) -> str:
    items = ALL_CAPABILITY_CHIPS
    if chip_keys is not None:
        key_set = set(chip_keys)
        items = [item for item in ALL_CAPABILITY_CHIPS if item[0] in key_set]
    chips = "".join(
        f'<span class="type-chip" style="--chip-color:{color}">{label}</span>'
        for _, label, color in items
    )
    return f'<div class="chip-row">{chips}</div>'


CHAT_BOX_HEIGHT = 680
CHAT_RESERVE_BOTTOM = 228

CHAT_PANEL_STYLES = """
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; font-family: "Segoe UI", sans-serif; background: transparent; }
.chat-box {
    height: 100%; border: 1px solid #cbd5e1; border-radius: 16px; background: #f8fafc;
    overflow: hidden; box-shadow: inset 0 1px 3px rgba(15, 23, 42, 0.04);
}
.chat-scroll {
    height: 100%; min-height: 480px; overflow-y: auto; overflow-x: hidden;
    padding: 14px 10px 14px 16px; scrollbar-width: thin; scrollbar-color: #64748b #e2e8f0;
}
.chat-scroll::-webkit-scrollbar { width: 8px; }
.chat-scroll::-webkit-scrollbar-track { background: #e2e8f0; border-radius: 4px; margin: 4px 0; }
.chat-scroll::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 4px; border: 2px solid #e2e8f0; }
.chat-scroll::-webkit-scrollbar-thumb:hover { background: #64748b; }
.chat-empty {
    height: 100%; min-height: 420px; display: flex; flex-direction: column;
    align-items: center; justify-content: center; text-align: center; color: #64748b;
}
.chat-empty-icon { font-size: 40px; margin-bottom: 10px; opacity: 0.85; }
.chat-empty-title { font-size: 16px; font-weight: 700; color: #334155; margin-bottom: 6px; }
.chat-empty-desc { font-size: 13px; color: #94a3b8; max-width: 240px; line-height: 1.5; }
.message-wrapper { display: flex; margin-bottom: 14px; }
.avatar {
    width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center; font-size: 15px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.user-avatar { background: #93c5fd; margin-left: 10px; color: #1e3a8a; }
.bot-avatar { background: linear-gradient(135deg, #10b981, #059669); margin-right: 10px; }
.message-bubble {
    max-width: 88%; padding: 12px 16px; line-height: 1.55; font-size: 14px;
    word-break: break-word; overflow-wrap: anywhere;
}
.user-message-wrapper { justify-content: flex-end; }
.user-message-bubble {
    background: #dbeafe; color: #1e3a8a;
    border: 1px solid #bfdbfe; border-radius: 18px 18px 4px 18px;
    box-shadow: 0 1px 4px rgba(59, 130, 246, 0.12);
}
.bot-message-wrapper { justify-content: flex-start; }
.bot-message-bubble {
    background: white; color: #334155; border: 1px solid #e2e8f0;
    border-radius: 18px 18px 18px 4px; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
}
.typing-indicator {
    display: flex; padding: 12px 16px; background: white; border-radius: 18px;
    border: 1px solid #e2e8f0; max-width: 100px;
}
.typing-dots { display: flex; gap: 5px; }
.typing-dot {
    width: 7px; height: 7px; background: #94a3b8; border-radius: 50%;
    animation: typingBounce 1.4s infinite ease-in-out;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce {
    0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
    40% { transform: scale(1); opacity: 1; }
}
"""


def _chat_message_html(msg: dict) -> str:
    content = _esc(msg["content"])
    if msg["is_user"]:
        return (
            f'<div class="message-wrapper user-message-wrapper">'
            f'<div class="message-bubble user-message-bubble">{content}</div>'
            f'<div class="avatar user-avatar">👤</div></div>'
        )
    return (
        f'<div class="message-wrapper bot-message-wrapper">'
        f'<div class="avatar bot-avatar">🤖</div>'
        f'<div class="message-bubble bot-message-bubble">{content}</div></div>'
    )


def _typing_indicator_html() -> str:
    return (
        '<div class="message-wrapper bot-message-wrapper">'
        '<div class="avatar bot-avatar">🤖</div>'
        '<div class="typing-indicator"><div class="typing-dots">'
        '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>'
        '</div></div></div>'
    )


def build_chat_panel_html(messages: list[dict], is_typing: bool) -> str:
    inner_parts: list[str] = []
    if not messages and not is_typing:
        inner_parts.append(
            '<div class="chat-empty">'
            '<div class="chat-empty-icon">💬</div>'
            '<div class="chat-empty-title">开始对话</div>'
            '<div class="chat-empty-desc">在下方输入问题，分析结果将展示在右侧</div>'
            '</div>'
        )
    else:
        for msg in messages:
            inner_parts.append(_chat_message_html(msg))
        if is_typing:
            inner_parts.append(_typing_indicator_html())

    inner = "".join(inner_parts)
    return f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><style>{CHAT_PANEL_STYLES}</style></head><body>
    <div class="chat-box">
        <div class="chat-scroll" id="chat-scroll-area">{inner}</div>
    </div>
    <script>
        (function() {{
            const reserveBottom = {CHAT_RESERVE_BOTTOM};
            function scrollToBottom() {{
                const el = document.getElementById('chat-scroll-area');
                if (el) el.scrollTop = el.scrollHeight;
            }}
            function fitChatHeight() {{
                try {{
                    const frame = window.frameElement;
                    if (!frame || !window.parent) return;
                    const parentH = window.parent.innerHeight
                        || window.parent.document.documentElement.clientHeight;
                    const top = frame.getBoundingClientRect().top;
                    const target = Math.max(480, Math.floor(parentH - top - reserveBottom));
                    frame.style.height = target + 'px';
                    const box = document.querySelector('.chat-box');
                    const el = document.getElementById('chat-scroll-area');
                    if (box) box.style.height = target + 'px';
                    if (el) el.style.height = Math.max(478, target - 2) + 'px';
                    scrollToBottom();
                }} catch (err) {{}}
            }}
            fitChatHeight();
            window.addEventListener('load', fitChatHeight);
            setTimeout(fitChatHeight, 100);
            setTimeout(fitChatHeight, 350);
            if (window.parent) window.parent.addEventListener('resize', fitChatHeight);
        }})();
    </script>
    </body></html>
    """


def render_chat_panel(messages: list[dict], is_typing: bool) -> None:
    components.html(
        build_chat_panel_html(messages, is_typing),
        height=CHAT_BOX_HEIGHT,
        scrolling=False,
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-logo">BI</div>
                <div>
                    <div class="sidebar-title">Agentic BI</div>
                    <div class="sidebar-subtitle">电商智能分析</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        ok, version = check_backend_health()
        if ok:
            st.markdown(
                f'<div class="status-pill status-ok">● 后端在线 · v{version}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="status-pill status-off">● 后端离线 · 请先启动 backend</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("**分析能力**")
        st.markdown(_capability_chips_html(), unsafe_allow_html=True)

        st.markdown("---")
        if st.button("清空对话", use_container_width=True, type="secondary"):
            st.session_state.messages = []
            st.session_state.history_context = []
            st.session_state.session_id = None
            st.session_state.pop("last_result", None)
            st.session_state.last_send_status = None
            st.session_state.last_error_message = ""
            st.rerun()

        msg_count = len(st.session_state.messages)
        st.caption(f"当前会话 · {msg_count} 条消息")


def _active_capability_keys(result: dict) -> list[str]:
    """Return capability chip keys triggered in this answer."""
    keys: list[str] = []
    analysis_type = result.get("analysis_type", "")
    if analysis_type in ANALYSIS_TYPE_LABELS:
        keys.append(analysis_type)
    if result.get("forecast_result") and (result["forecast_result"] or {}).get("forecast_values"):
        if "predictive" not in keys:
            keys.append("predictive")
    if result.get("nlp_result") and "nlp" not in keys:
        keys.append("nlp")
    if result.get("what_if_result"):
        keys.append("what_if")
    return keys


def render_analysis_overview(result: dict) -> None:
    analysis_type = result.get("analysis_type", "")
    label, color = ANALYSIS_TYPE_LABELS.get(analysis_type, ("未分类", "#64748b"))
    cols = st.columns(4)
    cols[0].markdown(
        f'<div class="overview-card"><div class="overview-label">主分析类型</div>'
        f'<div class="overview-value" style="color:{color}">{label}</div></div>',
        unsafe_allow_html=True,
    )
    cols[1].markdown(
        f'<div class="overview-card"><div class="overview-label">返回行数</div>'
        f'<div class="overview-value">{result.get("row_count", 0):,}</div></div>',
        unsafe_allow_html=True,
    )
    view_text = result.get("view_name") or "原始表"
    cols[2].markdown(
        f'<div class="overview-card"><div class="overview-label">数据视图</div>'
        f'<div class="overview-value overview-sm">{_esc(view_text)}</div></div>',
        unsafe_allow_html=True,
    )
    intent = result.get("intent") or "—"
    cols[3].markdown(
        f'<div class="overview-card"><div class="overview-label">业务意图</div>'
        f'<div class="overview-value overview-sm">{_esc(intent)}</div></div>',
        unsafe_allow_html=True,
    )

    active_keys = _active_capability_keys(result)
    if active_keys:
        st.markdown(
            f'<div class="trigger-row">'
            f'<span class="trigger-label">本次触发</span>'
            f'{_capability_chips_html(active_keys)}'
            f'</div>',
            unsafe_allow_html=True,
        )


def _priority_badge(priority: str) -> str:
    p = (priority or "P1").upper()
    fg, bg, border = PRIORITY_STYLES.get(p, PRIORITY_STYLES["P1"])
    return (
        f'<span class="priority-badge" style="color:{fg};background:{bg};border-color:{border}">{p}</span>'
    )


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
            #MainMenu, footer, header { visibility: hidden; }
            .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px; }

            /* Sidebar */
            section[data-testid="stSidebar"] {
                background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
            }
            section[data-testid="stSidebar"] .stMarkdown,
            section[data-testid="stSidebar"] label,
            section[data-testid="stSidebar"] .stCaption { color: #e2e8f0 !important; }
            section[data-testid="stSidebar"] hr { border-color: #334155; }
            .sidebar-brand { display: flex; align-items: center; gap: 12px; padding: 8px 0 16px; }
            .sidebar-logo {
                width: 44px; height: 44px; border-radius: 12px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                color: white; font-weight: 800; font-size: 15px;
                display: flex; align-items: center; justify-content: center;
                box-shadow: 0 8px 20px rgba(99, 102, 241, 0.35);
            }
            .sidebar-title { font-size: 18px; font-weight: 700; color: #f8fafc; }
            .sidebar-subtitle { font-size: 12px; color: #94a3b8; margin-top: 2px; }
            .status-pill {
                font-size: 12px; padding: 8px 12px; border-radius: 10px; margin-bottom: 4px;
            }
            .status-ok { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; }
            .status-off { background: rgba(239, 68, 68, 0.15); color: #fca5a5; }
            .chip-row {
                display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
            }
            .trigger-row {
                display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
                margin: 8px 0 4px;
            }
            .trigger-label {
                font-size: 12px; color: #64748b; white-space: nowrap;
            }
            .type-chip {
                display: inline-block; font-size: 11px; padding: 3px 9px; margin: 0;
                border-radius: 999px; white-space: nowrap;
                background: color-mix(in srgb, var(--chip-color) 18%, transparent);
                color: var(--chip-color); border: 1px solid color-mix(in srgb, var(--chip-color) 35%, transparent);
            }

            /* Panels */
            .panel {
                background: white; border-radius: 18px; padding: 18px 20px;
                border: 1px solid #e2e8f0; box-shadow: 0 4px 24px rgba(15, 23, 42, 0.06);
                margin-bottom: 16px;
            }
            .panel-header {
                display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px;
                color: #0f172a; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid #f1f5f9;
            }
            .panel-icon {
                width: 28px; height: 28px; border-radius: 8px; display: inline-flex;
                align-items: center; justify-content: center; font-size: 14px;
                background: linear-gradient(135deg, #eef2ff, #e0e7ff);
            }

            /* Overview cards */
            .overview-card {
                background: white; border: 1px solid #e2e8f0; border-radius: 14px;
                padding: 14px 16px; min-height: 78px;
                box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04);
            }
            .overview-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }
            .overview-value { font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 4px; }
            .overview-sm { font-size: 13px !important; font-weight: 600 !important; word-break: break-all; }

            /* Status & decisions */
            .status-success, .status-error {
                display: inline-block; font-size: 12px; padding: 5px 12px; border-radius: 999px; margin-top: 8px;
            }
            .status-success { color: #059669; background: #ecfdf5; border: 1px solid #a7f3d0; }
            .status-error { color: #dc2626; background: #fef2f2; border: 1px solid #fecaca; }
            .priority-badge {
                display: inline-block; font-size: 11px; font-weight: 700; padding: 2px 8px;
                border-radius: 6px; border: 1px solid; margin-right: 8px; vertical-align: middle;
            }
            .decision-card {
                background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
                padding: 14px 16px; margin-bottom: 10px;
            }
            .decision-action { font-weight: 600; color: #0f172a; line-height: 1.5; }
            .decision-meta { font-size: 12px; color: #64748b; margin-top: 6px; line-height: 1.5; }

            /* Empty state */
            .empty-state {
                text-align: center; padding: 56px 24px; border-radius: 16px;
                background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
                border: 1px dashed #cbd5e1;
            }
            .empty-icon { font-size: 52px; margin-bottom: 12px; opacity: 0.9; }
            .empty-title { font-size: 18px; font-weight: 700; color: #334155; margin-bottom: 6px; }
            .empty-desc { font-size: 14px; color: #94a3b8; max-width: 360px; margin: 0 auto; line-height: 1.6; }

            /* Streamlit overrides */
            div[data-testid="stExpander"] {
                background: white; border: 1px solid #e2e8f0; border-radius: 14px;
                box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04); overflow: hidden;
            }
            div[data-testid="stExpander"] summary { font-weight: 600; color: #0f172a; }
            .stButton > button[kind="secondary"] {
                border-radius: 10px; border-color: #cbd5e1; font-weight: 500;
            }
            /* 表单「发送」按钮（覆盖 Streamlit 主题 primary 色） */
            .stFormSubmitButton button,
            [data-testid="stFormSubmitButton"] button {
                border-radius: 10px !important;
                font-weight: 600 !important;
                background: #dbeafe !important;
                background-image: none !important;
                color: #1d4ed8 !important;
                border: 1px solid #93c5fd !important;
                box-shadow: none !important;
            }
            .stFormSubmitButton button:hover,
            [data-testid="stFormSubmitButton"] button:hover {
                background: #bfdbfe !important;
                border-color: #60a5fa !important;
                color: #1e40af !important;
            }
            .stFormSubmitButton button:active,
            [data-testid="stFormSubmitButton"] button:active {
                background: #93c5fd !important;
                color: #1e3a8a !important;
            }
            button[kind="primaryFormSubmit"],
            button[kind="secondaryFormSubmit"],
            .stButton > button[kind="primary"],
            .stButton > button[data-testid="stBaseButton-primary"] {
                border-radius: 10px !important;
                font-weight: 600 !important;
                background: #dbeafe !important;
                background-image: none !important;
                color: #1d4ed8 !important;
                border: 1px solid #93c5fd !important;
                box-shadow: none !important;
            }
            div[data-testid="stTextInput"] input {
                border-radius: 12px; border-color: #e2e8f0;
            }
            div[data-testid="stTextInput"] input:focus {
                border-color: #93c5fd; box-shadow: 0 0 0 3px rgba(147, 197, 253, 0.35);
            }
            .quick-label { font-size: 12px; font-weight: 600; color: #64748b; margin: 12px 0 6px; }

            @media (max-width: 768px) {
                .block-container { padding-top: 0.8rem; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    """Main Streamlit app entry."""
    st.set_page_config(
        page_title="Agentic BI 电商智能分析系统",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()
    inject_global_styles()
    render_sidebar()

    col1, col2 = st.columns([1, 1.45], gap="large")

    with col1:
        st.markdown(
            '<div class="panel"><div class="panel-header"><span class="panel-icon">💬</span>智能对话</div>',
            unsafe_allow_html=True,
        )
        render_chat_panel(st.session_state.messages, st.session_state.is_typing)

        if st.session_state.last_send_status == "success":
            st.markdown('<span class="status-success">✓ 分析完成</span>', unsafe_allow_html=True)
        elif st.session_state.last_send_status == "error":
            error_text = _esc(st.session_state.last_error_message or "请重试")
            st.markdown(f'<span class="status-error">✗ {error_text}</span>', unsafe_allow_html=True)

        with st.form(key="question_form", clear_on_submit=True):
            col_input, col_button = st.columns([4, 1])
            with col_input:
                user_input = st.text_input(
                    "输入您的问题:",
                    placeholder="例如：预测未来 6 周 GMV，并给出趋势解读",
                    label_visibility="collapsed",
                    key="input_text",
                )
            with col_button:
                submit_button = st.form_submit_button(
                    label="发送",
                    use_container_width=True,
                    type="secondary",
                    disabled=st.session_state.is_typing,
                )

        if submit_button:
            question = user_input.strip()
            if question:
                questions = split_questions(question)
                st.session_state.messages.append({"content": question, "is_user": True})
                st.session_state.last_send_status = None

                if len(questions) == 1:
                    with st.spinner("Agent 协作分析中，请稍候..."):
                        result = ask_question(questions[0])
                    if result:
                        st.session_state.messages.append({
                            "content": result.get("final_answer", "暂无分析结果"),
                            "is_user": False,
                        })
                        st.session_state.last_result = result
                else:
                    batch_answers = []
                    with st.spinner(f"检测到 {len(questions)} 个问题，逐个分析中..."):
                        for idx, item in enumerate(questions, 1):
                            result = ask_question(item)
                            if not result:
                                error_text = st.session_state.last_error_message or "未知错误"
                                batch_answers.append(f"问题{idx}: {item}\n分析失败：{error_text}")
                                break
                            batch_answers.append(
                                f"问题{idx}: {item}\n{result.get('final_answer', '暂无分析结果')}"
                            )
                            st.session_state.last_result = result
                    if batch_answers:
                        st.session_state.messages.append({"content": "\n\n".join(batch_answers), "is_user": False})
                st.rerun()
            else:
                st.session_state.last_send_status = "error"
                st.session_state.last_error_message = "请输入问题"
                st.rerun()

        st.markdown('<p class="quick-label">快捷提问</p>', unsafe_allow_html=True)
        quick_questions = [
            "2017年GMV按月趋势如何？",
            "各品类销售排名",
            "预测未来6周GMV",
            "Top 10 差评品类及原因",
        ]
        qcols = st.columns(2)
        for i, q in enumerate(quick_questions):
            with qcols[i % 2]:
                if st.button(q, key=f"quick_{i}", use_container_width=True):
                    st.session_state.messages.append({"content": q, "is_user": True})
                    st.session_state.last_send_status = None
                    with st.spinner("Agent 协作分析中，请稍候..."):
                        result = ask_question(q)
                    if result:
                        st.session_state.messages.append({
                            "content": result.get("final_answer", "暂无分析结果"),
                            "is_user": False,
                        })
                        st.session_state.last_result = result
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown(
            '<div class="panel"><div class="panel-header"><span class="panel-icon">📈</span>分析结果</div>',
            unsafe_allow_html=True,
        )

        if "last_result" in st.session_state:
            result = st.session_state.last_result
            render_analysis_overview(result)

            if result.get("final_answer"):
                with st.expander("📋 总结回答", expanded=st.session_state.expanded_sections.get("summary", True)):
                    st.markdown(result["final_answer"])

            display_sql_result(result)

            with st.expander("🎨 可视化图表", expanded=st.session_state.expanded_sections.get("visualization", True)):
                display_visualization(result)

            display_what_if_result(result)
            display_nlp_result(result)
            display_forecast_result(result)
            display_decision_result(result)
        else:
            st.markdown(
                """
                <div class="empty-state">
                    <div class="empty-icon">🔍</div>
                    <div class="empty-title">等待你的第一个问题</div>
                    <p class="empty-desc">在左侧输入自然语言问题，系统将自动完成 SQL 查询、图表渲染、预测与决策建议</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
