#!/bin/bash
# free-video-downloader 一键启动脚本
# 用途：同时启动 FastAPI 后端 (8000) 与 Vite 前端 (5173)
# 适用：macOS（本机浏览器可直接访问 localhost:5173）
# 停止：运行 stop-dev.sh

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

PY="/Users/mq/.workbuddy/binaries/python/envs/default/bin/python"
NODE="/Users/mq/.workbuddy/binaries/node/versions/22.22.2/bin/npm"

echo ">> 后端目录：$BACKEND"
echo ">> 前端目录：$FRONTEND"
echo

mkdir -p /tmp/fvd-logs

# 后端
echo "[1/2] 启动后端 (FastAPI @ :8000)..."
cd "$BACKEND"
nohup "$PY" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload \
  > /tmp/fvd-logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "    后端 PID=$BACKEND_PID，日志：/tmp/fvd-logs/backend.log"

# 前端
echo "[2/2] 启动前端 (Vite @ :5173, --host 暴露局域网)..."
cd "$FRONTEND"
nohup "$NODE" run dev -- --host 0.0.0.0 \
  > /tmp/fvd-logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "    前端 PID=$FRONTEND_PID，日志：/tmp/fvd-logs/frontend.log"

sleep 4
echo
echo "=== 端口监听 ==="
lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | tail -n +1
lsof -nP -iTCP:5173 -sTCP:LISTEN 2>/dev/null | tail -n +1

echo
echo "=== 健康检查 ==="
curl -sS -o /dev/null -w "后端 GET /api/health -> HTTP %{http_code}\n" http://127.0.0.1:8000/api/health
curl -sS -o /dev/null -w "前端 GET /            -> HTTP %{http_code}\n" http://127.0.0.1:5173/

echo
echo "============================================================"
echo "  ✅ 启动完成"
echo "  - 前端: http://localhost:5173   (本机浏览器直接打开)"
echo "  - 局域网: http://10.3.10.208:5173  (同网段其他设备)"
echo "  - 后端 API: http://localhost:8000"
echo "  - Swagger:  http://localhost:8000/docs"
echo
echo "  停止服务: ./stop-dev.sh"
echo "  查日志: tail -f /tmp/fvd-logs/{backend,frontend}.log"
echo "============================================================"