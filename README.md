# Alist-STRM

一个用于将 Alist 视频文件转换为 STRM 文件的工具，方便将网盘资源导入Emby/Jellyfin/Plex等媒体服务器。

本项目是基于[Alist-STRM](https://github.com/907739769/alist-strm)项目的Python实现，感谢原作者的贡献。

基于原作者代码思路，通过GPT改写，添加了WebUI界面，和一系列UI相关的配置(配置可通过环境变量/.env文件或直接通过WebUI设置)。支持定时扫描和UI手动启动扫描，支持优雅停止。支持Telegram通知，支持跳过指定目录、文件类型和模式，支持URL编码选项，支持多种视频格式（mp4, mkv, avi 等）。

## 功能特点

- 🚀 自动扫描 Alist 目录并生成 STRM 文件
- 🎯 支持跳过指定目录、文件类型和模式
- 📝 支持 URL 编码选项
- 🔄 支持自动启动扫描
- ⏰ 支持定时扫描任务
- 🌐 提供 Web 界面进行配置和控制
- 📱 支持 Telegram 通知
- ⏹ 支持优雅停止扫描
- 🎬 支持多种视频格式（mp4, mkv, avi 等）

## 使用方法

### Docker 部署

```bash
docker run -d \
  --name alist-strm \
  -p 8081:8081 \
  -v /path/to/data:/app/data \
  -e ALIST_URL=http://your-alist-url \
  -e ALIST_TOKEN=your-alist-token \
  -e ALIST_SCAN_PATH=/path/to/scan \
  ghcr.io/sebastian0619/alist-strm:latest
```

### Docker Compose 部署

```yaml
version: '3'
services:
  alist-strm:
    image: ghcr.io/sebastian0619/alist-strm:latest
    container_name: alist-strm
    ports:
      - "8081:8081"
    volumes:
      - ./data:/app/data
    environment:
      - ALIST_URL=http://your-alist-url
      - ALIST_TOKEN=your-alist-token
      - ALIST_SCAN_PATH=/path/to/scan
    restart: unless-stopped
```

## 配置说明

### 基本配置

- `RUN_AFTER_STARTUP`: 是否在启动时自动开始扫描（默认：false）
- `LOG_LEVEL`: 日志级别（默认：INFO）
- `SLOW_MODE`: 是否启用慢速模式（默认：false）

### 定时任务配置

- `SCHEDULE_ENABLED`: 是否启用定时扫描（默认：false）
- `SCHEDULE_CRON`: 定时任务 Cron 表达式（默认：0 */6 * * *，即每6小时执行一次）
  - Cron 表达式格式：分 时 日 月 星期
  - 示例：
    - `0 */6 * * *`: 每6小时执行一次
    - `0 0 * * *`: 每天凌晨执行
    - `0 */12 * * *`: 每12小时执行一次
    - `0 0 */2 * *`: 每2天执行一次

### Alist 配置

- `ALIST_URL`: Alist 服务器地址
- `ALIST_TOKEN`: Alist API Token
- `ALIST_SCAN_PATH`: 要扫描的 Alist 目录路径

### 文件处理配置

- `ENCODE`: 是否对 URL 进行编码（默认：true）
- `IS_DOWN_SUB`: 是否下载字幕文件（默认：false）
- `IS_DOWN_META`: 是否下载元数据文件（默认：false）
- `MIN_FILE_SIZE`: 最小文件大小（MB）（默认：100）
- `OUTPUT_DIR`: STRM 文件输出目录（默认：data）
- `REFRESH`: 是否刷新文件列表（默认：true）

### 跳过规则配置

- `SKIP_PATTERNS`: 要跳过的文件/目录模式，支持正则表达式（例如：sample,trailer,预告片）
- `SKIP_FOLDERS`: 要跳过的文件夹名称（例如：extras,花絮,番外,特典）
- `SKIP_EXTENSIONS`: 要跳过的文件扩展名（例如：.iso,.mka）

### Telegram 通知配置

- `TG_ENABLED`: 是否启用 Telegram 通知（默认：false）
- `TG_TOKEN`: Telegram Bot Token
- `TG_CHAT_ID`: Telegram 聊天 ID
- `TG_PROXY_URL`: Telegram 代理地址（可选）

## Web 界面

访问 `http://your-ip:8081` 可以进行以下操作：

- 查看和修改配置
- 启动/停止扫描
- 设置定时扫描任务
- 查看扫描状态和日志

## 注意事项

1. 确保 Alist 服务器可以正常访问
2. 配置正确的 Alist Token
3. 设置合适的文件大小限制
4. 根据需要配置跳过规则
5. 如需使用 Telegram 通知，请正确配置相关参数
6. 定时任务使用 Cron 表达式，请确保格式正确

## 系统要求

- Docker 环境
- 可访问的 Alist 服务器
- 足够的存储空间用于 STRM 文件

## 更新日志

### v1.0.0
- 初始版本发布

### v1.1.0
- 添加 Web 界面
- 添加 Telegram 通知支持
- 添加文件跳过规则
- 添加扫描控制功能

### v1.2.0
- 优化停止扫描功能
- 添加扫描状态显示
- 改进错误处理
- 优化配置管理

### v1.3.0
- 添加定时扫描功能
- 支持通过 Web 界面配置定时任务
- 优化任务调度逻辑

