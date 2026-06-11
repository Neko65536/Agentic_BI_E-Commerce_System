"""
Streamlit Web UI for Agentic BI E-Commerce System.

成员D负责：Web前端界面、图表展示、多轮问答
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
import streamlit as st
from streamlit_chat import message

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
                    "seller_label",
                    "seller_id",
                ]
                preferred_metrics = [
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
                    fig = px.bar(df, x=x_col, y=y_cols,
                                 title=chart.get("chart_title", "数据对比"),
                                 labels={x_col: x_col},
                                 template="plotly_white")
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
                numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
                
                if numeric_cols:
                    fig = px.scatter(df, 
                                     x=numeric_cols[0], 
                                     y=numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0],
                                     size=numeric_cols[0],
                                     color=state_col,
                                     title=chart.get("chart_title", "地理分布"),
                                     labels={state_col: "州"},
                                     template="plotly_white")
                    fig.update_layout(height=350)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.markdown("📍 **巴西各州数据分布**")
                    st.dataframe(df[[state_col] + numeric_cols[:3]])
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


def display_decision_result(result: dict):
    """Display decision/recommendation results with collapsible section."""
    decision_result = result.get("decision_result")
    if decision_result:
        with st.expander("🎯 决策建议", expanded=st.session_state.expanded_sections.get("decision", True)):
            if "business_problem" in decision_result:
                st.markdown(f"**识别的业务问题:** {decision_result['business_problem']}")
            
            if "recommendations" in decision_result:
                st.markdown("**运营建议:**")
                for i, rec in enumerate(decision_result["recommendations"][:5], 1):
                    if isinstance(rec, dict):
                        suggestion = rec.get("suggestion", rec.get("recommendation", str(rec)))
                        priority = rec.get("priority", "")
                        if priority:
                            st.write(f"{i}. **{suggestion}** (优先级: {priority})")
                        else:
                            st.write(f"{i}. {suggestion}")
                    else:
                        st.write(f"{i}. {rec}")
            
            if "priority" in decision_result:
                st.markdown(f"**整体优先级:** {decision_result['priority']}")
            
            if "expected_impact" in decision_result:
                st.markdown(f"**预期影响:** {decision_result['expected_impact']}")


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


def main():
    """Main Streamlit app entry."""
    init_session_state()
    
    st.set_page_config(
        page_title="Agentic BI 电商智能分析系统",
        page_icon="📊",
        layout="wide"
    )
    
    # Professional CSS styling for chat interface
    st.markdown("""
        <style>
            /* Base styles */
            * {
                box-sizing: border-box;
            }
            
            /* Chat container */
            .chat-container {
                background: linear-gradient(180deg, #fafbfc 0%, #f1f5f9 100%);
                border-radius: 20px;
                padding: 16px;
                min-height: 200px;
                max-height: 450px;
                overflow-y: auto;
                scrollbar-width: thin;
                scrollbar-color: #cbd5e1 #e2e8f0;
                position: relative;
            }
            
            .chat-container::-webkit-scrollbar {
                width: 6px;
            }
            
            .chat-container::-webkit-scrollbar-track {
                background: #e2e8f0;
                border-radius: 3px;
            }
            
            .chat-container::-webkit-scrollbar-thumb {
                background: #cbd5e1;
                border-radius: 3px;
            }
            
            /* Message wrapper */
            .message-wrapper {
                display: flex;
                margin-bottom: 12px;
                animation: fadeInUp 0.3s ease-out;
            }
            
            @keyframes fadeInUp {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            /* Avatar styling */
            .avatar {
                width: 36px;
                height: 36px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                font-size: 16px;
                font-weight: 600;
                margin-right: 10px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            
            .user-avatar {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            
            .bot-avatar {
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
            }
            
            /* Message bubble */
            .message-bubble {
                max-width: 85%;
                padding: 12px 16px;
                border-radius: 20px;
                position: relative;
                line-height: 1.5;
                font-size: 14px;
                word-wrap: break-word;
            }
            
            /* User message */
            .user-message-wrapper {
                justify-content: flex-end;
            }
            
            .user-message-wrapper .avatar {
                order: 2;
                margin-right: 0;
                margin-left: 10px;
            }
            
            .user-message-bubble {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 20px 20px 4px 20px;
                box-shadow: 0 4px 16px rgba(102, 126, 234, 0.35);
            }
            
            .user-message-bubble p {
                margin: 0;
                color: rgba(255, 255, 255, 0.95);
            }
            
            /* Bot message */
            .bot-message-wrapper {
                justify-content: flex-start;
            }
            
            .bot-message-bubble {
                background: white;
                color: #1e293b;
                border-radius: 20px 20px 20px 4px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
                border: 1px solid #e2e8f0;
            }
            
            .bot-message-bubble p {
                margin: 0;
                color: #334155;
            }
            
            /* Message metadata */
            .message-meta {
                display: flex;
                align-items: center;
                margin-top: 4px;
                font-size: 12px;
                opacity: 0.7;
            }
            
            .user-message-wrapper .message-meta {
                justify-content: flex-end;
            }
            
            .bot-message-wrapper .message-meta {
                justify-content: flex-start;
            }
            
            /* Typing indicator */
            .typing-indicator {
                display: flex;
                align-items: center;
                padding: 12px 16px;
                background: white;
                border-radius: 20px 20px 20px 4px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
                max-width: 120px;
            }
            
            .typing-dots {
                display: flex;
                gap: 4px;
            }
            
            .typing-dot {
                width: 8px;
                height: 8px;
                background: #94a3b8;
                border-radius: 50%;
                animation: typingBounce 1.4s infinite ease-in-out;
            }
            
            .typing-dot:nth-child(1) { animation-delay: 0s; }
            .typing-dot:nth-child(2) { animation-delay: 0.2s; }
            .typing-dot:nth-child(3) { animation-delay: 0.4s; }
            
            @keyframes typingBounce {
                0%, 80%, 100% {
                    transform: scale(0.6);
                    opacity: 0.5;
                }
                40% {
                    transform: scale(1);
                    opacity: 1;
                }
            }
            
            /* Input container */
            .input-container {
                background: white;
                border-radius: 16px;
                padding: 8px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                border: 1px solid #e2e8f0;
                margin-top: 8px;
                transition: all 0.3s ease;
            }
            
            .input-container:focus-within {
                border-color: #667eea;
                box-shadow: 0 4px 20px rgba(102, 126, 234, 0.2);
            }
            
            /* Send button */
            .send-btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 12px 24px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }
            
            .send-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
            }
            
            .send-btn:active {
                transform: translateY(0);
            }
            
            .send-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            
            /* Status indicators */
            .status-success {
                color: #10b981;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(16, 185, 129, 0.1);
                border-radius: 10px;
                display: inline-block;
                margin-top: 4px;
            }
            
            .status-error {
                color: #ef4444;
                font-size: 12px;
                padding: 4px 8px;
                background: rgba(239, 68, 68, 0.1);
                border-radius: 10px;
                display: inline-block;
                margin-top: 4px;
            }
            
            /* Section header */
            .section-header {
                font-weight: 600;
                color: #1e293b;
                padding: 10px 16px;
                background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
                border-radius: 12px;
                margin-bottom: 8px;
                display: flex;
                align-items: center;
                gap: 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
            }
            
            /* Result card */
            .result-card {
                background: white;
                border-radius: 16px;
                padding: 16px;
                margin-bottom: 8px;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
                border: 1px solid #e2e8f0;
                transition: all 0.3s ease;
            }
            
            .result-card:hover {
                box-shadow: 0 6px 24px rgba(0, 0, 0, 0.08);
            }
            
            /* Quick question buttons */
            .quick-question-btn {
                background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 12px;
                margin: 2px;
                cursor: pointer;
                transition: all 0.2s ease;
                font-size: 12px;
                color: #475569;
            }
            
            .quick-question-btn:hover {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-color: #667eea;
                color: white;
                transform: translateY(-1px);
            }
            
            /* Responsive design */
            @media (max-width: 768px) {
                .chat-container {
                    min-height: 150px;
                    max-height: 350px;
                    padding: 12px;
                }
                
                .message-bubble {
                    max-width: 90%;
                    padding: 12px 14px;
                }
                
                .avatar {
                    width: 32px;
                    height: 32px;
                    font-size: 14px;
                }
            }
            
            /* Reduce Streamlit default spacing */
            .stVerticalBlock {
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }
            
            div[data-testid="stVerticalBlock"] > div {
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }
            
            .stButton > button {
                margin-top: 0 !important;
                margin-bottom: 0 !important;
            }
            
            .stForm {
                padding: 0 !important;
            }
            
            .stColumns {
                gap: 8px !important;
            }
            
            /* Reduce header spacing */
            h1 {
                margin-bottom: 0.5rem !important;
            }
            
            .stMarkdown {
                margin-bottom: 0 !important;
            }
            
            hr {
                margin-top: 0.5rem !important;
                margin-bottom: 0.5rem !important;
            }
        </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.title("📊 Agentic BI 电商智能分析系统")
    st.markdown("基于大语言模型的电商数据分析智能体系统")
    st.divider()
    
    # Main layout with two columns
    col1, col2 = st.columns([1, 1.5], gap="large")
    
    with col1:
        # Chat section header
        st.markdown('<div class="section-header"><span>💬</span>对话</div>', unsafe_allow_html=True)
        
        # Chat container with styled messages
        st.markdown('<div class="chat-container" id="chat-messages">', unsafe_allow_html=True)
        
        if st.session_state.messages:
            for i, msg in enumerate(st.session_state.messages):
                if msg["is_user"]:
                    # User message with avatar
                    st.markdown(f'''
                        <div class="message-wrapper user-message-wrapper">
                            <div class="message-bubble user-message-bubble">
                                <p>{msg["content"]}</p>
                            </div>
                            <div class="avatar user-avatar">👤</div>
                        </div>
                    ''', unsafe_allow_html=True)
                else:
                    # Bot message with avatar
                    st.markdown(f'''
                        <div class="message-wrapper bot-message-wrapper">
                            <div class="avatar bot-avatar">🤖</div>
                            <div class="message-bubble bot-message-bubble">
                                <p>{msg["content"]}</p>
                            </div>
                        </div>
                    ''', unsafe_allow_html=True)
        
        # Typing indicator
        if st.session_state.is_typing:
            st.markdown('''
                <div class="message-wrapper bot-message-wrapper">
                    <div class="avatar bot-avatar">🤖</div>
                    <div class="typing-indicator">
                        <div class="typing-dots">
                            <span class="typing-dot"></span>
                            <span class="typing-dot"></span>
                            <span class="typing-dot"></span>
                        </div>
                    </div>
                </div>
            ''', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Status feedback
        if st.session_state.last_send_status == "success":
            st.markdown('<span class="status-success">✓ 发送成功</span>', unsafe_allow_html=True)
        elif st.session_state.last_send_status == "error":
            error_text = st.session_state.last_error_message or "请重试"
            st.markdown(f'<span class="status-error">✗ 发送失败：{error_text}</span>', unsafe_allow_html=True)
        
        # Input area with professional styling
        st.markdown('<div class="input-container">', unsafe_allow_html=True)
        with st.form(key="question_form", clear_on_submit=True):
            col_input, col_button = st.columns([4, 1])
            
            with col_input:
                user_input = st.text_input(
                    "输入您的问题:",
                    placeholder="例如：2017年GMV按月趋势如何？",
                    label_visibility="collapsed",
                    key="input_text"
                )
            
            with col_button:
                submit_button = st.form_submit_button(
                    label="发送",
                    use_container_width=True,
                    type="primary",
                    disabled=st.session_state.is_typing
                )

        if submit_button:
            question = user_input.strip()
            if question:
                questions = split_questions(question)
                st.session_state.messages.append({"content": question, "is_user": True})
                st.session_state.last_send_status = None

                if len(questions) == 1:
                    with st.spinner("分析中..."):
                        result = ask_question(questions[0])

                    if result:
                        final_answer = result.get("final_answer", "暂无分析结果")
                        st.session_state.messages.append({"content": final_answer, "is_user": False})
                        st.session_state.last_result = result
                else:
                    batch_answers = []
                    with st.spinner(f"检测到{len(questions)}个问题，正在逐个分析..."):
                        for idx, item in enumerate(questions, 1):
                            result = ask_question(item)
                            if not result:
                                error_text = st.session_state.last_error_message or "未知错误"
                                batch_answers.append(f"问题{idx}: {item}\n分析失败：{error_text}")
                                break

                            final_answer = result.get("final_answer", "暂无分析结果")
                            batch_answers.append(f"问题{idx}: {item}\n{final_answer}")
                            st.session_state.last_result = result

                    if batch_answers:
                        st.session_state.messages.append({
                            "content": "\n\n".join(batch_answers),
                            "is_user": False,
                        })

                st.rerun()
            else:
                st.session_state.last_send_status = "error"
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Quick questions with improved styling
        st.markdown('<div style="margin-top: 8px;">', unsafe_allow_html=True)
        st.markdown("<span style='font-size: 12px; font-weight: 500; color: #64748b;'>快捷问题:</span>", unsafe_allow_html=True)
        
        quick_questions = [
            "2017年GMV趋势",
            "各品类销售排名",
            "客户满意度分析",
            "预测未来销售额"
        ]
        
        cols = st.columns(2)
        for i, q in enumerate(quick_questions):
            with cols[i % 2]:
                if st.button(q, key=f"quick_{i}", use_container_width=True):
                    st.session_state.messages.append({"content": q, "is_user": True})
                    st.session_state.last_send_status = None
                    
                    with st.spinner("分析中..."):
                        result = ask_question(q)
                    
                    if result:
                        final_answer = result.get("final_answer", "暂无分析结果")
                        st.session_state.messages.append({"content": final_answer, "is_user": False})
                        st.session_state.last_result = result
                        st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        # Results section
        st.markdown('<div class="section-header"><span>📈</span>分析结果</div>', unsafe_allow_html=True)
        
        if "last_result" in st.session_state:
            result = st.session_state.last_result
            
            # Summary card
            if result.get("final_answer"):
                with st.expander("📋 总结回答", expanded=st.session_state.expanded_sections.get("summary", True)):
                    st.markdown('<div class="result-card">', unsafe_allow_html=True)
                    st.markdown(f"<p style='line-height: 1.8; color: #1e293b;'>{result['final_answer']}</p>", unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
            
            # SQL result
            display_sql_result(result)
            
            # Visualization
            with st.expander("🎨 可视化图表", expanded=st.session_state.expanded_sections.get("visualization", True)):
                display_visualization(result)
            
            # NLP result
            display_nlp_result(result)
            
            # Forecast result
            display_forecast_result(result)
            
            # Decision result
            display_decision_result(result)
        else:
            st.markdown('<div class="result-card" style="text-align: center; padding: 60px 20px;">', unsafe_allow_html=True)
            st.markdown("""
                <div style="font-size: 56px; margin-bottom: 20px;">🔍</div>
                <h3 style="color: #475569; margin-bottom: 8px;">开始数据分析</h3>
                <p style="color: #94a3b8; font-size: 14px;">在左侧对话框中输入您的问题，系统将自动进行分析并展示可视化结果</p>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
