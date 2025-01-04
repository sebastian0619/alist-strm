from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import Field, model_validator
import os

class Settings(BaseSettings):
    # 基本配置
    run_after_startup: bool = Field(default=True, alias="RUN_AFTER_STARTUP")
    log_level: Optional[str] = Field(default=None, alias="LOG_LEVEL")
    slow_mode: bool = Field(default=False, alias="SLOW_MODE")
    
    # Telegram配置
    tg_token: Optional[str] = Field(default=None, alias="TG_TOKEN")
    tg_user_id: Optional[str] = Field(default=None, alias="TG_USER_ID")
    telegram_bot_proxy_host: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_PROXY_HOST")
    telegram_bot_proxy_port: Optional[int] = Field(default=None, alias="TELEGRAM_BOT_PROXY_PORT")
    
    # Alist配置
    alist_url: str = Field(default="http://localhost:5244", alias="ALIST_URL")
    alist_token: Optional[str] = Field(default=None, alias="ALIST_TOKEN")
    alist_scan_path: str = Field(default="/", alias="ALIST_SCAN_PATH")
    
    # 文件处理配置
    encode: bool = Field(default=True, alias="ENCODE")
    is_down_sub: bool = Field(default=False, alias="IS_DOWN_SUB")
    is_down_meta: bool = Field(default=False, alias="IS_DOWN_META")
    min_file_size: int = Field(default=100, alias="MIN_FILE_SIZE")
    replace_dir: Optional[str] = Field(default=None, alias="REPLACE_DIR")
    src_dir: Optional[str] = Field(default=None, alias="SRC_DIR")
    dst_dir: Optional[str] = Field(default=None, alias="DST_DIR")
    refresh: bool = Field(default=True, alias="REFRESH")
    output_dir: str = Field(default="data", alias="OUTPUT_DIR")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_prefix = ""
        populate_by_name = True

    @model_validator(mode='after')
    def validate_boolean_fields(self):
        """验证并转换布尔值字符串"""
        bool_fields = ['run_after_startup', 'slow_mode', 'encode', 'is_down_sub', 'is_down_meta', 'refresh']
        for field in bool_fields:
            value = getattr(self, field)
            if isinstance(value, str):
                value = value.lower().strip()
                setattr(self, field, value in ['true', '1', 'yes', 'on', 't'])
        return self 