import os
import json
from typing import Any, Dict
from loguru import logger
from config import Settings

class ConfigService:
    def __init__(self):
        self.settings = Settings()
        self.config_file = "config/config.json"
        self._ensure_config_dir()
        self._init_config()
    
    def _ensure_config_dir(self):
        """确保配置目录存在"""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
    
    def _init_config(self):
        """初始化配置文件"""
        if not os.path.exists(self.config_file):
            # 从环境变量创建初始配置
            config = {
                # 基本配置
                "run_after_startup": self.settings.run_after_startup,
                "log_level": self.settings.log_level,
                "slow_mode": self.settings.slow_mode,
                
                # 定时任务配置
                "schedule_enabled": self.settings.schedule_enabled,
                "schedule_cron": self.settings.schedule_cron,
                
                # Alist配置
                "alist_url": self.settings.alist_url,
                "alist_token": self.settings.alist_token,
                "alist_scan_path": self.settings.alist_scan_path,
                
                # 文件处理配置
                "encode": self.settings.encode,
                "is_down_sub": self.settings.is_down_sub,
                "is_down_meta": self.settings.is_down_meta,
                "min_file_size": self.settings.min_file_size,
                "output_dir": self.settings.output_dir,
                "cache_dir": self.settings.cache_dir,
                "refresh": self.settings.refresh,
                "remove_empty_dirs": self.settings.remove_empty_dirs,
                
                # 跳过规则配置
                "skip_patterns": self.settings.skip_patterns,
                "skip_folders": self.settings.skip_folders,
                "skip_extensions": self.settings.skip_extensions,
                
                # Telegram配置
                "tg_enabled": self.settings.tg_enabled,
                "tg_token": self.settings.tg_token,
                "tg_chat_id": self.settings.tg_chat_id,
                "tg_proxy_url": self.settings.tg_proxy_url,
            }
            self.save_config(config)
            logger.info("已创建初始配置文件")
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
        return {}
    
    def save_config(self, config: Dict[str, Any]):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logger.info("配置已保存")
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")
    
    def update_config(self, key: str, value: Any):
        """更新单个配置项"""
        config = self.load_config()
        config[key] = value
        self.save_config(config)
        
        # 同步更新到settings
        if hasattr(self.settings, key):
            setattr(self.settings, key, value)
    
    def get_config(self, key: str) -> Any:
        """获取配置项"""
        config = self.load_config()
        return config.get(key) 