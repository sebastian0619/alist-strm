#!/bin/bash

# 启动前端开发服务器
cd /app/frontend && npm run dev -- --host &

# 启动后端服务
cd /app && python main.py 