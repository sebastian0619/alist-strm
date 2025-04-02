import os
import json
import time
import asyncio
import httpx
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from config import Settings
import importlib

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
        
        # 刷新队列
        self.refresh_queue: List[EmbyRefreshItem] = []
        self.queue_file = Path("data/emby_refresh_queue.json")
        self.queue_file.parent.mkdir(exist_ok=True)
        
        # 加载刷新队列
        self._load_refresh_queue()
        
        # 标志位
        self._is_processing = False
        self._stop_flag = False
        
        # 刷新任务的配置 - 增加延迟，给Emby更多时间扫描
        self.initial_delay = 1800  # 30分钟
        self.retry_delays = [3600, 7200, 14400, 28800]  # 1小时, 2小时, 4小时, 8小时
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
        # 如果Emby功能未开启，不添加到队列
        if not self.emby_enabled:
            logger.debug(f"Emby刷库功能未启用，不添加到刷新队列: {strm_path}")
            return
            
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
        
        logger.info(f"==== 路径转换详细日志 ====")
        logger.info(f"转换路径: {strm_path}")
        logger.info(f"STRM根路径: {strm_root}")
        logger.info(f"Emby根路径: {emby_root}")
        
        # 去除路径末尾的斜杠
        if strm_root.endswith('/'):
            strm_root = strm_root[:-1]
            logger.info(f"去除末尾斜杠后的STRM根路径: {strm_root}")
            
        if emby_root.endswith('/'):
            emby_root = emby_root[:-1]
            logger.info(f"去除末尾斜杠后的Emby根路径: {emby_root}")
            
        # 标准化路径（确保开头的斜杠一致）
        normalized_strm_path = '/' + strm_path.lstrip('/')
        normalized_strm_root = '/' + strm_root.lstrip('/')
        
        logger.info(f"标准化后的STRM路径: {normalized_strm_path}")
        logger.info(f"标准化后的STRM根路径: {normalized_strm_root}")
        
        # 检查路径是否匹配
        if normalized_strm_path.startswith(normalized_strm_root):
            # 提取相对路径
            relative_path = normalized_strm_path[len(normalized_strm_root):].lstrip('/')
            emby_path = f"{emby_root}/{relative_path}"
            logger.info(f"匹配成功 - 标准化路径匹配: {strm_path} -> {emby_path}")
            return emby_path
        
        # 检查不带前导斜杠的情况
        strm_root_no_slash = strm_root.lstrip('/')
        if strm_path.startswith(strm_root_no_slash):
            # 提取相对路径
            relative_path = strm_path[len(strm_root_no_slash):].lstrip('/')
            emby_path = f"{emby_root}/{relative_path}"
            logger.info(f"匹配成功 - 无斜杠路径匹配: {strm_path} -> {emby_path}")
            return emby_path
            
        # 如果以上都不匹配，尝试直接查找非路径部分
        try:
            # 获取最有可能的相对路径
            normalized_path = strm_path.lstrip('/')
            normalized_root = strm_root.lstrip('/')
            
            logger.info(f"尝试部分匹配 - 标准化后的STRM路径(无斜杠): {normalized_path}")
            logger.info(f"尝试部分匹配 - 标准化后的STRM根路径(无斜杠): {normalized_root}")
            
            # 检查路径中是否包含根路径的最后一部分
            root_parts = normalized_root.split('/')
            logger.info(f"根路径的组成部分: {root_parts}")
            
            if root_parts and root_parts[-1] in normalized_path:
                # 查找根目录的最后一部分在路径中的位置
                pos = normalized_path.find(root_parts[-1])
                logger.info(f"找到根目录最后部分 '{root_parts[-1]}' 在路径中的位置: {pos}")
                
                if pos >= 0:
                    # 找到根目录的最后一部分后的路径
                    end_pos = pos + len(root_parts[-1])
                    relative_path = normalized_path[end_pos:].lstrip('/')
                    emby_path = f"{emby_root}/{relative_path}"
                    logger.info(f"匹配成功 - 部分匹配路径转换: {strm_path} -> {emby_path}")
                    return emby_path
        except Exception as e:
            logger.warning(f"尝试部分匹配路径时出错: {str(e)}")
        
        # 如果不能转换，返回原路径并记录警告
        logger.warning(f"无法转换路径: {strm_path}，STRM根路径: {strm_root}, Emby根路径: {emby_root}")
        
        # 最后尝试直接使用Emby根路径加相对路径
        try:
            # 尝试提取相对路径的另一种方法
            # 使用STRM路径的目录结构，从后往前匹配
            strm_parts = normalized_path.split('/')
            logger.info(f"尝试使用STRM路径的目录结构: {strm_parts}")
            
            # 提取电视剧/电影名称和季信息等
            if len(strm_parts) >= 3:
                # 假设格式为 [media_type]/[series_name]/[season]/[episode.strm]
                file_name = strm_parts[-1]  # 文件名
                season_dir = strm_parts[-2] if len(strm_parts) > 1 else ""
                series_dir = strm_parts[-3] if len(strm_parts) > 2 else ""
                media_type = strm_parts[-4] if len(strm_parts) > 3 else ""
                
                logger.info(f"尝试从路径结构提取: 媒体类型={media_type}, 系列={series_dir}, 季={season_dir}, 文件={file_name}")
                
                # 构建Emby根路径下的相对路径
                if media_type and series_dir and (season_dir or file_name):
                    relative_path = "/".join(filter(None, [media_type, series_dir, season_dir, file_name]))
                    emby_path = f"{emby_root}/{relative_path}"
                    logger.info(f"回退方案 - 使用路径结构构建: {strm_path} -> {emby_path}")
                    return emby_path
            
            # 假设strm_path是相对于STRM根目录的路径，直接拼接
            relative_path = strm_path.lstrip('/')
            emby_path = f"{emby_root}/{relative_path}"
            logger.info(f"回退方案 - 直接拼接路径: {strm_path} -> {emby_path}")
            return emby_path
        except Exception as e:
            logger.error(f"回退路径转换失败: {str(e)}")
            logger.info(f"使用原始路径作为Emby路径: {strm_path}")
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
            
            # 构建API URL
            url = f"{self.emby_url}/Items"
            params = {
                "Path": path,
                "api_key": self.api_key
            }
            
            logger.debug(f"查询Emby项目: URL={url}, Path={path}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("Items") and len(data["Items"]) > 0:
                        logger.info(f"找到Emby项目: {path} -> {data['Items'][0].get('Name', '未知')}")
                        return data["Items"][0]
                    else:
                        logger.debug(f"未找到Emby项目: {path}")
                else:
                    logger.error(f"查询路径失败: {path}, 状态码: {response.status_code}, 响应: {response.text[:200]}")
            
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
            # 确保emby_url是合法的URL
            if not self.emby_url or not self.emby_url.startswith(('http://', 'https://')):
                logger.error(f"无效的Emby API URL: {self.emby_url}")
                return []
            
            # 构建搜索API URL
            url = f"{self.emby_url}/Items"
            params = {
                "api_key": self.api_key,
                "SearchTerm": name,
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series,Episode",
                "Limit": 10,
                "Fields": "Path,ParentId"
            }
            
            logger.info(f"通过名称搜索Emby项目: URL={url}, 参数={params}")
            
            # 发送请求
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("Items", [])
                    
                    if items:
                        logger.info(f"搜索\"{name}\"找到 {len(items)} 个结果")
                        for item in items:
                            logger.info(f"  - {item.get('Type')}: {item.get('Name')} (ID: {item.get('Id')})")
                    else:
                        logger.warning(f"搜索\"{name}\"未找到任何结果。原始响应: {data}")
                    
                    return items
                else:
                    logger.error(f"搜索失败，状态码: {response.status_code}")
                    logger.error(f"响应: {response.text[:500]}")
            
            return []
        except Exception as e:
            logger.error(f"通过名称搜索失败: {str(e)}")
            return []
    
    async def extract_media_name_from_strm(self, strm_path: str) -> Dict:
        """从STRM文件名提取媒体信息，并根据路径判断媒体类型"""
        try:
            # 获取文件名和路径
            filename = os.path.basename(strm_path)
            name_without_ext = os.path.splitext(filename)[0]
            full_path = str(strm_path).replace('\\', '/')
            
            # 根据路径判断媒体类型
            media_type = "Unknown"
            if "电影" in full_path:
                media_type = "Movie"
            elif any(keyword in full_path for keyword in ["电视剧", "动漫", "综艺"]):
                media_type = "TV"
            
            logger.info(f"根据路径识别媒体类型: {media_type}, 路径: {full_path}")
            
            # 解析媒体信息
            media_info = {
                "type": media_type,
                "name": name_without_ext
            }
            
            # 匹配电视剧格式: "洛基 - S02E05 - 第 5 集"
            import re
            tv_match = re.search(r'^(.+?) - S(\d+)E(\d+)(?:\s*-\s*(.+))?', name_without_ext)
            
            if tv_match and (media_type == "TV" or media_type == "Unknown"):
                series_name = tv_match.group(1).strip()
                season_num = int(tv_match.group(2))
                episode_num = int(tv_match.group(3))
                
                media_info = {
                    "type": "Episode",
                    "series_name": series_name,
                    "season": season_num,
                    "episode": episode_num
                }
                
                if tv_match.group(4):
                    media_info["episode_title"] = tv_match.group(4).strip()
                
                logger.info(f"识别为剧集: {series_name} S{season_num:02d}E{episode_num:02d}")
                return media_info
            
            # 匹配电影格式，提取年份
            movie_match = re.search(r'^(.+?)(?:\s*\((\d{4})\))?$', name_without_ext)
            if movie_match and (media_type == "Movie" or media_type == "Unknown"):
                title = movie_match.group(1).strip()
                media_info = {
                    "type": "Movie",
                    "title": title,
                }
                
                # 提取年份（如果有）
                if movie_match.group(2):
                    media_info["year"] = int(movie_match.group(2))
                
                logger.info(f"识别为电影: {title} ({media_info.get('year', '未知年份')})")
                return media_info
            
            logger.info(f"媒体类型识别结果: {media_type}, 名称: {name_without_ext}")
            return media_info
        except Exception as e:
            logger.error(f"提取媒体名称出错: {str(e)}")
            return {"type": "Unknown", "name": ""}
    
    async def find_episode_by_info(self, series_name: str, season_num: int, episode_num: int) -> Optional[Dict]:
        """通过系列名称和集数查找剧集"""
        try:
            # 详细记录搜索参数
            logger.info(f"开始查找剧集: 系列={series_name}, 季={season_num}, 集={episode_num}")
            
            # 首先搜索系列
            series_items = await self.search_by_name(series_name)
            series_id = None
            
            # 详细记录搜索结果
            if series_items:
                logger.info(f"搜索系列'{series_name}'返回 {len(series_items)} 个结果")
                for idx, item in enumerate(series_items):
                    logger.info(f"  [{idx+1}] 类型: {item.get('Type')}, 名称: {item.get('Name')}, ID: {item.get('Id')}")
            else:
                logger.warning(f"搜索系列'{series_name}'没有结果")
            
            # 找到匹配的系列
            for item in series_items:
                if item.get("Type") == "Series":
                    item_name = item.get("Name", "").lower()
                    search_name = series_name.lower()
                    logger.info(f"比较系列名称: '{item_name}' vs '{search_name}'")
                    
                    # 添加名称模糊匹配
                    if item_name == search_name or search_name in item_name or item_name in search_name:
                        series_id = item.get("Id")
                        logger.info(f"找到匹配的系列: {item.get('Name')} (ID: {series_id})")
                        break
            
            if not series_id:
                logger.warning(f"未找到系列: {series_name}")
                return None
            
            # 查找该系列的季
            url = f"{self.emby_url}/Shows/{series_id}/Seasons"
            params = {"api_key": self.api_key}
            
            logger.info(f"获取系列{series_id}的季列表")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"获取季失败: {response.status_code}")
                    return None
                
                seasons_data = response.json()
                seasons = seasons_data.get("Items", [])
                
                # 记录找到的季
                logger.info(f"系列{series_id}有 {len(seasons)} 个季")
                for s in seasons:
                    logger.info(f"  - 季 {s.get('IndexNumber', '未知')}: {s.get('Name')} (ID: {s.get('Id')})")
                
                # 找到对应的季
                season_id = None
                for season in seasons:
                    if season.get("IndexNumber") == season_num:
                        season_id = season.get("Id")
                        logger.info(f"找到季: {season.get('Name')} (ID: {season_id})")
                        break
            
            if not season_id:
                logger.warning(f"未找到季: {series_name} S{season_num:02d}, 尝试强制使用第一个季")
                if seasons:
                    season_id = seasons[0].get("Id")
                    logger.info(f"强制使用第一个季: {seasons[0].get('Name')} (ID: {season_id})")
                else:
                    return None
            
            # 查找该季的集
            url = f"{self.emby_url}/Shows/{series_id}/Episodes"
            params = {
                "api_key": self.api_key,
                "SeasonId": season_id
            }
            
            logger.info(f"获取季{season_id}的剧集列表")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"获取剧集失败: {response.status_code}")
                    return None
                
                episodes_data = response.json()
                episodes = episodes_data.get("Items", [])
                
                # 记录找到的集
                logger.info(f"季{season_id}有 {len(episodes)} 个剧集")
                for ep in episodes:
                    logger.info(f"  - 集 {ep.get('IndexNumber', '未知')}: {ep.get('Name')} (ID: {ep.get('Id')})")
                
                # 找到对应的集
                for episode in episodes:
                    if episode.get("IndexNumber") == episode_num:
                        logger.info(f"找到剧集: {episode.get('Name')} (ID: {episode.get('Id')})")
                        return episode
            
            logger.warning(f"未找到剧集: {series_name} S{season_num:02d}E{episode_num:02d}")
            return None
        except Exception as e:
            logger.error(f"查找剧集失败: {str(e)}")
            return None
    
    async def find_emby_item(self, strm_path: str) -> Optional[Dict]:
        """查找Emby中对应于STRM文件的媒体项"""
        try:
            # 记录原始STRM路径
            logger.info(f"开始查找STRM对应的Emby项目: {strm_path}")
            
            # 从STRM文件名提取媒体信息
            media_info = await self.extract_media_name_from_strm(strm_path)
            logger.info(f"从STRM提取的媒体信息: {media_info}")
            
            # 提取STRM文件所在的目录路径，用于分析媒体类型
            strm_dir = os.path.dirname(strm_path)
            logger.info(f"STRM所在目录: {strm_dir}")
            
            # 提取季信息和系列名称
            parent_dir = os.path.dirname(strm_dir)
            season_dir = os.path.basename(strm_dir)
            series_dir = os.path.basename(parent_dir)
            
            logger.info(f"目录层次结构: 系列目录={series_dir}, 季目录={season_dir}")
            
            # 改进剧集媒体信息，使用目录名和文件名
            if media_info.get("type") == "Episode":
                # 使用目录名可能更准确
                series_from_dir = series_dir.split(" (")[0] if " (" in series_dir else series_dir
                logger.info(f"从目录提取的系列名称: {series_from_dir}")
                
                series_name = media_info.get("series_name")
                logger.info(f"使用系列名称: {series_name} (从文件名) vs {series_from_dir} (从目录)")
                
                # 检查从文件名提取的系列名称是否可能不准确
                if len(series_name) < 4 and len(series_from_dir) > len(series_name):
                    logger.info(f"文件名中的系列名称可能不准确，改用目录名: {series_from_dir}")
                    series_name = series_from_dir
                    media_info["series_name"] = series_from_dir
            
            # 根据媒体类型使用不同的查找策略
            if media_info.get("type") == "Episode":
                # 查找剧集
                if media_info.get("series_name"):
                    logger.info(f"尝试查找系列: {media_info.get('series_name')}")
                    episode = await self.find_episode_by_info(
                        media_info.get("series_name", ""),
                        media_info.get("season", 1),
                        media_info.get("episode", 1)
                    )
                    
                    if episode:
                        logger.info(f"成功找到剧集: {episode.get('Name')}")
                        return episode
                    else:
                        logger.warning(f"未找到剧集，尝试使用目录名称查找系列")
                        # 尝试使用目录名称
                        episode = await self.find_episode_by_info(
                            series_from_dir,
                            media_info.get("season", 1),
                            media_info.get("episode", 1)
                        )
                        if episode:
                            logger.info(f"使用目录名成功找到剧集: {episode.get('Name')}")
                            return episode
                else:
                    # 没有具体的剧集信息，尝试搜索名称
                    tv_name = media_info.get("name", "")
                    if tv_name:
                        logger.info(f"没有剧集信息，尝试直接搜索TV名称: {tv_name}")
                        tv_items = await self.search_by_name(tv_name)
                        for item in tv_items:
                            if item.get("Type") in ["Series", "Episode"]:
                                logger.info(f"找到TV项目: {item.get('Name')}")
                                return item
            elif media_info.get("type") == "Movie":
                # 查找电影
                movie_title = media_info.get("title", "") or media_info.get("name", "")
                movie_year = media_info.get("year")
                
                logger.info(f"尝试查找电影: {movie_title} ({movie_year if movie_year else '未知年份'})")
                
                # 通过标题和年份搜索电影
                movie_items = await self.search_by_name(movie_title)
                
                # 过滤匹配项
                for item in movie_items:
                    if item.get("Type") == "Movie" and item.get("Name", "").lower() == movie_title.lower():
                        # 如果有年份，进一步匹配年份
                        if movie_year and item.get("ProductionYear") == movie_year:
                            logger.info(f"找到完全匹配的电影: {item.get('Name')} ({item.get('ProductionYear')})")
                            return item
                
                # 如果没有完全匹配，返回第一个类型为Movie的结果
                for item in movie_items:
                    if item.get("Type") == "Movie":
                        logger.info(f"找到最接近的电影: {item.get('Name')} ({item.get('ProductionYear', '未知')})")
                        return item
            else:
                # 尝试直接搜索
                search_name = media_info.get("name", "")
                logger.info(f"使用文件名直接搜索: {search_name}")
                items = await self.search_by_name(search_name)
                if items:
                    # 返回第一个结果
                    logger.info(f"搜索到结果: {items[0].get('Name')} (类型: {items[0].get('Type')})")
                    return items[0]
            
            # 旧的查找方法作为备选
            emby_path = self.convert_to_emby_path(strm_path)
            if emby_path:
                logger.info(f"使用路径转换结果查找: {strm_path} -> {emby_path}")
                item = await self.query_item_by_path(emby_path)
                if item:
                    logger.info(f"通过路径找到Emby项目: {strm_path} -> {item.get('Id')}")
                    return item
            
            logger.warning(f"无法找到Emby项目: {strm_path}")
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
            
            # 构建API URL
            url = f"{self.emby_url}/Items/{item_id}/Refresh"
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
                    logger.info(f"成功刷新Emby项目: {item_id}")
                    return True
                else:
                    logger.error(f"刷新Emby项目失败: {item_id}, 状态码: {response.status_code}, 响应: {response.text[:200]}")
            
            return False
        except Exception as e:
            logger.error(f"刷新Emby项目失败: {item_id}, 错误: {str(e)}")
            return False
    
    async def process_refresh_queue(self):
        """处理刷新队列，刷新到期的项目"""
        # 如果Emby功能未启用，不处理队列
        if not self.emby_enabled:
            return
            
        if self._is_processing:
            logger.debug("刷新任务已在运行中")
            return
        
        try:
            self._is_processing = True
            current_time = time.time()
            processed_items = []
            success_count = 0
            failed_count = 0
            refreshed_items = []  # 记录成功刷新的项目
            
            # 获取需要处理的项目数量
            pending_items = [item for item in self.refresh_queue 
                            if item.timestamp <= current_time 
                            and (item.status not in ["success", "failed"] 
                                 or (item.status == "failed" and item.retry_count < self.max_retries))]
            
            if not pending_items:
                self._is_processing = False
                return
                
            # 发送开始处理的通知
            service_manager = self._get_service_manager()
            if pending_items:
                start_msg = f"🔄 开始刷新Emby媒体库，共有 {len(pending_items)} 个项目待处理"
                logger.info(start_msg)
                try:
                    if service_manager.telegram_service:
                        await service_manager.telegram_service.send_message(start_msg)
                except Exception as e:
                    logger.error(f"发送通知失败: {str(e)}")
            
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
                            item_name = emby_item.get("Name", "未知项目")
                            item.item_id = item_id
                            
                            logger.info(f"开始刷新Emby项目: {item_name} (ID: {item_id})")
                            
                            success = await self.refresh_emby_item(item_id)
                            
                            if success:
                                item.status = "success"
                                success_count += 1
                                refreshed_items.append(f"✅ {item_name}")
                                logger.info(f"成功刷新项目: {item.strm_path} -> {item_id} ({item_name})")
                            else:
                                # 刷新失败，安排重试
                                item.status = "failed"
                                item.last_error = "刷新API调用失败"
                                item.retry_count += 1
                                failed_count += 1
                                
                                if item.retry_count < self.max_retries:
                                    delay = self.retry_delays[min(item.retry_count, len(self.retry_delays) - 1)]
                                    item.timestamp = current_time + delay
                                    logger.info(f"安排重试刷新: {item.strm_path}, 重试次数: {item.retry_count}, 延迟: {delay}秒")
                        else:
                            # 未找到项目，安排重试
                            item.status = "failed"
                            item.last_error = "未找到Emby项目"
                            item.retry_count += 1
                            failed_count += 1
                            
                            if item.retry_count < self.max_retries:
                                delay = self.retry_delays[min(item.retry_count, len(self.retry_delays) - 1)]
                                item.timestamp = current_time + delay
                                logger.info(f"未找到项目，安排重试: {item.strm_path}, 重试次数: {item.retry_count}, 延迟: {delay}秒")
                    
                    except Exception as e:
                        # 处理过程中的错误
                        item.status = "failed"
                        item.last_error = str(e)
                        item.retry_count += 1
                        failed_count += 1
                        
                        if item.retry_count < self.max_retries:
                            delay = self.retry_delays[min(item.retry_count, len(self.retry_delays) - 1)]
                            item.timestamp = current_time + delay
                            logger.error(f"处理刷新项目时出错: {item.strm_path}, 错误: {str(e)}")
                    
                    processed_items.append(item)
                    await asyncio.sleep(1)  # 防止API调用过于频繁
            
            # 保存队列
            if processed_items:
                self._save_refresh_queue()
                logger.info(f"已处理 {len(processed_items)} 个刷新项目，成功: {success_count}，失败: {failed_count}")
                
                # 发送处理结果通知
                if service_manager.telegram_service:
                    summary_msg = f"📊 Emby刷库完成\n成功: {success_count} 个\n失败: {failed_count} 个"
                    
                    # 如果成功刷新了项目，添加到通知
                    if refreshed_items:
                        # 如果项目太多，只显示前10个
                        if len(refreshed_items) > 10:
                            refreshed_info = "\n".join(refreshed_items[:10]) + f"\n...等共 {len(refreshed_items)} 个项目"
                        else:
                            refreshed_info = "\n".join(refreshed_items)
                        
                        summary_msg += f"\n\n刷新的项目:\n{refreshed_info}"
                    
                    await service_manager.telegram_service.send_message(summary_msg)
            
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
        # 如果Emby功能未启用，不启动任务
        if not self.emby_enabled:
            logger.info("Emby刷库功能未启用，不启动刷新任务")
            return
            
        logger.info("启动Emby刷新任务")
        self._stop_flag = False
        
        while not self._stop_flag:
            await self.process_refresh_queue()
            await asyncio.sleep(60)  # 每分钟检查一次队列
    
    def stop_refresh_task(self):
        """停止刷新任务"""
        logger.info("停止Emby刷新任务")
        self._stop_flag = True 

    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager 