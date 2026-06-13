"""Generate polished architecture diagrams for the project report."""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

OUT_DIR = Path(__file__).resolve().parent
FONT = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans", "sans-serif"]

# Modern palette
C = {
    "title": "#0f172a",
    "sub": "#475569",
    "edge": "#cbd5e1",
    "arrow": "#64748b",
    "bg": "#ffffff",
    "layers": ["#eff6ff", "#eef2ff", "#f5f3ff", "#fdf2f8", "#ecfdf5"],
    "node_blue": "#dbeafe",
    "node_indigo": "#e0e7ff",
    "node_purple": "#ede9fe",
    "node_pink": "#fce7f3",
    "node_green": "#dcfce7",
    "node_amber": "#fef3c7",
    "node_slate": "#f1f5f9",
    "accent": ["#2563eb", "#4f46e5", "#7c3aed", "#db2777", "#059669"],
}


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.sans-serif": FONT,
            "axes.unicode_minus": False,
            "figure.dpi": 200,
            "savefig.dpi": 200,
        }
    )


def save_fig(fig, name: str) -> None:
    for ext in ("png", "svg"):
        path = OUT_DIR / f"{name}.{ext}"
        fig.savefig(
            path,
            bbox_inches="tight",
            facecolor=C["bg"],
            edgecolor="none",
            pad_inches=0.35,
        )
        print(f"Saved: {path}")
    plt.close(fig)


def wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False))


def draw_shadow(ax, x, y, w, h, r=0.08, enabled: bool = True):
    if not enabled:
        return
    sh = FancyBboxPatch(
        (x + 0.04, y - 0.04),
        w,
        h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        linewidth=0,
        facecolor="#e2e8f0",
        alpha=0.45,
        zorder=1,
    )
    ax.add_patch(sh)


def draw_card(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    subtitle: str = "",
    face: str = "#f8fafc",
    accent: str = "#2563eb",
    title_size: float = 11,
    sub_size: float = 9,
    r: float = 0.1,
    shadow: bool = True,
):
    draw_shadow(ax, x, y, w, h, r, enabled=shadow)
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        linewidth=1.2,
        edgecolor=C["edge"],
        facecolor=face,
        zorder=2,
    )
    ax.add_patch(box)
    ax.add_patch(
        Rectangle((x, y), 0.12, h, facecolor=accent, edgecolor="none", zorder=3, clip_on=False)
    )
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            linewidth=0,
            facecolor="none",
            zorder=4,
        )
    )

    tx = x + w / 2 + 0.06
    if subtitle:
        ax.text(
            tx,
            y + h * 0.72,
            title,
            ha="center",
            va="center",
            fontsize=title_size,
            fontweight="bold",
            color=C["title"],
            zorder=5,
        )
        ax.text(
            tx,
            y + h * 0.28,
            subtitle,
            ha="center",
            va="center",
            fontsize=sub_size,
            color=C["sub"],
            linespacing=1.4,
            zorder=5,
        )
    else:
        ax.text(
            tx,
            y + h / 2,
            title,
            ha="center",
            va="center",
            fontsize=title_size,
            fontweight="bold",
            color=C["title"],
            zorder=5,
        )


def arrow_v(ax, x, y1, y2, color=None):
    ax.add_patch(
        FancyArrowPatch(
            (x, y1),
            (x, y2),
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.4,
            color=color or C["arrow"],
            zorder=1,
        )
    )


def arrow_h(ax, x1, x2, y, color=None):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y),
            (x2, y),
            arrowstyle="-|>",
            mutation_scale=11,
            linewidth=1.2,
            color=color or C["arrow"],
            zorder=1,
        )
    )


