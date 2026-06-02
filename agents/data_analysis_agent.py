"""
DataAnalysisAgent.

Responsibilities:
1. Receive the user question and CoordinatorAgent task.
2. Generate read-only SQL using data dictionary and pre-aggregation policy.
3. Validate SQL safety.
4. Execute SQL.
5. Return a stable JSON-friendly result:
   {
     "question": "用户问题",
     "sql": "执行的SQL语句",
     "used_view": true/false,
     "view_name": "mv_xxx" or None,
     "data": [..records..],
     "summary": "统计摘要"
   }
"""

from __future__ import annotations

import json
import math
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.llm_client import LLMClient
from agents.schemas import AgentTask, DataAnalysisResult
from agents.sql_guard import validate_readonly_sql
from config.settings import sqlalchemy_url


DATA_DICTIONARY_PATH = ROOT / "config" / "data_dictionary.yaml"
PROMPTS_PATH = ROOT / "config" / "prompts.yaml"


def get_engine():
    """Create database connection engine."""
    return create_engine(sqlalchemy_url(), pool_pre_ping=True)


def load_yaml_context(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    return loaded if isinstance(loaded, dict) else {}


def load_data_dictionary_context() -> str:
    """Return compact YAML context for SQL generation."""
    data = load_yaml_context(DATA_DICTIONARY_PATH)
    useful_context = {
        "meta": data.get("meta", {}),
        "tables": data.get("tables", {}),
        "materialized_aggregates": data.get("materialized_aggregates", {}),
    }
    return yaml.safe_dump(useful_context, allow_unicode=True, sort_keys=False)


def load_pre_aggregate_policy_context() -> str:
    """Return the pre-aggregation policy from prompts.yaml if available."""
    prompts = load_yaml_context(PROMPTS_PATH)
    useful_context = {
        "system_principles": prompts.get("system", {}).get("principles", []),
        "pre_aggregate_policy": prompts.get("pre_aggregate_policy", {}),
    }
    return yaml.safe_dump(useful_context, allow_unicode=True, sort_keys=False)


def _to_jsonable(value: Any) -> Any:
    """Convert pandas / Decimal / NaN values to JSON-friendly values."""
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, float) and math.isnan(value):
        return None

    if pd.isna(value):
        return None

    return value


