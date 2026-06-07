"""
FastAPI 应用入口。
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.routes import router
from config.settings import PORT

app = FastAPI(
    title="Agentic BI E-Commerce API",
    description="电商 BI 智能分析系统后端 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    """欢迎页面 - 提供 API 文档链接"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Agentic BI E-Commerce API</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px; }
            h1 { color: #2563eb; }
            .endpoint { background: #f3f4f6; padding: 12px; margin: 8px 0; border-radius: 4px; }
            .url { font-family: monospace; color: #16a34a; }
        </style>
    </head>
    <body>
        <h1>🚀 Agentic BI 电商智能分析系统</h1>
        <p>欢迎使用 Agentic BI 后端 API 服务。</p>
        
        <h2>📚 API 文档</h2>
        <div class="endpoint">
            <a href="/docs" target="_blank" class="url">/docs</a> - Swagger UI 交互式文档
        </div>
        <div class="endpoint">
            <a href="/redoc" target="_blank" class="url">/redoc</a> - ReDoc 文档
        </div>
        
        <h2>🔌 主要接口</h2>
        <div class="endpoint">
            <span class="url">GET /api/health</span> - 健康检查
        </div>
        <div class="endpoint">
            <span class="url">POST /api/ask</span> - 智能分析提问（核心接口）
        </div>
        <div class="endpoint">
            <span class="url">POST /api/parse</span> - 仅解析意图
        </div>
        
        <h2>🌐 前端界面</h2>
        <p>请访问 <a href="http://localhost:8501" target="_blank">http://localhost:8501</a> 打开前端可视化界面。</p>
    </body>
    </html>
    """

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
