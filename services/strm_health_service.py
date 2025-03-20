import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import importlib

logger = logging.getLogger(__name__)

class StrmHealthService:
    """STRM健康状态服务
    
    用于管理和维护STRM文件的健康状态信息
    """
    def __init__(self):
        """初始化STRM健康状态服务"""
        self._settings = None
        self._health_data = {
            "lastFullScanTime": 0,
            "strmFiles": {},
            "videoFiles": {}
        }
        self._health_file = "data/strm_health.json"
        self._is_loaded = False
        
    @property
    def settings(self):
        """获取配置"""
        if self._settings is None:
            from config import Settings
            self._settings = Settings()
        return self._settings
        
    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager
    
    def load_health_data(self) -> bool:
        """从JSON文件加载健康状态数据"""
        if self._is_loaded:
            return True
            
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self._health_file), exist_ok=True)
            
            if os.path.exists(self._health_file):
                with open(self._health_file, 'r', encoding='utf-8') as f:
                    self._health_data = json.load(f)
                logger.info(f"已加载STRM健康状态数据，包含 {len(self._health_data.get('strmFiles', {}))} 个STRM文件和 {len(self._health_data.get('videoFiles', {}))} 个视频文件")
                self._is_loaded = True
                return True
            else:
                logger.info("STRM健康状态数据文件不存在，将使用空数据")
                self._is_loaded = True
                return False
        except Exception as e:
            logger.error(f"加载STRM健康状态数据失败: {str(e)}")
            return False
    
    def save_health_data(self) -> bool:
        """保存健康状态数据到JSON文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self._health_file), exist_ok=True)
            
            with open(self._health_file, 'w', encoding='utf-8') as f:
                json.dump(self._health_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存STRM健康状态数据，包含 {len(self._health_data.get('strmFiles', {}))} 个STRM文件和 {len(self._health_data.get('videoFiles', {}))} 个视频文件")
            return True
        except Exception as e:
            logger.error(f"保存STRM健康状态数据失败: {str(e)}")
            return False
    
    def get_strm_status(self, strm_path: str) -> Dict:
        """获取STRM文件的健康状态"""
        self.load_health_data()
        return self._health_data.get("strmFiles", {}).get(strm_path, {
            "targetPath": None,
            "lastCheckTime": 0,
            "status": "unknown",
            "issueDetails": None
        })
    
    def get_video_status(self, video_path: str) -> Dict:
        """获取视频文件的健康状态"""
        self.load_health_data()
        return self._health_data.get("videoFiles", {}).get(video_path, {
            "hasStrm": False,
            "strmPath": None,
            "lastCheckTime": 0
        })
    
    def update_strm_status(self, strm_path: str, status: Dict) -> None:
        """更新STRM文件的健康状态"""
        self.load_health_data()
        if "strmFiles" not in self._health_data:
            self._health_data["strmFiles"] = {}
        
        # 获取现有状态或创建新状态
        current_status = self._health_data["strmFiles"].get(strm_path, {})
        
        # 如果状态从有效变为无效，记录首次检测时间
        if current_status.get("status") == "valid" and status.get("status") == "invalid":
            status["firstDetectedAt"] = time.time()
        
        # 更新现有状态
        current_status.update(status)
        
        # 更新最后检查时间
        current_status["lastCheckTime"] = time.time()
        
        # 保存回数据
        self._health_data["strmFiles"][strm_path] = current_status
    
    def update_video_status(self, video_path: str, status: Dict) -> None:
        """更新视频文件的健康状态"""
        self.load_health_data()
        if "videoFiles" not in self._health_data:
            self._health_data["videoFiles"] = {}
        
        # 获取现有状态或创建新状态
        current_status = self._health_data["videoFiles"].get(video_path, {})
        
        # 如果状态从有STRM变为没有STRM，记录首次检测时间
        if current_status.get("hasStrm") == True and status.get("hasStrm") == False:
            status["firstDetectedAt"] = time.time()
        
        # 更新现有状态
        current_status.update(status)
        
        # 更新最后检查时间
        current_status["lastCheckTime"] = time.time()
        
        # 保存回数据
        self._health_data["videoFiles"][video_path] = current_status
    
    def update_last_full_scan_time(self, scan_time: Optional[float] = None) -> None:
        """更新最后完整扫描时间"""
        self.load_health_data()
        self._health_data["lastFullScanTime"] = scan_time or time.time()
    
    def get_last_full_scan_time(self) -> float:
        """获取最后完整扫描时间"""
        self.load_health_data()
        return self._health_data.get("lastFullScanTime", 0)
    
    def get_all_invalid_strm_files(self) -> List[Dict]:
        """获取所有无效的STRM文件"""
        self.load_health_data()
        invalid_files = []
        
        for strm_path, status in self._health_data.get("strmFiles", {}).items():
            if status.get("status") == "invalid":
                invalid_files.append({
                    "path": strm_path,
                    "targetPath": status.get("targetPath"),
                    "issueDetails": status.get("issueDetails"),
                    "lastCheckTime": status.get("lastCheckTime"),
                    "firstDetectedAt": status.get("firstDetectedAt", status.get("lastCheckTime"))
                })
        
        return invalid_files
    
    def get_all_missing_strm_files(self) -> List[Dict]:
        """获取所有缺失STRM的视频文件"""
        self.load_health_data()
        missing_files = []
        
        for video_path, status in self._health_data.get("videoFiles", {}).items():
            if not status.get("hasStrm"):
                missing_files.append({
                    "path": video_path,
                    "lastCheckTime": status.get("lastCheckTime"),
                    "firstDetectedAt": status.get("firstDetectedAt", status.get("lastCheckTime"))
                })
        
        return missing_files
    
    def remove_strm_file(self, strm_path: str) -> None:
        """从健康状态数据中移除STRM文件"""
        self.load_health_data()
        if "strmFiles" in self._health_data and strm_path in self._health_data["strmFiles"]:
            # 获取目标视频路径
            target_path = self._health_data["strmFiles"][strm_path].get("targetPath")
            
            # 删除STRM文件记录
            del self._health_data["strmFiles"][strm_path]
            
            # 如果有对应的视频文件记录，也更新它的状态
            if target_path and "videoFiles" in self._health_data and target_path in self._health_data["videoFiles"]:
                self._health_data["videoFiles"][target_path]["hasStrm"] = False
                self._health_data["videoFiles"][target_path]["strmPath"] = None
    
    def add_strm_file(self, strm_path: str, video_path: str) -> None:
        """添加STRM文件和对应的视频文件记录"""
        self.load_health_data()
        
        # 更新STRM文件状态
        self.update_strm_status(strm_path, {
            "targetPath": video_path,
            "status": "valid",
            "issueDetails": None
        })
        
        # 更新视频文件状态
        self.update_video_status(video_path, {
            "hasStrm": True,
            "strmPath": strm_path
        })
    
    def clear_data(self) -> None:
        """清空健康状态数据"""
        self._health_data = {
            "lastFullScanTime": 0,
            "strmFiles": {},
            "videoFiles": {}
        }
        self.save_health_data()
    
    def get_stats(self) -> Dict:
        """获取健康状态统计信息"""
        self.load_health_data()
        
        total_strm = len(self._health_data.get("strmFiles", {}))
        invalid_strm = len([s for s in self._health_data.get("strmFiles", {}).values() if s.get("status") == "invalid"])
        
        total_videos = len(self._health_data.get("videoFiles", {}))
        missing_strm = len([v for v in self._health_data.get("videoFiles", {}).values() if not v.get("hasStrm")])
        
        return {
            "lastFullScanTime": self._health_data.get("lastFullScanTime", 0),
            "totalStrmFiles": total_strm,
            "invalidStrmFiles": invalid_strm,
            "totalVideoFiles": total_videos,
            "missingStrmFiles": missing_strm
        } 