def execute_sql(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Execute SQL and return DataFrame."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def dataframe_to_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert DataFrame to JSON-friendly records."""
    rows = df.to_dict(orient="records")
    return [
        {key: _to_jsonable(value) for key, value in row.items()}
        for row in rows
    ]


def detect_view_name(sql: str) -> str | None:
    """Detect first mv_* table referenced in generated SQL."""
    match = re.search(r"\b(?:FROM|JOIN)\s+`?(mv_[a-zA-Z0-9_]+)`?\b", sql, flags=re.IGNORECASE)
    return match.group(1) if match else None


def detect_view_names(sql: str) -> list[str]:
    """Detect all mv_* tables referenced in generated SQL."""
    matches = re.findall(r"\b(?:FROM|JOIN)\s+`?(mv_[a-zA-Z0-9_]+)`?\b", sql, flags=re.IGNORECASE)
    result: list[str] = []
    for name in matches:
        if name not in result:
            result.append(name)
    return result


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", "", question.lower())


def required_views_for_question(question: str) -> list[str]:
    """
    Return view coverage requirements for explicit multi-metric questions.

    This does not provide SQL. It only checks whether the LLM-generated SQL
    covers the source views required by the user's question.
    """
    q = _normalize_question(question)
    required: list[str] = []

    if (
        "2017" in q
        and "gmv" in q
        and ("按月" in q or "月" in q)
        and ("州" in q or "排名" in q)
    ):
        required.extend(["mv_monthly_sales", "mv_state_sales"])

    if ("准时" in q or "准时交付" in q) and ("延迟" in q or "州" in q):
        required.append("mv_delivery_perf")

    if ("配送时长" in q or "配送" in q) and ("州" in q or "全国均值" in q):
        required.append("mv_delivery_perf")

    if "支付方式" in q and ("最受欢迎" in q or "分期" in q):
        required.append("mv_payment_dist")

    if ("预测" in q or "未来" in q) and ("销售" in q or "gmv" in q):
        required.append("mv_monthly_sales")

    return list(dict.fromkeys(required))


def required_sql_signals_for_question(question: str) -> list[tuple[str, str]]:
    """Return non-view SQL coverage signals that the LLM must include."""
    q = _normalize_question(question)
    signals: list[tuple[str, str]] = []
    if "支付方式" in q and ("最受欢迎" in q or "分期" in q):
        signals.extend([
            ("GROUP BY payment_type", "支付方式整体偏好必须先GROUP BY payment_type汇总。"),
            ("SUM(total_transactions)", "支付方式整体偏好必须用SUM(total_transactions)汇总交易数。"),
        ])
        if "分期" in q:
            signals.append(
                ("avg_installments * total_transactions", "平均分期数必须按total_transactions加权计算。")
            )

    if "卖家" in q and "差评率" in q:
        signals.extend([
            ("order_reviews", "计算卖家差评率必须查询评论表。"),
            ("order_items", "计算卖家差评率必须通过订单明细关联seller_id。"),
            ("seller_id", "结果必须包含卖家ID维度。"),
            ("negative_rate", "结果必须显式计算差评率negative_rate。"),
        ])
    return signals


def missing_required_sql_signals(sql: str, signals: list[tuple[str, str]]) -> list[str]:
    sql_lower = sql.lower()
    sql_compact = re.sub(r"\s+", "", sql_lower)
    missing: list[str] = []
    for token, description in signals:
        token_lower = token.lower()
        token_compact = re.sub(r"\s+", "", token_lower)
        if token_compact == "avg_installments*total_transactions":
            reverse_token = "total_transactions*avg_installments"
            if token_compact in sql_compact or reverse_token in sql_compact:
                continue
        if token_lower not in sql_lower and token_compact not in sql_compact:
            missing.append(description)
    return missing


def validate_mysql_surface_sql(sql: str) -> str | None:
    """Catch MySQL syntax risks that are common in LLM-generated SQL."""
    if re.search(r"\bAS\s+`?rank`?\b", sql, flags=re.IGNORECASE):
        return "rank是MySQL窗口函数相关保留词，不要作为列别名；请改用state_rank、rank_value或ranking。"

    lowered = sql.lower()
    if "union all" in lowered and re.search(r"\border\s+by\b[\s\S]*\brnk\b", lowered):
        return "UNION查询的ORDER BY不能引用CTE内部别名rnk；请使用最终输出列别名，或用外层SELECT包装后排序。"

    return None


# 有已知粒度不一致风险的视图：粒度为 YEAR-MONTH × 维度，
# 但用户的问题通常只问维度的分布（忽略时间）。
GRAIN_MISMATCH_VIEWS: dict[str, dict[str, str]] = {
    "mv_payment_dist": {
        "dimension": "payment_type",
        "metric": "total_transactions",
    },
    "mv_category_sales": {
        "dimension": "product_category_english",
        "metric": "total_gmv",
    },
    "mv_state_sales": {
        "dimension": "customer_state",
        "metric": "total_gmv",
    },
}


def validate_distribution_grain(sql: str) -> str | None:
    """
    检测 SQL 是否在细粒度 mv_* 视图上计算占比，但未先聚合到业务维度。

    常见错误：SELECT dim, metric, ROUND(metric*100.0/SUM(metric) OVER(), 2)
    FROM mv_xxx  — 没有 GROUP BY，错误原因：视图粒度为 YEAR-MONTH × dim，
    每个 dim 值有多行（每月一行），直接窗口函数算出的占比不正确。

    返回 None（校验通过）或错误消息。
    """
    normalized = re.sub(r"\s+", " ", sql.strip().lower())

    # 查找 SQL 使用了哪个已知的粒度不一致风险视图
    matched_view = None
    matched_info = None
    for view_name, info in GRAIN_MISMATCH_VIEWS.items():
        if view_name in normalized:
            matched_view, matched_info = view_name, info
            break

    if not matched_view:
        return None

    dim = matched_info["dimension"]

    # 只检测“用 SUM(...) OVER() 计算整体占比”的风险。
    # ROW_NUMBER() / RANK() 等窗口排名可用于年月内州排名，不应拦截。
    has_over = bool(re.search(r"sum\s*\([^)]*\)\s*over\s*\(", normalized))
    has_group_by_dim = bool(re.search(rf"group\s+by\s+.*\b{dim}\b", normalized))

    if has_over and not has_group_by_dim:
        return (
            f"视图 {matched_view} 的粒度为 YEAR-MONTH × {dim}，"
            f"不能直接在其明细行上用窗口函数计算占比。"
            f"必须先 GROUP BY {dim} 用 SUM() 聚合后计算。"
        )

    return None


def generate_sql_plan(question: str, task: AgentTask) -> dict[str, Any]:
    """
    Ask the DataAnalysisAgent LLM to produce SQL and metadata.
    """
    data_dictionary = load_data_dictionary_context()
    pre_aggregate_policy = load_pre_aggregate_policy_context()

    system_prompt = f"""
你是电商 BI 系统中的数据分析 Agent。

你的职责：
1. 将业务问题转换为 MySQL SQL。
2. 判断是否命中预聚合视图 mv_*。
3. 如果预聚合视图可以准确回答问题，必须优先查询视图。
4. 如果预聚合视图无法准确回答问题，才查询原始表。
5. 只生成 SELECT 或 WITH 查询。
6. 禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE。
7. 不要编造不存在的表或字段。
8. 涉及 `year_month` 字段时必须使用反引号。
9. 默认加 LIMIT，除非查询是单行聚合指标。
10. 预测未来销售额/GMV时，必须优先查询 mv_monthly_sales 全量历史月份，不要使用 CURDATE() 或最近52周过滤，因为Olist是2016-2018年的历史数据集。
11. 如果问题同时包含多个指标或多个维度，允许使用 WITH 将多个预聚合视图组合到一条SQL中，优先保证所有被问到的指标都能被覆盖。
12. 当问题同时询问“2017年GMV”“按月趋势”“各州排名”时，SQL必须同时命中 mv_monthly_sales 和 mv_state_sales：用 mv_monthly_sales 计算年度GMV和月度GMV，用 mv_state_sales 计算州排名。
13. 当问题询问平台准时交付率和延迟严重州时，优先命中 mv_delivery_perf；如果需要订单级整体准时率，可回退orders原始表计算整体口径，并保留 mv_delivery_perf 输出州级延迟。
14. 当问题询问最受欢迎支付方式和平均分期数时，优先命中 mv_payment_dist，并使用 total_transactions 加权计算 avg_installments。
15. 当问题询问产品重量、尺寸与运费关系时，mv_*无法覆盖，查询 products、order_items 以及必要的品类翻译表。
16. 当问题询问差评品类和差评原因时，查询 order_reviews、order_items、products、product_category_name_translation，返回低评分评论文本和品类聚合，供NLPAgent提取主题。
17. 当问题询问“卖家差评率最高”时，必须查询 order_reviews、order_items、sellers，按 seller_id 计算 review_count、negative_reviews、negative_rate，并按 negative_rate 降序返回高差评率卖家。
18. 当问题同时询问州配送时长高于全国均值和高差评率卖家时，允许用 UNION ALL 或 JSON 字段在同一条SQL中同时返回州级配送异常和卖家差评率结果。
19. 当问题询问综合改进策略或多维诊断时，优先组合销售、配送、支付、评论/品类或卖家相关数据，返回足够的决策依据。

数据字典：
{data_dictionary}

预聚合视图策略：
{pre_aggregate_policy}

你必须返回 JSON，不要 Markdown，不要解释性正文。
返回格式必须为：
{{
  "sql": "SELECT ...",
  "used_view": true,
  "view_name": "mv_xxx 或 null",
  "summary_intent": "说明这个 SQL 计划如何回答问题"
}}
""".strip()

    user_prompt = f"""
用户问题：
{question}

协调器分配的子任务：
{json.dumps(task, ensure_ascii=False, indent=2)}

请生成可执行 SQL。
""".strip()

    client = LLMClient()

    def _call_llm(extra_guard: str = "") -> dict[str, Any]:
        guard_prompt = user_prompt
        if extra_guard:
            guard_prompt = f"{user_prompt}\n\n额外约束（必须满足）：\n{extra_guard}"
        return client.chat_json([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": guard_prompt},
        ])

    raw = _call_llm()

    sql = validate_readonly_sql(str(raw.get("sql", "")))
    view_name = raw.get("view_name")
    if view_name in ("", "null", "None"):
        view_name = None
    if not view_name:
        view_name = detect_view_name(sql)
    view_names = detect_view_names(sql)
    if view_names:
        view_name = ",".join(view_names)

    used_view = bool(raw.get("used_view")) or bool(view_name)

    # 通用粒度校验：检测分布类查询是否在 YEAR-MONTH × 维度粒度的明细上计算占比
    semantic_error = validate_distribution_grain(sql)
    if semantic_error:
        matched_view, matched_info = None, None
        for vn, info in GRAIN_MISMATCH_VIEWS.items():
            if vn in sql.lower():
                matched_view, matched_info = vn, info
                break
        dim = matched_info["dimension"] if matched_info else "业务维度"
        metric = matched_info["metric"] if matched_info else "度量值"

        retry_raw = _call_llm(
            f"你使用了 {matched_view} 但粒度错误。该视图粒度为 YEAR-MONTH × {dim}，"
            f"计算整体占比时需先 GROUP BY {dim} 并用 SUM({metric}) 聚合，"
            f"再基于聚合结果计算百分比。\n"
            f"注意：year_month 是 MySQL 9.x 保留关键字，所有出现 year_month 的地方都必须加反引号(\`year_month\`)。"
        )
        sql = validate_readonly_sql(str(retry_raw.get("sql", "")))
        view_name = retry_raw.get("view_name")
        if view_name in ("", "null", "None"):
            view_name = None
        if not view_name:
            view_name = detect_view_name(sql)
        view_names = detect_view_names(sql)
        if view_names:
            view_name = ",".join(view_names)
        used_view = bool(retry_raw.get("used_view")) or bool(view_name)
        semantic_error = validate_distribution_grain(sql)
        if semantic_error:
            raise ValueError(f"生成的分布查询 SQL 语义不符合口径：{semantic_error}")
        raw = retry_raw

    required_views = required_views_for_question(question)
    missing_views = [name for name in required_views if name not in detect_view_names(sql)]
    if missing_views:
        retry_raw = _call_llm(
            "当前SQL没有覆盖用户问题明确需要的数据来源。"
            f"必须同时命中这些预聚合视图：{', '.join(required_views)}。"
            "请重新生成一条可执行的MySQL SELECT或WITH查询，允许用CTE组合多个视图，"
            "并确保结果能回答用户问题中的所有指标和维度。"
        )
        sql = validate_readonly_sql(str(retry_raw.get("sql", "")))
        view_name = retry_raw.get("view_name")
        if view_name in ("", "null", "None"):
            view_name = None
        if not view_name:
            view_name = detect_view_name(sql)
        view_names = detect_view_names(sql)
        if view_names:
            view_name = ",".join(view_names)
        used_view = bool(retry_raw.get("used_view")) or bool(view_name)
        semantic_error = validate_distribution_grain(sql)
        if semantic_error:
            raise ValueError(f"生成的分布查询 SQL 语义不符合口径：{semantic_error}")
        missing_views = [name for name in required_views if name not in detect_view_names(sql)]
        if missing_views:
            raise ValueError(f"生成的SQL未覆盖必需预聚合视图：{', '.join(missing_views)}")
        raw = retry_raw

    required_signals = required_sql_signals_for_question(question)
    missing_signals = missing_required_sql_signals(sql, required_signals)
    if missing_signals:
        retry_raw = _call_llm(
            "当前SQL没有覆盖用户问题明确需要的诊断指标："
            f"{'；'.join(missing_signals)}"
            "请重新生成一条可执行的MySQL SELECT或WITH查询。"
            f"如果当前问题需要预聚合视图，也必须保留这些视图：{', '.join(required_views) or '无'}。"
            "如果问题还有配送时长诊断，也要保留 mv_delivery_perf 对州级配送表现的分析；"
            "如果问题询问卖家差评率，必须返回negative_rate。"
        )
        sql = validate_readonly_sql(str(retry_raw.get("sql", "")))
        view_name = retry_raw.get("view_name")
        if view_name in ("", "null", "None"):
            view_name = None
        if not view_name:
            view_name = detect_view_name(sql)
        view_names = detect_view_names(sql)
        if view_names:
            view_name = ",".join(view_names)
        used_view = bool(retry_raw.get("used_view")) or bool(view_name)
        semantic_error = validate_distribution_grain(sql)
        if semantic_error:
            raise ValueError(f"生成的分布查询 SQL 语义不符合口径：{semantic_error}")
        missing_signals = missing_required_sql_signals(sql, required_signals)
        if missing_signals:
            raise ValueError(f"生成的SQL未覆盖必需诊断指标：{'；'.join(missing_signals)}")
        missing_views = [name for name in required_views if name not in detect_view_names(sql)]
        if missing_views:
            raise ValueError(f"生成的SQL未覆盖必需预聚合视图：{', '.join(missing_views)}")
        raw = retry_raw

    surface_error = validate_mysql_surface_sql(sql)
    if surface_error:
        retry_raw = _call_llm(
            "当前SQL存在MySQL语法风险："
            f"{surface_error}"
            "请重新生成一条可执行的MySQL SELECT或WITH查询，仍需完整回答用户问题。"
        )
        sql = validate_readonly_sql(str(retry_raw.get("sql", "")))
        view_name = retry_raw.get("view_name")
        if view_name in ("", "null", "None"):
            view_name = None
        if not view_name:
            view_name = detect_view_name(sql)
        view_names = detect_view_names(sql)
        if view_names:
            view_name = ",".join(view_names)
        used_view = bool(retry_raw.get("used_view")) or bool(view_name)
        semantic_error = validate_distribution_grain(sql)
        if semantic_error:
            raise ValueError(f"生成的分布查询 SQL 语义不符合口径：{semantic_error}")
        missing_views = [name for name in required_views if name not in detect_view_names(sql)]
        if missing_views:
            raise ValueError(f"生成的SQL未覆盖必需预聚合视图：{', '.join(missing_views)}")
        missing_signals = missing_required_sql_signals(sql, required_signals)
        if missing_signals:
            raise ValueError(f"生成的SQL未覆盖必需诊断指标：{'；'.join(missing_signals)}")
        surface_error = validate_mysql_surface_sql(sql)
        if surface_error:
            raise ValueError(f"生成的SQL仍存在MySQL语法风险：{surface_error}")
        raw = retry_raw

    res = {
        "sql": sql,
        "used_view": used_view,
        "view_name": str(view_name) if view_name else None,
        "summary_intent": str(raw.get("summary_intent") or "已生成 SQL 查询计划。"),
    }
    print("=========数据分析Agent-LLM返回：============")
    print(res)
    print("==========================================")
    return res


def summarize_rows(
    question: str,
    sql_plan: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    """Generate a compact deterministic summary from returned rows."""
    if not rows:
        return "没有查询到符合条件的数据。"

    used_view_text = "使用了预聚合视图" if sql_plan["used_view"] else "未使用预聚合视图"
    view_text = f"，命中视图 {sql_plan['view_name']}" if sql_plan.get("view_name") else ""
    first_row = rows[0]
    sample_fields = "，".join(f"{key}={value}" for key, value in list(first_row.items())[:4])

    return (
        f"查询返回 {len(rows)} 行结果，{used_view_text}{view_text}。"
        f"首行关键字段：{sample_fields}。"
    )


def repair_sql_plan_after_error(
    question: str,
    task: AgentTask,
    failed_plan: dict[str, Any],
    error: Exception,
) -> dict[str, Any]:
    """
    Ask the LLM to repair its own SQL after a database execution error.

    This is not a rule fallback: the corrected SQL is still generated by the
    LLM from the schema, task, failed SQL, and concrete MySQL error.
    """
    data_dictionary = load_data_dictionary_context()
    pre_aggregate_policy = load_pre_aggregate_policy_context()

    system_prompt = f"""
你是电商 BI 系统中的数据分析 Agent，正在修复你上一次生成但执行失败的 MySQL SQL。

修复要求：
1. 仍然只能返回 SELECT 或 WITH 查询。
2. 禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE。
3. 必须根据数据库错误修正 SQL，不要返回解释正文。
4. 不要编造不存在的表或字段。
5. 所有出现 year_month 字段的地方都必须写成 `year_month`，包括 SELECT、WHERE、GROUP BY、ORDER BY、JOIN、CTE 中的引用。
6. 如果问题能由 mv_* 预聚合表覆盖，仍应优先使用 mv_*。
7. 不要使用 rank 作为列别名；需要排名字段时使用 state_rank、rank_value 或 ranking。
8. UNION / UNION ALL 查询的 ORDER BY 只能引用最终输出列或外层查询别名，不要引用CTE内部别名。

数据字典：
{data_dictionary}

预聚合视图策略：
{pre_aggregate_policy}

你必须返回 JSON，不要 Markdown，不要解释性正文。
返回格式必须为：
{{
  "sql": "SELECT ...",
  "used_view": true,
  "view_name": "mv_xxx 或 null",
  "summary_intent": "说明修复后的 SQL 如何回答问题"
}}
""".strip()

    user_prompt = f"""
用户问题：
{question}

协调器分配的子任务：
{json.dumps(task, ensure_ascii=False, indent=2)}

上一次失败的 SQL：
{failed_plan.get("sql")}

MySQL/SQLAlchemy 报错：
{error}

请修复 SQL，并保持查询口径能回答用户问题。
""".strip()

    raw = LLMClient().chat_json([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    sql = validate_readonly_sql(str(raw.get("sql", "")))
    view_name = raw.get("view_name")
    if view_name in ("", "null", "None"):
        view_name = None
    view_names = detect_view_names(sql)
    if view_names:
        view_name = ",".join(view_names)
    elif not view_name:
        view_name = detect_view_name(sql)

    semantic_error = validate_distribution_grain(sql)
    if semantic_error:
        raise ValueError(f"修复后的 SQL 语义不符合口径：{semantic_error}")

    surface_error = validate_mysql_surface_sql(sql)
    if surface_error:
        raise ValueError(f"修复后的 SQL 仍存在MySQL语法风险：{surface_error}")

    repaired = {
        "sql": sql,
        "used_view": bool(raw.get("used_view")) or bool(view_name),
        "view_name": str(view_name) if view_name else None,
        "summary_intent": str(raw.get("summary_intent") or "LLM已根据数据库错误修复SQL。"),
    }
    print("=========数据分析Agent-LLM修复SQL返回：============")
    print(repaired)
    print("==========================================")
    return repaired


def run_data_analysis(question: str, task: AgentTask) -> DataAnalysisResult:
    """
    Public entry point for DataAnalysisAgent.
    """
    sql_plan = generate_sql_plan(question, task)
    try:
        df = execute_sql(sql_plan["sql"])
    except Exception as exc:
        sql_plan = repair_sql_plan_after_error(question, task, sql_plan, exc)
        df = execute_sql(sql_plan["sql"])
    rows = dataframe_to_rows(df)
    summary = summarize_rows(question, sql_plan, rows)

    return {
        "question": question,
        "sql": sql_plan["sql"].strip(),
        "used_view": bool(sql_plan["used_view"]),
        "view_name": sql_plan["view_name"],
        "data": rows,
        "summary": summary,
    }


def recommend_chart(analysis_type: str, data_analysis: DataAnalysisResult) -> str | None:
    """Lightweight chart suggestion for downstream visualization agent."""
    data = data_analysis.get("data", [])
    if not data:
        return None

    first = data[0]
    numeric_fields = [key for key, value in first.items() if isinstance(value, (int, float))]
    categorical_fields = [key for key, value in first.items() if not isinstance(value, (int, float))]

    if len(data) == 1 and numeric_fields:
        return "big_number_card"
    if any("month" in key or "date" in key or "time" in key for key in first):
        return "line_chart"
    if categorical_fields and numeric_fields:
        return "bar_chart"
    if analysis_type in {"diagnostic", "prescriptive"}:
        return "table_with_highlights"
    return "table"


if __name__ == "__main__":
    from agents.coordinator_agent import create_task_plan

    q = "评价分数最低的卖家有哪些？"
    plan = create_task_plan(q)
    result = run_data_analysis(q, plan["task_plan"][0])
    print(json.dumps(result, ensure_ascii=False, indent=2))
