from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, RootModel
from typing import Dict, Any
import os
import json
from config import Settings
from services.config_service import ConfigService
from services.service_manager import scheduler_service, archive_service, emby_service

router = APIRouter()
settings = Settings()
config_service = ConfigService()

class ConfigUpdate(BaseModel):
    key: str
    value: Any

class MediaTypesConfig(RootModel):
    """媒体类型配置模型"""
    root: Dict[str, Dict[str, Any]]

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
        
        # 重新加载配置
        settings._load_from_config()
        
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
        archive_service.media_types = media_types.root
        return {"status": "success", "message": "媒体类型配置已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class EmbyTestConfig(BaseModel):
    url: str
    api_key: str

@router.post("/api/config/test_emby")
async def test_emby_connection(config: EmbyTestConfig):
    """测试Emby连接"""
    try:
        # 使用提供的配置临时替换emby_service的配置
        original_url = emby_service.emby_url
        original_key = emby_service.api_key
        
        try:
            # 临时设置
            emby_service.emby_url = config.url
            emby_service.api_key = config.api_key
            
            # 尝试获取系统信息作为测试
            import httpx
            url = f"{config.url}/System/Info"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, 
                    params={"api_key": config.api_key},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True, 
                        "message": f"连接成功! Emby服务器版本: {data.get('Version', '未知')}"
                    }
                else:
                    return {
                        "success": False, 
                        "message": f"连接失败，HTTP状态码: {response.status_code}"
                    }
        finally:
            # 恢复原始配置
            emby_service.emby_url = original_url
            emby_service.api_key = original_key
    
    except Exception as e:
        return {"success": False, "message": f"测试失败: {str(e)}"} 

@router.get("/api/config/emby")
async def get_emby_config():
    """获取Emby配置状态"""
    try:
        # 获取Emby当前配置
        config = {
            "emby_enabled": emby_service.emby_enabled,
            "emby_api_url": emby_service.emby_url,
            "emby_api_key": "******" if emby_service.api_key else None,  # 不返回实际密钥
            "strm_root_path": emby_service.strm_root_path,
            "emby_root_path": emby_service.emby_root_path
        }
        
        return {
            "success": True,
            "data": config
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"获取Emby配置失败: {str(e)}"
        } 