def diagram_41_layered_architecture() -> None:
    fig, ax = plt.subplots(figsize=(11, 12))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 12)
    ax.axis("off")
    ax.set_facecolor("#ffffff")
    ax.text(
        5.5,
        11.35,
        "图 4-1  Agentic BI 系统整体分层架构",
        ha="center",
        va="center",
        fontsize=17,
        fontweight="bold",
        color=C["title"],
    )

    layers = [
        (
            "①  用户界面层  ·  Streamlit",
            "左侧对话区  +  右侧可视化 / 分析结论 / 决策建议",
            "#dbeafe",
            C["accent"][0],
            1.05,
            0.5,
            False,
        ),
        (
            "②  API 层  ·  FastAPI",
            "/api/ask    /api/parse    /api/health",
            "#c7d2fe",
            C["accent"][1],
            0.95,
            1.4,
            True,  # 与下一层之间使用独立连接区
        ),
        (
            "③  Agent 编排层  ·  LangGraph",
            wrap(
                "parse → coordinator → data_analysis → package_downstream → "
                "forecast / nlp_review / what_if → visualization → decision → answer",
                44,
            ),
            "#ddd6fe",
            C["accent"][2],
            1.45,
            0.5,
            False,
        ),
        (
            "④  模型层  ·  models/",
            "forecast_model    sentiment_model    what_if_model",
            "#fbcfe8",
            C["accent"][3],
            0.95,
            0.5,
            False,
        ),
        (
            "⑤  数据层  ·  MySQL",
            "九张基表 (orders, order_items, …)  +  六张 mv_* 预聚合表",
            "#bbf7d0",
            C["accent"][4],
            0.95,
            0.0,
            False,
        ),
    ]

    x, w, cx = 0.8, 9.4, 5.5
    y_top = 10.05
    prev_bottom: float | None = None
    pending_bridge = False

    for title, sub, face, accent, h, gap_after, bridge_after in layers:
        y_bottom = y_top - h

        if prev_bottom is not None:
            curr_top = y_bottom + h
            if pending_bridge:
                z_top = prev_bottom - 0.05
                z_bot = curr_top + 0.05
                ax.add_patch(
                    FancyBboxPatch(
                        (x + 0.2, z_bot),
                        w - 0.4,
                        z_top - z_bot,
                        boxstyle="round,pad=0,rounding_size=0.08",
                        linewidth=1.2,
                        edgecolor="#64748b",
                        facecolor="#ffffff",
                        linestyle=(0, (5, 3)),
                        zorder=0,
                    )
                )
                mid = (z_top + z_bot) / 2
                arrow_v(ax, cx, z_top, mid + 0.18, color="#334155")
                ax.text(
                    cx,
                    mid,
                    "HTTP 调用\nPOST /api/ask  →  触发 LangGraph 编排",
                    ha="center",
                    va="center",
                    fontsize=9.5,
                    color="#334155",
                    fontweight="bold",
                    linespacing=1.35,
                    zorder=5,
                )
                arrow_v(ax, cx, mid - 0.18, z_bot, color="#334155")
            else:
                arrow_v(ax, cx, prev_bottom - 0.06, curr_top + 0.06)

        draw_card(
            ax, x, y_bottom, w, h, title, sub, face, accent,
            title_size=12.5, sub_size=9.5,
        )

        prev_bottom = y_bottom
        pending_bridge = bridge_after
        y_top = y_bottom - gap_after

    save_fig(fig, "fig_4_1_layered_architecture")


