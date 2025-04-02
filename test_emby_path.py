#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试Emby路径转换功能
"""

import asyncio
import os
import sys
from loguru import logger

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入服务
from services.emby_service import EmbyService
from config import Settings

async def test_path_conversion():
    """测试路径转换功能"""
    
    # 初始化EmbyService
    emby_service = EmbyService()
    
    # 打印当前配置
    settings = Settings()
    print("当前配置:")
    print(f"STRM根路径: {settings.strm_root_path}")
    print(f"Emby根路径: {settings.emby_root_path}")
    print("-" * 50)
    
    # 测试路径
    test_paths = [
        # 标准路径
        settings.strm_root_path + "/电影/测试电影 (2023)/测试电影.strm",
        # 无前导斜杠
        settings.strm_root_path.lstrip("/") + "/电视剧/测试剧集/Season 1/测试剧集 - S01E01.strm",
        # 路径带反斜杠
        settings.strm_root_path.replace("/", "\\") + "\\动漫\\测试动漫\\Season 1\\测试动漫 - S01E01.strm",
        # 不完全匹配路径
        "/mnt/user/media/测试媒体/测试电影 (2020).strm",
        # 完全不匹配路径
        "/completely/different/path/test.strm"
    ]
    
    # 测试每个路径
    for path in test_paths:
        emby_path = emby_service.convert_to_emby_path(path)
        print(f"原始路径: {path}")
        print(f"转换路径: {emby_path}")
        print("-" * 50)

if __name__ == "__main__":
    # 设置日志级别
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    
    # 运行测试
    asyncio.run(test_path_conversion()) 