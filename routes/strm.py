from fastapi import APIRouter, HTTPException
from services.strm_service import StrmService
import os
from loguru import logger

router = APIRouter(prefix="/api/strm")
strm_service = None

@router.post("/start")
async def start_scan():
    global strm_service
    if strm_service is not None:
        raise HTTPException(status_code=400, detail="扫描已在进行中")
    
    strm_service = StrmService()
    try:
        await strm_service.strm()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await strm_service.close()
        strm_service = None

@router.post("/stop")
async def stop_scan():
    """停止扫描"""
    global strm_service
    if strm_service is None:
        return {"status": "success", "message": "没有正在进行的扫描"}
    
    try:
        strm_service.stop()
        return {"status": "success", "message": "已发送停止信号"}
    except Exception as e:
        logger.error(f"停止扫描失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_status():
    """获取扫描状态"""
    return {"status": "scanning" if strm_service is not None else "idle"}

@router.get("/logs")
async def get_logs():
    """获取最新的日志内容"""
    try:
        log_file = "logs/alist-strm.log"
        if not os.path.exists(log_file):
            return ""
        
        # 读取最后1000行日志
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-1000:])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 