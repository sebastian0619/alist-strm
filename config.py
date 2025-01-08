from pydantic_settings import BaseSettings
from typing import Optional, List
from pydantic import Field, model_validator, ConfigDict
import os
import json

class Settings(BaseSettings):
    """应用配置"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_from_config()
    
    def _load_from_config(self):
        """从配置文件加载配置"""
        config_file = "config/config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key, value in config.items():
                        if hasattr(self, key):
                            setattr(self, key, value)
            except Exception:
                pass
    
    # 基本配置
    run_after_startup: bool = Field(default=False, alias="RUN_AFTER_STARTUP")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    slow_mode: bool = Field(default=False, alias="SLOW_MODE")
    
    # 定时任务配置
    schedule_enabled: bool = Field(default=False, alias="SCHEDULE_ENABLED")
    schedule_cron: str = Field(default="0 */6 * * *", alias="SCHEDULE_CRON")  # 默认每6小时执行一次
    archive_schedule_enabled: bool = Field(default=False, alias="ARCHIVE_SCHEDULE_ENABLED")
    archive_schedule_cron: str = Field(default="0 3 * * *", alias="ARCHIVE_SCHEDULE_CRON")  # 默认每天凌晨3点执行
    
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
    cache_dir: str = Field(default="cache", alias="CACHE_DIR")
    refresh: bool = Field(default=True, alias="REFRESH")
    remove_empty_dirs: bool = Field(default=False, alias="REMOVE_EMPTY_DIRS")
    
    # 跳过规则配置
    skip_patterns: str = Field(default="", alias="SKIP_PATTERNS")
    skip_folders: str = Field(default="", alias="SKIP_FOLDERS")
    skip_extensions: str = Field(default="", alias="SKIP_EXTENSIONS")
    
    # Telegram配置
    tg_enabled: bool = Field(default=False, alias="TG_ENABLED")
    tg_token: str = Field(default="", alias="TG_TOKEN")
    tg_chat_id: str = Field(default="", alias="TG_CHAT_ID")
    tg_proxy_url: str = Field(default="", alias="TG_PROXY_URL")
    
    # 归档配置
    archive_enabled: bool = Field(default=False, alias="ARCHIVE_ENABLED")
    archive_source_root: str = Field(default="", alias="ARCHIVE_SOURCE_ROOT")  # 源根目录
    archive_target_root: str = Field(default="", alias="ARCHIVE_TARGET_ROOT")  # 目标根目录
    archive_auto_strm: bool = Field(default=False, alias="ARCHIVE_AUTO_STRM")
    archive_delete_source: bool = Field(default=False, alias="ARCHIVE_DELETE_SOURCE")
    
    # 归档阈值配置
    archive_excluded_extensions: str = Field(
        default=".nfo,.ass,.srt,.jpg,.jpeg,.png",
        alias="ARCHIVE_EXCLUDED_EXTENSIONS"
    )
    
    # 媒体类型配置 - JSON格式
    # 格式: {"类型名称": {"dir": "目录名", "creation_days": 天数, "mtime_days": 天数}}
    # 例如: {"电影": {"dir": "movie", "creation_days": 20, "mtime_days": 20}}
    archive_media_types: str = Field(
        default=json.dumps({
            "电影": {"dir": "movie", "creation_days": 20, "mtime_days": 20},
            "完结动漫": {"dir": "anime", "creation_days": 100, "mtime_days": 45},
            "电视剧": {"dir": "tv", "creation_days": 10, "mtime_days": 90},
            "综艺": {"dir": "variety", "creation_days": 1, "mtime_days": 1}
        }, ensure_ascii=False),
        alias="ARCHIVE_MEDIA_TYPES"
    )
    
    # 定时任务配置

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
                      'schedule_enabled', 'remove_empty_dirs', 'archive_enabled',
                      'archive_auto_strm', 'archive_delete_source']
        for field in bool_fields:
            if field in values and isinstance(values[field], str):
                values[field] = str(values[field]).lower() in ('true', '1', 'yes', 'on', 't')
        return values 