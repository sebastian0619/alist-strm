from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import os
from config import Settings
from services.config_service import ConfigService
from services.service_manager import scheduler_service

router = APIRouter()
settings = Settings()
config_service = ConfigService()

class ConfigUpdate(BaseModel):
    key: str
    value: Any

@router.get("/api/config")
async def get_config():
    """获取当前配置"""
    return config_service.load_config()

@router.post("/api/config")
async def update_config(config_update: ConfigUpdate):
    """更新配置"""
    try:
        # 更新配置
        config_service.update_config(config_update.key, config_update.value)
        
        # 如果更新了定时任务配置，需要重新启动调度器
        if config_update.key in ['schedule_enabled', 'schedule_cron']:
            await scheduler_service.update_schedule(
                settings.schedule_enabled,
                settings.schedule_cron
            )
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 