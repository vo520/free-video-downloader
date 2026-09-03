FROM python:3.13-slim

WORKDIR /app

# yt-dlp 偶尔需要编译本地扩展，装最小工具链（libxml2/libxslt 给 sre-starlette 间接依赖；其他模块按需扩展）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单，复用 Docker 缓存（仅当 requirements.txt 变更才重装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再复制源码（高频变更层在后）
COPY . .

EXPOSE 8000

# --reload：源码挂载场景下文件变化时 uvicorn 自动重启；
# PYTHONUNBUFFERED=1：保证 docker logs 实时输出。
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]