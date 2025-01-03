from pydantic_settings import BaseSettings
from typing import Optional

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
        env_file = ".env"
        env_file_encoding = "utf-8" 