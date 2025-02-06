from fastapi import APIRouter, HTTPException
from services.strm_service import StrmService
import os
from loguru import logger
from pydantic import BaseModel
from services.service_manager import service_manager

router = APIRouter(prefix="/api/strm", tags=["strm"])

class MoveRequest(BaseModel):
    src_path: str
    dest_path: str

@router.post("/start")
async def start_scan():
    if service_manager.strm_service._is_running:
        raise HTTPException(status_code=400, detail="扫描已在进行中")
    
    try:
        await service_manager.strm_service.strm()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_scan():
    """停止扫描"""
    if not service_manager.strm_service._is_running:
        return {"status": "success", "message": "没有正在进行的扫描"}
    
    try:
        service_manager.strm_service.stop()
        return {"status": "success", "message": "已发送停止信号"}
    except Exception as e:
        logger.error(f"停止扫描失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_status():
    """获取扫描状态"""
    return {"status": "scanning" if service_manager.strm_service._is_running else "idle"}

@router.post("/clear-cache")
async def clear_cache():
    """清除缓存"""
    try:
        result = await service_manager.strm_service.clear_cache()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs")
async def get_logs():
    """获取最新的日志内容"""
    try:
        log_file = "logs/alist-strm.log"
        if not os.path.exists(log_file):
            return "暂无日志"
        
        # 读取最后1000行日志
        with open(log_file, "r", encoding="utf-8") as f:
            # 使用 deque 读取最后1000行
            from collections import deque
            lines = deque(f, 1000)
            return "".join(lines)
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 

@router.post("/move")
async def move_strm(request: MoveRequest):
    """移动strm文件和对应的云盘文件"""
    result = await service_manager.strm_service.move_strm(request.src_path, request.dest_path)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result 