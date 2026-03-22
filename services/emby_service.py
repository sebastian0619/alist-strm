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
        self.settings = Settings()
        self.refresh_settings()
        
        # 创建缓存目录
        cache_dir = "/app/cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        # 最近刷新记录
        self.last_refresh_time = None
        self.last_refresh_items = []
        self.last_refresh_file = Path(os.path.join(cache_dir, "emby_last_refresh.json"))
        
        # 加载最近刷新记录
        self._load_last_refresh()

    def refresh_settings(self):
        """重新加载运行时配置。"""
        self.settings = Settings()
        self.emby_url = self.settings.emby_api_url
        self.api_key = self.settings.emby_api_key
        self.strm_root_path = self.settings.strm_root_path
        self.emby_root_path = self.settings.emby_root_path
        self.emby_enabled = self.settings.emby_enabled

        logger.debug(
            f"Emby初始化 - emby_enabled: {self.emby_enabled}, "
            f"emby_url: {self.emby_url}, api_key set: {bool(self.api_key)}"
        )

        if not self.emby_url or not self.api_key:
            logger.warning("Emby配置不完整，服务将不可用")
            self.emby_enabled = False

    def convert_to_emby_path(self, strm_path: str) -> str:
        """将STRM路径映射到Emby媒体库路径。"""
        if not strm_path:
            return strm_path

        normalized = strm_path.replace("\\", "/")
        strm_root = (self.strm_root_path or "").replace("\\", "/").rstrip("/")
        emby_root = (self.emby_root_path or "").replace("\\", "/").rstrip("/")

        if not strm_root or not emby_root:
            return normalized

        if normalized == strm_root or normalized.startswith(f"{strm_root}/"):
            suffix = normalized[len(strm_root):].lstrip("/")
            target = f"{emby_root}/{suffix}" if suffix else emby_root
            return os.path.normpath(target).replace("\\", "/")

        stripped = normalized.lstrip("/")
        stripped_root = strm_root.lstrip("/")
        if stripped_root and (stripped == stripped_root or stripped.startswith(f"{stripped_root}/")):
            suffix = stripped[len(stripped_root):].lstrip("/")
            target = f"{emby_root}/{suffix}" if suffix else emby_root
            return os.path.normpath(target).replace("\\", "/")

        return normalized
    
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
        
        # 不再自动启动扫描任务
        logger.info("不启动自动扫描任务，需要手动触发刷新")
        # self._task = asyncio.create_task(self._auto_scan_task())
    
    def stop_background_tasks(self):
        """停止后台任务"""
        if hasattr(self, '_task') and self._task is not None:
            logger.info("停止Emby后台任务")
            self._task.cancel()
            self._task = None
    
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
                            # 构建详细的通知消息
                            message = f"🔄 Emby自动扫描完成\n\n" \
                                     f"- 发现 {result['total_found']} 个新项目\n" \
                                     f"- 成功刷新 {result['refreshed_count']} 个项目\n\n"
                            
                            # 添加刷新项目列表
                            if len(result["added_items"]) > 0:
                                message += "刷新项目：\n"
                                
                                # 按类型分组项目
                                items_by_type = {}
                                for item in result["added_items"]:
                                    item_type = item.get("type", "未知")
                                    if item_type not in items_by_type:
                                        items_by_type[item_type] = []
                                    items_by_type[item_type].append(item)
                                
                                # 添加每种类型的项目列表
                                for item_type, items in items_by_type.items():
                                    message += f"\n{item_type} ({len(items)}个):\n"
                                    # 限制每种类型最多显示5个项目
                                    for i, item in enumerate(items[:5]):
                                        name = item.get("name", "未知")
                                        year = f" ({item.get('year')})" if item.get("year") else ""
                                        message += f"  • {name}{year}\n"
                                    
                                    # 如果该类型有超过5个项目，添加省略提示
                                    if len(items) > 5:
                                        message += f"  • ... 等{len(items)-5}个项目\n"
                            
                            await service_manager.telegram_service.send_message(message)
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
                print(f"[Emby刷新] 错误: 无效的API URL: {self.emby_url}")
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
            
            logger.info(f"正在刷新Emby项目: ID={item_id}, 请求URL={url}")
            print(f"[Emby刷新] 发送刷新请求: ID={item_id}, URL={url}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                start_time = time.time()
                response = await client.post(url, params=params, timeout=30)
                duration = time.time() - start_time
                
                if response.status_code in (200, 204):
                    logger.info(f"成功刷新Emby项目: ID={item_id}, 状态码: {response.status_code}, 耗时: {duration:.2f}秒")
                    print(f"[Emby刷新] 成功: ID={item_id}, 状态码: {response.status_code}, 耗时: {duration:.2f}秒")
                    return True
                else:
                    logger.error(f"刷新Emby项目失败: ID={item_id}, 状态码: {response.status_code}, 耗时: {duration:.2f}秒")
                    logger.error(f"响应内容: {response.text[:500] if response.text else '无响应内容'}")
                    print(f"[Emby刷新] 失败: ID={item_id}, 状态码: {response.status_code}, 耗时: {duration:.2f}秒")
                    print(f"[Emby刷新] 响应内容: {response.text[:200] if response.text else '无响应内容'}")
                    return False
            
            return False
        except Exception as e:
            logger.error(f"刷新Emby项目失败: ID={item_id}, 错误: {str(e)}", exc_info=True)
            print(f"[Emby刷新] 出错: ID={item_id}, 错误: {str(e)}")
            return False

    async def get_latest_items(self, limit: int = 30, item_types: str = "Series,Movie", recursive: bool = True) -> List[Dict]:
        """获取最新入库的媒体项
        
        Args:
            limit: 返回的最大项目数量
            item_types: 媒体类型过滤（如 "Series,Movie"）
            recursive: 是否递归查询
            
        Returns:
            List[Dict]: 最新入库的媒体项列表
        """
        try:
            if not self.emby_enabled:
                logger.warning("Emby服务未启用，无法获取最新项目")
                print("[Emby] 错误: Emby服务未启用，无法获取最新项目")
                return []
            
            # 构建API URL
            base_url = self.emby_url.rstrip('/')
            url = f"{base_url}/Items"
            
            # 构建查询参数
            params = {
                "api_key": self.api_key,
                "Limit": limit,
                "Fields": "Path,DateCreated,ParentId,Overview,ProductionYear",
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Recursive": str(recursive).lower()
            }
            
            # 如果指定了媒体类型，添加过滤
            if item_types:
                params["IncludeItemTypes"] = item_types
            
            logger.info(f"获取最新入库项目: URL={url}, 类型={item_types or '全部'}, 数量={limit}, 递归={recursive}")
            print(f"[Emby] 请求最新项目: URL={url}")
            print(f"[Emby] 参数: 类型={item_types}, 数量={limit}, 递归={recursive}, Fields={params['Fields']}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                start_time = time.time()
                print(f"[Emby] 正在发送请求...")
                response = await client.get(url, params=params, timeout=30)
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("Items", [])
                    total_items = data.get("TotalRecordCount", 0)
                    logger.info(f"成功获取最新项目: 返回{len(items)}个项目 (总计{total_items}个), 耗时: {duration:.2f}秒")
                    print(f"[Emby] 成功获取最新项目: 返回{len(items)}个项目 (总计{total_items}个), 耗时: {duration:.2f}秒")
                    
                    # 记录一些项目信息用于调试
                    if items:
                        logger.debug("获取到的部分项目:")
                        print("[Emby] 获取到的部分项目:")
                        for i, item in enumerate(items[:5]):  # 只记录前5个项目
                            path = item.get('Path', '未知')
                            is_strm_path = '/media/Strm' in path if path else False
                            logger.debug(f"  {i+1}. ID={item.get('Id')}, 名称={item.get('Name')}, 类型={item.get('Type')}, 路径={path}, STRM={is_strm_path}")
                            print(f"[Emby]   {i+1}. ID={item.get('Id')}, 名称={item.get('Name')}, 类型={item.get('Type')}, STRM={is_strm_path}")
                            if item.get('DateCreated'):
                                print(f"[Emby]      创建时间: {item.get('DateCreated')}")
                    
                    return items
                else:
                    logger.error(f"获取最新项目失败: 状态码={response.status_code}, 耗时: {duration:.2f}秒")
                    logger.error(f"响应内容: {response.text[:500] if response.text else '无响应内容'}")
                    print(f"[Emby] 错误: 获取最新项目失败, 状态码={response.status_code}")
                    print(f"[Emby] 响应内容: {response.text[:200] if response.text else '无响应内容'}")
                    return []
                    
        except Exception as e:
            logger.error(f"获取最新项目时出错: {str(e)}", exc_info=True)
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
                logger.warning(f"Emby服务未启用，无法执行扫描，当前emby_enabled={self.emby_enabled}, emby_url={self.emby_url}")
                print(f"[Emby扫描] 错误: Emby服务未启用，请检查配置")
                return {"success": False, "message": "Emby服务未启用"}
            
            # 计算时间范围
            current_time = time.time()
            start_time = current_time - (hours * 3600)
            logger.info(f"开始扫描Emby项目 - 时间范围: 最近{hours}小时 (开始时间: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')})")
            print(f"[Emby扫描] 开始扫描最近{hours}小时的Emby项目...")
            
            # 获取最新项目
            logger.info(f"正在从Emby服务器获取最新项目，API URL: {self.emby_url}")
            print(f"[Emby扫描] 正在从服务器获取最新项目: {self.emby_url}")
            print(f"[Emby扫描] 参数: limit=300, item_types=Series,Movie, recursive=true")
            latest_items = await self.get_latest_items(limit=300, item_types="Series,Movie", recursive=True)
            logger.info(f"Emby服务器返回项目总数: {len(latest_items)}")
            print(f"[Emby扫描] 服务器返回项目总数: {len(latest_items)}")
            
            # 过滤时间范围内的项目
            new_items = []
            for item in latest_items:
                # 获取项目的添加时间
                date_created = item.get("DateCreated")
                item_id = item.get("Id")
                item_name = item.get("Name", "未知")
                item_type = item.get("Type", "未知")
                
                if date_created:
                    try:
                        # 解析ISO格式的时间
                        created_time = datetime.fromisoformat(date_created.replace('Z', '+00:00'))
                        created_timestamp = created_time.timestamp()
                        time_ago = (current_time - created_timestamp) / 3600
                        
                        logger.debug(f"检查项目: ID={item_id}, 名称={item_name}, 类型={item_type}, 添加时间={created_time.strftime('%Y-%m-%d %H:%M:%S')} ({time_ago:.1f}小时前)")
                        
                        if created_timestamp >= start_time:
                            new_items.append(item)
                            logger.info(f"找到符合条件的项目: ID={item_id}, 名称={item_name}, 类型={item_type}, 添加时间={created_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            print(f"[Emby扫描] 找到新项目: {item_name} ({item_type}), 添加时间: {created_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        logger.warning(f"解析项目时间出错: {str(e)}, 项目: ID={item_id}, 名称={item_name}, 原始时间值: {date_created}")
                        print(f"[Emby扫描] 警告: 解析项目时间出错: {item_name}, 错误: {str(e)}")
            
            logger.info(f"找到 {len(new_items)} 个最近 {hours} 小时内的新项目")
            print(f"[Emby扫描] 找到 {len(new_items)} 个最近 {hours} 小时内的新项目")
            
            # 直接刷新项目
            refreshed_count = 0
            refreshed_items = []
            
            if new_items:
                logger.info("开始刷新新项目元数据...")
                print(f"[Emby扫描] 开始刷新新项目元数据...")
            else:
                logger.info("没有找到需要刷新的新项目")
                print(f"[Emby扫描] 没有找到需要刷新的新项目")
            
            for item in new_items:
                item_id = item.get("Id")
                item_name = item.get("Name", "未知")
                item_type = item.get("Type", "未知")
                item_path = item.get("Path", "未知")
                
                if item_id:
                    # 执行刷新
                    logger.info(f"正在刷新项目: ID={item_id}, 名称={item_name}, 类型={item_type}, 路径={item_path}")
                    print(f"[Emby扫描] 正在刷新: {item_name} ({item_type})")
                    success = await self.refresh_emby_item(item_id)
                    
                    if success:
                        refreshed_count += 1
                        logger.info(f"成功刷新项目: ID={item_id}, 名称={item_name}")
                        print(f"[Emby扫描] ✓ 成功刷新: {item_name}")
                        
                        # 记录刷新的项目信息
                        refreshed_items.append({
                            "id": item_id,
                            "name": item_name,
                            "type": item_type,
                            "path": item_path,
                            "year": item.get("ProductionYear")
                        })
                    else:
                        logger.warning(f"刷新项目失败: ID={item_id}, 名称={item_name}")
                        print(f"[Emby扫描] ✗ 刷新失败: {item_name}")
            
            # 保存本次刷新记录
            if refreshed_items:
                self._save_last_refresh(refreshed_items)
                logger.info(f"已保存刷新记录，共 {len(refreshed_items)} 个项目")
                print(f"[Emby扫描] 已保存刷新记录，共 {len(refreshed_items)} 个项目")
            
            result = {
                "success": True,
                "message": f"扫描完成，发现 {len(new_items)} 个新项目，成功刷新 {refreshed_count} 个项目",
                "total_found": len(new_items),
                "refreshed_count": refreshed_count,
                "added_items": refreshed_items,
                "logs": [
                    f"开始扫描Emby项目 - 时间范围: 最近{hours}小时",
                    f"从Emby服务器获取最新项目 URL: {self.emby_url}",
                    f"API参数: limit=300, item_types=Series,Movie, recursive=true",
                    f"Emby服务器返回项目总数: {len(latest_items)}",
                    f"找到 {len(new_items)} 个最近 {hours} 小时内的新项目",
                    f"成功刷新 {refreshed_count} 个项目"
                ]
            }
            
            logger.info(f"扫描结果: {result['message']}")
            print(f"[Emby扫描] 完成: {result['message']}")
            return result
            
        except Exception as e:
            logger.error(f"扫描最新项目失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"扫描失败: {str(e)}",
                "logs": [f"扫描过程中出错: {str(e)}"]
            }

    async def scan_without_refresh(self, hours: int = 24) -> dict:
        """仅扫描最近指定时间内的Emby项目，不执行刷新
        
        Args:
            hours: 扫描最近多少小时的项目
            
        Returns:
            dict: 扫描结果，包含新项目列表
        """
        try:
            if not self.emby_enabled:
                logger.warning(f"Emby服务未启用，无法执行扫描，当前emby_enabled={self.emby_enabled}, emby_url={self.emby_url}")
                print(f"[Emby扫描] 错误: Emby服务未启用，请检查配置")
                return {"success": False, "message": "Emby服务未启用", "items": [], "logs": ["Emby服务未启用"]}
            
            # 计算时间范围
            current_time = time.time()
            start_time = current_time - (hours * 3600)
            logger.info(f"开始扫描Emby项目 - 时间范围: 最近{hours}小时 (开始时间: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')})")
            print(f"[Emby扫描] 开始扫描最近{hours}小时的Emby项目...")
            
            # 获取最新项目
            logger.info(f"正在从Emby服务器获取最新项目，API URL: {self.emby_url}")
            print(f"[Emby扫描] 正在从服务器获取最新项目: {self.emby_url}")
            print(f"[Emby扫描] 参数: limit=300, item_types=Series,Movie, recursive=true")
            latest_items = await self.get_latest_items(limit=300, item_types="Series,Movie", recursive=True)
            logger.info(f"Emby服务器返回项目总数: {len(latest_items)}")
            print(f"[Emby扫描] 服务器返回项目总数: {len(latest_items)}")
            
            # 过滤时间范围内的项目
            new_items = []
            new_items_details = []  # 包含更多详细信息的项目列表，用于UI显示
            strm_count = 0  # 统计STRM文件数量
            
            for item in latest_items:
                # 获取项目的添加时间
                date_created = item.get("DateCreated")
                item_id = item.get("Id")
                item_name = item.get("Name", "未知")
                item_type = item.get("Type", "未知")
                item_path = item.get("Path", "未知")
                
                # 检查是否是STRM路径
                is_strm_path = '/media/Strm' in item_path if item_path else False
                
                if date_created:
                    try:
                        # 解析ISO格式的时间 (格式如: 2025-05-15T19:00:04.0000000Z)
                        created_time = datetime.fromisoformat(date_created.replace('Z', '+00:00'))
                        created_timestamp = created_time.timestamp()
                        time_ago = (current_time - created_timestamp) / 3600
                        
                        # 由于path信息重要，添加到日志中
                        logger.debug(f"检查项目: ID={item_id}, 名称={item_name}, 类型={item_type}, 路径={item_path}, STRM={is_strm_path}, 添加时间={created_time.strftime('%Y-%m-%d %H:%M:%S')} ({time_ago:.1f}小时前)")
                        
                        if created_timestamp >= start_time:
                            new_items.append(item)
                            if is_strm_path:
                                strm_count += 1
                                
                            logger.info(f"找到符合条件的项目: ID={item_id}, 名称={item_name}, 类型={item_type}, 路径={item_path}, STRM={is_strm_path}, 添加时间={created_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            # 打印详细信息，但根据是否STRM路径进行区分显示
                            if is_strm_path:
                                print(f"[Emby扫描] 找到新STRM项目: {item_name} ({item_type}), 路径: {item_path}, 添加时间: {created_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            else:
                                print(f"[Emby扫描] 找到新项目: {item_name} ({item_type}), 添加时间: {created_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            # 添加到详细项目列表
                            new_items_details.append({
                                "id": item_id,
                                "name": item_name,
                                "type": item_type,
                                "path": item_path,
                                "is_strm": is_strm_path,
                                "year": item.get("ProductionYear"),
                                "created": created_time.strftime('%Y-%m-%d %H:%M:%S'),
                                "date_created_raw": date_created,  # 保留原始格式便于调试
                                "hoursAgo": round(time_ago, 1),
                                "overview": item.get("Overview", ""),
                                "selected": is_strm_path  # 默认只选中STRM路径的项目
                            })
                    except Exception as e:
                        logger.warning(f"解析项目时间出错: {str(e)}, 项目: ID={item_id}, 名称={item_name}, 原始时间值: {date_created}")
                        print(f"[Emby扫描] 警告: 解析项目时间出错: {item_name}, 错误: {str(e)}")
            
            logger.info(f"找到 {len(new_items)} 个最近 {hours} 小时内的新项目，其中 {strm_count} 个是STRM文件")
            print(f"[Emby扫描] 找到 {len(new_items)} 个最近 {hours} 小时内的新项目，其中 {strm_count} 个是STRM文件")
            
            # 返回扫描结果
            return {
                "success": True,
                "message": f"扫描完成，发现 {len(new_items)} 个新项目，其中 {strm_count} 个是STRM文件",
                "items": new_items_details,
                "total_found": len(new_items),
                "strm_count": strm_count,
                "logs": [
                    f"开始扫描Emby项目 - 时间范围: 最近{hours}小时",
                    f"从Emby服务器获取最新项目 URL: {self.emby_url}",
                    f"API参数: limit=300, item_types=Series,Movie, recursive=true",
                    f"Emby服务器返回项目总数: {len(latest_items)}",
                    f"找到 {len(new_items)} 个最近 {hours} 小时内的新项目，其中 {strm_count} 个是STRM文件"
                ]
            }
        except Exception as e:
            logger.error(f"扫描最新项目失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"扫描失败: {str(e)}",
                "items": [],
                "logs": [f"扫描过程中出错: {str(e)}"]
            }
            
    async def refresh_items(self, item_ids: List[str]) -> dict:
        """刷新指定的Emby项目
        
        Args:
            item_ids: 要刷新的项目ID列表
            
        Returns:
            dict: 刷新结果
        """
        try:
            if not self.emby_enabled:
                logger.warning(f"Emby服务未启用，无法执行刷新")
                print(f"[Emby刷新] 错误: Emby服务未启用，请检查配置")
                return {"success": False, "message": "Emby服务未启用", "refreshed_count": 0, "refreshed_items": []}
            
            logger.info(f"开始刷新 {len(item_ids)} 个Emby项目")
            print(f"[Emby刷新] 开始刷新 {len(item_ids)} 个Emby项目")
            
            # 刷新项目
            refreshed_count = 0
            refreshed_items = []
            failed_items = []
            
            if not item_ids:
                logger.info("没有找到需要刷新的项目")
                print(f"[Emby刷新] 没有找到需要刷新的项目")
                return {
                    "success": True, 
                    "message": "没有找到需要刷新的项目", 
                    "refreshed_count": 0,
                    "refreshed_items": []
                }
            
            # 直接循环刷新每个项目，不获取项目详情
            for item_id in item_ids:
                try:
                    # 执行刷新
                    logger.info(f"正在刷新项目: ID={item_id}")
                    print(f"[Emby刷新] 正在刷新: ID={item_id}")
                    success = await self.refresh_emby_item(item_id)
                    
                    if success:
                        refreshed_count += 1
                        logger.info(f"成功刷新项目: ID={item_id}")
                        print(f"[Emby刷新] ✓ 成功刷新: ID={item_id}")
                        
                        # 记录刷新的项目信息（基本信息）
                        refreshed_items.append({
                            "id": item_id,
                            "name": f"ID:{item_id}",  # 由于没有获取详情，只显示ID
                            "type": "unknown"         # 类型未知
                        })
                    else:
                        logger.warning(f"刷新项目失败: ID={item_id}")
                        print(f"[Emby刷新] ✗ 刷新失败: ID={item_id}")
                        failed_items.append({
                            "id": item_id,
                            "name": f"ID:{item_id}",
                            "type": "unknown"
                        })
                except Exception as e:
                    logger.error(f"刷新项目出错: ID={item_id}, 错误: {str(e)}")
                    print(f"[Emby刷新] ✗ 刷新项目出错: ID={item_id}, 错误: {str(e)}")
                    failed_items.append({
                        "id": item_id,
                        "name": f"ID:{item_id}",
                        "type": "unknown",
                        "error": str(e)
                    })
            
            # 保存本次刷新记录
            if refreshed_items:
                self._save_last_refresh(refreshed_items)
                logger.info(f"已保存刷新记录，共 {len(refreshed_items)} 个项目")
                print(f"[Emby刷新] 已保存刷新记录，共 {len(refreshed_items)} 个项目")
            
            result = {
                "success": True,
                "message": f"刷新完成，成功刷新 {refreshed_count} 个项目，失败 {len(failed_items)} 个项目",
                "refreshed_count": refreshed_count,
                "failed_count": len(failed_items),
                "refreshed_items": refreshed_items,
                "failed_items": failed_items,
                "logs": [
                    f"开始刷新 {len(item_ids)} 个Emby项目",
                    f"成功刷新 {refreshed_count} 个项目",
                    f"失败 {len(failed_items)} 个项目"
                ]
            }
            
            logger.info(f"刷新结果: {result['message']}")
            print(f"[Emby刷新] 完成: {result['message']}")
            return result
            
        except Exception as e:
            logger.error(f"刷新项目失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"刷新失败: {str(e)}",
                "refreshed_count": 0,
                "refreshed_items": [],
                "logs": [f"刷新过程中出错: {str(e)}"]
            }
            
    async def get_item_details(self, item_id: str) -> Optional[Dict]:
        """获取Emby项目详情
        
        Args:
            item_id: 项目ID
            
        Returns:
            Optional[Dict]: 项目详情，如果获取失败则返回None
        """
        try:
            if not self.emby_enabled:
                logger.warning("Emby服务未启用，无法获取项目详情")
                return None
            
            # 构建API URL
            base_url = self.emby_url.rstrip('/')
            url = f"{base_url}/Items/{item_id}"
            
            # 构建查询参数
            params = {
                "api_key": self.api_key,
                "Fields": "Path,ParentId,Overview,ProductionYear"
            }
            
            logger.info(f"获取项目详情: ID={item_id}")
            print(f"[Emby] 获取项目详情: ID={item_id}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"成功获取项目详情: ID={item_id}, 名称={data.get('Name', '未知')}")
                    return data
                else:
                    logger.error(f"获取项目详情失败: ID={item_id}, 状态码={response.status_code}")
                    logger.error(f"响应内容: {response.text[:500] if response.text else '无响应内容'}")
                    return None
                
        except Exception as e:
            logger.error(f"获取项目详情时出错: ID={item_id}, 错误: {str(e)}")
            return None

    async def find_items_with_tag(self, tag_name: str) -> List[Dict]:
        """查找包含指定标签的所有项目
        
        Args:
            tag_name: 要查找的标签名称
            
        Returns:
            List[Dict]: 包含该标签的项目列表
        """
        try:
            if not self.emby_enabled:
                logger.warning("Emby服务未启用，无法查找带标签的项目")
                print(f"[Emby标签] 错误: Emby服务未启用，请检查配置")
                return []
            
            # 构建API URL
            base_url = self.emby_url.rstrip('/')
            url = f"{base_url}/Items"
            
            # 构建查询参数 - 基于标签搜索
            params = {
                "api_key": self.api_key,
                "Recursive": "true",
                "Fields": "Path,DateCreated,Tags,Overview",
                "IncludeItemTypes": "Movie,Series",  # 只包含电影和剧集
                "Tags": tag_name,                    # 按标签过滤
                "Limit": 1000                        # 设置一个较大的限制
            }
            
            logger.info(f"查找带标签 '{tag_name}' 的项目")
            print(f"[Emby标签] 查找带标签 '{tag_name}' 的项目")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("Items", [])
                    total_items = data.get("TotalRecordCount", 0)
                    
                    logger.info(f"找到 {len(items)} 个带标签 '{tag_name}' 的项目")
                    print(f"[Emby标签] 找到 {len(items)} 个带标签 '{tag_name}' 的项目")
                    
                    # 记录找到的项目
                    for i, item in enumerate(items[:10]):  # 只记录前10个项目
                        logger.debug(f"  {i+1}. ID={item.get('Id')}, 名称={item.get('Name')}, 类型={item.get('Type')}")
                        print(f"[Emby标签]   {i+1}. ID={item.get('Id')}, 名称={item.get('Name')}, 类型={item.get('Type')}")
                    
                    if len(items) > 10:
                        logger.debug(f"  ... 以及 {len(items) - 10} 个其他项目")
                        print(f"[Emby标签]   ... 以及 {len(items) - 10} 个其他项目")
                    
                    return items
                else:
                    logger.error(f"查找带标签的项目失败: 状态码={response.status_code}")
                    logger.error(f"响应内容: {response.text[:500] if response.text else '无响应内容'}")
                    print(f"[Emby标签] 错误: 查找带标签的项目失败, 状态码={response.status_code}")
                    return []
        
        except Exception as e:
            logger.error(f"查找带标签的项目时出错: {str(e)}")
            print(f"[Emby标签] 错误: 查找带标签的项目时出错: {str(e)}")
            return []
    
    async def remove_tag_from_item(self, item_id: str, tag_to_remove: str) -> bool:
        """从项目中删除指定标签
        
        Args:
            item_id: 项目ID
            tag_to_remove: 要删除的标签名称
            
        Returns:
            bool: 操作是否成功
        """
        try:
            if not self.emby_enabled:
                logger.warning("Emby服务未启用，无法删除标签")
                print(f"[Emby标签] 错误: Emby服务未启用，请检查配置")
                return False
            
            # 首先获取项目当前标签
            item_details = await self.get_item_details(item_id)
            if not item_details:
                logger.error(f"无法获取项目详情: ID={item_id}")
                print(f"[Emby标签] 错误: 无法获取项目详情: ID={item_id}")
                return False
            
            current_tags = item_details.get("Tags", [])
            item_name = item_details.get("Name", "未知")
            
            # 检查标签是否存在
            if tag_to_remove not in current_tags:
                logger.info(f"项目没有该标签: ID={item_id}, 名称={item_name}, 标签={tag_to_remove}")
                print(f"[Emby标签] 项目 '{item_name}' 没有标签 '{tag_to_remove}'")
                return True  # 不需要删除
            
            # 移除标签
            new_tags = [tag for tag in current_tags if tag != tag_to_remove]
            
            # 构建API URL
            base_url = self.emby_url.rstrip('/')
            url = f"{base_url}/Items/{item_id}/Tags"
            
            # 构建请求参数
            params = {
                "api_key": self.api_key
            }
            
            # 构建请求体
            data = {
                "Tags": new_tags
            }
            
            logger.info(f"从项目中删除标签: ID={item_id}, 名称={item_name}, 标签={tag_to_remove}")
            print(f"[Emby标签] 从项目 '{item_name}' 中删除标签 '{tag_to_remove}'")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.post(url, params=params, json=data, timeout=30)
                
                if response.status_code == 200 or response.status_code == 204:
                    logger.info(f"成功删除标签: ID={item_id}, 名称={item_name}, 标签={tag_to_remove}")
                    print(f"[Emby标签] ✓ 成功从 '{item_name}' 删除标签 '{tag_to_remove}'")
                    return True
                else:
                    logger.error(f"删除标签失败: ID={item_id}, 名称={item_name}, 标签={tag_to_remove}, 状态码={response.status_code}")
                    logger.error(f"响应内容: {response.text[:500] if response.text else '无响应内容'}")
                    print(f"[Emby标签] ✗ 删除标签失败: ID={item_id}, 名称={item_name}, 状态码={response.status_code}")
                    return False
        
        except Exception as e:
            logger.error(f"删除标签时出错: ID={item_id}, 标签={tag_to_remove}, 错误: {str(e)}")
            print(f"[Emby标签] 错误: 删除标签时出错: ID={item_id}, 错误: {str(e)}")
            return False
    
    async def remove_tag_from_all_items(self, tag_name: str) -> dict:
        """从所有项目中删除指定标签
        
        Args:
            tag_name: 要删除的标签名称
            
        Returns:
            dict: 操作结果统计
        """
        if not tag_name or not tag_name.strip():
            return {
                "success": False,
                "message": "标签名称不能为空",
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "items": []
            }
        
        # 查找带有该标签的所有项目
        items = await self.find_items_with_tag(tag_name)
        
        if not items:
            return {
                "success": True,
                "message": f"未找到带标签 '{tag_name}' 的项目",
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "items": []
            }
        
        # 初始化统计
        total = len(items)
        success_count = 0
        failed_count = 0
        processed_items = []
        
        # 遍历所有项目，删除标签
        for item in items:
            item_id = item.get("Id")
            item_name = item.get("Name", "未知")
            item_type = item.get("Type", "未知")
            
            success = await self.remove_tag_from_item(item_id, tag_name)
            
            item_result = {
                "id": item_id,
                "name": item_name,
                "type": item_type,
                "success": success
            }
            
            processed_items.append(item_result)
            
            if success:
                success_count += 1
            else:
                failed_count += 1
        
        # 返回结果
        return {
            "success": True,
            "message": f"从 {success_count}/{total} 个项目中删除了标签 '{tag_name}'",
            "total": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "items": processed_items
        }
