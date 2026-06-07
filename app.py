"""
Agentic BI E-Commerce System - 系统入口

成员D负责：系统入口集成，整合数据分析Agent、NLPAgent、预测模型和决策Agent
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def start_backend():
    """启动 FastAPI 后端服务"""
    import uvicorn
    from config.settings import PORT
    
    print(f"🚀 启动后端服务，端口: {PORT}")
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)


def start_frontend():
    """启动 Streamlit 前端服务"""
    import subprocess
    import os
    
    os.chdir(ROOT)
    print("🎨 启动前端界面")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "dashboard/app_ui.py",
        "--server.port", "8501",
        "--server.address", "0.0.0.0"
    ])


def run_backend_only():
    """仅运行后端服务"""
    start_backend()


def run_frontend_only():
    """仅运行前端服务"""
    start_frontend()


def run_full_stack():
    """运行完整的前后端服务"""
    print("======================================")
    print("   Agentic BI 电商智能分析系统")
    print("======================================")
    print("📊 正在启动完整系统...")
    
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()
    
    time.sleep(3)
    
    frontend_thread = threading.Thread(target=start_frontend, daemon=True)
    frontend_thread.start()
    
    print("✅ 系统启动完成！")
    print("   后端 API: http://localhost:8000")
    print("   前端界面: http://localhost:8501")
    print("======================================")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 系统已停止")


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(description="Agentic BI 电商智能分析系统")
    parser.add_argument(
        "--mode",
        choices=["full", "backend", "frontend"],
        default="full",
        help="运行模式: full(完整), backend(仅后端), frontend(仅前端)"
    )
    args = parser.parse_args()
    
    if args.mode == "full":
        run_full_stack()
    elif args.mode == "backend":
        run_backend_only()
    elif args.mode == "frontend":
        run_frontend_only()


if __name__ == "__main__":
    main()