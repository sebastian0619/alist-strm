from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # 基本配置
    run_after_startup: bool = True
    log_level: Optional[str] = None
    slow_mode: bool = False
    
    # Telegram配置
    tg_token: Optional[str] = None
    tg_user_id: Optional[str] = None
    telegram_bot_proxy_host: Optional[str] = None
    telegram_bot_proxy_port: Optional[int] = None
    
    # Alist配置
    alist_url: str = "http://localhost:5244"
    alist_token: Optional[str] = None
    alist_scan_path: str = "/"
    
    # 文件处理配置
    encode: bool = True
    is_down_sub: bool = False
    min_file_size: int = 100  # MB
    replace_dir: Optional[str] = None
    src_dir: Optional[str] = None
    dst_dir: Optional[str] = None
    refresh: bool = True
    output_dir: str = "data"  # strm文件输出目录

    class Config:
        # 配置文件路径
        env_file = ".env"
        env_file_encoding = "utf-8"
        
        # 允许从环境变量读取
        case_sensitive = False  # 不区分大小写
        env_prefix = ""  # 不使用前缀
        
        # 字段别名，支持多种环境变量名格式
        fields = {
            "run_after_startup": {"env": ["RUN_AFTER_STARTUP", "run_after_startup"]},
            "log_level": {"env": ["LOG_LEVEL", "log_level"]},
            "slow_mode": {"env": ["SLOW_MODE", "slow_mode"]},
            "alist_url": {"env": ["ALIST_URL", "alist_url", "alistServerUrl"]},
            "alist_token": {"env": ["ALIST_TOKEN", "alist_token", "alistServerToken"]},
            "alist_scan_path": {"env": ["ALIST_SCAN_PATH", "alist_scan_path", "alistScanPath"]},
            "encode": {"env": ["ENCODE", "encode"]},
            "is_down_sub": {"env": ["IS_DOWN_SUB", "is_down_sub", "isDownSub"]},
            "min_file_size": {"env": ["MIN_FILE_SIZE", "min_file_size"]},
            "output_dir": {"env": ["OUTPUT_DIR", "output_dir"]},
            "refresh": {"env": ["REFRESH", "refresh"]},
            "src_dir": {"env": ["SRC_DIR", "src_dir"]},
            "dst_dir": {"env": ["DST_DIR", "dst_dir"]},
            "replace_dir": {"env": ["REPLACE_DIR", "replace_dir"]},
            "tg_token": {"env": ["TG_TOKEN", "tg_token"]},
            "tg_user_id": {"env": ["TG_USER_ID", "tg_user_id"]},
            "telegram_bot_proxy_host": {"env": ["TELEGRAM_BOT_PROXY_HOST", "telegram_bot_proxy_host"]},
            "telegram_bot_proxy_port": {"env": ["TELEGRAM_BOT_PROXY_PORT", "telegram_bot_proxy_port"]}
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 转换布尔值字符串
        for field in ['run_after_startup', 'slow_mode', 'encode', 'is_down_sub', 'refresh']:
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, value.lower() == 'true') 