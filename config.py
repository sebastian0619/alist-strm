from pydantic_settings import BaseSettings
from typing import Optional, List
from pydantic import Field, model_validator

class Settings(BaseSettings):
    # 基本配置
    run_after_startup: bool = Field(default=False, alias="RUN_AFTER_STARTUP")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    slow_mode: bool = Field(default=False, alias="SLOW_MODE")

    # Alist配置
    alist_url: str = Field(default="", alias="ALIST_URL")
    alist_token: str = Field(default="", alias="ALIST_TOKEN")
    alist_scan_path: str = Field(default="", alias="ALIST_SCAN_PATH")

    # 文件处理配置
    encode: bool = Field(default=True, alias="ENCODE")
    is_down_sub: bool = Field(default=False, alias="IS_DOWN_SUB")
    is_down_meta: bool = Field(default=False, alias="IS_DOWN_META")
    min_file_size: int = Field(default=100, alias="MIN_FILE_SIZE")
    output_dir: str = Field(default="data", alias="OUTPUT_DIR")
    refresh: bool = Field(default=True, alias="REFRESH")

    # 跳过规则配置
    skip_patterns: List[str] = Field(default=[], alias="SKIP_PATTERNS")
    skip_folders: List[str] = Field(default=[], alias="SKIP_FOLDERS")
    skip_extensions: List[str] = Field(default=[], alias="SKIP_EXTENSIONS")

    # Telegram配置
    tg_enabled: bool = Field(default=False, alias="TG_ENABLED")
    tg_token: str = Field(default="", alias="TG_TOKEN")
    tg_chat_id: str = Field(default="", alias="TG_CHAT_ID")
    tg_proxy_url: str = Field(default="", alias="TG_PROXY_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @model_validator(mode='before')
    def parse_lists(cls, values):
        """解析列表类型的字段"""
        list_fields = ['skip_patterns', 'skip_folders', 'skip_extensions']
        for field in list_fields:
            if field in values and isinstance(values[field], str):
                values[field] = [item.strip() for item in values[field].split(',') if item.strip()]
        return values

    @model_validator(mode='before')
    def parse_booleans(cls, values):
        """解析布尔类型的字段"""
        bool_fields = ['run_after_startup', 'slow_mode', 'encode', 
                      'is_down_sub', 'is_down_meta', 'refresh', 'tg_enabled']
        for field in bool_fields:
            if field in values and isinstance(values[field], str):
                values[field] = str(values[field]).lower() in ('true', '1', 'yes', 'on', 't')
        return values 