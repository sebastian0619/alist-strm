from pydantic_settings import BaseSettings
from typing import Optional, List
from pydantic import Field, model_validator, ConfigDict

class Settings(BaseSettings):
    """应用配置"""
    
    # 基本配置
    run_after_startup: bool = Field(default=False, alias="RUN_AFTER_STARTUP")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    slow_mode: bool = Field(default=False, alias="SLOW_MODE")
    
    # 定时任务配置
    schedule_enabled: bool = Field(default=False, alias="SCHEDULE_ENABLED")
    schedule_cron: str = Field(default="0 */6 * * *", alias="SCHEDULE_CRON")  # 默认每6小时执行一次
    
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
    skip_patterns: str = Field(default="", alias="SKIP_PATTERNS")
    skip_folders: str = Field(default="", alias="SKIP_FOLDERS")
    skip_extensions: str = Field(default="", alias="SKIP_EXTENSIONS")
    
    # Telegram配置
    tg_enabled: bool = Field(default=False, alias="TG_ENABLED")
    tg_token: str = Field(default="", alias="TG_TOKEN")
    tg_chat_id: str = Field(default="", alias="TG_CHAT_ID")
    tg_proxy_url: str = Field(default="", alias="TG_PROXY_URL")

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

    @property
    def skip_patterns_list(self) -> List[str]:
        """获取跳过模式列表"""
        return [item.strip() for item in self.skip_patterns.split(",") if item.strip()]
    
    @property
    def skip_folders_list(self) -> List[str]:
        """获取跳过文件夹列表"""
        return [item.strip() for item in self.skip_folders.split(",") if item.strip()]
    
    @property
    def skip_extensions_list(self) -> List[str]:
        """获取跳过扩展名列表"""
        return [item.strip() for item in self.skip_extensions.split(",") if item.strip()]
    
    @model_validator(mode='before')
    def parse_booleans(cls, values):
        """解析布尔类型的字段"""
        bool_fields = ['run_after_startup', 'slow_mode', 'encode', 
                      'is_down_sub', 'is_down_meta', 'refresh', 'tg_enabled',
                      'schedule_enabled']
        for field in bool_fields:
            if field in values and isinstance(values[field], str):
                values[field] = str(values[field]).lower() in ('true', '1', 'yes', 'on', 't')
        return values 