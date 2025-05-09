from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
import os
import logging
from services.service_manager import service_manager

router = APIRouter(prefix="/api/tmdb", tags=["tmdb"])
logger = logging.getLogger(__name__)

@router.get("/stats")
async def get_tmdb_stats():
    """获取TMDB元数据统计信息"""
    try:
        stats = service_manager.strm_assistant_service.get_cache_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"获取TMDB元数据统计信息失败: {str(e)}")
        return {"success": False, "message": f"获取统计信息失败: {str(e)}"}

@router.get("/items")
async def get_tmdb_items(
    type: str = Query(..., description="元数据类型: tmdb-tv, tmdb-movies2, tmdb-collections"),
    search: str = Query("", description="搜索关键词")
):
    """获取TMDB元数据项目列表"""
    try:
        # 验证类型
        if type not in ["tmdb-tv", "tmdb-movies2", "tmdb-collections"]:
            return {"success": False, "message": "无效的元数据类型"}
        
        # 搜索项目
        results = service_manager.strm_assistant_service.search_items(search)
        
        # 返回指定类型的结果
        return {"success": True, "data": results.get(type, [])}
    except Exception as e:
        logger.error(f"获取TMDB元数据项目列表失败: {str(e)}")
        return {"success": False, "message": f"获取项目列表失败: {str(e)}"}

@router.get("/detail")
async def get_tmdb_detail(
    type: str = Query(..., description="元数据类型: tmdb-tv, tmdb-movies2, tmdb-collections"),
    id: str = Query(..., description="TMDB ID")
):
    """获取TMDB元数据详情"""
    try:
        # 验证类型
        if type not in ["tmdb-tv", "tmdb-movies2", "tmdb-collections"]:
            return {"success": False, "message": "无效的元数据类型"}
        
        # 获取详情
        detail = service_manager.strm_assistant_service.get_item_metadata(type, id)
        
        if not detail:
            return {"success": False, "message": "未找到元数据"}
        
        return {"success": True, "data": detail}
    except Exception as e:
        logger.error(f"获取TMDB元数据详情失败: {str(e)}")
        return {"success": False, "message": f"获取详情失败: {str(e)}"}

@router.get("/seasons")
async def get_tmdb_seasons(id: str = Query(..., description="剧集TMDB ID")):
    """获取剧集的季节列表"""
    try:
        # 获取季节列表
        seasons = service_manager.strm_assistant_service.get_seasons("tmdb-tv", id)
        return {"success": True, "data": seasons}
    except Exception as e:
        logger.error(f"获取季节列表失败: {str(e)}")
        return {"success": False, "message": f"获取季节列表失败: {str(e)}"}

@router.get("/episodes")
async def get_tmdb_episodes(
    id: str = Query(..., description="剧集TMDB ID"),
    season: int = Query(..., description="季号")
):
    """获取指定季的集列表"""
    try:
        # 获取集列表
        episodes = service_manager.strm_assistant_service.get_episodes("tmdb-tv", id, season)
        return {"success": True, "data": episodes}
    except Exception as e:
        logger.error(f"获取集列表失败: {str(e)}")
        return {"success": False, "message": f"获取集列表失败: {str(e)}"}

@router.delete("/item")
async def delete_tmdb_item(
    type: str = Query(..., description="元数据类型: tmdb-tv, tmdb-movies2, tmdb-collections"),
    id: str = Query(..., description="TMDB ID")
):
    """删除TMDB元数据项目"""
    try:
        # 验证类型
        if type not in ["tmdb-tv", "tmdb-movies2", "tmdb-collections"]:
            return {"success": False, "message": "无效的元数据类型"}
        
        # 删除项目
        success = service_manager.strm_assistant_service.delete_item(type, id)
        
        if not success:
            return {"success": False, "message": "删除失败"}
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        logger.error(f"删除TMDB元数据项目失败: {str(e)}")
        return {"success": False, "message": f"删除失败: {str(e)}"}

@router.post("/reload")
async def reload_tmdb_metadata():
    """重新加载所有TMDB元数据"""
    try:
        # 重新加载元数据
        stats = service_manager.strm_assistant_service.load_all_metadata()
        return {"success": True, "data": stats, "message": "元数据已重新加载"}
    except Exception as e:
        logger.error(f"重新加载TMDB元数据失败: {str(e)}")
        return {"success": False, "message": f"重新加载失败: {str(e)}"}

@router.post("/check_directories")
async def check_tmdb_directories():
    """检查并创建TMDB元数据目录结构"""
    try:
        cache_path = service_manager.strm_assistant_service.cache_path
        
        # 确保主缓存目录存在
        if not cache_path:
            return {
                "success": False, 
                "message": "未设置缓存目录路径，请先在配置页面设置TMDB缓存目录"
            }
        
        # 确保缓存目录存在
        os.makedirs(cache_path, exist_ok=True)
        
        # 检查并创建子目录
        directories = {}
        for data_type in ["tmdb-tv", "tmdb-movies2", "tmdb-collections"]:
            subdir_path = os.path.join(cache_path, data_type)
            existed = os.path.exists(subdir_path)
            os.makedirs(subdir_path, exist_ok=True)
            directories[data_type] = {
                "path": subdir_path,
                "existed_before": existed,
                "exists_now": True
            }
        
        return {
            "success": True,
            "message": f"TMDB缓存目录检查完成，所有必要目录已创建",
            "cache_path": cache_path,
            "directories": directories
        }
    except Exception as e:
        logger.error(f"检查TMDB目录失败: {str(e)}")
        return {"success": False, "message": f"检查目录失败: {str(e)}"} 