def diagram_43_langgraph_workflow() -> None:
    fig, ax = plt.subplots(figsize=(10, 15))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 15)
    ax.axis("off")
    ax.text(
        5,
        14.55,
        "图 4-2  LangGraph 多 Agent 工作流",
        ha="center",
        va="center",
        fontsize=17,
        fontweight="bold",
        color=C["title"],
    )

    cx, nw, nh = 5.0, 4.6, 0.82
    y = 13.55

    main_nodes = [
        ("用户提问", "", C["node_amber"], C["accent"][0], 0.72),
        ("parse_question", "规范化问题文本", C["node_blue"], C["accent"][0], nh),
        ("coordinator_plan", wrap("意图识别 / 分析类型 / 任务拆解", 18), C["node_blue"], C["accent"][1], nh),
        ("data_analysis", "NL → SQL → 执行 → 摘要", C["node_indigo"], C["accent"][1], nh),
        ("package_downstream", "打包结构化数据", C["node_indigo"], C["accent"][2], nh),
    ]

    prev_bottom = None
    for title, sub, face, accent, h in main_nodes:
        draw_card(ax, cx - nw / 2, y - h, nw, h, title, sub, face, accent, title_size=11, sub_size=8.8)
        if prev_bottom is not None:
            arrow_v(ax, cx, prev_bottom - 0.06, y + 0.06)
        prev_bottom = y - h
        y = prev_bottom - 0.38

    # Branch group box
    group_y = y - 0.15
    group_h = 1.55
    group_w = 8.6
    group_x = 0.7
    draw_shadow(ax, group_x, group_y - group_h, group_w, group_h, 0.12)
    gbox = FancyBboxPatch(
        (group_x, group_y - group_h),
        group_w,
        group_h,
        boxstyle="round,pad=0,rounding_size=0.12",
        linewidth=1.2,
        edgecolor="#c4b5fd",
        facecolor="#faf5ff",
        linestyle="--",
        zorder=2,
    )
    ax.add_patch(gbox)
    ax.text(
        5,
        group_y - 0.18,
        "并行分支（按问题类型条件触发）",
        ha="center",
        va="center",
        fontsize=9.5,
        color="#6d28d9",
        fontweight="bold",
        zorder=5,
    )

    arrow_v(ax, cx, prev_bottom - 0.06, group_y + 0.06)

    bw, bh = 2.35, 0.78
    branch_y = group_y - group_h + 0.42
    branches = [
        (2.05, "forecast", "销售预测", C["node_pink"], C["accent"][3]),
        (5.0, "nlp_review", "评论 NLP", C["node_pink"], C["accent"][3]),
        (7.95, "what_if", "假设模拟", C["node_pink"], C["accent"][3]),
    ]
    branch_tops = []
    for bx, title, sub, face, accent in branches:
        draw_card(ax, bx - bw / 2, branch_y, bw, bh, title, sub, face, accent, title_size=10.5, sub_size=8.5)
        branch_tops.append(branch_y + bh)
        arrow_v(ax, bx, group_y - 0.06, branch_y + bh + 0.06, color="#a78bfa")

    y = branch_y - 0.45
    merge_top = y
    for bx, *_ in branches:
        arrow_v(ax, bx, branch_y - 0.06, merge_top + 0.06, color="#a78bfa")

    tail_nodes = [
        ("visualization", "图表推荐与生成", C["node_purple"], C["accent"][2], nh),
        ("decision", wrap("运营建议 (P0 / P1 / P2)", 20), C["node_green"], C["accent"][4], nh),
        ("final_answer", "整合输出", C["node_amber"], C["accent"][0], nh),
        ("END", "", C["node_slate"], "#94a3b8", 0.68),
    ]

    prev_bottom = merge_top
    for title, sub, face, accent, h in tail_nodes:
        y = prev_bottom - 0.38 - h
        draw_card(ax, cx - nw / 2, y, nw, h, title, sub, face, accent, title_size=11, sub_size=8.8)
        arrow_v(ax, cx, prev_bottom - 0.06, y + h + 0.06)
        prev_bottom = y

    save_fig(fig, "fig_4_2_langgraph_workflow")


