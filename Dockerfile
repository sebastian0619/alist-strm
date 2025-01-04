# 使用多阶段构建
# 阶段1: 构建前端
FROM node:18-alpine as frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# 阶段2: 构建后端
FROM python:3.11-slim
WORKDIR /app

# 安装必要的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY . .

# 创建静态文件目录
RUN mkdir -p static

# 复制前端构建产物到static目录
COPY --from=frontend-builder /app/frontend/dist/* /app/static/

# 设置环境变量
ENV PYTHONPATH=/app
ENV PORT=8081

# 暴露端口
EXPOSE 8081

# 启动命令
CMD ["python", "main.py"]