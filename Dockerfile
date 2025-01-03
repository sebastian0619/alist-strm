# 使用多阶段构建
# 阶段1: 构建前端
FROM node:18-alpine as frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .

# 阶段2: 构建后端
FROM python:3.11-slim
WORKDIR /app

# 安装 Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY . .

# 复制前端代码和依赖
COPY --from=frontend-builder /app/frontend /app/frontend
WORKDIR /app/frontend
RUN npm install
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PORT=8081

# 暴露端口
EXPOSE 8081 5173

# 启动脚本
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]