import os
import json
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import webbrowser
from config import Settings

logger = logging.getLogger(__name__)

class StrmAssistantService:
    """TMDB元数据助手服务，用于管理和操作TMDB元数据缓存"""
    
    def __init__(self):
        """初始化TMDB元数据助手服务"""
        # 初始化变量
        self.settings = Settings()
        self.cache_path = self.settings.tmdb_cache_dir
        self.all_items = {
            "tmdb-tv": {},
            "tmdb-movies2": {},
            "tmdb-collections": {}
        }
        
        # 确保缓存目录存在
        if self.cache_path:
            os.makedirs(self.cache_path, exist_ok=True)
            logger.info(f"已设置缓存目录: {self.cache_path}")
    
    def set_cache_directory(self, cache_path: str) -> bool:
        """设置缓存目录路径
        
        Args:
            cache_path: 缓存目录的路径
            
        Returns:
            bool: 设置是否成功
        """
        if not os.path.exists(cache_path):
            logger.warning(f"缓存目录不存在: {cache_path}")
            return False
            
        self.cache_path = cache_path
        logger.info(f"已设置缓存目录: {self.cache_path}")
        return True
    
    def load_all_metadata(self) -> Dict[str, int]:
        """加载所有元数据
        
        Returns:
            Dict[str, int]: 各类型的项目数量
        """
        if not self.cache_path:
            logger.error("未设置缓存目录，无法加载元数据")
            return {"tmdb-tv": 0, "tmdb-movies2": 0, "tmdb-collections": 0}
        
        # 初始化搜索缓存
        self.all_items = {
            "tmdb-tv": {},
            "tmdb-movies2": {},
            "tmdb-collections": {}
        }
        
        # 加载各类型数据
        tv_count = self.load_type_metadata("tmdb-tv")
        movie_count = self.load_type_metadata("tmdb-movies2")
        collection_count = self.load_type_metadata("tmdb-collections")
        
        logger.info(f"加载完成 - 剧集: {tv_count}个, 电影: {movie_count}个, 合集: {collection_count}个")
        
        return {
            "tmdb-tv": tv_count,
            "tmdb-movies2": movie_count,
            "tmdb-collections": collection_count
        }
    
    def load_type_metadata(self, data_type: str) -> int:
        """加载指定类型的元数据
        
        Args:
            data_type: 数据类型 (tmdb-tv, tmdb-movies2, tmdb-collections)
            
        Returns:
            int: 加载的项目数量
        """
        # 构建路径
        type_path = os.path.join(self.cache_path, data_type)
        
        if not os.path.exists(type_path):
            logger.warning(f"类型目录不存在: {type_path}")
            return 0
        
        # 初始化计数器
        item_count = 0
        
        # 遍历目录
        for item in os.listdir(type_path):
            item_path = os.path.join(type_path, item)
            if os.path.isdir(item_path):
                # 尝试加载主JSON文件
                json_file = os.path.join(item_path, "series.json" if data_type == "tmdb-tv" else "movie.json")
                all_json_file = os.path.join(item_path, "all.json")
                data = {}
                
                # 优先尝试加载all.json
                if os.path.exists(all_json_file):
                    try:
                        with open(all_json_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception as e:
                        logger.error(f"加载{all_json_file}时出错: {str(e)}")
                elif os.path.exists(json_file):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception as e:
                        logger.error(f"加载{json_file}时出错: {str(e)}")
                
                # 提取基本信息
                item_id = data.get("id", item)
                name = data.get("title", data.get("name", ""))  # 优先使用title字段
                date_str = data.get("first_air_date", data.get("release_date", ""))
                year = self.format_date(date_str)[:4] if date_str else ""
                
                # 添加到搜索缓存
                item_iid = f"{data_type}_{item_id}"
                self.all_items[data_type][item_iid] = {
                    "name": name,
                    "id": item_id,
                    "year": year,
                    "path": item_path
                }
                
                # 增加计数器
                item_count += 1
        
        return item_count
    
    def format_date(self, date_str: str) -> str:
        """格式化日期，只保留年月日部分
        
        Args:
            date_str: 日期字符串
            
        Returns:
            str: 格式化后的日期字符串
        """
        if not date_str:
            return ""
        
        try:
            # 尝试解析带时间的日期格式
            if "T" in date_str:
                dt = datetime.strptime(date_str.split("T")[0], "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            # 尝试解析简单日期格式
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            return date_str
    
    def search_items(self, search_term: str) -> Dict[str, List[Dict]]:
        """搜索项目
        
        Args:
            search_term: 搜索关键词
            
        Returns:
            Dict[str, List[Dict]]: 按类型分组的搜索结果
        """
        search_term = search_term.lower()
        
        if not search_term:
            # 如果搜索词为空，返回所有项目
            return {
                "tmdb-tv": list(self.all_items["tmdb-tv"].values()),
                "tmdb-movies2": list(self.all_items["tmdb-movies2"].values()),
                "tmdb-collections": list(self.all_items["tmdb-collections"].values())
            }
        
        # 搜索结果
        results = {
            "tmdb-tv": [],
            "tmdb-movies2": [],
            "tmdb-collections": []
        }
        
        # 在每个类型中搜索匹配的项目
        for data_type in ["tmdb-tv", "tmdb-movies2", "tmdb-collections"]:
            for item_id, item_data in self.all_items[data_type].items():
                name = item_data["name"].lower()
                tmdb_id = item_id.split("_")[1]
                
                if search_term in name or search_term in tmdb_id:
                    results[data_type].append(item_data)
        
        return results
    
    def get_item_metadata(self, data_type: str, item_id: str) -> Optional[Dict]:
        """获取项目元数据
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            
        Returns:
            Optional[Dict]: 项目元数据
        """
        # 构建项目路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        
        if not os.path.exists(type_path):
            logger.warning(f"项目路径不存在: {type_path}")
            return None
        
        # 尝试加载JSON文件
        json_file = os.path.join(type_path, "series.json" if data_type == "tmdb-tv" else "movie.json")
        all_json_file = os.path.join(type_path, "all.json")
        data = {}
        
        # 优先尝试加载all.json
        if os.path.exists(all_json_file):
            try:
                with open(all_json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"加载{all_json_file}时出错: {str(e)}")
        elif os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"加载{json_file}时出错: {str(e)}")
        
        if not data:
            logger.warning(f"未找到项目元数据: {data_type}/{item_id}")
            return None
        
        return data
    
    def get_season_metadata(self, data_type: str, item_id: str, season_number: int) -> Optional[Dict]:
        """获取季节元数据
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            season_number: 季号
            
        Returns:
            Optional[Dict]: 季节元数据
        """
        if data_type != "tmdb-tv":
            logger.warning(f"非剧集类型无法获取季节元数据: {data_type}")
            return None
        
        # 构建季节文件路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        season_file = os.path.join(type_path, f"season-{season_number}.json")
        
        if not os.path.exists(season_file):
            logger.warning(f"季节文件不存在: {season_file}")
            return None
        
        # 加载季节数据
        try:
            with open(season_file, "r", encoding="utf-8") as f:
                season_data = json.load(f)
            return season_data
        except Exception as e:
            logger.error(f"加载季节数据出错: {str(e)}")
            return None
    
    def get_episode_metadata(self, data_type: str, item_id: str, season_number: int, episode_number: int) -> Optional[Dict]:
        """获取集元数据
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            season_number: 季号
            episode_number: 集号
            
        Returns:
            Optional[Dict]: 集元数据
        """
        if data_type != "tmdb-tv":
            logger.warning(f"非剧集类型无法获取集元数据: {data_type}")
            return None
        
        # 构建集文件路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        episode_file = os.path.join(type_path, f"season-{season_number}-episode-{episode_number}.json")
        
        if not os.path.exists(episode_file):
            logger.warning(f"集文件不存在: {episode_file}")
            return None
        
        # 加载集数据
        try:
            with open(episode_file, "r", encoding="utf-8") as f:
                episode_data = json.load(f)
            return episode_data
        except Exception as e:
            logger.error(f"加载集数据出错: {str(e)}")
            return None
    
    def get_seasons(self, data_type: str, item_id: str) -> List[Dict]:
        """获取项目的所有季节信息
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            
        Returns:
            List[Dict]: 季节信息列表
        """
        if data_type != "tmdb-tv":
            logger.warning(f"非剧集类型无法获取季节信息: {data_type}")
            return []
        
        # 构建路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        
        if not os.path.exists(type_path):
            logger.warning(f"项目路径不存在: {type_path}")
            return []
        
        # 查找所有季文件
        season_files = [f for f in os.listdir(type_path) if f.startswith("season-") and f.endswith(".json") and "-episode-" not in f]
        
        seasons = []
        
        for season_file in season_files:
            try:
                season_number = int(season_file.split("-")[1].split(".")[0])
                season_path = os.path.join(type_path, season_file)
                
                with open(season_path, "r", encoding="utf-8") as f:
                    season_data = json.load(f)
                
                seasons.append({
                    "season_number": season_number,
                    "name": season_data.get("name", f"第{season_number}季"),
                    "episode_count": season_data.get("episode_count", 0),
                    "air_date": season_data.get("air_date", ""),
                    "id": season_data.get("id", "")
                })
            except Exception as e:
                logger.error(f"加载季节信息出错: {str(e)}")
        
        # 按季号排序
        seasons.sort(key=lambda x: x["season_number"])
        return seasons
    
    def get_episodes(self, data_type: str, item_id: str, season_number: int) -> List[Dict]:
        """获取指定季的所有集信息
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            season_number: 季号
            
        Returns:
            List[Dict]: 集信息列表
        """
        if data_type != "tmdb-tv":
            logger.warning(f"非剧集类型无法获取集信息: {data_type}")
            return []
        
        # 构建路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        
        if not os.path.exists(type_path):
            logger.warning(f"项目路径不存在: {type_path}")
            return []
        
        # 查找指定季的所有集文件
        episode_files = [f for f in os.listdir(type_path) 
                      if f.startswith(f"season-{season_number}-episode-") and f.endswith(".json")]
        
        episodes = []
        
        for episode_file in episode_files:
            try:
                episode_number = int(episode_file.split("-")[3].split(".")[0])
                episode_path = os.path.join(type_path, episode_file)
                
                with open(episode_path, "r", encoding="utf-8") as f:
                    episode_data = json.load(f)
                
                episodes.append({
                    "episode_number": episode_number,
                    "name": episode_data.get("name", f"第{episode_number}集"),
                    "air_date": episode_data.get("air_date", ""),
                    "id": episode_data.get("id", ""),
                    "overview": episode_data.get("overview", "")
                })
            except Exception as e:
                logger.error(f"加载集信息出错: {str(e)}")
        
        # 按集号排序
        episodes.sort(key=lambda x: x["episode_number"])
        return episodes
    
    def delete_item(self, data_type: str, item_id: str) -> bool:
        """删除项目
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            
        Returns:
            bool: 是否删除成功
        """
        # 构建项目路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        
        if not os.path.exists(type_path):
            logger.warning(f"项目路径不存在: {type_path}")
            return False
        
        try:
            # 删除目录及其内容
            shutil.rmtree(type_path)
            
            # 从搜索缓存中删除
            item_iid = f"{data_type}_{item_id}"
            if data_type in self.all_items and item_iid in self.all_items[data_type]:
                del self.all_items[data_type][item_iid]
            
            logger.info(f"成功删除项目: {data_type}/{item_id}")
            return True
        except Exception as e:
            logger.error(f"删除项目失败: {str(e)}")
            return False
    
    def delete_season(self, data_type: str, item_id: str, season_number: int) -> bool:
        """删除季节
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            season_number: 季号
            
        Returns:
            bool: 是否删除成功
        """
        if data_type != "tmdb-tv":
            logger.warning(f"非剧集类型无法删除季节: {data_type}")
            return False
        
        # 构建项目路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        
        if not os.path.exists(type_path):
            logger.warning(f"项目路径不存在: {type_path}")
            return False
        
        try:
            # 删除季文件
            season_file = os.path.join(type_path, f"season-{season_number}.json")
            if os.path.exists(season_file):
                os.remove(season_file)
            
            # 删除所有集文件
            for f in os.listdir(type_path):
                if f.startswith(f"season-{season_number}-episode-") and f.endswith(".json"):
                    os.remove(os.path.join(type_path, f))
            
            logger.info(f"成功删除季节: {data_type}/{item_id}/第{season_number}季")
            return True
        except Exception as e:
            logger.error(f"删除季节失败: {str(e)}")
            return False
    
    def delete_episode(self, data_type: str, item_id: str, season_number: int, episode_number: int) -> bool:
        """删除集
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            season_number: 季号
            episode_number: 集号
            
        Returns:
            bool: 是否删除成功
        """
        if data_type != "tmdb-tv":
            logger.warning(f"非剧集类型无法删除集: {data_type}")
            return False
        
        # 构建项目路径
        type_path = os.path.join(self.cache_path, data_type, item_id)
        
        if not os.path.exists(type_path):
            logger.warning(f"项目路径不存在: {type_path}")
            return False
        
        try:
            # 删除集文件
            episode_file = os.path.join(type_path, f"season-{season_number}-episode-{episode_number}.json")
            if os.path.exists(episode_file):
                os.remove(episode_file)
                logger.info(f"成功删除集: {data_type}/{item_id}/第{season_number}季/第{episode_number}集")
                return True
            else:
                logger.warning(f"集文件不存在: {episode_file}")
                return False
        except Exception as e:
            logger.error(f"删除集失败: {str(e)}")
            return False
    
    def get_tmdb_url(self, data_type: str, item_id: str) -> str:
        """获取TMDB网站URL
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            
        Returns:
            str: TMDB网站URL
        """
        if data_type == "tmdb-tv":
            return f"https://www.themoviedb.org/tv/{item_id}"
        elif data_type == "tmdb-movies2":
            return f"https://www.themoviedb.org/movie/{item_id}"
        elif data_type == "tmdb-collections":
            return f"https://www.themoviedb.org/collection/{item_id}"
        else:
            return f"https://www.themoviedb.org/movie/{item_id}"
    
    def open_tmdb_in_browser(self, data_type: str, item_id: str) -> bool:
        """在浏览器中打开TMDB页面
        
        Args:
            data_type: 数据类型
            item_id: 项目ID
            
        Returns:
            bool: 是否成功打开
        """
        url = self.get_tmdb_url(data_type, item_id)
        try:
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"在浏览器中打开TMDB URL失败: {str(e)}")
            return False
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息
        
        Returns:
            Dict[str, int]: 缓存统计信息
        """
        stats = {
            "total": 0,
            "tmdb-tv": 0,
            "tmdb-movies2": 0,
            "tmdb-collections": 0
        }
        
        for data_type in ["tmdb-tv", "tmdb-movies2", "tmdb-collections"]:
            stats[data_type] = len(self.all_items[data_type])
            stats["total"] += stats[data_type]
        
        return stats 