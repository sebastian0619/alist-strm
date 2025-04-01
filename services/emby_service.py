import os
import json
import time
import asyncio
import httpx
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# 设置日志
logger = logging.getLogger(__name__)

class EmbyRefreshItem:
    """表示需要刷新的Emby项目"""
    def __init__(self, strm_path: str, timestamp: float = None, retry_count: int = 0):
        self.strm_path = strm_path  # STRM文件路径
        self.timestamp = timestamp or time.time()  # 计划刷新时间
        self.retry_count = retry_count  # 重试次数
        self.item_id = None  # Emby中的ItemID，如果找到
        self.status = "pending"  # 状态：pending, processing, success, failed
        self.last_error = None  # 最后的错误信息

    def to_dict(self) -> Dict:
        """转换为字典，用于序列化"""
        return {
            "strm_path": self.strm_path,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
            "item_id": self.item_id,
            "status": self.status,
            "last_error": self.last_error
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'EmbyRefreshItem':
        """从字典创建实例，用于反序列化"""
        item = cls(
            strm_path=data["strm_path"],
            timestamp=data.get("timestamp", time.time()),
            retry_count=data.get("retry_count", 0)
        )
        item.item_id = data.get("item_id")
        item.status = data.get("status", "pending")
        item.last_error = data.get("last_error")
        return item

class EmbyService:
    """Emby服务，用于与Emby API通信和刷新元数据"""
    
    def __init__(self):
        """初始化Emby服务"""
        # 从环境变量读取配置
        self.emby_url = os.environ.get("EMBY_API_URL", "")
        self.api_key = os.environ.get("EMBY_API_KEY", "")
        self.strm_root_path = os.environ.get("STRM_ROOT_PATH", "")
        self.emby_root_path = os.environ.get("EMBY_ROOT_PATH", "")
        
        # 验证必要的配置
        if not self.emby_url or not self.api_key:
            logger.warning("Emby配置不完整，服务将不可用")
        
        # 刷新队列
        self.refresh_queue: List[EmbyRefreshItem] = []
        self.queue_file = Path("data/emby_refresh_queue.json")
        self.queue_file.parent.mkdir(exist_ok=True)
        
        # 加载刷新队列
        self._load_refresh_queue()
        
        # 标志位
        self._is_processing = False
        self._stop_flag = False
        
        # 刷新任务的配置
        self.initial_delay = 600  # 初始延迟10分钟
        self.retry_delays = [1800, 3600, 7200, 14400]  # 重试延迟：30分钟, 1小时, 2小时, 4小时
        self.max_retries = len(self.retry_delays)
    
    def _load_refresh_queue(self):
        """从文件加载刷新队列"""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.refresh_queue = [EmbyRefreshItem.from_dict(item) for item in data]
                logger.info(f"已加载刷新队列，共{len(self.refresh_queue)}个项目")
            else:
                self.refresh_queue = []
                logger.info("刷新队列文件不存在，创建新队列")
        except Exception as e:
            logger.error(f"加载刷新队列失败: {e}")
            self.refresh_queue = []
    
    def _save_refresh_queue(self):
        """保存刷新队列到文件"""
        try:
            data = [item.to_dict() for item in self.refresh_queue]
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存刷新队列，共{len(self.refresh_queue)}个项目")
        except Exception as e:
            logger.error(f"保存刷新队列失败: {e}")
    
    def add_to_refresh_queue(self, strm_path: str):
        """添加STRM文件到刷新队列"""
        # 检查是否已在队列中
        for item in self.refresh_queue:
            if item.strm_path == strm_path and item.status in ["pending", "processing"]:
                logger.info(f"STRM文件已在刷新队列中: {strm_path}")
                return
        
        # 添加到队列，设置延迟时间
        refresh_time = time.time() + self.initial_delay
        item = EmbyRefreshItem(strm_path, refresh_time)
        self.refresh_queue.append(item)
        
        # 保存队列
        self._save_refresh_queue()
        logger.info(f"已将STRM文件添加到刷新队列: {strm_path}，计划刷新时间: {datetime.fromtimestamp(refresh_time).strftime('%Y-%m-%d %H:%M:%S')}")
    
    def convert_to_emby_path(self, strm_path: str) -> str:
        """将STRM文件路径转换为Emby中的路径"""
        # 处理路径中的反斜杠
        strm_path = strm_path.replace('\\', '/')
        strm_root = self.strm_root_path.replace('\\', '/')
        emby_root = self.emby_root_path.replace('\\', '/')
        
        # 去除路径末尾的斜杠
        if strm_root.endswith('/'):
            strm_root = strm_root[:-1]
        if emby_root.endswith('/'):
            emby_root = emby_root[:-1]
        
        # 如果STRM路径以STRM根路径开头，替换为Emby根路径
        if strm_path.startswith(strm_root):
            relative_path = strm_path[len(strm_root):].lstrip('/')
            emby_path = f"{emby_root}/{relative_path}"
            logger.debug(f"路径转换: {strm_path} -> {emby_path}")
            return emby_path
        
        # 如果不能转换，返回原路径
        logger.warning(f"无法转换路径: {strm_path}，STRM根路径: {strm_root}")
        return strm_path
    
    def parse_media_info_from_path(self, path: str) -> Dict[str, Any]:
        """从路径解析媒体信息"""
        import re
        
        path = Path(path)
        filename = path.name
        parent = path.parent.name
        
        info = {
            "type": None,  # movie, series, episode
            "title": None,
            "year": None,
            "season": None,
            "episode": None
        }
        
        # 移除扩展名
        name_without_ext = os.path.splitext(filename)[0]
        
        # 尝试识别电视剧格式 (例如: "Show Name - S01E01 - Episode Title.strm")
        tv_match = re.search(r'(.+?)\s*-\s*S(\d+)E(\d+)(?:\s*-\s*(.+))?', name_without_ext)
        if tv_match:
            info["type"] = "episode"
            info["title"] = tv_match.group(1).strip()
            info["season"] = int(tv_match.group(2))
            info["episode"] = int(tv_match.group(3))
            if tv_match.group(4):
                info["episode_title"] = tv_match.group(4).strip()
            return info
        
        # 尝试识别电影格式 (例如: "Movie Name (2020).strm")
        movie_match = re.search(r'(.+?)(?:\s*\((\d{4})\))?$', name_without_ext)
        if movie_match:
            info["type"] = "movie"
            info["title"] = movie_match.group(1).strip()
            if movie_match.group(2):
                info["year"] = int(movie_match.group(2))
            
            # 检查父目录是否包含年份，如果文件名没有
            if not info["year"] and re.search(r'\(\d{4}\)', parent):
                year_match = re.search(r'\((\d{4})\)', parent)
                if year_match:
                    info["year"] = int(year_match.group(1))
        
        return info
    
    async def query_item_by_path(self, path: str) -> Optional[Dict]:
        """通过路径查询Emby中的媒体项"""
        try:
            # 构建API URL
            encoded_path = httpx.get(path).url
            url = f"{self.emby_url}/Items"
            params = {
                "Path": path,
                "api_key": self.api_key
            }
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("Items") and len(data["Items"]) > 0:
                        return data["Items"][0]
                else:
                    logger.error(f"查询路径失败: {path}, 状态码: {response.status_code}")
            
            return None
        except Exception as e:
            logger.error(f"查询Emby项目失败: {path}, 错误: {str(e)}")
            return None
    
    async def search_items_by_info(self, media_info: Dict[str, Any]) -> List[Dict]:
        """通过媒体信息搜索Emby中的项目"""
        try:
            # 构建API URL和参数
            url = f"{self.emby_url}/Items"
            params = {"api_key": self.api_key}
            
            # 根据媒体类型添加不同的查询参数
            if media_info["type"] == "episode" and media_info.get("title") and media_info.get("season") and media_info.get("episode"):
                params["SearchTerm"] = media_info["title"]
                params["IncludeItemTypes"] = "Episode"
                params["RecursiveItemTypes"] = "true"
                
            elif media_info["type"] == "movie" and media_info.get("title"):
                params["SearchTerm"] = media_info["title"]
                params["IncludeItemTypes"] = "Movie"
                
                if media_info.get("year"):
                    params["Years"] = str(media_info["year"])
            else:
                return []
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("Items", [])
                else:
                    logger.error(f"搜索媒体失败, 状态码: {response.status_code}")
            
            return []
        except Exception as e:
            logger.error(f"搜索Emby项目失败, 错误: {str(e)}")
            return []
    
    def find_best_match(self, items: List[Dict], strm_path: str) -> Optional[Dict]:
        """从搜索结果中找到最匹配的项目"""
        if not items:
            return None
        
        # 解析STRM路径中的媒体信息
        media_info = self.parse_media_info_from_path(strm_path)
        
        best_score = 0
        best_item = None
        
        for item in items:
            score = 0
            
            # 对电视剧集进行匹配
            if media_info["type"] == "episode":
                if item.get("Type") == "Episode":
                    # 检查季和集是否匹配
                    if item.get("ParentIndexNumber") == media_info.get("season") and item.get("IndexNumber") == media_info.get("episode"):
                        score += 50
                    
                    # 检查标题是否匹配
                    if media_info.get("episode_title") and media_info["episode_title"].lower() in item.get("Name", "").lower():
                        score += 30
            
            # 对电影进行匹配
            elif media_info["type"] == "movie":
                if item.get("Type") == "Movie":
                    # 检查标题
                    if media_info["title"].lower() in item.get("Name", "").lower():
                        score += 40
                    
                    # 检查年份
                    if media_info.get("year") and item.get("ProductionYear") == media_info["year"]:
                        score += 40
            
            # 更新最佳匹配
            if score > best_score:
                best_score = score
                best_item = item
        
        # 要求最低匹配分数
        if best_score >= 40:
            return best_item
        
        return None
    
    async def find_emby_item(self, strm_path: str) -> Optional[Dict]:
        """查找Emby中对应于STRM文件的媒体项"""
        # 策略1: 直接路径查询
        emby_path = self.convert_to_emby_path(strm_path)
        item = await self.query_item_by_path(emby_path)
        if item:
            logger.info(f"通过路径找到Emby项目: {strm_path} -> {item.get('Id')}")
            return item
        
        # 策略2: 解析文件名进行搜索
        media_info = self.parse_media_info_from_path(strm_path)
        if media_info and media_info["type"]:
            items = await self.search_items_by_info(media_info)
            if items:
                best_match = self.find_best_match(items, strm_path)
                if best_match:
                    logger.info(f"通过内容搜索找到Emby项目: {strm_path} -> {best_match.get('Id')}")
                    return best_match
        
        # 策略3: 尝试搜索父目录
        parent_path = os.path.dirname(emby_path)
        parent_item = await self.query_item_by_path(parent_path)
        if parent_item:
            logger.info(f"找到父目录项目: {parent_path} -> {parent_item.get('Id')}")
            return parent_item
        
        logger.warning(f"无法找到Emby项目: {strm_path}")
        return None
    
    async def refresh_emby_item(self, item_id: str) -> bool:
        """刷新Emby中的媒体项"""
        try:
            # 构建API URL
            url = f"{self.emby_url}/Items/{item_id}/Refresh"
            params = {
                "api_key": self.api_key,
                "Recursive": "true",
                "MetadataRefreshMode": "FullRefresh",
                "ImageRefreshMode": "FullRefresh"
            }
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.post(url, params=params, timeout=30)
                
                if response.status_code in (200, 204):
                    logger.info(f"成功刷新Emby项目: {item_id}")
                    return True
                else:
                    logger.error(f"刷新Emby项目失败: {item_id}, 状态码: {response.status_code}")
            
            return False
        except Exception as e:
            logger.error(f"刷新Emby项目失败: {item_id}, 错误: {str(e)}")
            return False
    
    async def process_refresh_queue(self):
        """处理刷新队列，刷新到期的项目"""
        if self._is_processing:
            logger.debug("刷新任务已在运行中")
            return
        
        try:
            self._is_processing = True
            current_time = time.time()
            processed_items = []
            
            for item in self.refresh_queue:
                if self._stop_flag:
                    break
                
                # 跳过已处理的项目
                if item.status in ["success", "failed"] and item.retry_count >= self.max_retries:
                    continue
                
                # 检查是否到达刷新时间
                if item.timestamp <= current_time:
                    item.status = "processing"
                    
                    try:
                        # 查找Emby项目
                        emby_item = await self.find_emby_item(item.strm_path)
                        
                        if emby_item:
                            # 找到项目，刷新元数据
                            item_id = emby_item.get("Id")
                            item.item_id = item_id
                            
                            success = await self.refresh_emby_item(item_id)
                            
                            if success:
                                item.status = "success"
                                logger.info(f"成功刷新项目: {item.strm_path} -> {item_id}")
                            else:
                                # 刷新失败，安排重试
                                item.status = "failed"
                                item.last_error = "刷新API调用失败"
                                item.retry_count += 1
                                
                                if item.retry_count < self.max_retries:
                                    delay = self.retry_delays[min(item.retry_count, len(self.retry_delays) - 1)]
                                    item.timestamp = current_time + delay
                                    logger.info(f"安排重试刷新: {item.strm_path}, 重试次数: {item.retry_count}, 延迟: {delay}秒")
                        else:
                            # 未找到项目，安排重试
                            item.status = "failed"
                            item.last_error = "未找到Emby项目"
                            item.retry_count += 1
                            
                            if item.retry_count < self.max_retries:
                                delay = self.retry_delays[min(item.retry_count, len(self.retry_delays) - 1)]
                                item.timestamp = current_time + delay
                                logger.info(f"未找到项目，安排重试: {item.strm_path}, 重试次数: {item.retry_count}, 延迟: {delay}秒")
                    
                    except Exception as e:
                        # 处理过程中的错误
                        item.status = "failed"
                        item.last_error = str(e)
                        item.retry_count += 1
                        
                        if item.retry_count < self.max_retries:
                            delay = self.retry_delays[min(item.retry_count, len(self.retry_delays) - 1)]
                            item.timestamp = current_time + delay
                            logger.error(f"处理刷新项目时出错: {item.strm_path}, 错误: {str(e)}")
                    
                    processed_items.append(item)
                    await asyncio.sleep(1)  # 防止API调用过于频繁
            
            # 保存队列
            if processed_items:
                self._save_refresh_queue()
                logger.info(f"已处理 {len(processed_items)} 个刷新项目")
            
            # 清理成功且已完成的项目
            if len(self.refresh_queue) > 1000:  # 如果队列太长，清理已完成的项目
                self.refresh_queue = [
                    item for item in self.refresh_queue 
                    if not (item.status == "success" and item.retry_count == 0)
                ]
                logger.info(f"已清理队列，剩余 {len(self.refresh_queue)} 个项目")
                self._save_refresh_queue()
            
        except Exception as e:
            logger.error(f"处理刷新队列时出错: {str(e)}")
        finally:
            self._is_processing = False
    
    async def start_refresh_task(self):
        """启动定期刷新任务"""
        logger.info("启动Emby刷新任务")
        self._stop_flag = False
        
        while not self._stop_flag:
            await self.process_refresh_queue()
            await asyncio.sleep(60)  # 每分钟检查一次队列
    
    def stop_refresh_task(self):
        """停止刷新任务"""
        logger.info("停止Emby刷新任务")
        self._stop_flag = True 