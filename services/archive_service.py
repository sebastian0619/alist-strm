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
from services.alist_client import AlistClient
import re
from urllib.parse import quote

SEASON_DIR_PATTERN = re.compile(r'(?i)season\s*\d+|s\d+|第.+?季')

class MediaThreshold(NamedTuple):
    """媒体文件的时间阈值配置"""
    creation_days: int
    mtime_days: int

class ArchiveService:
    def __init__(self):
        self.settings = Settings()
        self._stop_flag = False
        self._is_running = False
        self._current_media_type = None  # 当前处理的媒体类型
        
        # 添加日志历史记录列表
        self.logger_history = []
        # 添加日志处理器
        self._setup_logger_handler()
        
        # 从配置加载要排除的文件扩展名
        self.excluded_extensions = set(
            ext.strip().lower() for ext in self.settings.archive_excluded_extensions.split(',')
        )
        
        # 从文件加载媒体类型配置
        self._media_types = self._load_media_types()
        # 初始化阈值配置
        self.thresholds = {
            name: MediaThreshold(
                info["creation_days"],
                info["mtime_days"]
            ) for name, info in self._media_types.items()
        }
        
        # 定义待删除文件列表的JSON文件路径
        self._pending_deletions_file = os.path.join("/app/cache", "pending_deletions.json")
        # 初始化待删除文件队列
        self._pending_deletions = self._load_pending_deletions()
        # 删除延迟时间（秒）- 从配置中读取
        self._deletion_delay = self.settings.archive_delete_delay_days * 24 * 3600  # 转换为秒
        
        # 初始化AlistClient
        self.alist_client = AlistClient(
            self.settings.alist_url,
            self.settings.alist_token
        )
        
        # 删除检查任务将在initialize方法中启动
        self._deletion_check_task = None

    def _normalize_cloud_path(self, cloud_path: str) -> str:
        normalized = cloud_path.replace('\\', '/')
        normalized = normalized.rstrip('/')
        return normalized

    def _relative_cloud_path(self, cloud_path: str) -> str:
        normalized = self._normalize_cloud_path(cloud_path)
        prefix = self.settings.alist_scan_path.rstrip('/')
        if normalized.startswith(prefix):
            return normalized[len(prefix):].lstrip('/')
        return normalized.lstrip('/')

    def _archive_target_paths(self, cloud_path: str) -> dict | None:
        relative = self._relative_cloud_path(cloud_path)
        if not relative:
            return None
        target_dir = self.settings.alist_scan_path.rstrip('/')
        archive_base = os.path.join(target_dir, 'archive')
        archive_path = os.path.join(archive_base, relative)
        season_dir = bool(SEASON_DIR_PATTERN.search(relative))
        return {
            'cloud_path': self._normalize_cloud_path(cloud_path),
            'relative': relative,
            'archive_path': archive_path,
            'season_dir': season_dir
        }

    def _local_relative_path(self, path: Path) -> Path:
        """计算路径相对于归档源目录的相对路径。"""
        source_root = Path(self.settings.archive_source_root)
        try:
            return path.relative_to(source_root)
        except ValueError:
            rel_str = str(path)
            source_str = str(source_root)
            if rel_str.startswith(source_str):
                return Path(rel_str[len(source_str):].lstrip('/'))
            raise

    def _build_archive_paths_from_relative(self, relative_path: Path) -> dict:
        """基于相对路径统一构建本地显示路径和 Alist 源/目标路径。"""
        rel_path_str = str(relative_path).replace('\\', '/').lstrip('/')

        source_alist = self.settings.archive_source_alist.rstrip('/')
        target_root = self.settings.archive_target_root.rstrip('/')

        source_alist_path = f"{source_alist}/{rel_path_str}".replace('\\', '/').lstrip("/")
        dest_alist_path = f"{target_root}/{rel_path_str}".replace('\\', '/').lstrip("/")

        return {
            "relative_path": relative_path,
            "relative_str": rel_path_str,
            "dest_path": Path(self.settings.archive_target_root) / relative_path,
            "source_alist_path": source_alist_path,
            "dest_alist_path": dest_alist_path,
            "season_dir": bool(SEASON_DIR_PATTERN.search(rel_path_str)),
        }

    def _season_archive_candidate(self, directory: Path, media_root: Path) -> Path:
        """如果目录位于某一季中，则统一返回季目录作为归档候选。"""
        current = directory
        while current != media_root and current != current.parent:
            if SEASON_DIR_PATTERN.search(current.name):
                return current
            current = current.parent
        if current == media_root and SEASON_DIR_PATTERN.search(current.name):
            return current
        return directory


    def refresh_settings(self):
        """重新加载运行时配置。"""
        self.settings = Settings()
        self.excluded_extensions = set(
            ext.strip().lower() for ext in self.settings.archive_excluded_extensions.split(',')
        )
        self._deletion_delay = self.settings.archive_delete_delay_days * 24 * 3600
    
    def _load_pending_deletions(self) -> list:
        """从JSON文件加载待删除列表"""
        try:
            # 确保cache目录存在
            os.makedirs("/app/cache", exist_ok=True)
            if os.path.exists(self._pending_deletions_file):
                with open(self._pending_deletions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 转换路径字符串回Path对象
                    for item in data:
                        if 'path' in item and isinstance(item['path'], str):
                            item['path'] = Path(item['path'])
                    logger.info(f"从 {self._pending_deletions_file} 加载了 {len(data)} 个待删除项目")
                    return data
            else:
                logger.info(f"待删除文件列表不存在: {self._pending_deletions_file}")
        except Exception as e:
            logger.error(f"加载待删除列表失败: {e}")
        return []
    
    def _save_pending_deletions(self):
        """将待删除列表保存到JSON文件"""
        try:
            # 确保cache目录存在
            os.makedirs("/app/cache", exist_ok=True)
            
            # 将Path对象转换为字符串以便JSON序列化
            data_to_save = []
            for item in self._pending_deletions:
                data_item = item.copy()
                if 'path' in data_item and isinstance(data_item['path'], Path):
                    data_item['path'] = str(data_item['path'])
                data_to_save.append(data_item)
                
            with open(self._pending_deletions_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            logger.info(f"成功保存 {len(data_to_save)} 个待删除项目到 {self._pending_deletions_file}")
        except Exception as e:
            logger.error(f"保存待删除列表失败: {e}")
    
    def _setup_logger_handler(self):
        """设置日志处理器，记录日志历史"""
        class LoggerHistoryHandler:
            def __init__(self, history_list):
                self.history_list = history_list
                
            def write(self, record):
                # 修复：处理不同类型的record
                if isinstance(record, dict) and "message" in record:
                    # 旧格式，保持兼容
                    message = record["message"]
                else:
                    # 新格式，record直接是消息字符串
                    message = str(record)
                    
                self.history_list.append(message)
                # 保持日志历史在一个合理的大小
                if len(self.history_list) > 1000:
                    self.history_list.pop(0)
        
        # 添加自定义处理器到logger
        logger.add(LoggerHistoryHandler(self.logger_history).write)
    
    async def initialize(self):
        """初始化服务，启动后台任务"""
        if not self._deletion_check_task:
            self._deletion_check_task = asyncio.create_task(self._check_pending_deletions())
    
    async def shutdown(self):
        """关闭服务，清理资源"""
        if self._deletion_check_task:
            self._deletion_check_task.cancel()
            try:
                await self._deletion_check_task
            except asyncio.CancelledError:
                pass
            self._deletion_check_task = None
        
        if self.alist_client:
            await self.alist_client.close()
    
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
        """检查目录中是否有最近修改的文件（排除指定扩展名）"""
        recent_files = []
        try:
            for file_path in directory.rglob("*"):
                if self._stop_flag:
                    break
                    
                if file_path.is_file() and file_path.suffix.lower() not in self.excluded_extensions:
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
    
    async def _check_pending_deletions(self):
        """定期检查待删除文件，删除超过延迟时间的文件"""
        logger.info("待删除文件检查任务已启动")
        
        # 初始加载，确保有最新数据
        self._pending_deletions = self._load_pending_deletions()
        logger.info(f"初始化时待删除文件数量: {len(self._pending_deletions)}")
        
        while True:
            try:
                current_time = time.time()
                items_to_delete = []
                items_to_remove = []  # 记录需要从列表中移除的项目
                
                # 确保使用最新列表
                if len(self._pending_deletions) > 0:
                    logger.info(f"检查待删除文件列表，共 {len(self._pending_deletions)} 个项目")
                
                # 检查每个项目
                for item in self._pending_deletions:
                    path = item["path"]
                    if not item.get("move_success", True):
                        logger.debug(f"等待目标确认，暂不删除: {item.get('archive_path') or path}")
                        continue
                    
                    # 如果文件已经不存在，直接从列表中移除
                    if not path.exists():
                        items_to_remove.append(item)
                        logger.info(f"文件已不存在，将从待删除列表中移除: {path}")
                        continue
                    
                    # 如果已到删除时间，添加到待删除列表
                    if current_time >= item["delete_time"]:
                        items_to_delete.append(item)
                
                # 处理需要从列表中移除的项目（文件不存在的情况）
                for item in items_to_remove:
                    self._pending_deletions.remove(item)
                    # 发送通知
                    service_manager = self._get_service_manager()
                    notification_msg = f"📝 从待删除列表移除不存在的文件:\n{item['path']}"
                    await service_manager.telegram_service.send_message(notification_msg)
                
                # 执行删除操作
                successful_deletions = []  # 记录成功删除的项目，方便后续从队列移除
                for item in items_to_delete:
                    path = item["path"]
                    try:
                        delete_success = await self._delete_file(path)
                        if delete_success:
                            logger.info(f"已删除延迟文件: {path}")
                            successful_deletions.append(item)  # 只有成功删除的才添加到此列表
                            
                            # 发送删除通知
                            service_manager = self._get_service_manager()
                            notification_msg = f"🗑️ 已删除延迟文件:\n{path}"
                            await service_manager.telegram_service.send_message(notification_msg)
                        else:
                            logger.warning(f"删除文件失败，将保留在队列中稍后重试: {path}")
                    except Exception as e:
                        logger.error(f"删除文件时发生异常 {path}: {e}")
                        # 如果文件不存在，从列表中移除
                        if not path.exists():
                            successful_deletions.append(item)
                            logger.info(f"文件不存在，已从待删除列表中移除: {path}")
                
                # 从队列中移除成功删除的项目
                for item in successful_deletions:
                    if item in self._pending_deletions:
                        self._pending_deletions.remove(item)
                
                # 如果有任何更改，保存更新后的列表
                if successful_deletions or items_to_remove:
                    self._save_pending_deletions()
                    logger.info(f"已删除 {len(successful_deletions)} 个过期文件，移除 {len(items_to_remove)} 个不存在的记录，剩余 {len(self._pending_deletions)} 个待删除项目")
                    
            except Exception as e:
                logger.error(f"检查待删除文件时出错: {e}")
            finally:
                await asyncio.sleep(60)  # 每分钟检查一次，确保及时处理

    def _add_to_pending_deletion(self, path: Path, cloud_path: str = "", archive_path: str = "", move_success: bool = True):
        """将文件或目录添加到待删除列表
        
        Args:
            path: 要删除的文件或目录路径
        """
        try:
            # 检查文件是否已经在待删除列表中
            for item in self._pending_deletions:
                if str(item["path"]) == str(path):
                    logger.info(f"文件已在待删除列表中: {path}")
                    return
            
            # 计算删除时间（当前时间 + 延迟时间）
            delete_time = time.time() + self._deletion_delay
            
            # 添加到待删除列表
            self._pending_deletions.append({
                "path": path,
                "cloud_path": cloud_path or str(path),
                "archive_path": archive_path or "",
                "delete_time": delete_time,
                "move_success": move_success
            })
            
            # 保存到文件
            self._save_pending_deletions()
            
            # 记录添加信息
            logger.info(f"已将文件添加到待删除列表: {path}")
            
            # 发送通知
            try:
                service_manager = self._get_service_manager()
                delete_time_str = datetime.fromtimestamp(delete_time).strftime("%Y-%m-%d %H:%M:%S")
                notification_msg = f"📝 文件已加入待删除列表:\n{path}\n计划删除时间: {delete_time_str}"
                asyncio.create_task(service_manager.telegram_service.send_message(notification_msg))
            except Exception as e:
                logger.error(f"发送通知失败: {e}")
            
        except Exception as e:
            logger.error(f"添加文件到待删除列表失败: {e}")

    async def _delete_file(self, path: Path) -> bool:
        """删除文件或目录
        
        Args:
            path: 要删除的文件或目录路径
            
        Returns:
            bool: 是否成功删除
        """
        try:
            if not path.exists():
                logger.info(f"文件不存在，无需删除: {path}")
                return True

            if path.is_dir():
                for root, dirs, files in os.walk(path, topdown=False):
                    root_path = Path(root)

                    for file_name in files:
                        file_path = root_path / file_name
                        try:
                            file_path.unlink()
                        except FileNotFoundError:
                            logger.debug(f"删除目录时文件已不存在，跳过: {file_path}")

                    for dir_name in dirs:
                        dir_path = root_path / dir_name
                        try:
                            dir_path.rmdir()
                        except FileNotFoundError:
                            logger.debug(f"删除目录时子目录已不存在，跳过: {dir_path}")

                try:
                    path.rmdir()
                except FileNotFoundError:
                    logger.debug(f"删除目录时根目录已不存在，跳过: {path}")
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    logger.debug(f"删除文件时文件已不存在，跳过: {path}")
                
            # 让出控制权
            await asyncio.sleep(0)
                
            logger.info(f"成功删除文件: {path}")
            return True
        except Exception as e:
            logger.error(f"删除文件失败 {path}: {e}")
            return False

    def _should_skip_directory(self, path: Path) -> bool:
        """检查是否应该跳过某个目录"""
        # 系统目录
        if any(skip_dir in str(path) for skip_dir in self._skip_dirs):
            logger.debug(f"跳过系统目录: {path}")
            return True
        
        # 用户配置的目录
        if any(skip_folder in str(path) for skip_folder in self.settings.skip_folders_list):
            logger.debug(f"跳过用户配置的目录: {path}")
            return True
        
        # 检查用户配置的模式
        if any(re.search(pattern, str(path)) for pattern in self.settings.skip_patterns_list):
            logger.debug(f"跳过匹配模式的目录: {path}")
            return True
        
        return False

    async def process_directory(self, directory: Path, test_mode: bool = False) -> Dict:
        """处理单个目录的归档
        
        Args:
            directory: 要归档的目录
            test_mode: 是否为测试模式（只识别不执行）
            
        Returns:
            Dict: 处理结果
        """
        result = {
            "success": False,
            "message": "",
            "moved_files": 0,
            "total_size": 0
        }
        
        try:
            logger.info(f"开始处理目录: {directory}")
            
            # 获取相对于源目录的路径
            try:
                rel_path = self._local_relative_path(directory)
                logger.debug(f"- 相对路径: {rel_path}")
            except ValueError:
                # 如果不是source_dir的子目录，记录错误并尝试从绝对路径获取相对路径
                source_dir = Path(self.settings.archive_source_root)
                logger.warning(f"目录 {directory} 不是源目录 {source_dir} 的子目录")
                rel_path = Path(directory.name)
                logger.warning(f"- 无法获取相对路径，使用目录名: {rel_path}")
            
            # 获取最后的文件夹名称
            folder_name = directory.name
            
            # 获取完整的剧集名称（如果是季目录）
            full_folder_name = folder_name
            parent_dir_name = ""
            
            if SEASON_DIR_PATTERN.search(folder_name):
                parent_dir = directory.parent
                source_dir = Path(self.settings.archive_source_root)
                if parent_dir.name and parent_dir != source_dir:
                    parent_dir_name = parent_dir.name
                    # 记录电视剧名称用于日志
                    logger.debug(f"- 电视剧名称: {parent_dir_name}")
                    # 构建完整的显示名称(使用 - 而不是特殊字符)
                    full_folder_name = f"{parent_dir_name} - {folder_name}"
            
            # 处理特殊字符，确保路径安全
            safe_folder_name = re.sub(r'[:\\*?\"<>|]', '_', full_folder_name)
            if safe_folder_name != full_folder_name:
                logger.debug(f"- 处理后的安全名称: {safe_folder_name}")
            
            # 使用外部设置的媒体类型，而不是尝试匹配
            media_type = getattr(self, '_current_media_type', None)
            if not media_type:
                result["message"] = (
                    f"[跳过] {full_folder_name}\n"
                    f"原因: 未指定媒体类型"
                )
                logger.debug(f"目录 {directory} 未指定媒体类型")
                return result
            
            logger.info(f"使用媒体类型: {media_type}")
            
            # 获取阈值配置
            threshold = self.thresholds[media_type]
            logger.debug(f"阈值设置: 创建时间 {threshold.creation_days} 天, 修改时间 {threshold.mtime_days} 天")
            
            # 初始化记录最近文件的列表
            recent_files = []
            
            # 扫描文件
            logger.debug("开始扫描文件时间...")
            
            # 预先统计文件信息
            files_info = []
            total_size = 0
            for root, _, files in os.walk(directory):
                root_path = Path(root)
                for file in files:
                    # 检查文件扩展名是否在排除列表中
                    if any(file.lower().endswith(ext.strip().lower()) for ext in self.excluded_extensions):
                        logger.debug(f"跳过排除的文件: {file}")
                        continue
                        
                    file_path = root_path / file
                    stats = file_path.stat()
                    mtime = stats.st_mtime
                    ctime = self.get_creation_time(file_path)
                    
                    # 计算文件的创建时间和修改时间距今的天数
                    mtime_days = (time.time() - mtime) / 86400
                    ctime_days = (time.time() - ctime) / 86400
                    
                    logger.debug(f"文件: {file}")
                    logger.debug(f"- 创建时间: {ctime_days:.1f} 天前")
                    logger.debug(f"- 修改时间: {mtime_days:.1f} 天前")
                    
                    # 使用配置的阈值
                    if ctime_days < threshold.creation_days or mtime_days < threshold.mtime_days:
                        recent_files.append((file_path, min(mtime_days, ctime_days)))
                        logger.debug(f"- 状态: 未达到阈值")
                    else:
                        logger.debug(f"- 状态: 已达到阈值")
                        # 记录需要处理的文件信息
                        file_size = stats.st_size
                        total_size += file_size
                        files_info.append({
                            "path": file_path,
                            "size": file_size,
                            "relative_path": file_path.relative_to(directory)
                        })
            
            # 如果有最近修改的文件，记录并返回
            if recent_files:
                recent_files.sort(key=lambda x: x[1])  # 按时间升序排序
                most_recent = recent_files[0]
                days = most_recent[1]
                
                result["message"] = (
                    f"[跳过] {full_folder_name}\n"
                    f"原因: 存在最近文件\n"
                    f"最近文件: {most_recent[0].name}\n"
                    f"距今时间: {days:.1f} 天"
                )
                return result

            # 如果没有文件需要处理，跳过
            if not files_info:
                result["message"] = (
                    f"[跳过] {full_folder_name}\n"
                    f"原因: 目录中没有需要处理的文件"
                )
                return result
            
            # 构建源和目标的相对路径
            source_relative_path = rel_path  # 我们在上面已经计算过rel_path了
            path_info = self._build_archive_paths_from_relative(source_relative_path)
            rel_path_str = path_info["relative_str"]
            source_alist_path = path_info["source_alist_path"]
            dest_alist_path = path_info["dest_alist_path"]
            
            logger.debug(f"- 相对路径用于Alist: {rel_path_str}")
            logger.debug(f"- 完整源Alist路径: {source_alist_path}")
            logger.debug(f"- 完整目标Alist路径: {dest_alist_path}")
            
            # 检查是否是季文件夹，如果是则记录额外信息
            if parent_dir_name and SEASON_DIR_PATTERN.search(folder_name):
                # 记录详细信息，方便调试
                logger.debug(f"- 处理季目录路径:")
                logger.debug(f"  - 父目录: {parent_dir_name}")
                logger.debug(f"  - 季目录: {folder_name}")
                logger.debug(f"  - 完整名称: {full_folder_name}")
                logger.debug(f"  - 安全名称: {safe_folder_name}")
            
            # 确认路径不包含非法字符（不包括斜杠）
            safe_source_path = re.sub(r'[:\\*?\"<>|]', '_', source_alist_path)
            safe_dest_path = re.sub(r'[:\\*?\"<>|]', '_', dest_alist_path)
            
            if safe_source_path != source_alist_path or safe_dest_path != dest_alist_path:
                logger.warning(f"路径包含特殊字符，将被替换（保留路径分隔符）:")
                logger.warning(f"  原始源路径: {source_alist_path}")
                logger.warning(f"  安全源路径: {safe_source_path}")
                source_alist_path = safe_source_path
                dest_alist_path = safe_dest_path
            
            logger.info(f"准备归档: {full_folder_name}")
            logger.debug(f"- 源Alist路径: {source_alist_path}")
            logger.debug(f"- 目标Alist路径: {dest_alist_path}")
            logger.debug(f"- 文件数量: {len(files_info)}")
            logger.debug(f"- 总大小: {total_size / 1024 / 1024 / 1024:.2f} GB")

            if test_mode:
                result["message"] = (
                    f"[测试] {full_folder_name}\n"
                    f"状态: 可以归档，无近期文件\n"
                    f"文件数: {len(files_info)}\n"
                    f"总大小: {total_size / 1024 / 1024 / 1024:.2f} GB"
                )
                result["success"] = True
                result["moved_files"] = len(files_info)
                result["total_size"] = total_size
                return result
            
            # 使用Alist API复制目录
            logger.info("开始使用Alist API复制目录...")
            
            # 详细记录源路径和目标路径，以便于调试
            logger.info(f"源完整路径: {source_alist_path}")
            logger.info(f"目标完整路径: {dest_alist_path}")
            
            copy_result = await self.alist_client.copy_directory(source_alist_path, dest_alist_path)
            
            # 检查复制结果
            if copy_result["success"]:
                # 处理文件已存在的情况
                if copy_result["file_exists"]:
                    logger.info(f"目标位置已存在文件: {copy_result['message']}")
                    # 处理同已存在相同
                    if self.settings.archive_delete_source:
                        self._add_to_pending_deletion(
                            directory,
                            cloud_path=source_alist_path,
                            archive_path=dest_alist_path,
                            move_success=True
                        )
                        logger.info(f"已将原目录添加到待删除队列: {directory}")
                    
                    result["message"] = (
                        f"[已存在] {full_folder_name}\n"
                        f"文件数: {len(files_info)}\n"
                        f"总大小: {total_size / 1024 / 1024 / 1024:.2f} GB\n"
                        f"信息: {copy_result['message']}"
                    )
                    result["success"] = True
                    result["moved_files"] = len(files_info)
                    result["total_size"] = total_size
                else:
                    # 正常复制成功情况 - 简化逻辑，不再等待任务完成和验证文件
                    logger.info("目录复制请求成功，任务已创建")
                    result["total_size"] = total_size
                    result["moved_files"] = len(files_info)
                    
                    # 添加到删除队列
                    if self.settings.archive_delete_source:
                        self._add_to_pending_deletion(
                            directory,
                            cloud_path=source_alist_path,
                            archive_path=dest_alist_path,
                            move_success=True
                        )
                        logger.info(f"已将原目录添加到待删除队列: {directory}")
                    
                    result["message"] = (
                        f"[归档] {full_folder_name}\n"
                        f"文件数: {len(files_info)}\n"
                        f"总大小: {total_size / 1024 / 1024 / 1024:.2f} GB"
                    )
                
                # 无论是已存在还是正常复制成功，都生成STRM文件
                try:
                    strm_generated = await self.generate_strm_for_target(dest_alist_path, directory, files_info)
                    if strm_generated:
                        logger.info(f"已生成指向目标目录的STRM文件: {dest_alist_path}")
                except Exception as e:
                    logger.error(f"生成STRM文件失败: {str(e)}")
                
                result["success"] = True
                return result
            else:
                logger.error(f"Alist API复制目录失败: {copy_result['message']}")
                result["message"] = f"[错误] {full_folder_name}\n复制失败\n源路径: {source_alist_path}\n目标路径: {dest_alist_path}\n详情: {copy_result['message']}"
            
        except Exception as e:
            result["message"] = f"[错误] 归档失败 {full_folder_name}: {str(e)}"
            logger.error(f"处理目录失败 {directory}: {e}", exc_info=True)
            
        return result
    
    async def generate_strm_for_target(self, target_alist_path: str, source_directory: Path, files_info: list) -> bool:
        """根据目标Alist路径生成STRM文件，不等待复制完成
        
        Args:
            target_alist_path: 目标Alist路径
            source_directory: 源目录Path对象
            files_info: 文件信息列表
            
        Returns:
            bool: 是否成功生成STRM文件
        """
        try:
            logger.info(f"立即为目标路径生成STRM文件: {target_alist_path}")
            service_manager = self._get_service_manager()
            strm_service = service_manager.strm_service
            
            # 确保输出目录存在
            os.makedirs(strm_service.settings.output_dir, exist_ok=True)
            
            # 统计处理文件数
            strm_count = 0
            generated_strm_files = []
            
            # 确保路径格式一致
            target_alist_path = target_alist_path.rstrip('/')
            if not target_alist_path.startswith('/'):
                target_alist_path = '/' + target_alist_path
                
            logger.info(f"规范化后的目标路径: {target_alist_path}")
            logger.info(f"Alist扫描路径前缀: {strm_service.settings.alist_scan_path}")
            
            # 先检查目标路径是否在alist_scan_path下
            if not target_alist_path.startswith(strm_service.settings.alist_scan_path):
                logger.error(f"目标路径不在扫描路径下: {target_alist_path}")
                logger.error(f"扫描路径: {strm_service.settings.alist_scan_path}")
                return False
            
            # 如果启用了元数据下载，先复制元数据文件
            if strm_service.settings.download_metadata:
                logger.info(f"已启用元数据下载，将直接复制元数据文件到STRM目录")
                
                # 从配置中获取元数据文件扩展名
                metadata_extensions = set(strm_service.settings.metadata_extensions_list)
                logger.info(f"元数据文件扩展名: {metadata_extensions}")
                
                # 获取源目录相对于alist_scan_path的路径
                source_rel_path = str(source_directory.relative_to(self.settings.archive_source_root)).replace('\\', '/')
                if source_rel_path.startswith('/'):
                    source_rel_path = source_rel_path[1:]
                
                # 计算目标STRM目录路径
                # 主要思路：获取相对路径，然后计算STRM目录下对应的路径
                target_strm_dir = os.path.join(strm_service.settings.output_dir, source_rel_path)
                logger.info(f"目标STRM目录: {target_strm_dir}")
                
                # 确保目标目录存在
                os.makedirs(target_strm_dir, exist_ok=True)
                
                # 查找源目录中的所有元数据文件
                metadata_files = []
                for root, _, files in os.walk(source_directory):
                    for file in files:
                        ext = os.path.splitext(file)[1].lower()
                        if ext in metadata_extensions:
                            source_file = Path(os.path.join(root, file))
                            
                            # 获取相对于源目录的路径
                            rel_path = source_file.relative_to(source_directory)
                            
                            # 构建目标路径
                            target_file = os.path.join(target_strm_dir, str(rel_path))
                            
                            metadata_files.append((source_file, target_file))
                
                # 复制元数据文件
                copied_count = 0
                if metadata_files:
                    logger.info(f"找到 {len(metadata_files)} 个元数据文件需要复制")
                    
                    for source_file, target_file in metadata_files:
                        try:
                            # 确保目标目录存在
                            os.makedirs(os.path.dirname(target_file), exist_ok=True)
                            
                            # 复制文件
                            shutil.copy2(source_file, target_file)
                            copied_count += 1
                            logger.info(f"复制元数据文件: {source_file} -> {target_file}")
                        except Exception as e:
                            logger.error(f"复制元数据文件失败: {source_file} -> {target_file}, 错误: {str(e)}")
                    
                    logger.info(f"成功复制 {copied_count}/{len(metadata_files)} 个元数据文件到STRM目录")
                else:
                    logger.info(f"未找到元数据文件")
            
            # 遍历文件列表，为每个视频文件生成strm
            for file_info in files_info:
                file_path = file_info["path"]
                filename = file_path.name
                
                # 只处理视频文件
                if not strm_service._is_video_file(filename):
                    continue
                    
                # 检查文件大小
                if file_info.get("size", 0) < strm_service.settings.min_file_size * 1024 * 1024:
                    logger.debug(f"跳过小视频文件: {filename}")
                    continue
                
                # 获取相对路径，用于构建目标路径
                rel_file_path = str(file_info["relative_path"]).replace('\\', '/')
                if rel_file_path.startswith('/'):
                    rel_file_path = rel_file_path[1:]
                    
                logger.info(f"文件相对路径: {rel_file_path}")
                
                # 构建完整的目标文件路径（目标Alist路径 + 相对文件路径）
                full_file_path = f"{target_alist_path}/{rel_file_path}"
                
                # 确保路径以/开头
                if not full_file_path.startswith('/'):
                    full_file_path = '/' + full_file_path
                    
                logger.info(f"完整目标文件路径: {full_file_path}")
                
                # 按照strm_service中的逻辑计算相对路径和STRM文件路径
                # 1. 计算相对于alist_scan_path的路径
                if not full_file_path.startswith(strm_service.settings.alist_scan_path):
                    logger.error(f"文件路径不在扫描路径下: {full_file_path}")
                    continue
                    
                relative_path = full_file_path[len(strm_service.settings.alist_scan_path):].lstrip('/')
                logger.info(f"相对于扫描路径的路径: {relative_path}")
                
                # 2. 将扩展名修改为.strm，并在文件名后添加@remote(网盘)后缀
                base_path, _ = os.path.splitext(relative_path)
                # 在文件名后添加@remote(网盘)后缀，然后再添加.strm扩展名
                strm_relative_path = f"{base_path}@remote(网盘).strm"
                
                # 3. 根据output_dir构建STRM文件存放路径
                strm_path = os.path.join(strm_service.settings.output_dir, strm_relative_path)
                
                # 确保STRM文件所在目录存在
                os.makedirs(os.path.dirname(strm_path), exist_ok=True)
                
                # 4. 确定使用的URL基础地址
                base_url = strm_service.settings.alist_url
                if hasattr(strm_service.settings, 'use_external_url') and strm_service.settings.use_external_url and strm_service.settings.alist_external_url:
                    base_url = strm_service.settings.alist_external_url
                base_url = base_url.rstrip('/')
                
                # 5. 构建STRM文件内容
                if strm_service.settings.encode:
                    # 进行URL编码，但保留路径分隔符
                    encoded_path = quote(full_file_path)
                    strm_url = f"{base_url}/d{encoded_path}"
                else:
                    # 不进行URL编码
                    strm_url = f"{base_url}/d{full_file_path}"
                
                # 记录详细日志
                logger.info(f"处理视频文件: {filename}")
                logger.info(f"源路径: {full_file_path}")
                logger.info(f"STRM文件路径: {strm_path}")
                logger.info(f"STRM内容URL: {strm_url}")
                
                # 检查文件是否已存在且内容相同
                if os.path.exists(strm_path):
                    try:
                        with open(strm_path, 'r', encoding='utf-8') as f:
                            existing_content = f.read().strip()
                        if existing_content == strm_url:
                            logger.debug(f"STRM文件已存在且内容相同，跳过: {strm_path}")
                            continue
                    except Exception as e:
                        logger.warning(f"读取现有STRM文件失败: {str(e)}")
                
                # 写入strm文件
                with open(strm_path, 'w', encoding='utf-8') as f:
                    f.write(strm_url)
                
                logger.info(f"生成STRM文件成功: {strm_path} -> {strm_url}")
                strm_count += 1
                
                # 将STRM文件添加到健康状态服务
                service_manager.health_service.add_strm_file(strm_path, full_file_path)
                
                # 记录生成的STRM文件路径，用于后续添加到刷新队列
                generated_strm_files.append({
                    "path": strm_path,
                    "source_path": full_file_path,
                    "filename": filename
                })
            
            # 将生成的STRM文件添加到Emby刷新队列
            if generated_strm_files and hasattr(service_manager, 'emby_service') and service_manager.emby_service:
                for strm_file in generated_strm_files:
                    # 构建与strm_service一致的媒体信息结构
                    media_info = {
                        "path": strm_file["path"],
                        "source_path": strm_file["source_path"],
                        "filename": strm_file["filename"],
                        "title": os.path.splitext(strm_file["filename"])[0],
                        "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    service_manager.emby_service.add_to_refresh_queue(strm_file["path"], media_info=media_info)
                logger.info(f"已将 {len(generated_strm_files)} 个STRM文件添加到Emby刷新队列")
            
            logger.info(f"成功生成 {strm_count} 个STRM文件，指向目标路径: {target_alist_path}")
            return strm_count > 0
            
        except Exception as e:
            logger.error(f"生成STRM文件失败: {str(e)}", exc_info=True)
            return False

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
            # 确保config目录存在
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.media_types, f, ensure_ascii=False, indent=4)
            logger.info("媒体类型配置已保存")
        except Exception as e:
            logger.error(f"保存媒体类型配置失败: {e}")
            
    @property
    def media_types(self) -> Dict[str, Dict]:
        return self._media_types
        
    @media_types.setter
    def media_types(self, value: Dict[str, Dict]):
        # 验证数据结构
        processed_value = {}
        try:
            # 遍历并验证每个媒体类型
            for name, info in value.items():
                if not isinstance(info, dict):
                    logger.warning(f"媒体类型'{name}'的配置不是字典类型，跳过")
                    continue
                    
                # 确保必须的字段存在
                if "dir" not in info or "creation_days" not in info or "mtime_days" not in info:
                    logger.warning(f"媒体类型'{name}'缺少必要字段，使用默认值")
                    dir_value = info.get("dir", "")
                    creation_days = info.get("creation_days", 30)
                    mtime_days = info.get("mtime_days", 7)
                else:
                    dir_value = info["dir"]
                    # 确保是数值类型
                    try:
                        creation_days = int(float(info["creation_days"]))
                        mtime_days = int(float(info["mtime_days"]))
                    except (ValueError, TypeError):
                        logger.warning(f"媒体类型'{name}'的天数值无效，使用默认值")
                        creation_days = 30
                        mtime_days = 7
                
                # 创建处理后的配置
                processed_value[name] = {
                    "dir": str(dir_value),
                    "creation_days": creation_days,
                    "mtime_days": mtime_days
                }
                
            # 设置处理后的值
            self._media_types = processed_value
            
            # 更新阈值配置
            self.thresholds = {
                name: MediaThreshold(
                    info["creation_days"],
                    info["mtime_days"]
                ) for name, info in self._media_types.items()
            }
                
            # 记录更新信息
            logger.info(f"已更新媒体类型配置，共{len(self._media_types)}个类型")
            
            # 自动保存到文件
            self.save_media_types()
        except Exception as e:
            logger.error(f"设置媒体类型配置失败: {str(e)}", exc_info=True)
            raise

    async def process_file(self, source_path: Path) -> Dict:
        """处理单个文件的归档
        
        Args:
            source_path: 源文件路径
            
        Returns:
            Dict: 处理结果，包含success、message和size字段
        """
        try:
            # 检查文件是否存在且是文件
            if not source_path.is_file():
                return {
                    "success": False,
                    "message": f"❌ {source_path} 不是文件",
                    "size": 0
                }
            
            # 获取文件大小
            file_size = source_path.stat().st_size
            
            # 使用当前媒体类型
            media_type = getattr(self, '_current_media_type', None)
            if not media_type:
                return {
                    "success": False,
                    "message": f"❌ {source_path} 未指定媒体类型",
                    "size": 0
                }
            
            # 检查文件是否满足阈值条件
            creation_time = self.get_creation_time(source_path)
            mtime = source_path.stat().st_mtime
            
            threshold = self.thresholds[media_type]
            creation_days = (time.time() - creation_time) / (24 * 3600)
            mtime_days = (time.time() - mtime) / (24 * 3600)
            
            if creation_days < threshold.creation_days or mtime_days < threshold.mtime_days:
                return {
                    "success": False,
                    "message": f"⏳ {source_path} 未达到归档阈值",
                    "size": 0
                }
            
            try:
                relative_path = self._local_relative_path(source_path)
            except ValueError:
                return {
                    "success": False,
                    "message": f"❌ {source_path} 不在源目录 {self.settings.archive_source_root} 中",
                    "size": 0
                }

            path_info = self._build_archive_paths_from_relative(relative_path)
            dest_path = path_info["dest_path"]
            source_alist_path = path_info["source_alist_path"]
            dest_alist_path = path_info["dest_alist_path"]
            
            logger.debug(f"- 源文件路径: {source_path}")
            logger.debug(f"- 目标文件路径: {dest_path}")
            logger.debug(f"- 源Alist路径: {source_alist_path}")
            logger.debug(f"- 目标Alist路径: {dest_alist_path}")
            
            # 使用Alist API复制文件
            copy_result = await self.alist_client.copy_file(source_alist_path, dest_alist_path)

            # 检查复制结果
            if not copy_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {source_path} 复制失败: {copy_result['message']}",
                    "size": 0
                }
                
            # 处理文件已存在的情况
            if copy_result["file_exists"]:
                logger.info(f"目标位置已存在文件: {copy_result['message']}")
                # 如果配置了删除源文件
                if self.settings.archive_delete_source:
                    self._add_to_pending_deletion(
                        source_path,
                        cloud_path=source_alist_path,
                        archive_path=dest_alist_path,
                        move_success=True
                    )
                    return {
                        "success": True,
                        "message": f"🗑️ {source_path} 已存在于目标位置，已加入延迟删除队列",
                        "size": file_size
                    }
                return {
                    "success": False,
                    "message": f"⏭️ {source_path} 已存在于目标位置",
                    "size": 0
                }
            
            # 验证复制后的文件
            if not self.verify_files(source_path, dest_path):
                # 如果验证失败，删除目标文件
                try:
                    await self.alist_client.delete(dest_alist_path)
                except Exception as e:
                    logger.error(f"删除失败的目标文件时出错: {e}")
                    
                return {
                    "success": False,
                    "message": f"❌ {source_path} 复制验证失败",
                    "size": 0
                }
            
            # 如果配置了删除源文件
            if self.settings.archive_delete_source:
                self._add_to_pending_deletion(
                    source_path,
                    cloud_path=source_alist_path,
                    archive_path=dest_alist_path,
                    move_success=True
                )
                return {
                    "success": True,
                    "message": f"✅ {source_path} -> {dest_path} (已加入延迟删除队列)",
                    "size": file_size
                }
            
            return {
                "success": True,
                "message": f"✅ {source_path} -> {dest_path}",
                "size": file_size
            }
            
        except Exception as e:
            logger.error(f"处理文件失败 {source_path}: {e}")
            return {
                "success": False,
                "message": f"❌ {source_path} 处理失败: {str(e)}",
                "size": 0
            }

    async def archive(self, test_mode: bool = False):
        """执行归档处理
        
        Args:
            test_mode: 是否为测试模式（只识别不执行）
            
        Returns:
            Dict: 处理结果摘要和详情
        """
        if self._is_running:
            logger.warning("归档任务已在运行中")
            return {
                "summary": "归档任务已在运行中",
                "total_processed": 0,
                "total_size": 0,
                "results": []
            }
            
        try:
            self._stop_flag = False
            self._is_running = True
            
            service_manager = self._get_service_manager()
            
            # 初始化结果变量
            total_processed = 0
            total_size = 0
            success_results = []
            all_results = []  # 保存所有处理结果
            
            # 在开始归档时发送Telegram通知
            start_msg = "🔍 开始归档测试..." if test_mode else "🚀 开始归档处理..."
            logger.info(start_msg)
            await service_manager.telegram_service.send_message(start_msg)
            
            # 检查配置
            logger.debug(f"当前配置:")
            logger.debug(f"- 本地源目录: {self.settings.archive_source_root}")
            logger.debug(f"- Alist源目录: {self.settings.archive_source_alist}")
            logger.debug(f"- 目标目录: {self.settings.archive_target_root}")
            
            # 确保源目录是绝对路径
            source_dir = Path(self.settings.archive_source_root)
            if not source_dir.is_absolute():
                logger.warning(f"源目录不是绝对路径: {source_dir}")
                # 尝试获取绝对路径
                source_dir = source_dir.absolute()
                logger.info(f"已转换为绝对路径: {source_dir}")
                
            if not source_dir.exists():
                error_msg = f"本地源目录不存在: {source_dir}"
                logger.error(error_msg)
                await service_manager.telegram_service.send_message(f"❌ {error_msg}")
                return {
                    "summary": error_msg,
                    "total_processed": 0,
                    "total_size": 0,
                    "results": []
                }
            
            # 检查目录权限
            try:
                test_file = source_dir / ".archive_test"
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                error_msg = f"本地源目录权限检查失败: {source_dir}, 错误: {str(e)}"
                logger.error(error_msg)
                await service_manager.telegram_service.send_message(f"❌ {error_msg}")
                return {
                    "summary": error_msg,
                    "total_processed": 0,
                    "total_size": 0,
                    "results": []
                }
            
            processed_candidates = set()

            # 直接处理配置的媒体类型目录
            for media_type, config in self.media_types.items():
                if self._stop_flag:
                    break
                
                # 获取该媒体类型的目录配置
                media_dir = config.get('dir', '')
                if not media_dir:
                    logger.warning(f"媒体类型 '{media_type}' 未配置目录，跳过")
                    continue
                
                # 构建完整的媒体类型目录路径
                media_path = None
                # 删除绝对路径的判断，将所有路径都视为相对路径
                # 即使以/开头的路径也被视为相对路径
                if media_dir.startswith('/'):
                    # 移除开头的斜杠，以便与source_dir正确拼接
                    media_dir = media_dir.lstrip('/')
                    logger.info(f"媒体类型 '{media_type}' 路径以/开头，已处理为相对路径: {media_dir}")
                
                # 与源目录拼接
                media_path = source_dir / media_dir
                logger.info(f"媒体类型 '{media_type}' 最终路径: {media_path}")
                
                if not media_path.exists():
                    logger.warning(f"媒体类型 '{media_type}' 的目录不存在: {media_path}")
                    continue
                
                logger.info(f"开始处理媒体类型 '{media_type}' 的目录: {media_path}")
                
                # 设置该媒体类型的阈值
                threshold = self.thresholds.get(media_type)
                if not threshold:
                    logger.warning(f"媒体类型 '{media_type}' 没有对应的阈值配置，使用默认值")
                    threshold = MediaThreshold(30, 7)  # 默认值
                
                logger.debug(f"- 阈值设置: 创建时间 {threshold.creation_days} 天, 修改时间 {threshold.mtime_days} 天")
                
                # 遍历当前媒体类型目录下的所有子目录
                for sub_path in media_path.glob("**/*"):
                    if self._stop_flag:
                        break
                    
                    # 只处理目录
                    if not sub_path.is_dir():
                        continue
                    
                    # 获取该目录下的所有文件（非递归）
                    files = [f for f in sub_path.iterdir() if f.is_file()]
                    
                    # 如果目录包含文件
                    if files:
                        candidate_path = self._season_archive_candidate(sub_path, media_path)
                        candidate_key = str(candidate_path)
                        if candidate_key in processed_candidates:
                            logger.debug(f"跳过已处理的归档候选: {candidate_path}")
                            continue

                        processed_candidates.add(candidate_key)

                        candidate_files = [f for f in candidate_path.iterdir() if f.is_file()] if candidate_path.exists() else []

                        # 记录详细信息，方便调试
                        logger.debug(f"\n处理目录: {candidate_path}")
                        logger.debug(f"- 触发目录: {sub_path}")
                        logger.debug(f"- 候选目录包含文件数: {len(candidate_files)}")
                        if candidate_path != sub_path:
                            logger.debug(f"- 季目录归并: {sub_path} -> {candidate_path}")
                        
                        # 创建一个临时的处理上下文，包含媒体类型信息
                        self._current_media_type = media_type
                        
                        # 处理目录
                        result = await self.process_directory(candidate_path, test_mode)

                        # 清除临时上下文
                        self._current_media_type = None
                        
                        if result["success"]:
                            total_processed += result["moved_files"]
                            total_size += result["total_size"]
                            if "[归档]" in result["message"]:
                                success_results.append(result["message"])
                        
                        # 无论是否成功，都添加到所有结果中
                        all_results.append(result)
                    
                    # 让出控制权
                    await asyncio.sleep(0)
            
            # 生成汇总消息
            summary = (
                f"✅ 归档{'测试' if test_mode else ''}完成\n"
                f"📁 {'识别' if test_mode else '处理'}文件: {total_processed} 个\n"
                f"💾 总大小: {total_size / 1024 / 1024 / 1024:.2f} GB"
            )
            logger.info(summary)
            
            # 发送最终的汇总消息到Telegram
            await service_manager.telegram_service.send_message(summary)
            
            # 如果有成功归档的结果，单独发送到Telegram
            if success_results:
                # 格式化每个结果，增强电视剧目录的显示
                formatted_results = []
                for result in success_results:
                    # 从结果消息中提取相关信息
                    folder_name = ""
                    file_count = 0
                    total_size_gb = 0.0
                    
                    # 提取 [归档] 后面的文件夹名称
                    if folder_match := re.search(r'\[归档\] ([^\n]+)', result):
                        folder_name = folder_match.group(1)
                    
                    # 提取文件数量
                    if files_match := re.search(r'文件数: (\d+)', result):
                        file_count = int(files_match.group(1))
                    
                    # 提取文件大小
                    if size_match := re.search(r'总大小: ([0-9.]+) GB', result):
                        total_size_gb = float(size_match.group(1))
                    
                    # 查找该文件夹对应的剧集信息
                    show_name = ""
                    for log_entry in self.logger_history:
                        if f"开始处理目录" in log_entry and folder_name in log_entry:
                            # 找到了处理该目录的日志，查找后续的电视剧名称
                            index = self.logger_history.index(log_entry)
                            # 查找后面几条日志中是否有电视剧名称
                            for i in range(index, min(index + 5, len(self.logger_history))):
                                if "电视剧名称" in self.logger_history[i]:
                                    show_name_match = re.search(r'- 电视剧名称: (.+)', self.logger_history[i])
                                    if show_name_match:
                                        show_name = show_name_match.group(1)
                                        break
                            break
                    
                    # 构建格式化的结果字符串
                    if show_name and ("Season" in folder_name or "season" in folder_name):
                        # 这是一个电视剧季文件夹，显示剧名和季信息
                        formatted_results.append(f"{show_name} - {folder_name} ({file_count}个文件, {total_size_gb:.2f} GB)")
                    else:
                        # 其他文件夹，只显示文件夹名
                        formatted_results.append(f"{folder_name} ({file_count}个文件, {total_size_gb:.2f} GB)")
                
                success_message = "归档成功的文件夹:\n\n" + "\n".join(formatted_results)
                # 如果消息太长，只保留前20个结果
                if len(success_message) > 3000:
                    formatted_results = formatted_results[:20]
                    success_message = "归档成功的文件夹（仅显示前20个）:\n\n" + "\n".join(formatted_results)
                await service_manager.telegram_service.send_message(success_message)
            
            return {
                "summary": summary,
                "total_processed": total_processed,
                "total_size": total_size,
                "results": all_results
            }
            
        except Exception as e:
            error_msg = f"❌ 归档{'测试' if test_mode else '处理'}出错: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
            return {
                "summary": error_msg,
                "total_processed": 0,
                "total_size": 0,
                "results": []
            }
        finally:
            self._is_running = False 
