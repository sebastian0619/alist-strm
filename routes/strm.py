from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.strm_service import StrmService
from config import Settings

router = APIRouter(prefix="/api/strm", tags=["strm"])

class StrmRequest(BaseModel):
    path: str

@router.post("/generate")
async def generate_strm(request: StrmRequest):
    """生成 STRM 文件"""
    try:
        service = StrmService()
        await service.strm_dir(request.path)
        await service.close()
        return {"success": True, "message": "STRM 文件生成成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 