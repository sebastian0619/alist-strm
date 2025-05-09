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
    
    def save_to_config(self):
        """保存当前配置到config/config.json文件"""
        config_file = "config/config.json"
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            
            # 如果文件已存在，先读取现有配置
            existing_config = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        existing_config = json.load(f)
                except Exception:
                    pass
            
            # 获取实例的所有属性，但排除以下划线开头的私有属性
            config_dict = {}
            for key, value in self.__dict__.items():
                if not key.startswith('_') and key != 'model_config':
                    config_dict[key] = value
            
            # 更新现有配置
            existing_config.update(config_dict)
            
            # 写入文件
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(existing_config, f, ensure_ascii=False, indent=4)
                
            return True
        except Exception as e:
            print(f"保存配置失败: {str(e)}")
            return False
    
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
    alist_url: str = Field(default="http://localhost:5244", description="AList服务地址")
    alist_external_url: str = Field(default="", description="AList外部访问地址（用于STRM文件）")
    use_external_url: bool = Field(default=False, description="是否在STRM文件中使用外部访问地址")
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
    archive_enabled: bool = Field(default=False, alias="ARCHIVE_ENABLED")  # 是否启用归档
    archive_source_root: str = Field(default="", alias="ARCHIVE_SOURCE_ROOT")  # 源目录（本地路径）
    archive_source_alist: str = Field(default="", alias="ARCHIVE_SOURCE_ALIST")  # 源目录（Alist路径）
    archive_target_root: str = Field(default="", alias="ARCHIVE_TARGET_ROOT")  # 目标目录（Alist路径）
    archive_auto_strm: bool = Field(default=False, alias="ARCHIVE_AUTO_STRM")
    archive_delete_source: bool = Field(default=False, alias="ARCHIVE_DELETE_SOURCE")
    archive_delete_delay_days: int = Field(default=7, alias="ARCHIVE_DELETE_DELAY_DAYS")  # 删除延迟天数
    
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
    
    # Emby配置
    emby_enabled: bool = Field(default=False, alias="EMBY_ENABLED")  # 是否启用Emby刷库
    emby_api_url: str = Field(default="http://localhost:8096/emby", alias="EMBY_API_URL", description="Emby API地址")
    emby_api_key: str = Field(default="", alias="EMBY_API_KEY", description="Emby API密钥")
    strm_root_path: str = Field(default="", alias="STRM_ROOT_PATH", description="STRM文件根路径")
    emby_root_path: str = Field(default="", alias="EMBY_ROOT_PATH", description="Emby媒体库根路径")
    
    # 下载元数据文件配置
    download_metadata: bool = Field(default=False, alias="DOWNLOAD_METADATA")
    
    # TMDB元数据配置
    tmdb_cache_dir: str = Field(default="cache/tmdb", alias="TMDB_CACHE_DIR", description="TMDB元数据缓存目录")
    
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
                      'archive_auto_strm', 'archive_delete_source', 'emby_enabled',
                      'use_external_url']
        for field in bool_fields:
            if field in values and isinstance(values[field], str):
                values[field] = str(values[field]).lower() in ('true', '1', 'yes', 'on', 't')
        return values 