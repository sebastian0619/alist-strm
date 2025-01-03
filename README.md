# Alist-Strm

Alist流媒体服务 Python版本

## 功能特点

- 基于FastAPI的现代Web框架
- 异步处理所有I/O操作
- 集成Telegram机器人功能
- 支持定时任务
- 完整的日志记录

## 系统要求

- Python 3.8+
- 运行中的Alist服务器

## 安装

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/alist-strm.git
cd alist-strm
```

2. 创建虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
.\venv\Scripts\activate  # Windows
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

## 配置说明

在 `.env` 文件中配置以下参数：

### 基本配置
- `RUN_AFTER_STARTUP`: 是否在启动时执行任务（true/false）
- `LOG_LEVEL`: 日志级别（DEBUG/INFO/WARNING/ERROR）
- `SLOW_MODE`: 是否启用慢速模式（true/false）

### Telegram配置
- `TG_TOKEN`: Telegram机器人token
- `TG_USER_ID`: Telegram用户ID
- `TELEGRAM_BOT_PROXY_HOST`: 代理服务器地址（可选）
- `TELEGRAM_BOT_PROXY_PORT`: 代理服务器端口（可选）

### Alist配置
- `ALIST_URL`: Alist服务器地址
- `ALIST_TOKEN`: Alist访问令牌

## 运行

```bash
python main.py
```

服务将在 http://localhost:8080 启动

## Docker支持

1. 构建镜像：
```bash
docker build -t alist-strm .
```

2. 运行容器：
```bash
docker run -d \
  --name alist-strm \
  -p 8080:8080 \
  -v $(pwd)/.env:/app/.env \
  alist-strm
```

## 定时任务

默认每天凌晨2点执行一次流媒体处理任务。可以通过修改 `scheduled_task.py` 来调整定时任务的执行时间。

## Telegram机器人命令

- `/start` - 开始使用机器人
- `/help` - 显示帮助信息

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License