def diagram_62_data_analysis_pipeline() -> None:
    fig, ax = plt.subplots(figsize=(14.5, 6.4))
    ax.set_xlim(0, 14.5)
    ax.set_ylim(0, 6.4)
    ax.axis("off")
    ax.text(
        7.25,
        5.85,
        "图 6-1  数据分析 Agent 核心功能链",
        ha="center",
        va="center",
        fontsize=17,
        fontweight="bold",
        color=C["title"],
    )
    ax.text(
        7.25,
        5.45,
        "执行失败时：LLM 自动修复 SQL 并重试；高频问题启用 deterministic_required_view_plan 兜底",
        ha="center",
        va="center",
        fontsize=8.8,
        color="#64748b",
        style="italic",
    )

    phases = [
        ("输入", [("用户\n问题", C["node_amber"], C["accent"][0])]),
        ("SQL 计划", [("generate\nsql_plan", C["node_blue"], C["accent"][0])]),
        (
            "六层校验",
            [
                ("readonly\n校验", C["node_indigo"], C["accent"][1]),
                ("distribution\n粒度", C["node_indigo"], C["accent"][1]),
                ("视图\n覆盖", C["node_purple"], C["accent"][2]),
                ("诊断\n信号", C["node_purple"], C["accent"][2]),
            ],
        ),
        ("执行", [("execute\nsql", C["node_blue"], C["accent"][0])]),
        (
            "输出",
            [
                ("normalize", C["node_green"], C["accent"][4]),
                ("summarize", C["node_green"], C["accent"][4]),
            ],
        ),
    ]

    y_base = 2.05
    box_h = 1.0
    box_w = 1.15
    gap_x = 0.16
    phase_gap = 0.38
    label_h = 0.36
    pad_x = 0.2

    x = 0.25
    phase_boxes = []

    for phase_name, nodes in phases:
        n = len(nodes)
        phase_w = pad_x * 2 + n * box_w + max(0, n - 1) * gap_x
        inner_h = box_h + 0.18
        total_h = label_h + inner_h + 0.12

        draw_shadow(ax, x, y_base, phase_w, total_h, 0.08)
        pbox = FancyBboxPatch(
            (x, y_base),
            phase_w,
            total_h,
            boxstyle="round,pad=0,rounding_size=0.08",
            linewidth=1.0,
            edgecolor=C["edge"],
            facecolor="#f8fafc",
            zorder=1,
        )
        ax.add_patch(pbox)
        ax.text(
            x + phase_w / 2,
            y_base + total_h - label_h / 2 - 0.02,
            phase_name,
            ha="center",
            va="center",
            fontsize=9.2,
            color="#334155",
            fontweight="bold",
            zorder=5,
        )

        node_centers = []
        nx = x + pad_x
        ny = y_base + 0.08
        for label, face, accent in nodes:
            draw_card(
                ax,
                nx,
                ny,
                box_w,
                box_h,
                label,
                "",
                face,
                accent,
                title_size=7.8,
                r=0.06,
            )
            node_centers.append(nx + box_w / 2)
            if len(node_centers) > 1:
                arrow_h(
                    ax,
                    node_centers[-2] + box_w / 2 + 0.02,
                    node_centers[-1] - box_w / 2 - 0.02,
                    ny + box_h / 2,
                )
            nx += box_w + gap_x

        phase_boxes.append((x, x + phase_w, node_centers, ny + box_h / 2))
        x += phase_w + phase_gap

    for i in range(len(phase_boxes) - 1):
        x1 = phase_boxes[i][1]
        x2 = phase_boxes[i + 1][0]
        mid_y = phase_boxes[i][3]
        arrow_h(ax, x1 + 0.04, x2 - 0.04, mid_y)

    ax.text(
        7.25,
        0.95,
        "LLM 生成 SQL  →  六层安全防护  →  MySQL 执行  →  结果归一化与统计摘要",
        ha="center",
        va="center",
        fontsize=10.5,
        color=C["sub"],
        fontweight="bold",
    )

    legends = [
        ("输入/计划", C["node_amber"]),
        ("校验", C["node_indigo"]),
        ("路由", C["node_purple"]),
        ("执行", C["node_blue"]),
        ("输出", C["node_green"]),
    ]
    lx = 1.4
    for name, color in legends:
        ax.add_patch(
            Rectangle((lx, 0.35), 0.28, 0.18, facecolor=color, edgecolor=C["edge"], linewidth=0.8)
        )
        ax.text(lx + 0.38, 0.44, name, va="center", fontsize=8.2, color=C["sub"])
        lx += 1.35

    save_fig(fig, "fig_6_1_data_analysis_pipeline")


