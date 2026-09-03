#!/bin/bash

PROJECT_DIR="/Users/mq/Documents/Zoom/free-video-downloader"
cd "$PROJECT_DIR"

echo "🚀 启动 AI 万能视频下载器..."

# 停止所有旧进程
pkill -9 -f "uvicorn" 2>/dev/null
pkill -9 -f "vite" 2>/dev/null
sleep 1

# 启动后端
echo "📦 启动后端服务..."
cd "$PROJECT_DIR/backend"
/usr/local/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

sleep 3

# 检查后端是否启动成功
if ! lsof -ti:8000 > /dev/null; then
    echo "❌ 后端启动失败！查看日志："
    cat /tmp/backend.log | tail -20
    exit 1
fi

echo "✅ 后端启动成功 (PID: $BACKEND_PID)"

# 启动前端
echo "🌐 启动前端服务..."
cd "$PROJECT_DIR/frontend"
unset QCLAW_CLI_NODE_BINARY
npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!

sleep 3

# 检查前端是否启动成功
if ! lsof -ti:5173,5174,5175,5176 > /dev/null; then
    echo "❌ 前端启动失败！查看日志："
    cat /tmp/frontend.log | tail -20
    exit 1
fi

FRONTEND_PORT=$(lsof -ti:5173 2>/dev/null && echo "5173" || \
                (lsof -ti:5174 2>/dev/null && echo "5174") || \
                (lsof -ti:5175 2>/dev/null && echo "5175") || \
                (lsof -ti:5176 2>/dev/null && echo "5176") || echo "未知")

echo "✅ 前端启动成功 (端口: $FRONTEND_PORT, PID: $FRONTEND_PID)"

echo ""
echo "========================================"
echo "✅ 启动完成！"
echo "   后端地址: http://localhost:8000"
echo "   前端地址: http://localhost:$FRONTEND_PORT"
echo "   API 文档: http://localhost:8000/docs"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 捕获退出信号
cleanup() {
    echo ""
    echo "🛑 停止所有服务..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

# 等待
wait
