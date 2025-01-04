from pydantic_settings import BaseSettings
from typing import List
from dotenv import load_dotenv
import os

# 加载 .env 文件
load_dotenv()

class Settings(BaseSettings):
    """应用配置"""
    
    # 基本配置
    run_after_startup: bool = False
    log_level: str = "INFO"
    slow_mode: bool = False
    
    # 定时任务配置
    schedule_enabled: bool = False
    schedule_cron: str = "0 */6 * * *"  # 默认每6小时执行一次
    
    # Alist配置
    alist_url: str = "http://localhost:5244"
    alist_token: str = ""
    alist_scan_path: str = "/"
    
    # 文件处理配置
    encode: str = "UTF-8"
    is_down_sub: bool = True
    is_down_meta: bool = True
    min_file_size: int = 100
    output_dir: str = "./strm"
    refresh: bool = False
    
    # 跳过规则配置
    skip_patterns: List[str] = []
    skip_folders: List[str] = []
    skip_extensions: List[str] = []
    
    # Telegram配置
    tg_enabled: bool = False
    tg_token: str = ""
    tg_chat_id: str = ""
    tg_proxy_url: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False 