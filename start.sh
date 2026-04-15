#!/bin/bash

# 一键启动 AI 万能视频下载总结器

PROJECT_DIR="/Users/mq/Documents/Zoom/free-video-downloader"

echo "🚀 启动项目中..."

# 启动后端
echo "📦 启动后端服务..."
cd "$PROJECT_DIR/backend"
python3 main.py &
BACKEND_PID=$!

# 等待后端启动
sleep 3

# 启动前端
echo "🌐 启动前端服务..."
cd "$PROJECT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ 启动完成！"
echo "   后端地址: http://localhost:8000"
echo "   前端地址: http://localhost:5173"
echo "   API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获退出信号，停止所有子进程
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

# 等待
wait