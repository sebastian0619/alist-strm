from pathlib import Path
import shutil
import time
import hashlib
from datetime import datetime
import os
from typing import NamedTuple, Optional, List, Dict, Tuple
from loguru import logger
from config import Settings
import asyncio
import importlib
import json

class MediaThreshold(NamedTuple):
    """媒体文件的时间阈值配置"""
    creation_days: int
    mtime_days: int

class ArchiveService:
    def __init__(self):
        self.settings = Settings()
        self._stop_flag = False
        self._is_running = False
        
        # 从配置加载视频文件扩展名
        self.video_extensions = set(
            ext.strip() for ext in self.settings.archive_video_extensions.split(',')
        )
        
        # 从文件加载媒体类型配置
        self.media_types = self._load_media_types()
        self.thresholds = {
            name: MediaThreshold(
                info["creation_days"],
                info["mtime_days"]
            ) for name, info in self.media_types.items()
        }
    
    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager
    
    def get_creation_time(self, path: Path) -> float:
        """获取文件或目录的创建时间"""
        try:
            stat = path.stat()
            return getattr(stat, 'st_birthtime', stat.st_mtime)
        except Exception as e:
            logger.error(f"获取创建时间失败 {path}: {e}")
            return time.time()
    
    def get_media_type(self, path: Path) -> str:
        """根据路径判断媒体类型"""
        path_str = str(path)
        for media_type, info in self.media_types.items():
            if f"/{info['dir']}/" in path_str:
                return media_type
        return ""
    
    def calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """计算文件的MD5哈希值"""
        try:
            md5_hash = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    def verify_files(self, source: Path, dest: Path) -> bool:
        """验证源文件和目标文件是否相同"""
        try:
            if not source.exists() or not dest.exists():
                return False
            
            source_hash = self.calculate_file_hash(source)
            dest_hash = self.calculate_file_hash(dest)
            
            return source_hash and dest_hash and source_hash == dest_hash
        except Exception as e:
            logger.error(f"文件验证失败: {e}")
            return False
    
    async def has_recent_files(self, directory: Path, mtime_threshold: int) -> Tuple[bool, List[Path]]:
        """检查目录中是否有最近修改的视频文件"""
        recent_files = []
        try:
            for file_path in directory.rglob("*"):
                if self._stop_flag:
                    break
                    
                if file_path.is_file() and file_path.suffix.lower() in self.video_extensions:
                    mtime = file_path.stat().st_mtime
                    age_days = (time.time() - mtime) / 86400
                    if age_days < mtime_threshold:
                        recent_files.append(file_path)
                        
                # 让出控制权
                await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"检查最近文件失败: {e}")
            
        return bool(recent_files), recent_files
    
    def stop(self):
        """停止归档处理"""
        if not self._is_running:
            return
        self._stop_flag = True
        logger.info("收到停止信号，正在停止归档...")
    
    async def process_directory(self, directory: Path) -> Dict:
        """处理单个目录的归档"""
        result = {
            "success": False,
            "message": "",
            "moved_files": 0,
            "total_size": 0
        }
        
        try:
            media_type = self.get_media_type(directory)
            if not media_type or media_type not in self.thresholds:
                result["message"] = f"未知的媒体类型: {directory}"
                return result

            threshold = self.thresholds[media_type]
            creation_time = self.get_creation_time(directory)
            age_days = (time.time() - creation_time) / 86400

            if age_days < threshold.creation_days:
                result["message"] = f"[跳过] {media_type}: {directory.name} (创建时间 {age_days:.1f}天 < {threshold.creation_days}天)"
                return result

            has_recent, recent_files = await self.has_recent_files(directory, threshold.mtime_days)
            if has_recent:
                example_files = [f.name for f in recent_files[:2]]
                result["message"] = f"[跳过] {media_type}: {directory.name} (存在近期文件，如: {', '.join(example_files)})"
                return result

            # 准备归档
            source_dir = Path(self.settings.archive_source_dir)
            target_dir = Path(self.settings.archive_target_dir)
            relative_path = directory.relative_to(source_dir)
            destination = target_dir / relative_path
            
            # 创建目标目录
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # 复制或移动文件
            if self.settings.archive_delete_source:
                # 如果需要删除源文件，先复制再验证
                shutil.copytree(str(directory), str(destination), dirs_exist_ok=True)
                
                # 验证所有文件
                all_verified = True
                for src_file in directory.rglob("*"):
                    if src_file.is_file():
                        dst_file = destination / src_file.relative_to(directory)
                        if not self.verify_files(src_file, dst_file):
                            all_verified = False
                            break
                        result["total_size"] += src_file.stat().st_size
                        result["moved_files"] += 1
                
                if all_verified:
                    # 验证成功后删除源文件
                    shutil.rmtree(str(directory))
                    result["message"] = f"[归档] {media_type}: {directory.name} -> {destination.name} (已验证并删除源文件)"
                else:
                    result["message"] = f"[错误] {media_type}: {directory.name} 文件验证失败"
                    return result
            else:
                # 如果不需要删除源文件，直接复制
                shutil.copytree(str(directory), str(destination), dirs_exist_ok=True)
                for src_file in directory.rglob("*"):
                    if src_file.is_file():
                        result["total_size"] += src_file.stat().st_size
                        result["moved_files"] += 1
                result["message"] = f"[归档] {media_type}: {directory.name} -> {destination.name}"
            
            result["success"] = True
            
        except Exception as e:
            result["message"] = f"[错误] 归档失败 {directory.name}: {str(e)}"
            logger.error(f"处理目录失败 {directory}: {e}")
            
        return result
    
    async def archive(self):
        """执行归档处理"""
        if self._is_running:
            logger.warning("归档任务已在运行中")
            return
            
        try:
            self._stop_flag = False
            self._is_running = True
            
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message("🚀 开始归档处理...")
            
            source_dir = Path(self.settings.archive_source_dir)
            total_processed = 0
            total_size = 0
            
            patterns = [
                "电视剧/*/*",
                "动漫/完结动漫/*",
                "电影/*/*",
                "综艺/*"
            ]
            
            for pattern in patterns:
                if self._stop_flag:
                    break
                    
                directories = list(source_dir.glob(pattern))
                if directories:
                    logger.info(f"\n处理类型: {pattern}")
                    await service_manager.telegram_service.send_message(f"📂 处理类型: {pattern}")
                    
                    for directory in directories:
                        if self._stop_flag:
                            break
                            
                        if directory.is_dir() and not str(directory).startswith(str(self.settings.archive_target_dir)):
                            result = await self.process_directory(directory)
                            if result["success"]:
                                total_processed += result["moved_files"]
                                total_size += result["total_size"]
                            await service_manager.telegram_service.send_message(result["message"])
                            
                        # 让出控制权
                        await asyncio.sleep(0)
            
            summary = (
                f"✅ 归档完成\n"
                f"📁 处理文件: {total_processed} 个\n"
                f"💾 总大小: {total_size / 1024 / 1024:.2f} MB"
            )
            logger.info(summary)
            await service_manager.telegram_service.send_message(summary)
            
            # 如果配置了自动运行STRM扫描
            if self.settings.archive_auto_strm and total_processed > 0:
                logger.info("开始自动STRM扫描...")
                await service_manager.telegram_service.send_message("🔄 开始自动STRM扫描...")
                await service_manager.strm_service.strm()
            
        except Exception as e:
            error_msg = f"❌ 归档处理出错: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
            raise
        finally:
            self._is_running = False
            self._stop_flag = False 

    def _load_media_types(self) -> Dict[str, Dict]:
        """从config/archive.json加载媒体类型配置"""
        config_file = "config/archive.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载媒体类型配置失败: {e}")
        return json.loads(self.settings.archive_media_types)

    def save_media_types(self):
        """保存媒体类型配置到config/archive.json"""
        config_file = "config/archive.json"
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.media_types, f, ensure_ascii=False, indent=4)
            logger.info("媒体类型配置已保存")
        except Exception as e:
            logger.error(f"保存媒体类型配置失败: {e}") 