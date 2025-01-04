from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import os
from config import Settings
from main import scheduler_service

router = APIRouter()
settings = Settings()

class ConfigUpdate(BaseModel):
    key: str
    value: Any

@router.get("/api/config")
async def get_config():
    """获取当前配置"""
    return {
        # 基本配置
        "run_after_startup": settings.run_after_startup,
        "log_level": settings.log_level,
        "slow_mode": settings.slow_mode,
        
        # 定时任务配置
        "schedule_enabled": settings.schedule_enabled,
        "schedule_cron": settings.schedule_cron,
        
        # Alist配置
        "alist_url": settings.alist_url,
        "alist_token": settings.alist_token,
        "alist_scan_path": settings.alist_scan_path,
        
        # 文件处理配置
        "encode": settings.encode,
        "is_down_sub": settings.is_down_sub,
        "is_down_meta": settings.is_down_meta,
        "min_file_size": settings.min_file_size,
        "output_dir": settings.output_dir,
        "refresh": settings.refresh,
        
        # 跳过规则配置
        "skip_patterns": settings.skip_patterns,
        "skip_folders": settings.skip_folders,
        "skip_extensions": settings.skip_extensions,
        
        # Telegram配置
        "tg_enabled": settings.tg_enabled,
        "tg_token": settings.tg_token,
        "tg_chat_id": settings.tg_chat_id,
        "tg_proxy_url": settings.tg_proxy_url,
    }

@router.post("/api/config")
async def update_config(config: ConfigUpdate):
    """更新配置项"""
    try:
        # 更新环境变量
        os.environ[config.key.upper()] = str(config.value)
        
        # 如果更新的是定时任务相关配置，需要重新启动调度器
        if config.key in ["schedule_enabled", "schedule_cron"]:
            await scheduler_service.update_schedule(
                enabled=settings.schedule_enabled,
                cron=settings.schedule_cron if config.key == "schedule_cron" else None
            )
        
        return {"message": "配置更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置更新失败: {str(e)}") 