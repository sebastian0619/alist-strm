from fastapi import APIRouter, HTTPException
from services.service_manager import service_manager
from pydantic import BaseModel
import json
import logging
from datetime import datetime
from pathlib import Path

router = APIRouter(prefix="/api/archive")
logger = logging.getLogger(__name__)

class DeleteItemInfo(BaseModel):
    path: str
    delete_time: float

class DelayDaysSettings(BaseModel):
    days: int

@router.get("/pending-deletions")
async def get_pending_deletions():
    """获取待删除文件列表"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        pending_items = []
        for item in service_manager.archive_service._pending_deletions:
            # 将Path对象转换为字符串
            path_str = str(item["path"]) if isinstance(item["path"], Path) else item["path"]
            
            pending_items.append({
                "path": path_str,
                "delete_time": item["delete_time"]  # 返回原始时间戳，由前端进行格式化
            })
        
        return {
            "success": True,
            "data": pending_items,
            "message": f"获取成功，共 {len(pending_items)} 个待删除项目"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/clear-pending-deletion")
async def clear_pending_deletion(item_info: DeleteItemInfo):
    """从待删除列表中移除指定项目"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        # 找到匹配的项目
        for item in service_manager.archive_service._pending_deletions[:]:
            path_str = str(item["path"]) if isinstance(item["path"], Path) else item["path"]
            if path_str == item_info.path and abs(item["delete_time"] - item_info.delete_time) < 1:
                service_manager.archive_service._pending_deletions.remove(item)
                # 保存更新后的列表
                service_manager.archive_service._save_pending_deletions()
                return {
                    "success": True,
                    "message": f"已从待删除列表中移除: {path_str}"
                }
        
        return {
            "success": False,
            "message": "未找到匹配的待删除项目"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/clear-all-pending-deletions")
async def clear_all_pending_deletions():
    """清空所有待删除项目"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        count = len(service_manager.archive_service._pending_deletions)
        service_manager.archive_service._pending_deletions = []
        # 保存空列表
        service_manager.archive_service._save_pending_deletions()
        
        return {
            "success": True,
            "message": f"已清空所有待删除项目，共 {count} 项"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/start")
async def start_archive():
    """开始归档处理"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        result = await service_manager.archive_service.archive()
        
        # 返回更详细的结果
        return {
            "success": True,
            "message": "归档任务已完成",
            "data": {
                "summary": result["summary"],
                "total_processed": result["total_processed"],
                "total_size": result["total_size"],
                "total_size_gb": result["total_size"] / 1024 / 1024 / 1024,
                "results": result["results"]
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"归档处理失败: {str(e)}"
        }

@router.post("/test")
async def test_archive():
    """测试归档处理（只识别不执行）"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        result = await service_manager.archive_service.archive(test_mode=True)
        
        # 返回更详细的结果
        return {
            "success": True,
            "message": "归档测试完成",
            "data": {
                "summary": result["summary"],
                "total_processed": result["total_processed"],
                "total_size": result["total_size"],
                "total_size_gb": result["total_size"] / 1024 / 1024 / 1024,
                "results": result["results"]
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"归档测试失败: {str(e)}"
        }

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
        return {
            "success": True,
            "data": media_types,
            "message": "获取成功"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/media_types")
async def save_media_types(media_types: dict):
    """保存媒体类型配置"""
    try:
        logger.info(f"收到保存媒体类型请求: {json.dumps(media_types, ensure_ascii=False)}")
        service_manager.archive_service.media_types = media_types
        service_manager.archive_service.save_media_types()
        logger.info("媒体类型配置保存成功")
        return {"success": True, "message": "保存成功"}
    except Exception as e:
        logger.error(f"保存媒体类型配置失败: {str(e)}")
        return {"success": False, "message": str(e)}

@router.get("/deletion-delay")
async def get_deletion_delay():
    """获取删除延迟天数设置"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        days = service_manager.archive_service.settings.archive_delete_delay_days
        return {
            "success": True,
            "data": {"days": days},
            "message": f"当前延迟删除天数: {days}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/deletion-delay")
async def update_deletion_delay(settings: DelayDaysSettings):
    """更新删除延迟天数设置"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        if settings.days < 1:
            return {
                "success": False,
                "message": "延迟天数必须大于0"
            }
        
        # 更新配置文件
        service_manager.archive_service.settings.archive_delete_delay_days = settings.days
        
        # 保存到config.json文件
        save_result = service_manager.archive_service.settings.save_to_config()
        
        # 更新服务的延迟时间
        service_manager.archive_service._deletion_delay = settings.days * 24 * 3600
        
        message = f"延迟删除天数已更新为: {settings.days}"
        if not save_result:
            message += "（但保存到配置文件失败）"
            
        return {
            "success": True,
            "message": message
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/delete-now")
async def delete_file_now(item_info: DeleteItemInfo):
    """立即删除指定的文件"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        # 找到匹配的项目
        for item in service_manager.archive_service._pending_deletions[:]:
            path_str = str(item["path"]) if isinstance(item["path"], Path) else item["path"]
            if path_str == item_info.path and abs(item["delete_time"] - item_info.delete_time) < 1:
                # 执行删除操作
                result = await service_manager.archive_service._delete_file(item["path"])
                if result:
                    # 从待删除列表中移除
                    service_manager.archive_service._pending_deletions.remove(item)
                    # 保存更新后的列表
                    service_manager.archive_service._save_pending_deletions()
                    return {
                        "success": True,
                        "message": f"已删除文件: {path_str}"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"删除文件失败: {path_str}"
                    }
        
        return {
            "success": False,
            "message": "未找到匹配的待删除项目"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

@router.post("/delete-all-now")
async def delete_all_files_now():
    """立即删除所有待删除项目"""
    try:
        if not service_manager.archive_service.settings.archive_enabled:
            raise HTTPException(status_code=400, detail="归档功能未启用")
        
        # 复制一份待删除列表，避免在迭代过程中修改原列表
        pending_items = service_manager.archive_service._pending_deletions.copy()
        if not pending_items:
            return {
                "success": True,
                "message": "待删除列表为空"
            }
        
        deleted_count = 0
        failed_count = 0
        
        # 执行删除操作
        for item in pending_items:
            path = item["path"]
            # 立即删除文件
            result = await service_manager.archive_service._delete_file(path)
            if result:
                service_manager.archive_service._pending_deletions.remove(item)
                deleted_count += 1
            else:
                failed_count += 1
        
        # 保存更新后的列表
        service_manager.archive_service._save_pending_deletions()
        
        return {
            "success": True,
            "message": f"已删除 {deleted_count} 个文件，失败 {failed_count} 个"
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        } 