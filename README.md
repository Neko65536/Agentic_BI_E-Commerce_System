# AgenticBI_Final_Olist — 成员 A 数据层快速上手

本项目按课程建议目录搭建；你已选择 **成员 A**：负责清洗、入库与 `mv_*` 汇总层。

## 1. 本机前置

| 组件 | 说明 |
|------|------|
| Python | 建议 3.10+ |
| MySQL | 8.x 均可；记下 root（或专属账号）与密码 |

## 2. 数据准备

1. 下载 [Kaggle Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 全部 CSV。
2. 将全部 CSV **原样放进** `data/raw/`（见 `data/README.md`）。

## 3. 安装依赖

在项目根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. 配置环境变量

```bash
cp .env.example .env
```
- 在 `.env` 中配置必要环境变量

### 数据库配置

```bash
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your-username
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=your-database-name
```

### LLM 配置

```bash
LLM_PROVIDER=llm-provider-name
LLM_BASE_URL=https://api.example.com/api/v1
LLM_API_KEY=llm-api-key
LLM_MODEL=llm-model-name
LLM_TEMPERATURE=0.6
LLM_TIMEOUT_SECONDS=60
```

- 测试 `LLM` 可用性：

```bash
source .venv/bin/activate
python -m utils.test_llm
```

## 5. 执行流水线

仍在项目根：

```bash
source .venv/bin/activate
python utils/data_cleaning.py
python utils/db_init.py
```

- 第一次会向 MySQL 连接的库，执行 `utils/schema_ddl.sql`，`TRUNCATE` 各基表再导入清洗后的 CSV，然后执行 `utils/pre_aggregation.sql` 填满六张 `mv_*`。
- 若仅需空表：`python utils/db_init.py --ddl-only`

## 6. 性能对比（报告截图）

在 Workbench / DBeaver 里对同一业务问题记下执行时间：

- **快路径：** 查 `mv_*`（示例见 `utils/perf_comparison_queries.sql`）。
- **慢路径：** 多表 JOIN 实时聚合。

截取前后耗时（可加 `EXPLAIN`）写入报告。

## 7. 给成员 B / 全班同步

- **必须提交/共享：** `config/data_dictionary.yaml`、`utils/schema_ddl.sql`、`utils/pre_aggregation.sql`、`utils/data_cleaning.py`、`utils/db_init.py`。
- **与全组统一：** GMV / 准时率口径（见 `config/data_dictionary.yaml` 顶部 `meta`）。

## 8. 目录说明

```
AgenticBI_Final_Olist/
├── config/
│   ├── settings.py
│   └── data_dictionary.yaml
├── utils/
│   ├── data_cleaning.py
│   ├── db_init.py
│   ├── schema_ddl.sql
│   ├── pre_aggregation.sql
│   └── perf_comparison_queries.sql
├── data/raw/
├── data/clean/
├── outputs/
├── requirements.txt
└── README.md
```
