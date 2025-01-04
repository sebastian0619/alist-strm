from fastapi import APIRouter, HTTPException
from services.strm_service import StrmService
from loguru import logger

router = APIRouter(prefix="/api/strm", tags=["strm"])

# 全局变量来跟踪扫描状态和服务实例
scanning = False
strm_service = None

@router.post("/start")
async def start_scan():
    """开始扫描"""
    global scanning, strm_service
    try:
        if scanning:
            raise HTTPException(status_code=400, detail="扫描已在进行中")
        
        scanning = True
        strm_service = StrmService()
        
        # 异步执行扫描
        try:
            await strm_service.strm()
            scanning = False
            return {"code": 200, "message": "扫描完成"}
        except Exception as e:
            scanning = False
            if strm_service:
                await strm_service.close()
            strm_service = None
            raise HTTPException(status_code=500, detail=f"扫描过程出错: {str(e)}")
    except Exception as e:
        scanning = False
        if strm_service:
            await strm_service.close()
        strm_service = None
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_scan():
    """停止扫描"""
    global scanning, strm_service
    try:
        if not scanning:
            return {"code": 200, "message": "当前没有正在进行的扫描"}
        
        if strm_service:
            await strm_service.close()
            strm_service = None
        
        scanning = False
        return {"code": 200, "message": "扫描已停止"}
    except Exception as e:
        logger.error(f"停止扫描失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_status():
    """获取扫描状态"""
    try:
        return {
            "code": 200,
            "data": {
                "scanning": scanning
            }
        }
    except Exception as e:
        logger.error(f"获取状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 