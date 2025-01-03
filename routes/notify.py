from fastapi import APIRouter, Body
from typing import Optional
from pydantic import BaseModel
from loguru import logger
from services.copy_service import CopyService
import os

router = APIRouter(prefix="/api/v1")

class NotifyByDirRequest(BaseModel):
    dir: Optional[str] = None

@router.post("/notify")
async def notify_sync():
    """触发全量同步"""
    copy_service = CopyService()
    try:
        await copy_service.sync_files()
        return {"message": "同步任务已启动"}
    finally:
        await copy_service.close()

@router.post("/notifyByDir")
async def notify_by_dir(request: NotifyByDirRequest):
    """根据目录触发同步"""
    copy_service = CopyService()
    try:
        relative_path = ""
        if request.dir and copy_service.settings.replace_dir:
            relative_path = request.dir.replace(copy_service.settings.replace_dir, "", 1)
            # 判断是否为视频文件
            if _is_video_file(relative_path):
                await copy_service.sync_one_file(relative_path)
            else:
                await copy_service.sync_files(relative_path)
        else:
            await copy_service.sync_files(relative_path)
        return {"message": "同步任务已启动"}
    finally:
        await copy_service.close()

def _is_video_file(path: str) -> bool:
    """判断是否为视频文件"""
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.rmvb'}
    return os.path.splitext(path)[1].lower() in video_extensions 