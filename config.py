from pydantic_settings import BaseSettings
from typing import List
from pydantic import Field, model_validator

class Settings(BaseSettings):
    """应用配置"""
    
    # 基本配置
    run_after_startup: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    slow_mode: bool = Field(default=False)
    
    # 定时任务配置
    schedule_enabled: bool = Field(default=False)
    schedule_cron: str = Field(default="0 */6 * * *")  # 默认每6小时执行一次
    
    # Alist配置
    alist_url: str = Field(default="http://localhost:5244")
    alist_token: str = Field(default="")
    alist_scan_path: str = Field(default="/")
    
    # 文件处理配置
    encode: str = Field(default="UTF-8")
    is_down_sub: bool = Field(default=True)
    is_down_meta: bool = Field(default=True)
    min_file_size: int = Field(default=100)
    output_dir: str = Field(default="./data")
    refresh: bool = Field(default=False)
    
    # 跳过规则配置（字符串形式，用逗号分隔）
    skip_patterns: str = Field(default="")
    skip_folders: str = Field(default="")
    skip_extensions: str = Field(default="")
    
    # Telegram配置
    tg_enabled: bool = Field(default=False)
    tg_token: str = Field(default="")
    tg_chat_id: str = Field(default="")
    tg_proxy_url: str = Field(default="")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
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
        bool_fields = ['run_after_startup', 'slow_mode', 'is_down_sub', 
                      'is_down_meta', 'refresh', 'tg_enabled', 'schedule_enabled']
        for field in bool_fields:
            if field in values and isinstance(values[field], str):
                values[field] = str(values[field]).lower() in ('true', '1', 'yes', 'on', 't')
        return values 