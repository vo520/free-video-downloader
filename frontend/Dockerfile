FROM node:22-alpine

WORKDIR /app

# 先复制 package.json 复用 Docker 缓存
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .

EXPOSE 5173

# --host 0.0.0.0 让宿主机可访问；vite.config.js 的 proxy target 通过 VITE_BACKEND_HOST 指向后端容器名
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]