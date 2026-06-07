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
# Windows 系统
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Linux/Mac 系统
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. 配置环境变量

```bash
# Windows 系统
copy .env.example .env

# Linux/Mac 系统
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
.\.venv\Scripts\Activate.ps1
python -m utils.test_llm
```

## 5. 执行流水线

仍在项目根：

```bash
.\.venv\Scripts\Activate.ps1
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

## 8. 启动 Agent 服务端 API

本系统内置 FastAPI 服务端，提供 RESTful 接口供前端或第三方调用智能 BI 分析能力。

### 启动服务

```bash
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # 首次或新增依赖后执行
python server.py
```

服务默认监听 `0.0.0.0:3000`（端口由 `config/settings.py` 中的 `PORT` 控制）。

启动后访问 [http://localhost:3000/docs](http://localhost:3000/docs) 查看 Swagger 交互式 API 文档。

### API 接口

| 方法   | 路径          | 说明                                                       |
|--------|---------------|------------------------------------------------------------|
| `GET`  | `/api/health` | 健康检查，返回 `{"status": "ok", "version": "1.0.0"}`      |
| `POST` | `/api/ask`    | **核心接口** — 完整分析链路（协调器 → 数据分析 → 最终答案） |
| `POST` | `/api/parse`  | 仅协调器解析，不执行 SQL，用于快速预览分析类型与意图         |

### 调用示例

```bash
# 健康检查
curl http://localhost:3000/api/health

# 智能分析提问
curl -X POST http://localhost:3000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "上个月哪个品类的 GMV 最高？"}'

# 仅解析意图（不查数据库）
curl -X POST http://localhost:3000/api/parse \
  -H "Content-Type: application/json" \
  -d '{"question": "上个月哪个品类的 GMV 最高？"}'
```

### `POST /api/ask` 响应结构

```json
{
  "success": true,
  "data": {
    "question": "上个月哪个品类的 GMV 最高？",
    "analysis_type": "single_question_aggregation",
    "intent": "查询上个月各品类 GMV 并排序取最高",
    "sql": "SELECT ...",
    "row_count": 1,
    "summary": "上月最高 GMV 品类为 xx，金额 xx 元。",
    "final_answer": "上个月 GMV 最高的品类是 xx，为 xx 元。",
    "downstream_payload": null,
    "errors": []
  }
}
```

> **提示**：`downstream_payload` 字段为后续成员 B / C 的前端或可视化下游预留扩展，当前为 `null`。

---

## 9. 目录说明

```
AgenticBI_Final_Olist/
├── api/                        # API 路由层
│   ├── __init__.py
│   ├── schemas.py              # 请求/响应 Pydantic 模型
│   └── routes.py               # 路由处理函数
├── agents/                     # 智能 Agent 层
│   ├── __init__.py
│   ├── orchestrator_agent.py   # 工作流编排（LangGraph）
│   ├── coordinator_agent.py    # 协调器：分类意图、生成计划
│   ├── data_analysis_agent.py  # 数据分析：生成 SQL + 执行查询
│   ├── visualization_agent.py  # 可视化 Agent：图表类型选择与生成
│   ├── nlp_review_agent.py     # NLP Agent：评论分析
│   ├── decision_agent.py       # 决策 Agent：运营建议
│   └── what_if_agent.py        # 假设分析 Agent
├── dashboard/                  # Streamlit 前端界面（成员 D）
│   ├── app_ui.py               # 主界面：对话输入 + 可视化展示
│   └── chart_renderer.py       # 图表渲染器：支持六类图表
├── config/
│   ├── settings.py             # 全局配置（端口、LLM、数据库）
│   ├── data_dictionary.yaml    # 数据字典 / 口径定义
│   └── prompts.yaml            # 提示词模板
├── models/                     # 预测模型
│   ├── forecast_model.py       # 销售预测模型
│   ├── anomaly_model.py        # 异常检测模型
│   ├── sentiment_model.py      # 情感分析模型
│   └── what_if_model.py        # 假设分析模型
├── utils/
│   ├── data_cleaning.py
│   ├── db_init.py
│   ├── schema_ddl.sql
│   ├── pre_aggregation.sql
│   └── perf_comparison_queries.sql
├── data/raw/
├── data/clean/
├── outputs/                    # 输出目录（成员 D）
│   ├── charts/                 # 生成的图表文件
│   ├── screenshots/            # 运行截图
│   └── demo/                   # 演示材料
├── app.py                      # 系统入口（成员 D）
├── server.py                   # FastAPI 应用入口
├── requirements.txt
└── README.md
```

---

## 10. 可视化与前端界面（成员 D）

### 10.1 启动方式

#### 方式一：完整启动（前后端同时启动）

```bash
.\.venv\Scripts\Activate.ps1
python app.py --mode full
```

#### 方式二：仅启动后端

```bash
.\.venv\Scripts\Activate.ps1
python app.py --mode backend
```

#### 方式三：仅启动前端

```bash
.\.venv\Scripts\Activate.ps1
python app.py --mode frontend
```

### 10.2 访问地址

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:8501 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

### 10.3 前端界面功能

- **左侧对话输入区**：用户输入问题，支持多轮问答
- **右侧可视化展示区**：展示分析结果和图表
- **图表类型支持**：
  - 时间序列折线图
  - 地理气泡图（巴西各州）
  - 柱状图/条形图
  - 矩阵热力图
  - 散点图/气泡图
  - 词云图
- **多轮问答**：支持上下文关联，后续问题可引用前一次分析结果

### 10.4 演示流程

1. **启动系统**：
   ```bash
   python app.py --mode full
   ```

2. **打开前端界面**：访问 http://localhost:8501

3. **示例问题**：
   - "2017年GMV按月趋势如何？"
   - "哪个州的销售额最高？"
   - "最受欢迎的支付方式是什么？"
   - "评价分数最低的卖家有哪些？"
   - "未来六周的销售预测是多少？"

4. **查看结果**：
   - 系统会自动选择合适的图表类型
   - 展示 SQL 查询详情
   - 显示 NLP 分析结果（如果涉及评论）
   - 提供决策建议

### 10.5 数据传递格式

#### 数据分析 Agent 输出格式
```json
{
  "question": "用户问题",
  "sql": "执行的SQL语句",
  "used_view": true,
  "view_name": "mv_xxx",
  "data": [...],
  "summary": "统计摘要"
}
```

#### 可视化 Agent 输出格式
```json
{
  "chart_type": "bar_chart",
  "chart_path": "outputs/charts/xxx.json",
  "chart_title": "图表标题",
  "chart_insight": "图表解释"
}
```

#### NLP Agent 输出格式
```json
{
  "sentiment_score": 0.75,
  "positive_keywords": ["good", "fast"],
  "negative_keywords": ["slow", "broken"],
  "main_complaints": ["配送延迟"],
  "related_sellers_or_categories": ["电子产品"]
}
```

#### 决策 Agent 输出格式
```json
{
  "business_problem": "识别出的业务问题",
  "recommendations": ["建议1", "建议2"],
  "priority": "high",
  "expected_impact": "预期影响",
  "evidence": "依据的数据和分析结果"
}
```
