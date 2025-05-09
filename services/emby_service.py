import os
import json
import re
import time
import asyncio
import httpx
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from config import Settings
import importlib
from urllib.parse import quote

# 设置日志
logger = logging.getLogger(__name__)

class EmbyService:
    """Emby服务，用于与Emby API通信和刷新元数据"""
    
    def __init__(self):
        """初始化Emby服务"""
        # 从配置获取设置
        self.settings = Settings()
        self.emby_url = self.settings.emby_api_url
        self.api_key = self.settings.emby_api_key
        self.strm_root_path = self.settings.strm_root_path
        self.emby_root_path = self.settings.emby_root_path
        self.emby_enabled = self.settings.emby_enabled
        
        # 验证必要的配置
        if not self.emby_url or not self.api_key:
            logger.warning("Emby配置不完整，服务将不可用")
            self.emby_enabled = False
        
        # 创建缓存目录
        cache_dir = "/app/cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        # 最近刷新记录
        self.last_refresh_time = None
        self.last_refresh_items = []
        self.last_refresh_file = Path(os.path.join(cache_dir, "emby_last_refresh.json"))
        
        # 加载最近刷新记录
        self._load_last_refresh()
    
    def add_to_refresh_queue(self, strm_path: str, media_info: dict = None):
        """兼容方法 - 不再使用刷新队列，但保留此方法以兼容现有调用
        
        Args:
            strm_path: STRM文件路径
            media_info: 媒体信息 (可选)
        """
        logger.debug(f"已废弃的add_to_refresh_queue被调用: {strm_path}")
        # 这个方法不再做任何事情
        return
            
    async def start_background_tasks(self):
        """启动后台任务 - 启动自动扫描任务"""
        if not self.emby_enabled:
            logger.info("Emby服务未启用，跳过启动后台任务")
            return
        
        logger.info("Emby服务已启动")
        
        # 启动自动扫描任务
        asyncio.create_task(self._auto_scan_task())
    
    async def _auto_scan_task(self):
        """定期执行扫描最新项目的任务，每6小时执行一次"""
        logger.info("启动自动扫描Emby最新项目任务")
        
        while True:
            try:
                # 执行扫描
                logger.info("执行定时Emby新项目扫描")
                result = await self.scan_latest_items(hours=12)  # 扫描最近12小时的项目
                
                if result["success"]:
                    logger.info(f"定时扫描完成: {result['message']}")
                    # 发送通知
                    try:
                        service_manager = self._get_service_manager()
                        if result["refreshed_count"] > 0:
                            await service_manager.telegram_service.send_message(
                                f"🔄 Emby自动扫描完成\n{result['message']}"
                            )
                    except Exception as e:
                        logger.error(f"发送Telegram通知失败: {str(e)}")
                else:
                    logger.error(f"定时扫描失败: {result['message']}")
            except Exception as e:
                logger.error(f"执行定时扫描任务时出错: {str(e)}")
            
            # 等待6小时
            await asyncio.sleep(6 * 60 * 60)  # 6小时

    def _load_last_refresh(self):
        """从文件加载最近一次刷新记录"""
        try:
            if self.last_refresh_file.exists():
                with open(self.last_refresh_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.last_refresh_time = data.get('time')
                    self.last_refresh_items = data.get('items', [])
                logger.info(f"已加载最近刷新记录，共{len(self.last_refresh_items)}个项目")
            else:
                self.last_refresh_time = None
                self.last_refresh_items = []
                logger.info("最近刷新记录文件不存在，使用空记录")
        except Exception as e:
            logger.error(f"加载最近刷新记录失败: {e}")
            self.last_refresh_time = None
            self.last_refresh_items = []
    
    def _save_last_refresh(self, items=None):
        """保存最近一次刷新记录到文件"""
        try:
            # 如果提供了新的项目列表，更新记录
            if items is not None:
                self.last_refresh_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.last_refresh_items = items
                
            data = {
                'time': self.last_refresh_time,
                'items': self.last_refresh_items
            }
            
            with open(self.last_refresh_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存最近刷新记录，共{len(self.last_refresh_items)}个项目")
        except Exception as e:
            logger.error(f"保存最近刷新记录失败: {e}")

    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager 
    
    async def refresh_emby_item(self, item_id: str) -> bool:
        """刷新Emby中的媒体项"""
        try:
            # 确保emby_url是合法的URL
            if not self.emby_url or not self.emby_url.startswith(('http://', 'https://')):
                logger.error(f"无效的Emby API URL: {self.emby_url}")
                return False
            
            # 构建API URL - 修复路径重复问题
            base_url = self.emby_url
            if base_url.endswith('/'):
                base_url = base_url[:-1]  # 移除末尾的斜杠
                
            # 检查并调整API路径
            url = f"{base_url}/Items/{item_id}/Refresh"
            
            params = {
                "api_key": self.api_key,
                "Recursive": "true",
                "MetadataRefreshMode": "FullRefresh",
                "ImageRefreshMode": "FullRefresh"
            }
            
            logger.debug(f"刷新Emby项目: ID={item_id}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.post(url, params=params, timeout=30)
                
                if response.status_code in (200, 204):
                    logger.debug(f"成功刷新Emby项目: {item_id}")
                    return True
                else:
                    logger.error(f"刷新Emby项目失败: {item_id}, 状态码: {response.status_code}")
                    return False
            
            return False
        except Exception as e:
            logger.error(f"刷新Emby项目失败: {item_id}, 错误: {str(e)}")
            return False

    async def get_latest_items(self, limit: int = 200, item_type: str = None) -> List[Dict]:
        """获取最新入库的媒体项
        
        Args:
            limit: 返回的最大项目数量
            item_type: 媒体类型过滤（Movie, Series, Episode等）
            
        Returns:
            List[Dict]: 最新入库的媒体项列表
        """
        try:
            if not self.emby_enabled:
                logger.warning("Emby服务未启用，无法获取最新项目")
                return []
            
            # 构建API URL
            base_url = self.emby_url.rstrip('/')
            url = f"{base_url}/Items"
            
            # 构建查询参数
            params = {
                "api_key": self.api_key,
                "Limit": limit,
                "Fields": "Path,ParentId,Overview,ProductionYear",
                "SortBy": "DateCreated,SortName",
                "SortOrder": "Descending"
            }
            
            # 如果指定了媒体类型，添加过滤
            if item_type:
                params["IncludeItemTypes"] = item_type
            
            logger.debug(f"获取最新入库项目: 类型={item_type}, 数量={limit}, 排序={params['SortBy']}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("Items", [])
                    logger.debug(f"成功获取 {len(items)} 个最新项目")
                    return items
                else:
                    logger.error(f"获取最新项目失败: 状态码={response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"获取最新项目时出错: {str(e)}")
            return []

    async def scan_latest_items(self, hours: int = 24) -> dict:
        """扫描指定时间范围内新入库的项目并执行刷新
        
        Args:
            hours: 扫描最近多少小时的项目
            
        Returns:
            dict: 扫描结果
        """
        try:
            if not self.emby_enabled:
                return {"success": False, "message": "Emby服务未启用"}
            
            # 计算时间范围
            current_time = time.time()
            start_time = current_time - (hours * 3600)
            
            # 获取最新项目
            latest_items = await self.get_latest_items(limit=300)
            
            # 过滤时间范围内的项目
            new_items = []
            for item in latest_items:
                # 获取项目的添加时间
                date_created = item.get("DateCreated")
                if date_created:
                    try:
                        # 解析ISO格式的时间
                        created_time = datetime.fromisoformat(date_created.replace('Z', '+00:00'))
                        created_timestamp = created_time.timestamp()
                        
                        if created_timestamp >= start_time:
                            new_items.append(item)
                    except Exception as e:
                        logger.debug(f"解析项目时间出错: {str(e)}")
            
            logger.info(f"找到 {len(new_items)} 个最近 {hours} 小时内的新项目")
            
            # 直接刷新项目
            refreshed_count = 0
            refreshed_items = []
            
            for item in new_items:
                item_id = item.get("Id")
                
                if item_id:
                    # 执行刷新
                    success = await self.refresh_emby_item(item_id)
                    
                    if success:
                        refreshed_count += 1
                        # 记录刷新的项目信息
                        refreshed_items.append({
                            "id": item_id,
                            "name": item.get("Name"),
                            "type": item.get("Type"),
                            "path": item.get("Path"),
                            "year": item.get("ProductionYear")
                        })
            
            # 保存本次刷新记录
            if refreshed_items:
                self._save_last_refresh(refreshed_items)
            
            return {
                "success": True,
                "message": f"扫描完成，发现 {len(new_items)} 个新项目，成功刷新 {refreshed_count} 个项目",
                "total_found": len(new_items),
                "refreshed_count": refreshed_count,
                "added_items": refreshed_items
            }
            
        except Exception as e:
            logger.error(f"扫描最新项目失败: {str(e)}")
            return {
                "success": False,
                "message": f"扫描失败: {str(e)}"
            }