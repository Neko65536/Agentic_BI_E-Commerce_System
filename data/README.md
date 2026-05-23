将 Kaggle 「Brazilian E-Commerce」九张 CSV 解压后的 **原始文件**放在本目录 `raw/`：

建议文件名（与其它文件一致时可不改名）：
- olist_orders_dataset.csv
- olist_order_items_dataset.csv
- olist_products_dataset.csv
- olist_customers_dataset.csv
- olist_sellers_dataset.csv
- olist_order_payments_dataset.csv
- olist_order_reviews_dataset.csv
- olist_geolocation_dataset.csv
- product_category_name_translation.csv

若文件名略有差异，请在 `utils/data_cleaning.py` 顶部的 `_resolve_raw_path(...)` 对应分支中调整。

命令流程：

```
cd AgenticBI_Final_Olist
pip install -r requirements.txt
python utils/data_cleaning.py   → 产出 data/clean/*.csv
python utils/db_init.py          → MySQL：建库/建基表/TRUNCATE+导入/build mv_*
```

`clean/` 为中间产物，可被 `.gitignore` 忽略体积；演示或备份可考虑保留一份 zip。
