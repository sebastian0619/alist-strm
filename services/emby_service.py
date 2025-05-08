import os
import json
import re
import time
import asyncio
import httpx
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from config import Settings
import importlib
from urllib.parse import urlencode, quote

# 设置日志
logger = logging.getLogger(__name__)

class EmbyRefreshItem:
    """表示需要刷新的Emby项目"""
    def __init__(self, strm_path: str, timestamp: float = None, retry_count: int = 0, media_info: dict = None):
        self.strm_path = strm_path  # STRM文件路径
        self.timestamp = timestamp or time.time()  # 计划刷新时间
        self.retry_count = retry_count  # 重试次数
        self.item_id = None  # Emby中的ItemID，如果找到
        self.status = "pending"  # 状态：pending, processing, success, failed
        self.last_error = None  # 最后的错误信息
        self.next_retry_time = self.timestamp  # 下次重试时间
        self.media_info = media_info or {}  # 媒体信息，包含原始路径、文件名等

    def to_dict(self) -> Dict:
        """转换为字典，用于序列化"""
        return {
            "strm_path": self.strm_path,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
            "item_id": self.item_id,
            "status": self.status,
            "last_error": self.last_error,
            "next_retry_time": getattr(self, "next_retry_time", self.timestamp),
            "media_info": self.media_info
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'EmbyRefreshItem':
        """从字典创建实例，用于反序列化"""
        item = cls(
            strm_path=data["strm_path"],
            timestamp=data.get("timestamp", time.time()),
            retry_count=data.get("retry_count", 0),
            media_info=data.get("media_info", {})
        )
        item.item_id = data.get("item_id")
        item.status = data.get("status", "pending")
        item.last_error = data.get("last_error")
        item.next_retry_time = data.get("next_retry_time", item.timestamp)
        return item

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
        
        # 刷新队列
        self.refresh_queue: List[EmbyRefreshItem] = []
        self.queue_file = Path(os.path.join(cache_dir, "emby_refresh_queue.json"))
        
        # 加载刷新队列
        self._load_refresh_queue()
        
        # 标志位
        self._is_processing = False
        self._stop_flag = False
        
        # 刷新任务的配置 - 增加延迟，给Emby更多时间扫描
        self.initial_delay = 1800  # 30分钟
        self.retry_delays = [3600, 7200, 14400, 28800]  # 1小时, 2小时, 4小时, 8小时
        self.max_retries = len(self.retry_delays)
        
        # 媒体路径到Emby ID的映射缓存
        self.path_to_id_cache = {}
        self.cache_file = Path(os.path.join(cache_dir, "emby_path_cache.json"))
        self._load_path_cache()
        
        # 跟踪最近一次刷新的项目
        self.last_refresh_items = []
        self.last_refresh_time = None
        self.last_refresh_file = Path(os.path.join(cache_dir, "emby_last_refresh.json"))
        self._load_last_refresh()
    
    def _load_refresh_queue(self):
        """从文件加载刷新队列"""
        try:
            # 确保缓存目录存在
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            
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
            # 确保缓存目录存在
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            
            data = [item.to_dict() for item in self.refresh_queue]
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存刷新队列，共{len(self.refresh_queue)}个项目")
        except Exception as e:
            logger.error(f"保存刷新队列失败: {e}")
    
    def add_to_refresh_queue(self, strm_path: str, media_info: dict = None):
        """添加STRM文件到刷新队列"""
        # 如果Emby功能未开启，不添加到队列
        if not self.emby_enabled:
            logger.debug(f"Emby刷库功能未启用，不添加到刷新队列")
            return
            
        try:
            # 规范化路径格式，确保Windows和Linux路径格式一致
            strm_path = str(strm_path).replace('\\', '/')
            # 记录详细的文件信息
            file_exists = os.path.exists(strm_path)
            logger.debug(f"添加到刷新队列: {strm_path}")
            
            # 检查文件是否存在，不存在则记录警告但仍尝试添加到队列
            if not file_exists:
                logger.warning(f"STRM文件不存在: {strm_path}，但仍将添加到队列")
                
            # 检查是否已在队列中
            duplicate = False
            for item in self.refresh_queue:
                if item.strm_path == strm_path and item.status in ["pending", "processing"]:
                    logger.debug(f"STRM文件已在刷新队列中: {strm_path}")
                    duplicate = True
                    break
                    
            if duplicate:
                return
            
            # 分析文件以获取更多调试信息
            filename = os.path.basename(strm_path)
            dirname = os.path.dirname(strm_path)
            
            # 补充媒体信息(如果未提供)
            if not media_info:
                media_info = {
                    "path": strm_path,
                    "filename": filename,
                    "dirname": dirname,
                    "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            
            # 尝试从文件名中解析媒体信息
            if not media_info.get("title"):
                name_without_ext = os.path.splitext(filename)[0]
                media_info["title"] = name_without_ext
            
            # 添加到队列，设置延迟时间
            refresh_time = time.time() + self.initial_delay
            next_time_str = datetime.fromtimestamp(refresh_time).strftime('%Y-%m-%d %H:%M:%S')
            logger.debug(f"计划刷新时间: {next_time_str}")
            
            item = EmbyRefreshItem(strm_path, refresh_time, 0, media_info)
            self.refresh_queue.append(item)
            
            # 保存队列
            self._save_refresh_queue()
            
        except Exception as e:
            logger.error(f"添加STRM文件到刷新队列时出错: {strm_path}, 错误: {str(e)}")
            # 记录异常堆栈
            import traceback
            logger.error(f"异常详情: {traceback.format_exc()}")
    
    def convert_to_emby_path(self, strm_path: str) -> str:
        """将STRM文件路径转换为Emby中的路径"""
        # 统一路径格式：使用正斜杠，去除末尾斜杠
        strm_path = strm_path.replace('\\', '/')
        strm_root = self.strm_root_path.replace('\\', '/')
        emby_root = self.emby_root_path.replace('\\', '/')
        
        # 去除路径末尾的斜杠
        strm_root = strm_root.rstrip('/')
        emby_root = emby_root.rstrip('/')
        
        # 标准化路径（确保处理各种路径格式）
        normalized_strm_path = '/' + strm_path.lstrip('/')
        normalized_strm_root = '/' + strm_root.lstrip('/')
        
        # 直接替换根路径部分
        if normalized_strm_path.startswith(normalized_strm_root):
            # 提取相对路径
            relative_path = normalized_strm_path[len(normalized_strm_root):].lstrip('/')
            emby_path = f"{emby_root}/{relative_path}"
            return emby_path
        
        # 尝试从路径提取媒体相对路径
        try:
            # 分析路径结构
            strm_parts = strm_path.split('/')
            # 查找常见媒体类型目录名
            media_types = ['电影', '电视剧', '动漫', 'Movies', 'TV Shows', 'Anime']
            
            for idx, part in enumerate(strm_parts):
                if part in media_types and idx < len(strm_parts) - 1:
                    # 找到媒体类型目录，取其后的路径作为相对路径
                    relative_path = '/'.join(strm_parts[idx:])
                    emby_path = f"{emby_root}/{relative_path}"
                    return emby_path
            
            # 最后尝试：如果是多层路径，尝试使用最后2-3层
            if len(strm_parts) >= 3:
                # 取最后3层路径（通常是媒体类型/标题/文件）
                relative_path = '/'.join(strm_parts[-3:])
                emby_path = f"{emby_root}/{relative_path}"
                return emby_path
                
            # 如果所有尝试都失败，返回原始路径
            logger.warning(f"无法转换路径，使用原始路径: {strm_path}")
            return strm_path
        except Exception as e:
            logger.error(f"路径转换失败: {str(e)}")
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
            # 确保emby_url是合法的URL
            if not self.emby_url or not self.emby_url.startswith(('http://', 'https://')):
                logger.error(f"无效的Emby API URL: {self.emby_url}")
                return None
            
            # URL编码路径
            from urllib.parse import quote
            encoded_path = quote(path)
            
            # 构建API URL
            url = f"{self.emby_url}/Items"
            params = {
                "Path": encoded_path,  # 使用编码后的路径
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
                        return None
                else:
                    logger.error(f"查询路径失败: {path}, 状态码: {response.status_code}")
                    return None
            
            return None
        except Exception as e:
            logger.error(f"查询Emby项目失败: {path}, 错误: {str(e)}")
            return None
    
    async def search_items_by_info(self, media_info: Dict[str, Any]) -> List[Dict]:
        """通过媒体信息搜索Emby中的项目"""
        try:
            # 确保emby_url是合法的URL
            if not self.emby_url or not self.emby_url.startswith(('http://', 'https://')):
                logger.error(f"无效的Emby API URL: {self.emby_url}")
                return []
            
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
                logger.debug(f"媒体信息不完整或类型不支持: {media_info}")
                return []
            
            logger.debug(f"搜索Emby项目: URL={url}, 参数={params}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("Items", [])
                    if items:
                        logger.info(f"搜索到 {len(items)} 个匹配项: {media_info.get('title', '')}")
                    return items
                else:
                    logger.error(f"搜索媒体失败, 状态码: {response.status_code}, 响应: {response.text[:200]}")
            
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
    
    async def search_by_name(self, name: str) -> List[Dict]:
        """通过名称搜索Emby媒体项目"""
        try:
            # 空白检查
            if not name or len(name.strip()) < 2:
                logger.warning(f"搜索名称太短或为空: '{name}'")
                return []
                
            # 预处理名称，去除常见的噪音字符
            original_name = name
            name = name.replace('.', ' ').replace('_', ' ')  # 替换常见分隔符为空格
            name = re.sub(r'\s+', ' ', name).strip()  # 合并多个空格并去除首尾空格
            
            # 确保emby_url是合法的URL
            if not self.emby_url or not self.emby_url.startswith(('http://', 'https://')):
                logger.error(f"无效的Emby API URL: {self.emby_url}")
                return []
            
            # 构建搜索API URL
            base_url = self.emby_url.rstrip('/')
            url = f"{base_url}/Items"
            
            # URL编码搜索名称
            encoded_name = quote(name)
            
            params = {
                "api_key": self.api_key,
                "SearchTerm": encoded_name,
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series,Episode,Season",
                "Limit": 15,  # 增加返回数量
                "Fields": "Path,ParentId,Overview,ProductionYear",
                "EnableTotalRecordCount": "false"  # 提高性能
            }
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("Items", [])
                    return items
                else:
                    logger.error(f"搜索失败，状态码: {response.status_code}")
                    return []
            
            return []
        except Exception as e:
            logger.error(f"搜索'{name}'失败: {str(e)}")
            return []
    
    async def find_episode_by_info(self, series_name: str, season_num: int, episode_num: int) -> Optional[Dict]:
        """通过系列名称和集数查找剧集"""
        try:
            logger.debug(f"查找剧集: {series_name} S{season_num:02d}E{episode_num:02d}")
            
            # 首先搜索系列
            series_items = await self.search_by_name(series_name)
            series_id = None
            
            # 找到匹配的系列
            for item in series_items:
                if item.get("Type") == "Series":
                    item_name = item.get("Name", "").lower()
                    search_name = series_name.lower()
                    
                    # 添加名称模糊匹配
                    if item_name == search_name or search_name in item_name or item_name in search_name:
                        series_id = item.get("Id")
                        logger.debug(f"找到匹配的系列: {item.get('Name')}")
                        break
            
            if not series_id:
                logger.debug(f"未找到系列: {series_name}")
                return None
            
            # 构建基础URL
            base_url = self.emby_url
            if base_url.endswith('/'):
                base_url = base_url[:-1]  # 移除末尾的斜杠
                
            # 查找该系列的季
            try:
                # 修复URL拼接 
                url = f"{base_url}/Shows/{series_id}/Seasons"
                params = {"api_key": self.api_key}
                
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, params=params, timeout=30)
                    
                    if response.status_code != 200:
                        logger.error(f"获取季失败: 状态码={response.status_code}")
                        return None
                    
                    seasons_data = response.json()
                    seasons = seasons_data.get("Items", [])
                    
                    # 找到对应的季
                    season_id = None
                    for season in seasons:
                        if season.get("IndexNumber") == season_num:
                            season_id = season.get("Id")
                            logger.debug(f"找到季: {season.get('Name')}")
                            break
            except Exception as e:
                logger.error(f"获取季列表失败: {str(e)}")
                return None
            
            if not season_id:
                logger.debug(f"未找到季: {series_name} S{season_num:02d}，尝试使用第一个季")
                if seasons:
                    season_id = seasons[0].get("Id")
                else:
                    return None
            
            # 查找该季的集
            try:
                # 修复URL拼接
                url = f"{base_url}/Shows/{series_id}/Episodes"
                params = {
                    "api_key": self.api_key,
                    "SeasonId": season_id
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, params=params, timeout=30)
                    
                    if response.status_code != 200:
                        logger.error(f"获取剧集失败: 状态码={response.status_code}")
                        return None
                    
                    episodes_data = response.json()
                    episodes = episodes_data.get("Items", [])
                    
                    # 找到对应的集
                    for episode in episodes:
                        if episode.get("IndexNumber") == episode_num:
                            logger.debug(f"找到剧集: {episode.get('Name')}")
                            return episode
            except Exception as e:
                logger.error(f"获取剧集列表失败: {str(e)}")
                return None
            
            logger.debug(f"未找到剧集: {series_name} S{season_num:02d}E{episode_num:02d}")
            return None
        except Exception as e:
            logger.error(f"查找剧集失败: {str(e)}")
            return None
    
    async def find_emby_item(self, strm_path: str) -> Optional[Dict]:
        """查找Emby中对应于STRM文件的媒体项"""
        try:
            # 保存原始路径用于备用方案
            original_path = strm_path
            
            # 尝试方案1：通过路径直接查询
            try:
                emby_path = self.convert_to_emby_path(strm_path)
                if emby_path:
                    item = await self.query_item_by_path(emby_path)
                    if item:
                        return item
            except Exception as e:
                pass
            
            # 尝试方案2：从STRM提取媒体信息并搜索
            try:
                media_info = await self.extract_media_name_from_strm(strm_path)
                
                if media_info.get("type") == "Episode" and media_info.get("series_name"):
                    episode = await self.find_episode_by_info(
                        media_info.get("series_name", ""),
                        media_info.get("season", 1),
                        media_info.get("episode", 1)
                    )
                    
                    if episode:
                        return episode
                    
                elif media_info.get("type") == "Movie" and media_info.get("title"):
                    title = media_info.get("title", "")
                    year = media_info.get("year", None)
                    search_text = f"{title}" if not year else f"{title} {year}"
                    
                    items = await self.search_by_name(search_text)
                    
                    if items:
                        # 筛选电影类型的结果
                        movie_items = [item for item in items if item.get("Type") == "Movie"]
                        if movie_items:
                            # 如果有年份，优先匹配年份相同的电影
                            if year:
                                exact_year_items = [item for item in movie_items if item.get("ProductionYear") == year]
                                if exact_year_items:
                                    return exact_year_items[0]
                            
                            # 返回第一个匹配的电影
                            return movie_items[0]
            except Exception as e:
                pass
            
            # 尝试方案3：使用文件名和目录名进行多种组合搜索
            try:
                filename = os.path.basename(strm_path)
                name_without_ext = os.path.splitext(filename)[0]
                parent_dir = os.path.dirname(strm_path)
                parent_name = os.path.basename(parent_dir)
                
                # 尝试多种搜索组合
                search_terms = [
                    name_without_ext,  # 文件名
                    parent_name,       # 父目录名
                ]
                
                # 如果文件名包含 S00E00 格式，提取系列名
                series_match = re.search(r'^(.+?)\s*-\s*S\d+E\d+', name_without_ext)
                if series_match:
                    search_terms.append(series_match.group(1).strip())
                
                # 如果父目录是季目录，使用祖父目录作为系列名
                if re.search(r'^(?:Season\s*\d+|S\d+|第.+?季)$', parent_name, re.IGNORECASE):
                    grandparent_dir = os.path.dirname(parent_dir)
                    grandparent_name = os.path.basename(grandparent_dir)
                    search_terms.append(grandparent_name)
                
                # 搜索不同的名称组合
                for term in search_terms:
                    if not term or len(term) < 2:
                        continue
                        
                    items = await self.search_by_name(term)
                    if items:
                        return items[0]
            except Exception as e:
                pass
            
            # 尝试方案4：使用路径的相似性搜索
            try:
                # 将strm路径分解为目录和文件名
                filename = os.path.basename(strm_path)
                dirname = os.path.dirname(strm_path)
            except Exception as e:
                pass
            
            # 如果上述所有方法都失败，尝试最后的方法：使用正则表达式提取简化名称进行搜索
            try:
                filename = os.path.basename(strm_path)
                name_without_ext = os.path.splitext(filename)[0]
                
                # 移除常见的格式标记和无关字符，只保留关键标题
                simplified_name = re.sub(r'\s*-\s*.*$', '', name_without_ext)  # 移除 - 之后的内容
                simplified_name = re.sub(r'\s*\(.*\)', '', simplified_name)    # 移除括号内容
                simplified_name = re.sub(r'\s*\[.*\]', '', simplified_name)    # 移除方括号内容
                simplified_name = re.sub(r'\s*\d+p\s*', '', simplified_name)   # 移除分辨率
                simplified_name = re.sub(r'\s+', ' ', simplified_name)         # 合并空格
                simplified_name = simplified_name.strip()
                
                if simplified_name and len(simplified_name) >= 3 and simplified_name != name_without_ext:
                    items = await self.search_by_name(simplified_name)
                    if items:
                        return items[0]
            except Exception as e:
                pass
            
            logger.warning(f"所有方法都失败，无法找到Emby项目: {strm_path}")
            return None
        except Exception as e:
            logger.error(f"查找Emby项目过程中出错: {str(e)}, strm文件: {strm_path}")
            return None
    
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
    
    async def process_refresh_queue(self):
        """处理刷新队列中的条目"""
        if not self.emby_enabled:
            logger.debug("Emby服务未启用，跳过处理刷新队列")
            return
        
        if self._is_processing:
            logger.debug("队列正在处理中，跳过")
            return
        
        current_time = time.time()
        self._is_processing = True
        try:
            logger.info("开始处理Emby刷新队列...")
            
            # 统计初始队列状态
            total_items = len(self.refresh_queue)
            pending_items = sum(1 for item in self.refresh_queue if item.status == "pending" and item.timestamp <= current_time)
            
            logger.info(f"当前队列共有 {total_items} 个项目，其中 {pending_items} 个待处理")
            
            processed_count = 0
            success_count = 0
            for item in self.refresh_queue:
                if self._stop_flag:
                    logger.info("收到停止信号，中断队列处理")
                    break
                
                # 只处理状态为pending且时间已到的项目
                if item.status == "pending" and item.timestamp <= current_time:
                    processed_count += 1
                    
                    # 更新状态为processing
                    item.status = "processing"
                    self._save_refresh_queue()
                    
                    try:
                        # 优先使用已有的item_id（新方法直接获取了ID）
                        item_id = item.item_id
                        
                        # 如果没有item_id，再尝试从缓存或通过查找获取
                        if not item_id:
                            # 从缓存中查找
                            cached_id = self.get_from_path_cache(item.strm_path)
                            if cached_id:
                                logger.debug(f"从缓存找到ItemID: {cached_id}")
                                item_id = cached_id
                                item.item_id = item_id
                            else:
                                # 只有在缓存中找不到时才使用find_emby_item
                                logger.debug(f"缓存中未找到，尝试搜索Emby项目: {item.strm_path}")
                                emby_item = await self.find_emby_item(item.strm_path)
                                if emby_item:
                                    item_id = emby_item.get("Id")
                                    item.item_id = item_id
                                    # 添加到缓存
                                    self.add_to_path_cache(
                                        item.strm_path, 
                                        item_id,
                                        emby_item.get("Type"),
                                        emby_item.get("Name")
                                    )
                        
                        # 刷新Emby项目
                        if item_id:
                            refresh_success = await self.refresh_emby_item(item_id)
                            
                            if refresh_success:
                                # 刷新成功
                                item.status = "success"
                                success_count += 1
                                logger.info(f"成功刷新Emby项目ID: {item_id}")
                            else:
                                # 刷新失败，设置为失败状态
                                item.status = "failed"
                                item.last_error = "刷新API调用失败"
                                
                                # 设置下次重试时间
                                if item.retry_count < self.max_retries:
                                    delay = self.retry_delays[item.retry_count]
                                    item.next_retry_time = current_time + delay
                                    logger.warning(f"刷新失败，将在 {delay/3600:.1f} 小时后重试: {item.strm_path}")
                                else:
                                    logger.error(f"刷新失败，超过最大重试次数: {item.strm_path}")
                        else:
                            # 未找到项目，设置为失败状态
                            item.status = "failed"
                            item.last_error = "未找到Emby中的媒体项目"
                            
                            # 设置下次重试时间
                            if item.retry_count < self.max_retries:
                                delay = self.retry_delays[item.retry_count]
                                item.next_retry_time = current_time + delay
                                item.timestamp = item.next_retry_time  # 更新计划时间为下次重试时间
                                item.retry_count += 1
                                logger.warning(f"未找到媒体项目，将在 {delay/3600:.1f} 小时后重试 (第{item.retry_count}次): {item.strm_path}")
                            else:
                                logger.error(f"未找到媒体项目，超过最大重试次数，不再尝试: {item.strm_path}")
                    
                    except Exception as e:
                        # 处理过程中出错，设置为失败状态
                        item.status = "failed"
                        item.last_error = str(e)
                        
                        # 设置下次重试时间
                        if item.retry_count < self.max_retries:
                            delay = self.retry_delays[item.retry_count]
                            item.next_retry_time = current_time + delay
                            item.timestamp = item.next_retry_time  # 更新计划时间为下次重试时间
                            item.retry_count += 1
                            logger.error(f"处理刷新项目时出错，将在 {delay/3600:.1f} 小时后重试 (第{item.retry_count}次): {item.strm_path}, 错误: {str(e)}")
                        else:
                            logger.error(f"处理刷新项目时出错，超过最大重试次数，不再尝试: {item.strm_path}, 错误: {str(e)}")
                    
                    # 保存队列
                    self._save_refresh_queue()
                    
                    # 添加一点延迟，避免过快请求
                    await asyncio.sleep(1)
            
            # 更新失败项的重试时间
            if processed_count > 0:
                # 检查是否有需要重试的项目，并设置它们的时间戳
                for item in self.refresh_queue:
                    if item.status == "failed" and item.retry_count < self.max_retries:
                        # 下次处理时间已经在上面设置好了，不需要再次设置
                        pass
                
                # 保存队列
                self._save_refresh_queue()
            
            logger.info(f"完成队列处理，共处理 {processed_count} 个项目，成功 {success_count} 个")
        
        finally:
            self._is_processing = False
    
    async def start_refresh_task(self):
        """启动定期刷新任务"""
        # 如果Emby功能未启用，不启动任务
        if not self.emby_enabled:
            logger.info("Emby刷库功能未启用，不启动刷新任务")
            return
            
        logger.info("启动Emby刷新任务")
        self._stop_flag = False
        
        # 启动自动扫描任务
        asyncio.create_task(self._auto_scan_task())
        
        while not self._stop_flag:
            await self.process_refresh_queue()
            await asyncio.sleep(60)  # 每分钟检查一次队列
    
    async def _auto_scan_task(self):
        """定期执行扫描最新项目的任务，每6小时执行一次"""
        logger.info("启动自动扫描Emby最新项目任务")
        
        while not self._stop_flag:
            try:
                # 执行扫描
                logger.info("执行定时Emby新项目扫描")
                result = await self.scan_latest_items(hours=12)  # 扫描最近12小时的项目
                
                if result["success"]:
                    logger.info(f"定时扫描完成: {result['message']}")
                    # 发送通知
                    try:
                        service_manager = self._get_service_manager()
                        if result["added_to_queue"] > 0:
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
    
    def stop_refresh_task(self):
        """停止刷新任务"""
        logger.info("停止Emby刷新任务")
        self._stop_flag = True 

    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager 

    def clear_refresh_queue(self):
        """清空刷新队列"""
        try:
            # 记录当前队列大小
            queue_size = len(self.refresh_queue)
            logger.info(f"开始清空刷新队列，当前队列大小: {queue_size}")
            
            # 保留成功的项目，清除待处理和失败的项目
            self.refresh_queue = [item for item in self.refresh_queue if item.status == "success"]
            
            # 保存更新后的队列
            self._save_refresh_queue()
            
            removed_count = queue_size - len(self.refresh_queue)
            logger.info(f"已清空刷新队列，移除了 {removed_count} 个项目，保留 {len(self.refresh_queue)} 个成功项目")
            
            return {
                "success": True,
                "message": f"已清空刷新队列，移除了 {removed_count} 个待处理和失败项目，保留 {len(self.refresh_queue)} 个成功项目",
                "removed_count": removed_count,
                "remaining_count": len(self.refresh_queue)
            }
        except Exception as e:
            logger.error(f"清空刷新队列失败: {str(e)}")
            return {
                "success": False,
                "message": f"清空刷新队列失败: {str(e)}"
            }

    def clean_failed_refresh_queue(self):
        """清理失败的刷新队列项，移除404错误项"""
        try:
            # 记录当前队列大小
            queue_size = len(self.refresh_queue)
            logger.info(f"开始清理失败的刷新队列项，当前队列大小: {queue_size}")
            
            # 移除404错误的项目
            old_queue = self.refresh_queue.copy()
            self.refresh_queue = [
                item for item in old_queue 
                if not (item.status == "failed" and item.last_error and "404" in item.last_error)
            ]
            
            # 保存更新后的队列
            self._save_refresh_queue()
            
            removed_count = queue_size - len(self.refresh_queue)
            logger.info(f"已清理失败的刷新队列项，移除了 {removed_count} 个404错误项，剩余 {len(self.refresh_queue)} 个项目")
            
            return {
                "success": True, 
                "message": f"已清理队列中的404错误项，移除了 {removed_count} 个项目",
                "removed_count": removed_count,
                "remaining_count": len(self.refresh_queue)
            }
        except Exception as e:
            logger.error(f"清理失败的刷新队列项失败: {str(e)}")
            return {
                "success": False,
                "message": f"清理失败: {str(e)}"
            }

    # 添加获取单个媒体项的方法，作为临时方案
    async def get_item(self, item_id: str) -> Optional[Dict]:
        """通过ID获取Emby媒体项目的基本信息（不调用API）"""
        try:
            # 不再调用/Items/{item_id} API，直接返回简单对象
            logger.debug(f"使用item_id: {item_id}，返回基本信息对象")
            return {"Id": item_id, "Name": f"媒体项 {item_id}", "Type": "Unknown"}
        except Exception as e:
            logger.error(f"处理item_id时出错: {item_id}, 错误: {str(e)}")
            return {"Id": item_id, "Name": "处理出错", "Error": str(e)}

    def _load_path_cache(self):
        """加载路径缓存"""
        try:
            # 确保缓存目录存在
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.path_to_id_cache = json.load(f)
                logger.info(f"已加载路径缓存，共{len(self.path_to_id_cache)}个记录")
            else:
                self.path_to_id_cache = {}
                logger.info("路径缓存文件不存在，创建新缓存")
        except Exception as e:
            logger.error(f"加载路径缓存失败: {e}")
            self.path_to_id_cache = {}
    
    def _save_path_cache(self):
        """保存路径缓存到文件"""
        try:
            # 确保缓存目录存在
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.path_to_id_cache, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存路径缓存，共{len(self.path_to_id_cache)}个记录")
        except Exception as e:
            logger.error(f"保存路径缓存失败: {e}")
            
    def add_to_path_cache(self, path: str, item_id: str, media_type: str = None, title: str = None):
        """添加路径到ID的映射
        
        Args:
            path: 路径（可以是STRM路径或源文件路径）
            item_id: Emby媒体项ID
            media_type: 媒体类型（如Movie, Episode）
            title: 媒体标题
        """
        if not path or not item_id:
            return
            
        # 标准化路径
        path = str(path).replace('\\', '/').rstrip('/')
        
        # 创建或更新缓存条目
        cache_entry = {
            "item_id": item_id,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if media_type:
            cache_entry["media_type"] = media_type
            
        if title:
            cache_entry["title"] = title
            
        # 添加到缓存
        self.path_to_id_cache[path] = cache_entry
        self._save_path_cache()
        logger.debug(f"添加路径映射到缓存: {path} -> {item_id}")
        
    def get_from_path_cache(self, path: str) -> Optional[str]:
        """从路径缓存中获取Emby媒体项ID
        
        Args:
            path: 路径（可以是STRM路径或源文件路径）
            
        Returns:
            Optional[str]: Emby媒体项ID，如果不存在则返回None
        """
        if not path:
            return None
            
        # 标准化路径
        path = str(path).replace('\\', '/').rstrip('/')
        
        # 从缓存中获取
        cache_entry = self.path_to_id_cache.get(path)
        if cache_entry:
            logger.debug(f"从缓存中找到路径映射: {path} -> {cache_entry.get('item_id')}")
            return cache_entry.get("item_id")
        
        return None
        
    def clear_path_cache(self):
        """清空路径缓存"""
        self.path_to_id_cache = {}
        self._save_path_cache()
        logger.info("已清空路径缓存")

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

    async def test_search(self, query: str, mode: str = "name") -> dict:
        """测试搜索功能
        
        Args:
            query: 搜索查询
            mode: 搜索模式 (name: 按名称, path: 按路径)
            
        Returns:
            dict: 搜索结果
        """
        try:
            if not self.emby_enabled:
                return {"success": False, "message": "Emby服务未启用"}
            
            results = []
            
            if mode == "path":
                # 转换路径
                emby_path = self.convert_to_emby_path(query)
                logger.info(f"测试按路径搜索: 原始路径={query}, 转换后={emby_path}")
                
                # 查询媒体项
                item = await self.query_item_by_path(emby_path)
                if item:
                    results.append({
                        "id": item.get("Id"),
                        "name": item.get("Name"),
                        "type": item.get("Type"),
                        "path": item.get("Path"),
                        "year": item.get("ProductionYear")
                    })
                
            else:  # 默认按名称搜索
                logger.info(f"测试按名称搜索: {query}")
                items = await self.search_by_name(query)
                
                # 提取结果
                for item in items[:10]:  # 最多返回10个结果
                    results.append({
                        "id": item.get("Id"),
                        "name": item.get("Name"),
                        "type": item.get("Type"),
                        "path": item.get("Path"),
                        "year": item.get("ProductionYear")
                    })
            
            # 缓存状态
            cache_count = len(self.path_to_id_cache)
            
            return {
                "success": True,
                "query": query,
                "mode": mode,
                "result_count": len(results),
                "results": results,
                "cache_count": cache_count
            }
            
        except Exception as e:
            logger.error(f"测试搜索失败: {str(e)}")
            import traceback
            return {
                "success": False,
                "message": str(e),
                "error_detail": traceback.format_exc()
            }

    async def force_refresh(self, path: str) -> dict:
        """强制刷新指定文件
        
        Args:
            path: 文件路径
            
        Returns:
            dict: 刷新结果
        """
        try:
            if not self.emby_enabled:
                return {"success": False, "message": "Emby服务未启用"}
            
            # 标准化路径
            path = str(path).replace('\\', '/')
            
            # 首先检查是否存在于缓存中
            emby_id = self.get_from_path_cache(path)
            
            if emby_id:
                logger.info(f"从缓存中找到路径 {path} 对应的Emby项目ID: {emby_id}")
                # 直接刷新
                refresh_result = await self.refresh_emby_item(emby_id)
                if refresh_result:
                    return {
                        "success": True,
                        "message": f"成功刷新Emby项目ID: {emby_id}",
                        "refresh_method": "cache"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"刷新Emby项目失败: {emby_id}",
                        "refresh_method": "cache"
                    }
            
            # 如果不在缓存中，尝试搜索
            logger.info(f"在缓存中未找到路径 {path}，尝试搜索Emby")
            
            # 尝试通过路径查询
            emby_path = self.convert_to_emby_path(path)
            item = await self.query_item_by_path(emby_path)
            
            if item:
                # 添加到缓存
                self.add_to_path_cache(path, item.get("Id"), item.get("Type"), item.get("Name"))
                
                # 刷新
                refresh_result = await self.refresh_emby_item(item.get("Id"))
                if refresh_result:
                    return {
                        "success": True,
                        "message": f"成功刷新Emby项目: {item.get('Name')} (ID: {item.get('Id')})",
                        "refresh_method": "path_query"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"刷新Emby项目失败: {item.get('Name')} (ID: {item.get('Id')})",
                        "refresh_method": "path_query"
                    }
            
            # 如果通过路径查询失败，尝试通过文件名搜索
            filename = os.path.basename(path)
            name_without_ext = os.path.splitext(filename)[0]
            
            items = await self.search_by_name(name_without_ext)
            if items:
                item = items[0]  # 使用第一个匹配结果
                
                # 添加到缓存
                self.add_to_path_cache(path, item.get("Id"), item.get("Type"), item.get("Name"))
                
                # 刷新
                refresh_result = await self.refresh_emby_item(item.get("Id"))
                if refresh_result:
                    return {
                        "success": True,
                        "message": f"成功刷新Emby项目: {item.get('Name')} (ID: {item.get('Id')})",
                        "refresh_method": "name_search"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"刷新Emby项目失败: {item.get('Name')} (ID: {item.get('Id')})",
                        "refresh_method": "name_search"
                    }
            
            # 如果所有方法都失败
            return {
                "success": False,
                "message": f"未找到路径 {path} 对应的Emby项目"
            }
            
        except Exception as e:
            logger.error(f"强制刷新失败: {str(e)}")
            import traceback
            return {
                "success": False,
                "message": str(e),
                "error_detail": traceback.format_exc()
            }

    async def get_queue_status(self) -> dict:
        """获取刷新队列状态
        
        Returns:
            dict: 队列状态
        """
        try:
            if not self.emby_enabled:
                return {"success": False, "message": "Emby服务未启用"}
            
            # 统计各状态的数量
            total = len(self.refresh_queue)
            pending = sum(1 for item in self.refresh_queue if item.status == "pending")
            processing = sum(1 for item in self.refresh_queue if item.status == "processing")
            success = sum(1 for item in self.refresh_queue if item.status == "success")
            failed = sum(1 for item in self.refresh_queue if item.status == "failed")
            
            # 获取下一个待处理项的时间
            next_item = None
            current_time = time.time()
            for item in self.refresh_queue:
                if item.status == "pending" and item.timestamp > current_time:
                    if next_item is None or item.timestamp < next_item.timestamp:
                        next_item = item
            
            next_time = None
            if next_item:
                next_time = datetime.fromtimestamp(next_item.timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取最近的几个项目详情
            recent_items = []
            for item in sorted(self.refresh_queue, key=lambda x: x.timestamp, reverse=True)[:10]:
                recent_items.append({
                    "path": item.strm_path,
                    "status": item.status,
                    "time": datetime.fromtimestamp(item.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                    "retry_count": item.retry_count,
                    "error": item.last_error
                })
            
            # 缓存状态
            cache_count = len(self.path_to_id_cache)
            
            return {
                "success": True,
                "queue_status": {
                    "total": total,
                    "pending": pending,
                    "processing": processing,
                    "success": success,
                    "failed": failed,
                    "next_time": next_time
                },
                "recent_items": recent_items,
                "cache_status": {
                    "total": cache_count
                }
            }
            
        except Exception as e:
            logger.error(f"获取刷新队列状态失败: {str(e)}")
            import traceback
            return {
                "success": False,
                "message": str(e),
                "error_detail": traceback.format_exc()
            }
            
    async def get_last_refresh_info(self) -> dict:
        """获取最近一次刷新的信息
        
        Returns:
            dict: 最近一次刷新的信息
        """
        try:
            if not self.emby_enabled:
                return {"success": False, "message": "Emby服务未启用"}
            
            if not self.last_refresh_time:
                return {
                    "success": True,
                    "message": "尚未执行过刷新",
                    "has_refresh": False
                }
            
            # 获取队列中这些项目的当前状态
            item_statuses = []
            for item in self.last_refresh_items:
                item_id = item.get("id")
                item_path = item.get("path")
                
                # 查找在队列中的状态
                queue_item = next((q for q in self.refresh_queue if q.strm_path == item_path), None)
                status = "unknown"
                last_error = None
                
                if queue_item:
                    status = queue_item.status
                    last_error = queue_item.last_error
                    
                item_statuses.append({
                    "id": item_id,
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "status": status,
                    "error": last_error
                })
                
            return {
                "success": True,
                "message": "获取最近刷新信息成功",
                "has_refresh": True,
                "time": self.last_refresh_time,
                "items": item_statuses,
                "total_count": len(item_statuses)
            }
            
        except Exception as e:
            logger.error(f"获取最近刷新信息失败: {str(e)}")
            return {
                "success": False,
                "message": f"获取失败: {str(e)}"
            }

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
                "SortOrder": "Descending",
                "HasTmdbId": "false"  # 只获取没有TMDB ID的项目，避免刷新已有元数据的文件
            }
            
            # 如果指定了媒体类型，添加过滤
            if item_type:
                params["IncludeItemTypes"] = item_type
            
            logger.debug(f"获取最新入库项目: 类型={item_type}, 数量={limit}, 排序={params['SortBy']}, 仅未识别={params['HasTmdbId']}")
            
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

    async def scan_latest_items(self, hours: int = 24, force_refresh: bool = False) -> dict:
        """扫描指定时间范围内新入库的项目并添加到刷新队列
        
        Args:
            hours: 扫描最近多少小时的项目
            force_refresh: 是否强制刷新(忽略HasTmdbId)
            
        Returns:
            dict: 扫描结果
        """
        try:
            if not self.emby_enabled:
                return {"success": False, "message": "Emby服务未启用"}
            
            # 计算时间范围
            current_time = time.time()
            start_time = current_time - (hours * 3600)
            
            # 获取最新项目，使用排序和过滤
            params = {
                "limit": 300,  # 获取较多项目以确保覆盖
                "item_type": None  # 不限制类型
            }
            
            # 获取最新项目
            latest_items = await self.get_latest_items(**params)
            
            # 过滤时间范围内的项目
            new_items = []
            for item in latest_items:
                # 获取项目的添加时间
                date_created = item.get("DateCreated")
                if date_created:
                    try:
                        # 解析ISO格式的时间
                        from datetime import datetime
                        created_time = datetime.fromisoformat(date_created.replace('Z', '+00:00'))
                        created_timestamp = created_time.timestamp()
                        
                        if created_timestamp >= start_time:
                            # 如果是强制刷新，或者项目没有元数据，则添加
                            if force_refresh or not item.get("ProviderIds", {}).get("Tmdb"):
                                new_items.append(item)
                    except Exception as e:
                        logger.debug(f"解析项目时间出错: {str(e)}")
            
            # 添加到刷新队列
            added_count = 0
            added_items = []  # 记录添加的项目信息
            for item in new_items:
                item_path = item.get("Path")
                if item_path:
                    # 检查是否已在队列中
                    if not any(q_item.strm_path == item_path for q_item in self.refresh_queue):
                        # 添加到队列
                        media_info = {
                            "title": item.get("Name"),
                            "type": item.get("Type"),
                            "year": item.get("ProductionYear"),
                            "source_path": item_path
                        }
                        self.add_to_refresh_queue(item_path, media_info)
                        added_count += 1
                        
                        # 记录添加的项目简要信息
                        added_items.append({
                            "id": item.get("Id"),
                            "name": item.get("Name"),
                            "type": item.get("Type"),
                            "path": item_path,
                            "year": item.get("ProductionYear")
                        })
            
            # 保存本次刷新记录
            if added_items:
                self._save_last_refresh(added_items)
            
            return {
                "success": True,
                "message": f"扫描完成，发现 {len(new_items)} 个新项目，添加 {added_count} 个到刷新队列",
                "total_found": len(new_items),
                "added_to_queue": added_count,
                "added_items": added_items
            }
            
        except Exception as e:
            logger.error(f"扫描最新项目失败: {str(e)}")
            return {
                "success": False,
                "message": f"扫描失败: {str(e)}"
            }