"""
数据库与路径配置。
优先读环境变量，便于组员各自本机互不冲突。
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

# 项目根目录 AgenticBI_Final_Olist/
ROOT = Path(__file__).resolve().parents[1]

DATA_RAW = ROOT / "data" / "raw"
DATA_CLEAN = ROOT / "data" / "clean"

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")  # 建议本机设置环境变量，勿提交密码到 git
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "olist_agentic_bi")


def sqlalchemy_url(password: str | None = None) -> str:
    pwd = MYSQL_PASSWORD if password is None else password
    safe = quote_plus(str(pwd) if pwd is not None else "")
    return (
        f"mysql+pymysql://{MYSQL_USER}:{safe}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
    )


def ensure_dirs() -> None:
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    DATA_CLEAN.mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs").mkdir(parents=True, exist_ok=True)
