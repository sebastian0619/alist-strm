from fastapi import APIRouter

router = APIRouter()

@router.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"} 