"""
Olist 九表清洗：从 data/raw 读 CSV，写出 data/clean（UTF-8），供 db_init 导入 MySQL。

用法：
  python utils/data_cleaning.py

说明：
- 时间列统一为 pandas 可解析的 datetime；非法值转 NaT 再导入时变 NULL。
- geolocation 表体量大，可在下面打开去重策略（默认按 prefix+lat+lng 去重一行）。
- 与全组约定：GMV 在预聚合层使用 SUM(price)+SUM(freight_value)（见 data_dictionary.yaml）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import DATA_CLEAN, DATA_RAW, ensure_dirs  # noqa: E402

TS_COLUMNS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}


def _resolve_raw_path(preferred: str, alt: str) -> Path | None:
    p1 = DATA_RAW / preferred
    if p1.exists():
        return p1
    p2 = DATA_RAW / alt
    if p2.exists():
        return p2
    return None


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["order_id"] = out["order_id"].astype(str).str.strip()
    out["customer_id"] = out["customer_id"].astype(str).str.strip()
    out["order_status"] = out["order_status"].astype(str).str.strip()
    for col in TS_COLUMNS["orders"]:
        if col in out.columns:
            out[col] = _to_datetime(out[col])
    # 去掉完全重复的订单行（若有）
    out = out.drop_duplicates(subset=["order_id"], keep="first")
    return out


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["order_id"] = out["order_id"].astype(str).str.strip()
    out["product_id"] = out["product_id"].astype(str).str.strip()
    out["seller_id"] = out["seller_id"].astype(str).str.strip()
    out["shipping_limit_date"] = _to_datetime(out["shipping_limit_date"])
    out["price"] = pd.to_numeric(out["price"], errors="coerce").fillna(0)
    out["freight_value"] = pd.to_numeric(out["freight_value"], errors="coerce").fillna(0)
    out = out.drop_duplicates(subset=["order_id", "order_item_id"], keep="first")
    return out


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]:
        out[c] = out[c].astype(str).str.strip()
    out = out.drop_duplicates(subset=["customer_id"], keep="first")
    return out


def clean_sellers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]:
        out[c] = out[c].astype(str).str.strip()
    out = out.drop_duplicates(subset=["seller_id"], keep="first")
    return out


def clean_products(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["product_id"] = out["product_id"].astype(str).str.strip()
    if "product_category_name" in out.columns:
        out["product_category_name"] = out["product_category_name"].apply(
            lambda x: str(x).strip() if pd.notna(x) else None
        )
    num_cols = [
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]
    for c in num_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.drop_duplicates(subset=["product_id"], keep="first")
    return out


def clean_payments(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["order_id"] = out["order_id"].astype(str).str.strip()
    out["payment_type"] = out["payment_type"].astype(str).str.strip()
    out["payment_sequential"] = pd.to_numeric(out["payment_sequential"], errors="coerce").fillna(0).astype(int)
    out["payment_installments"] = pd.to_numeric(out["payment_installments"], errors="coerce").fillna(0).astype(int)
    out["payment_value"] = pd.to_numeric(out["payment_value"], errors="coerce").fillna(0)
    out = out.drop_duplicates(subset=["order_id", "payment_sequential"], keep="first")
    return out


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # 有些版本带 review_id，有些没有；统一与 DB 对齐时由 MySQL 自增或保留原列
    if "review_id" in out.columns:
        out["review_id"] = pd.to_numeric(out["review_id"], errors="coerce")
    out["order_id"] = out["order_id"].astype(str).str.strip()
    out["review_score"] = pd.to_numeric(out["review_score"], errors="coerce").fillna(0).astype(int)
    for c in ["review_comment_title", "review_comment_message"]:
        if c in out.columns:
            out[c] = out[c].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != "nan" else None)
    for col in TS_COLUMNS["order_reviews"]:
        if col in out.columns:
            out[col] = _to_datetime(out[col])
    # 若存在 review_id 则按其去重，否则按 order_id+时间
    if "review_id" in out.columns and out["review_id"].notna().any():
        out = out.drop_duplicates(subset=["review_id"], keep="first")
    else:
        out = out.drop_duplicates(subset=["order_id", "review_creation_date"], keep="first")
    return out


def clean_geolocation(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    cols = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"]
    for c in cols:
        out[c] = out[c].apply(lambda x: x if isinstance(x, (int, float)) else str(x).strip())
    out["geolocation_lat"] = pd.to_numeric(out["geolocation_lat"], errors="coerce")
    out["geolocation_lng"] = pd.to_numeric(out["geolocation_lng"], errors="coerce")
    invalid = out["geolocation_lat"].isna() | out["geolocation_lng"].isna()
    out = out.loc[~invalid]
    # geolocation 常重复几百万行：按前缀+经纬度聚合去重便于入库
    out = out.drop_duplicates(
        subset=["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"], keep="first"
    )
    return out


def clean_translation(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["product_category_name"] = out["product_category_name"].astype(str).str.strip()
    out["product_category_name_english"] = out["product_category_name_english"].astype(str).str.strip()
    out = out.drop_duplicates(subset=["product_category_name"], keep="first")
    return out


def main() -> None:
    ensure_dirs()
    if not DATA_RAW.exists() or not any(DATA_RAW.iterdir()):
        raise SystemExit(f"请将 Kaggle CSV 放入: {DATA_RAW}\n可参考 data/README.md")

    mappings = [
        (_resolve_raw_path("olist_orders_dataset.csv", "orders_dataset.csv"), clean_orders, "orders.csv"),
        (_resolve_raw_path("olist_order_items_dataset.csv", "order_items_dataset.csv"), clean_order_items, "order_items.csv"),
        (_resolve_raw_path("olist_products_dataset.csv", "products_dataset.csv"), clean_products, "products.csv"),
        (_resolve_raw_path("olist_customers_dataset.csv", "customers_dataset.csv"), clean_customers, "customers.csv"),
        (_resolve_raw_path("olist_sellers_dataset.csv", "sellers_dataset.csv"), clean_sellers, "sellers.csv"),
        (_resolve_raw_path("olist_order_payments_dataset.csv", "order_payments_dataset.csv"), clean_payments, "payments.csv"),
        (_resolve_raw_path("olist_order_reviews_dataset.csv", "order_reviews_dataset.csv"), clean_reviews, "order_reviews.csv"),
        (_resolve_raw_path("olist_geolocation_dataset.csv", "geolocation_dataset.csv"), clean_geolocation, "geolocation.csv"),
        (
            _resolve_raw_path(
                "product_category_name_translation.csv", "product_category_name_translation.csv"
            ),
            clean_translation,
            "product_category_name_translation.csv",
        ),
    ]

    for src, cleaner, dst_name in mappings:
        if src is None:
            raise SystemExit(f"缺少 CSV 文件，请将九表放入 data/raw（缺: {dst_name} 对应文件名）")

        df = pd.read_csv(src)
        cleaned = cleaner(df)
        outp = DATA_CLEAN / dst_name
        cleaned.to_csv(outp, index=False, encoding="utf-8-sig")
        print(f"OK  {dst_name}: {len(cleaned)} 行")


if __name__ == "__main__":
    main()
