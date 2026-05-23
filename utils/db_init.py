"""
创建数据库 → 执行九表 DDL → 导入 data/clean 下 CSV → 构建预聚合汇总表 mv_*。

用法（在项目根 AgenticBI_Final_Olist/ 下执行）：
  pip install -r requirements.txt     # 已装可跳过
  python utils/data_cleaning.py       # 先清洗生成 data/clean
  python utils/db_init.py             # 再导入数据库

如需指定密码：
  PowerShell:
    setx MYSQL_PASSWORD "你的密码"
  新开终端后再运行；或运行时按提示输入（无密码可直接回车）。

注意：
  - 必须先执行 schema_ddl.sql 建好基表再通过本脚本追加数据。
  - 禁止对基表使用 pandas to_sql(if_exists="replace")，否则会覆盖 DDL 导致列类型与约定不一致。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymysql
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import (
    DATA_CLEAN,
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    ROOT as PROJECT_ROOT,
    ensure_dirs,
    sqlalchemy_url,
)


def _read_sql_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ensure_database(password: str) -> None:
    pw = password if password else None
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=pw,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def run_sql_script(engine, sql_path: Path) -> None:
    raw = _read_sql_file(sql_path)
    statements = [s.strip() for s in raw.split(";") if s.strip()]
    with engine.connect() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()


def load_clean_tables(engine) -> None:
    ensure_dirs()
    if not DATA_CLEAN.exists():
        raise SystemExit(f"未找到清洗后目录: {DATA_CLEAN} ，请先运行 python utils/data_cleaning.py")

    spec = [
        ("orders.csv", "orders"),
        ("order_items.csv", "order_items"),
        ("customers.csv", "customers"),
        ("sellers.csv", "sellers"),
        ("products.csv", "products"),
        ("payments.csv", "payments"),
        ("order_reviews.csv", "order_reviews"),
        ("geolocation.csv", "geolocation"),
        ("product_category_name_translation.csv", "product_category_name_translation"),
    ]

    for fname, tbl in spec:
        path = DATA_CLEAN / fname
        if not path.exists():
            raise SystemExit(f"缺少 {path}")

        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE `{tbl}`"))

        reader = pd.read_csv(path, chunksize=50_000)
        for chunk in reader:
            # MySQL 单次 prepared 占位符约 65535 上限；method="multi" 为「列数×批大小」。
            # 批太大易触发 “too many placeholders” 或包过大；200 行/批在本项目列宽下安全。
            chunk.to_sql(
                tbl,
                engine,
                if_exists="append",
                index=False,
                chunksize=200,
                method="multi",
            )
        print(f"导入 {tbl}: {fname}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ddl-only", action="store_true", help="仅建空表，不导入数据、不建 mv_*")
    args = parser.parse_args()

    pwd = MYSQL_PASSWORD if MYSQL_PASSWORD else input("请输入 MySQL 密码（无则直接回车）: ").strip()

    ensure_database(pwd)
    engine = create_engine(sqlalchemy_url(pwd), pool_pre_ping=True)

    ddl_path = PROJECT_ROOT / "utils" / "schema_ddl.sql"
    agg_path = PROJECT_ROOT / "utils" / "pre_aggregation.sql"

    print("执行 schema_ddl.sql …")
    run_sql_script(engine, ddl_path)

    if not args.ddl_only:
        print("载入 CSV …")
        load_clean_tables(engine)
        print("执行 pre_aggregation.sql …")
        run_sql_script(engine, agg_path)

    print("完成。可在 MySQL 客户端中预览基表与各 mv_* 汇总表。")


if __name__ == "__main__":
    main()