def diagram_43_comprehensive_architecture() -> None:
    """Fig 4-3: Agent workflow + pre-aggregation layer (assignment requirement)."""
    fig, ax = plt.subplots(figsize=(14, 9.5))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9.5)
    ax.axis("off")
    ax.set_facecolor("#ffffff")
    ax.text(
        7,
        9.1,
        "图 4-3  系统综合架构（Agent 协作流程 + 预聚合加速层）",
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold",
        color=C["title"],
    )

    # ── 顶部：交互与 API ──
    draw_card(ax, 0.6, 8.05, 5.8, 0.72, "Streamlit 前端", "自然语言问答 + 可视化展示", "#dbeafe", C["accent"][0], 10.5, 8.5, 0.08)
    draw_card(ax, 7.2, 8.05, 5.8, 0.72, "FastAPI 接口层", "POST /api/ask  ·  /api/parse", "#c7d2fe", C["accent"][1], 10.5, 8.5, 0.08)
    arrow_h(ax, 6.52, 7.12, 8.41)

    # ── 左侧：LangGraph Agent 流程 ──
    ax.text(3.5, 7.65, "LangGraph 多 Agent 协作流程", ha="center", fontsize=11, fontweight="bold", color="#4338ca")

    left_x, lw, lh = 0.85, 5.3, 0.62
    agent_steps = [
        ("Orchestrator", "parse → coordinator_plan", "#e0e7ff", C["accent"][1]),
        ("Coordinator Agent", "意图识别 / 任务拆解", "#e0e7ff", C["accent"][1]),
        ("Data Analysis Agent", "NL→SQL  ·  视图路由  ·  查询执行", "#dbeafe", C["accent"][0]),
        ("扩展分析（条件触发）", "forecast  ·  nlp_review  ·  what_if", "#fce7f3", C["accent"][3]),
        ("Visualization Agent", "图表推荐与生成", "#ede9fe", C["accent"][2]),
        ("Decision Agent", "P0/P1/P2 运营建议", "#dcfce7", C["accent"][4]),
        ("final_answer", "整合输出 → 返回前端", "#fef3c7", C["accent"][0]),
    ]
    y = 6.85
    da_y = None
    for title, sub, face, accent in agent_steps:
        draw_card(ax, left_x, y - lh, lw, lh, title, sub, face, accent, 10, 8, 0.07)
        if "Data Analysis" in title:
            da_y = y - lh / 2
        y -= lh + 0.22

    # ── 右侧：MySQL 数据层 ──
    rx, rw = 7.0, 6.3
    ax.text(rx + rw / 2, 7.65, "MySQL 数据访问层  ·  olist_agentic_bi", ha="center", fontsize=11, fontweight="bold", color="#047857")

    # Pre-aggregation layer
    pa_y, pa_h = 4.55, 2.55
    draw_shadow(ax, rx, pa_y, rw, pa_h, 0.1)
    pa_box = FancyBboxPatch(
        (rx, pa_y), rw, pa_h,
        boxstyle="round,pad=0,rounding_size=0.1",
        linewidth=1.5, edgecolor="#059669", facecolor="#ecfdf5", zorder=2,
    )
    ax.add_patch(pa_box)
    ax.add_patch(Rectangle((rx, pa_y), 0.14, pa_h, facecolor="#059669", zorder=3))
    ax.text(rx + rw / 2 + 0.05, pa_y + pa_h - 0.28, "Pre-Aggregation 预聚合加速层", ha="center", fontsize=10.5, fontweight="bold", color="#065f46", zorder=5)
    ax.text(rx + rw / 2 + 0.05, pa_y + pa_h - 0.55, "utils/pre_aggregation.sql  ·  离线批计算  ·  Agent 优先查询", ha="center", fontsize=8.5, color="#047857", zorder=5)

    mv_items = [
        "mv_monthly_sales", "mv_state_sales", "mv_category_sales",
        "mv_delivery_perf", "mv_seller_perf", "mv_payment_dist",
    ]
    col1_x, col2_x = rx + 0.45, rx + rw / 2 + 0.15
    item_y = pa_y + pa_h - 0.95
    for i, mv in enumerate(mv_items):
        cx = col1_x if i < 3 else col2_x
        cy = item_y - (i % 3) * 0.42
        ax.add_patch(FancyBboxPatch(
            (cx, cy), 2.55, 0.34, boxstyle="round,pad=0,rounding_size=0.05",
            linewidth=0.8, edgecolor="#6ee7b7", facecolor="#ffffff", zorder=4,
        ))
        ax.text(cx + 1.275, cy + 0.17, mv, ha="center", va="center", fontsize=8, color="#065f46", zorder=5)

    # Base tables layer
    bt_y, bt_h = 1.05, 3.15
    draw_shadow(ax, rx, bt_y, rw, bt_h, 0.1)
    bt_box = FancyBboxPatch(
        (rx, bt_y), rw, bt_h,
        boxstyle="round,pad=0,rounding_size=0.1",
        linewidth=1.5, edgecolor="#64748b", facecolor="#f1f5f9", zorder=2,
    )
    ax.add_patch(bt_box)
    ax.add_patch(Rectangle((rx, bt_y), 0.14, bt_h, facecolor="#64748b", zorder=3))
    # 标题区（独立一行，避免与表名重叠）
    header_y = bt_y + bt_h - 0.38
    ax.text(
        rx + rw / 2 + 0.05, header_y,
        "九张业务基表（原始层）",
        ha="center", va="center", fontsize=10.5, fontweight="bold", color="#334155", zorder=5,
    )
    ax.plot([rx + 0.35, rx + rw - 0.25], [header_y - 0.22, header_y - 0.22], color="#cbd5e1", linewidth=0.8, zorder=4)
    # 表名分三行固定排版
    table_lines = [
        "orders  ·  order_items  ·  products",
        "customers  ·  sellers  ·  payments",
        "order_reviews  ·  geolocation  ·  category_translation",
    ]
    line_y = header_y - 0.48
    for line in table_lines:
        ax.text(
            rx + rw / 2 + 0.05, line_y, line,
            ha="center", va="top", fontsize=8.3, color="#475569", zorder=5,
        )
        line_y -= 0.38
    ax.text(
        rx + rw / 2 + 0.05, bt_y + 0.32,
        "跨表 JOIN 实时聚合（慢路径）",
        ha="center", va="center", fontsize=8.5, color="#64748b", style="italic", zorder=5,
    )

    # ETL arrow base → pre-agg
    ax.text(rx + rw / 2, 4.42, "db_init.py  离线构建 / 刷新", ha="center", fontsize=8.5, color="#047857", zorder=5)
    arrow_v(ax, rx + rw / 2, bt_y + bt_h + 0.06, pa_y - 0.06, color="#059669")

    # Data Analysis Agent → data layer arrows
    if da_y is not None:
        mv_mid_y = pa_y + pa_h / 2
        bt_mid_y = bt_y + bt_h / 2
        # priority path
        ax.add_patch(FancyArrowPatch(
            (left_x + lw + 0.05, da_y + 0.15), (rx - 0.05, mv_mid_y),
            arrowstyle="-|>", mutation_scale=13, linewidth=2.0, color="#059669", zorder=6,
        ))
        ax.text(6.35, mv_mid_y + 0.35, "优先命中 mv_*", ha="center", fontsize=9.5, fontweight="bold", color="#059669",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#ecfdf5", edgecolor="#6ee7b7"))
        # fallback path
        ax.add_patch(FancyArrowPatch(
            (left_x + lw + 0.05, da_y - 0.15), (rx - 0.05, bt_mid_y),
            arrowstyle="-|>", mutation_scale=13, linewidth=1.8, color="#ea580c",
            linestyle="dashed", zorder=6,
        ))
        ax.text(6.35, bt_mid_y - 0.35, "无法覆盖时回退基表", ha="center", fontsize=9.5, fontweight="bold", color="#ea580c",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#fff7ed", edgecolor="#fdba74"))

    # Legend
    ax.text(0.6, 0.55, "图例：", fontsize=9, fontweight="bold", color=C["sub"])
    ax.add_patch(FancyArrowPatch((1.2, 0.55), (1.9, 0.55), arrowstyle="-|>", mutation_scale=10, linewidth=2, color="#059669"))
    ax.text(2.0, 0.55, "预聚合优先", va="center", fontsize=8.5, color="#059669")
    ax.add_patch(FancyArrowPatch((3.5, 0.55), (4.2, 0.55), arrowstyle="-|>", mutation_scale=10, linewidth=1.6, color="#ea580c", linestyle="dashed"))
    ax.text(4.3, 0.55, "基表回退", va="center", fontsize=8.5, color="#ea580c")

    save_fig(fig, "fig_4_3_comprehensive_architecture")


def main() -> None:
    setup_style()
    diagram_41_layered_architecture()
    diagram_43_langgraph_workflow()
    diagram_43_comprehensive_architecture()
    diagram_62_data_analysis_pipeline()


if __name__ == "__main__":
    main()
