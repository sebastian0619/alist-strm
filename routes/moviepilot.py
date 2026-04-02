from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.service_manager import service_manager

router = APIRouter(prefix="/api/moviepilot", tags=["moviepilot"])


class SubmitQueueRequest(BaseModel):
    item_id: str


@router.get("/status")
async def get_moviepilot_status():
    try:
        status = await service_manager.moviepilot_service.get_status()
        return {"success": True, "data": status}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/queue")
async def get_moviepilot_queue():
    try:
        return {
            "success": True,
            "data": service_manager.moviepilot_service.get_queue(),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/queue/submit")
async def submit_moviepilot_queue_item(request: SubmitQueueRequest):
    try:
        item = await service_manager.moviepilot_service.submit_queue_item(request.item_id)
        return {"success": True, "data": item}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        return {"success": False, "message": str(e)}
