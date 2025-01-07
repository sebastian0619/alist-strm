from fastapi import APIRouter, HTTPException
from services.service_manager import service_manager
from loguru import logger

router = APIRouter(prefix="/api/archive")

@router.post("/start")
async def start_archive():
    """开始归档处理"""
    if not service_manager.settings.archive_enabled:
        raise HTTPException(status_code=400, detail="归档功能未启用")
        
    try:
        await service_manager.archive_service.archive()
        return {"status": "success", "message": "归档处理已启动"}
    except Exception as e:
        logger.error(f"启动归档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_archive():
    """停止归档处理"""
    if not service_manager.settings.archive_enabled:
        raise HTTPException(status_code=400, detail="归档功能未启用")
        
    try:
        service_manager.archive_service.stop()
        return {"status": "success", "message": "已发送停止归档信号"}
    except Exception as e:
        logger.error(f"停止归档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 