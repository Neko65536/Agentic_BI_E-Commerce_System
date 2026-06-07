"""
Chart Renderer - 图表渲染器

支持六类图表：
1. 时间序列折线图
2. 地理热力图或气泡图
3. 柱状图或条形图
4. 热力图或矩阵图
5. 散点图或气泡图
6. 词云或文本主题图
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


class ChartRenderer:
    """图表渲染器类"""
    
    def __init__(self, output_dir: str = "outputs/charts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _safe_filename(self, text: str) -> str:
        """生成安全的文件名"""
        slug = re.sub(r"[^0-9A-Za-z_\-]+", "_", text).strip("_")
        return (slug or "chart")[:70]
    
    def _format_value(self, value: Any) -> str:
        """格式化数值显示"""
        if isinstance(value, (int, float)):
            if abs(value) >= 1000:
                return f"{value:,.2f}"
            return f"{value:.4g}"
        return str(value)
    
    def render_line_chart(self, data: list[dict], title: str = "时间序列图") -> dict:
        """渲染时间序列折线图"""
        df = pd.DataFrame(data)
        time_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ["month", "date", "week", "time"])]
        
        if not time_cols:
            return {"success": False, "error": "未找到时间字段"}
        
        time_col = time_cols[0]
        numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
        
        if not numeric_cols:
            return {"success": False, "error": "未找到数值字段"}
        
        chart_data = {
            "chart_type": "line_chart",
            "title": title,
            "x_label": time_col,
            "data": {
                "labels": df[time_col].tolist(),
                "datasets": [
                    {"label": col, "data": df[col].tolist()}
                    for col in numeric_cols[:3]
                ]
            }
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True,
            "chart_type": "line_chart",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"时间序列图展示了{len(data)}个时间点的数据变化趋势",
            "data": chart_data
        }
    
    def render_bar_chart(self, data: list[dict], title: str = "柱状图") -> dict:
        """渲染柱状图"""
        df = pd.DataFrame(data)
        cat_cols = [col for col in df.columns if df[col].dtype not in ["int64", "float64", "datetime64"]]
        numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
        
        if not cat_cols or not numeric_cols:
            return {"success": False, "error": "缺少分类或数值字段"}
        
        chart_data = {
            "chart_type": "bar_chart",
            "title": title,
            "x_label": cat_cols[0],
            "data": {
                "labels": df[cat_cols[0]].tolist(),
                "datasets": [
                    {"label": col, "data": df[col].tolist()}
                    for col in numeric_cols[:3]
                ]
            }
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True,
            "chart_type": "bar_chart",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"柱状图展示了{len(data)}个类别的对比",
            "data": chart_data
        }
    
    def render_geo_bubble(self, data: list[dict], title: str = "地理气泡图") -> dict:
        """渲染地理气泡图"""
        df = pd.DataFrame(data)
        
        state_col = None
        for col in ["customer_state", "seller_state", "geolocation_state", "state"]:
            if col in df.columns:
                state_col = col
                break
        
        if not state_col:
            return {"success": False, "error": "未找到州/地区字段"}
        
        numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
        if not numeric_cols:
            return {"success": False, "error": "未找到数值字段"}
        
        # 巴西州坐标
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
        
        bubble_data = []
        for _, row in df.iterrows():
            state = str(row[state_col]).upper()
            if state in state_coords:
                lng, lat = state_coords[state]
                bubble_data.append({
                    "state": state,
                    "latitude": lat,
                    "longitude": lng,
                    "value": row[numeric_cols[0]]
                })
        
        chart_data = {
            "chart_type": "geographic_bubble_map",
            "title": title,
            "data": bubble_data,
            "metric": numeric_cols[0]
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True,
            "chart_type": "geographic_bubble_map",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"地理气泡图展示了巴西{len(bubble_data)}个州的数据分布",
            "data": chart_data
        }
    
    def render_heatmap(self, data: list[dict], title: str = "热力图") -> dict:
        """渲染矩阵热力图"""
        df = pd.DataFrame(data)
        cat_cols = [col for col in df.columns if df[col].dtype not in ["int64", "float64"]]
        numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
        
        if len(cat_cols) < 2 or not numeric_cols:
            return {"success": False, "error": "需要至少两个分类字段和一个数值字段"}
        
        pivot_df = df.pivot(
            index=cat_cols[0],
            columns=cat_cols[1],
            values=numeric_cols[0]
        ).fillna(0)
        
        chart_data = {
            "chart_type": "matrix_heatmap",
            "title": title,
            "x_labels": pivot_df.columns.tolist(),
            "y_labels": pivot_df.index.tolist(),
            "values": pivot_df.values.tolist(),
            "metric": numeric_cols[0]
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True,
            "chart_type": "matrix_heatmap",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"热力图展示了{cat_cols[0]}与{cat_cols[1]}的交叉分析",
            "data": chart_data
        }
    
    def render_scatter_chart(self, data: list[dict], title: str = "散点图") -> dict:
        """渲染散点图/气泡图"""
        df = pd.DataFrame(data)
        numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
        
        if len(numeric_cols) < 2:
            return {"success": False, "error": "需要至少两个数值字段"}
        
        size_col = None
        if len(numeric_cols) >= 3:
            size_col = numeric_cols[2]
        
        color_col = None
        cat_cols = [col for col in df.columns if df[col].dtype not in ["int64", "float64"]]
        if cat_cols:
            color_col = cat_cols[0]
        
        chart_data = {
            "chart_type": "scatter_bubble_chart",
            "title": title,
            "x_label": numeric_cols[0],
            "y_label": numeric_cols[1],
            "size_label": size_col,
            "color_label": color_col,
            "data": []
        }
        
        for _, row in df.iterrows():
            point = {
                "x": row[numeric_cols[0]],
                "y": row[numeric_cols[1]]
            }
            if size_col:
                point["size"] = row[size_col]
            if color_col:
                point["color"] = row[color_col]
            chart_data["data"].append(point)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True,
            "chart_type": "scatter_bubble_chart",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"散点图展示了{len(data)}个数据点的分布关系",
            "data": chart_data
        }
    
    def render_word_cloud(self, words: list[dict | tuple], title: str = "词云") -> dict:
        """渲染词云图"""
        word_list = []
        for item in words:
            if isinstance(item, dict):
                word = item.get("keyword", item.get("word", ""))
                count = item.get("count", 0)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                word, count = item[0], item[1]
            else:
                continue
            if word:
                word_list.append({"word": str(word), "count": int(count) if count else 1})
        
        if not word_list:
            return {"success": False, "error": "没有可展示的关键词"}
        
        max_count = max([w["count"] for w in word_list])
        
        chart_data = {
            "chart_type": "word_cloud",
            "title": title,
            "data": word_list,
            "max_count": max_count
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        top_word = word_list[0]["word"] if word_list else "无"
        
        return {
            "success": True,
            "chart_type": "word_cloud",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"词云展示{len(word_list)}个关键词，最高频为{top_word}",
            "data": chart_data
        }
    
    def render_big_number(self, data: list[dict], title: str = "关键指标") -> dict:
        """渲染大数字卡片"""
        if not data or len(data) != 1:
            return {"success": False, "error": "大数字卡片需要且仅需要一行数据"}
        
        row = data[0]
        numeric_cols = [col for col in row if isinstance(row[col], (int, float))]
        
        if not numeric_cols:
            return {"success": False, "error": "未找到数值字段"}
        
        chart_data = {
            "chart_type": "big_number_card",
            "title": title,
            "metric": numeric_cols[0],
            "value": row[numeric_cols[0]],
            "formatted_value": self._format_value(row[numeric_cols[0]])
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True,
            "chart_type": "big_number_card",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"关键指标{numeric_cols[0]}的值为{chart_data['formatted_value']}",
            "data": chart_data
        }
    
    def render_table(self, data: list[dict], title: str = "数据表格") -> dict:
        """渲染数据表格"""
        if not data:
            return {"success": False, "error": "没有可展示的数据"}
        
        chart_data = {
            "chart_type": "table",
            "title": title,
            "columns": list(data[0].keys()),
            "data": data[:50]
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{self._safe_filename(title)}.json"
        filepath = self.output_dir / filename
        filepath.write_text(json.dumps(chart_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "success": True,
            "chart_type": "table",
            "chart_path": str(filepath),
            "chart_title": title,
            "chart_insight": f"表格展示了{len(data)}行数据的前50行",
            "data": chart_data
        }
    
    def infer_and_render(self, data: list[dict], question: str = "", recommended_type: str = None) -> dict:
        """根据数据和问题自动推断并渲染图表"""
        if not data:
            return self.render_table(data, title=f"{question[:30]}-数据表格")
        
        df = pd.DataFrame(data)
        
        if recommended_type:
            chart_func = {
                "line_chart": self.render_line_chart,
                "bar_chart": self.render_bar_chart,
                "geographic_bubble_map": self.render_geo_bubble,
                "matrix_heatmap": self.render_heatmap,
                "scatter_bubble_chart": self.render_scatter_chart,
                "word_cloud": self.render_word_cloud,
                "big_number_card": self.render_big_number,
                "table": self.render_table
            }.get(recommended_type)
            
            if chart_func:
                return chart_func(data, title=f"{question[:30]}-{recommended_type}")
        
        if len(data) == 1:
            return self.render_big_number(data, title=f"{question[:30]}-关键指标")
        
        time_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ["month", "date", "week", "time"])]
        if time_cols:
            return self.render_line_chart(data, title=f"{question[:30]}-时间序列")
        
        state_cols = ["customer_state", "seller_state", "geolocation_state", "state"]
        if any(col in df.columns for col in state_cols):
            return self.render_geo_bubble(data, title=f"{question[:30]}-地理分布")
        
        cat_cols = [col for col in df.columns if df[col].dtype not in ["int64", "float64"]]
        numeric_cols = [col for col in df.columns if df[col].dtype in ["int64", "float64"]]
        
        if len(cat_cols) >= 2 and numeric_cols:
            return self.render_heatmap(data, title=f"{question[:30]}-热力图")
        
        if len(numeric_cols) >= 2:
            return self.render_scatter_chart(data, title=f"{question[:30]}-散点图")
        
        if cat_cols and numeric_cols:
            return self.render_bar_chart(data, title=f"{question[:30]}-柱状图")
        
        return self.render_table(data, title=f"{question[:30]}-数据表格")


if __name__ == "__main__":
    renderer = ChartRenderer()
    
    sample_data = [
        {"year_month": "2017-01", "total_gmv": 120000, "orders": 500},
        {"year_month": "2017-02", "total_gmv": 145000, "orders": 620},
        {"year_month": "2017-03", "total_gmv": 138000, "orders": 580},
        {"year_month": "2017-04", "total_gmv": 165000, "orders": 720},
        {"year_month": "2017-05", "total_gmv": 152000, "orders": 650},
    ]
    
    result = renderer.render_line_chart(sample_data, "月度GMV趋势")
    print(json.dumps(result, ensure_ascii=False, indent=2))