# Alist-STRM

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue.js-3.x-green)](https://vuejs.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Alist](https://img.shields.io/badge/Alist-3.x-orange)](https://alist.nn.ci/)

[English](README_en.md) | 简体中文

一个用于自动为Alist媒体文件生成STRM文件的工具，支持Vue3前端配置界面。

## 主要功能

- 🎬 自动扫描Alist目录并生成STRM文件
- 📝 支持字幕文件自动下载
- 📊 支持媒体元数据文件下载（NFO、海报等）
- 🌐 Vue3前端配置界面
- 🐳 Docker支持
- 🔄 支持目录替换和路径映射
- 📱 Telegram通知支持

## 快速开始

### Docker部署

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/alist-strm.git
cd alist-strm
```

2. 配置环境变量：
创建`.env`文件或直接使用环境变量：
```env
ALIST_URL=http://your-alist-url:5244
ALIST_TOKEN=your-alist-token
ALIST_SCAN_PATH=/path/to/scan
OUTPUT_DIR=data
```

3. 启动服务：
```bash
docker-compose up -d
```

### 本地部署

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量（同上）

3. 启动服务：
```bash
python main.py
```

## 配置说明

### 基本配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| ALIST_URL | Alist服务器地址 | http://localhost:5244 |
| ALIST_TOKEN | Alist认证令牌 | 无 |
| ALIST_SCAN_PATH | 扫描路径 | / |
| OUTPUT_DIR | STRM文件输出目录 | data |

### 功能开关

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| ENCODE | 是否对URL进行编码 | true |
| IS_DOWN_SUB | 是否下载字幕文件 | false |
| IS_DOWN_META | 是否下载元数据文件 | false |
| SLOW_MODE | 是否启用慢速模式 | false |
| RUN_AFTER_STARTUP | 启动后是否立即运行 | true |

### 高级配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| MIN_FILE_SIZE | 最小文件大小(MB) | 100 |
| REPLACE_DIR | 目录替换规则 | 无 |
| SRC_DIR | 源目录路径 | 无 |
| DST_DIR | 目标目录路径 | 无 |

### Telegram通知配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| TG_TOKEN | Telegram Bot Token | 无 |
| TG_USER_ID | Telegram用户ID | 无 |
| TELEGRAM_BOT_PROXY_HOST | 代理服务器地址 | 无 |
| TELEGRAM_BOT_PROXY_PORT | 代理服务器端口 | 无 |

## 支持的文件类型

### 视频文件
- .mp4
- .mkv
- .avi
- .mov
- .wmv
- .flv
- .m4v
- .rmvb

### 字幕文件
- .srt
- .ass
- .ssa
- .sub

### 元数据文件
- .nfo（媒体信息）
- .jpg/.jpeg/.png（封面图片）
- .tbn（缩略图）
- poster.jpg（海报）
- fanart.jpg（同人画）
- banner.jpg（横幅）
- landscape.jpg（风景图）
- thumb.jpg（缩略图）
- logo.png（Logo）
- clearart.png（清晰艺术图）
- disc.png（光盘图）
- backdrop.jpg（背景图）

## 前端界面

访问 `http://your-ip:3000` 可以打开Web配置界面，支持：

- 基本配置管理
- STRM文件生成
- 实时日志查看
- 配置导入导出

## 注意事项

1. 确保Alist Token具有足够的权限
2. 大型目录建议开启慢速模式
3. 输出目录需要有写入权限
4. Docker部署时注意映射正确的端口和目录

## 常见问题

1. STRM文件无法播放
   - 检查Alist URL是否可访问
   - 确认Token权限是否正确
   - 验证文件路径是否正确

2. 字幕文件未下载
   - 确认IS_DOWN_SUB已开启
   - 检查字幕文件格式是否支持
   - 验证输出目录权限

3. 目录替换不生效
   - 检查REPLACE_DIR配置格式
   - 确认SRC_DIR和DST_DIR配置正确

## 贡献指南

欢迎提交Issue和Pull Request！

## 许可证

MIT License

