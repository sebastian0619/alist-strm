from fastapi import APIRouter, HTTPException
from services.service_manager import service_manager
from pydantic import BaseModel
import json

router = APIRouter(prefix="/api/archive")

@router.post("/start")
async def start_archive():
    """开始归档处理"""
    if not service_manager.archive_service.settings.archive_enabled:
        raise HTTPException(status_code=400, detail="归档功能未启用")
    await service_manager.archive_service.archive()
    return {"message": "归档任务已启动"}

@router.post("/test")
async def test_archive():
    """测试归档处理（只识别不执行）"""
    if not service_manager.archive_service.settings.archive_enabled:
        raise HTTPException(status_code=400, detail="归档功能未启用")
    result = await service_manager.archive_service.archive(test_mode=True)
    return {"message": "归档测试完成", "data": result}

@router.post("/stop")
async def stop_archive():
    """停止归档处理"""
    if not service_manager.archive_service.settings.archive_enabled:
        raise HTTPException(status_code=400, detail="归档功能未启用")
    service_manager.archive_service.stop()
    return {"message": "归档任务已停止"}

@router.get("/media_types")
async def get_media_types():
    """获取媒体类型配置"""
    try:
        media_types = service_manager.archive_service.media_types
        return {"success": True, "data": media_types}
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.post("/media_types")
async def save_media_types(media_types: dict):
    """保存媒体类型配置"""
    try:
        service_manager.archive_service.media_types = media_types
        service_manager.archive_service.save_media_types()
        return {"success": True, "message": "保存成功"}
    except Exception as e:
        return {"success": False, "message": str(e)} 