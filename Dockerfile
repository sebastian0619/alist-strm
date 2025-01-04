# 阶段1: 构建前端
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# 阶段2: 构建后端
FROM python:3.11-slim
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist /app/static

# 复制后端代码
COPY . .

# 设置环境变量
ENV PORT=8081

# 启动应用
CMD ["python", "main.py"]