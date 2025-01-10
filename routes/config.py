from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import os
import json
from config import Settings
from services.config_service import ConfigService
from services.service_manager import scheduler_service, archive_service

router = APIRouter()
settings = Settings()
config_service = ConfigService()

class ConfigUpdate(BaseModel):
    key: str
    value: Any

class MediaTypesConfig(BaseModel):
    """媒体类型配置模型"""
    __root__: Dict[str, Dict[str, Any]]

@router.get("/api/config")
async def get_config():
    """获取当前配置"""
    return config_service.load_config()

@router.get("/api/config/load")
async def load_config():
    """加载完整配置"""
    try:
        config = config_service.load_config()
        return {
            "success": True,
            "data": config
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/api/config/save")
async def save_config(config: dict):
    """保存完整配置"""
    try:
        config_service.save_config(config)
        
        # 如果更新了定时任务配置，需要重新启动调度器
        if any(key in config for key in ['schedule_enabled', 'schedule_cron']):
            await scheduler_service.update_schedule(
                settings.schedule_enabled,
                settings.schedule_cron
            )
        
        return {"success": True, "message": "配置保存成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.post("/api/config")
async def update_config(config_update: ConfigUpdate):
    """更新单个配置项"""
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

@router.get("/api/config/archive_types")
async def get_archive_types():
    """获取媒体类型配置"""
    try:
        return archive_service.media_types
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/config/archive_types")
async def save_archive_types(media_types: MediaTypesConfig):
    """保存媒体类型配置到archive.json"""
    try:
        archive_service.media_types = media_types.__root__
        return {"status": "success", "message": "媒体类型配置已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 