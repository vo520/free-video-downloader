#!/bin/bash
# 关闭 free-video-downloader 开发服务

echo ">> 关闭后端..."
pkill -f "uvicorn main:app" 2>/dev/null && echo "   后端已停止" || echo "   后端未运行"

echo ">> 关闭前端..."
pkill -f "vite" 2>/dev/null && echo "   前端已停止" || echo "   前端未运行"

sleep 1
echo
echo "=== 端口监听(应为空) ==="
lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null
lsof -nP -iTCP:5173 -sTCP:LISTEN 2>/dev/null
echo "完成。"