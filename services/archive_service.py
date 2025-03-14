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

class MediaThreshold(NamedTuple):
    """媒体文件的时间阈值配置"""
    creation_days: int
    mtime_days: int

class ArchiveService:
    def __init__(self):
        self.settings = Settings()
        self._stop_flag = False
        self._is_running = False
        
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
        self._pending_deletions_file = os.path.join("config", "pending_deletions.json")
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
    
    def _load_pending_deletions(self) -> list:
        """从JSON文件加载待删除列表"""
        try:
            # 确保config目录存在
            os.makedirs("config", exist_ok=True)
            if os.path.exists(self._pending_deletions_file):
                with open(self._pending_deletions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 转换路径字符串回Path对象
                    for item in data:
                        if 'path' in item and isinstance(item['path'], str):
                            item['path'] = Path(item['path'])
                    return data
        except Exception as e:
            logger.error(f"加载待删除列表失败: {e}")
        return []
    
    def _save_pending_deletions(self):
        """将待删除列表保存到JSON文件"""
        try:
            # 确保config目录存在
            os.makedirs("config", exist_ok=True)
            
            # 将Path对象转换为字符串以便JSON序列化
            data_to_save = []
            for item in self._pending_deletions:
                data_item = item.copy()
                if 'path' in data_item and isinstance(data_item['path'], Path):
                    data_item['path'] = str(data_item['path'])
                data_to_save.append(data_item)
                
            with open(self._pending_deletions_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存待删除列表失败: {e}")
    
    def _setup_logger_handler(self):
        """设置日志处理器，记录日志历史"""
        class LoggerHistoryHandler:
            def __init__(self, history_list):
                self.history_list = history_list
                
            def write(self, record):
                self.history_list.append(record["message"])
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
    
    def get_media_type(self, path: Path) -> str:
        """根据路径判断媒体类型，优先匹配更具体的路径
        
        例如：
        - 路径为 "/video/动漫/动画电影/xxx"
        - 如果同时配置了 "动漫/动画电影" 和 "动漫"
        - 会优先匹配 "动漫/动画电影" 类型
        
        匹配规则：
        1. 将路径转换为相对路径（相对于source_root）
        2. 按照配置的顺序（优先级）依次匹配
        3. 对于每个媒体类型，检查其配置的目录是否是当前路径的一部分
        4. 返回第一个匹配的类型（优先级最高的）
        """
        path_str = str(path)
        
        # 转换路径分隔符为统一格式
        normalized_path = path_str.replace('\\', '/').rstrip('/')
        source_root = str(self.settings.archive_source_root).replace('\\', '/').rstrip('/')
        
        # 获取相对路径
        if normalized_path.startswith(source_root):
            relative_path = normalized_path[len(source_root):].lstrip('/')
        else:
            relative_path = normalized_path
            
        logger.debug(f"检查路径: {relative_path}")
            
        # 将路径分割成部分
        path_parts = relative_path.split('/')
        
        # 使用最长匹配原则，先尝试匹配最具体的路径
        matched_type = ""
        max_match_length = 0
        
        for media_type, info in self.media_types.items():
            if "dir" not in info:
                continue
                
            dir_path = info['dir'].replace('\\', '/').strip('/')
            dir_parts = dir_path.split('/')
            
            logger.debug(f"尝试匹配类型 {media_type} (目录: {dir_path})")
            
            # 检查目录是否匹配
            # 1. 配置的目录部分必须完全匹配路径的开始部分
            # 2. 配置的目录层级必须小于等于实际路径的层级
            if (len(dir_parts) <= len(path_parts) and 
                all(dp == pp for dp, pp in zip(dir_parts, path_parts))):
                
                # 找到匹配，但使用最长匹配原则
                if len(dir_parts) > max_match_length:
                    max_match_length = len(dir_parts)
                    matched_type = media_type
                    logger.debug(f"找到更优匹配: {media_type}, 匹配长度: {len(dir_parts)}")
            else:
                logger.debug(f"匹配失败: 路径部分={path_parts[:len(dir_parts)]}, 配置部分={dir_parts}")
        
        if matched_type:
            logger.debug(f"最终匹配: {matched_type}")
            return matched_type
        else:        
            logger.debug("没有找到匹配的媒体类型")
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
        while True:
            try:
                current_time = time.time()
                items_changed = False
                
                # 复制列表以避免在迭代时修改
                for item in self._pending_deletions[:]:
                    if current_time >= item["delete_time"]:
                        path = item["path"]
                        try:
                            if path.is_dir():
                                shutil.rmtree(str(path))
                            else:
                                path.unlink()
                            logger.info(f"已删除延迟文件: {path}")
                            self._pending_deletions.remove(item)
                            items_changed = True
                        except Exception as e:
                            logger.error(f"删除文件失败 {path}: {e}")
                
                # 如果列表有变化，保存到文件
                if items_changed:
                    self._save_pending_deletions()
                    
            except Exception as e:
                logger.error(f"检查待删除文件时出错: {e}")
            finally:
                await asyncio.sleep(3600)  # 每小时检查一次

    def _add_to_pending_deletion(self, path: Path):
        """添加文件到待删除队列"""
        self._pending_deletions.append({
            "path": path,
            "delete_time": time.time() + self._deletion_delay
        })
        # 保存待删除列表到JSON文件
        self._save_pending_deletions()
        logger.info(f"已添加到延迟删除队列: {path}, 将在 {self._deletion_delay/86400:.1f} 天后删除")

    async def process_directory(self, directory: Path, test_mode: bool = False) -> Dict:
        result = {
            "success": False,
            "message": "",
            "moved_files": 0,
            "total_size": 0
        }
        
        try:
            logger.info(f"开始处理目录: {directory}")
            rel_path = directory.relative_to(self.settings.archive_source_root)
            logger.info(f"- 相对路径: {rel_path}")
            
            # 获取最后的文件夹名称
            folder_name = directory.name
            
            # 记录电视剧目录的更完整信息
            if "Season" in folder_name or "season" in folder_name:
                parent_dir = directory.parent
                if parent_dir.name and parent_dir != self.settings.archive_source_root:
                    logger.info(f"- 电视剧名称: {parent_dir.name}")
            
            # 检查目录中的文件修改时间
            recent_files = []
            # 获取媒体类型
            media_type = self.get_media_type(directory)
            if not media_type:
                result["message"] = (
                    f"[跳过] {folder_name}\n"
                    f"原因: 未匹配到媒体类型"
                )
                logger.info(f"目录 {directory} 未匹配到媒体类型")
                return result
            
            logger.info(f"匹配到媒体类型: {media_type}")
            
            # 获取阈值配置
            threshold = self.thresholds[media_type]
            logger.info(f"阈值设置: 创建时间 {threshold.creation_days} 天, 修改时间 {threshold.mtime_days} 天")
            
            # 扫描文件
            logger.info("开始扫描文件时间...")
            
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
            
            if recent_files:
                # 按时间排序，展示最近的3个文件
                recent_files.sort(key=lambda x: x[1])
                example_files = []
                for f, days in recent_files[:3]:
                    example_files.append(f"{f.name} ({days:.1f}天)")
                
                result["message"] = (
                    f"[跳过] {folder_name}\n"
                    f"原因: 存在近期创建或修改的文件\n"
                    f"文件: {', '.join(example_files)}"
                )
                logger.info(f"目录包含近期文件，跳过处理")
                logger.info(f"近期文件示例: {', '.join(example_files)}")
                return result

            # 获取目标路径
            relative_path = directory.relative_to(self.settings.archive_source_root)
            
            # 构建Alist路径
            source_alist_path = str(Path(self.settings.archive_source_alist) / relative_path).lstrip("/")
            dest_alist_path = str(Path(self.settings.archive_target_root) / relative_path).lstrip("/")
            
            logger.info("准备进行归档:")
            logger.info(f"- 源Alist路径: {source_alist_path}")
            logger.info(f"- 目标Alist路径: {dest_alist_path}")
            logger.info(f"- 文件数量: {len(files_info)}")
            logger.info(f"- 总大小: {total_size / 1024 / 1024 / 1024:.2f} GB")

            if test_mode:
                result["message"] = (
                    f"[测试] {folder_name}\n"
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
            success = await self.alist_client.copy_directory(source_alist_path, dest_alist_path)
            
            if success:
                logger.info("目录复制成功，开始验证文件...")
                # 验证目录中的所有文件
                all_verified = True
                moved_files = 0
                
                for file_info in files_info:
                    # 获取本地和Alist的相对路径
                    dst_file = Path(self.settings.archive_target_root) / relative_path / file_info["relative_path"]
                    
                    logger.debug(f"验证文件: {file_info['path'].name}")
                    if not self.verify_files(file_info["path"], dst_file):
                        logger.error(f"文件验证失败: {file_info['path'].name}")
                        all_verified = False
                        break
                    moved_files += 1
                    logger.debug(f"- 验证成功")
                
                if all_verified:
                    result["total_size"] = total_size
                    result["moved_files"] = moved_files
                    
                    logger.info(f"所有文件验证成功")
                    logger.info(f"- 移动文件数: {moved_files}")
                    logger.info(f"- 总大小: {total_size / 1024 / 1024 / 1024:.2f} GB")
                    
                    # 验证成功后将源目录添加到待删除队列
                    if self.settings.archive_delete_source:
                        self._add_to_pending_deletion(directory)
                        result["message"] = (
                            f"[归档] {folder_name}\n"
                            f"已验证并加入延迟删除队列\n"
                            f"文件数: {moved_files}\n"
                            f"总大小: {total_size / 1024 / 1024 / 1024:.2f} GB"
                        )
                    else:
                        result["message"] = (
                            f"[归档] {folder_name}\n"
                            f"文件数: {moved_files}\n"
                            f"总大小: {total_size / 1024 / 1024 / 1024:.2f} GB"
                        )
                    
                    result["success"] = True
                else:
                    # 如果验证失败，删除目标目录
                    logger.error("文件验证失败，正在删除目标目录...")
                    await self.alist_client.delete(dest_alist_path)
                    result["message"] = f"[错误] {folder_name} 文件验证失败"
            else:
                logger.error("Alist API复制目录失败")
                result["message"] = f"[错误] {folder_name} 复制失败"
            
        except Exception as e:
            result["message"] = f"[错误] 归档失败 {folder_name}: {str(e)}"
            logger.error(f"处理目录失败 {directory}: {e}", exc_info=True)
            
        return result
    
    async def archive(self, test_mode: bool = False):
        """执行归档处理
        
        Args:
            test_mode: 是否为测试模式（只识别不执行）
            
        Returns:
            Dict: 处理结果摘要和详情
        """
        if self._is_running:
            logger.warning("归档任务已在运行中")
            return
            
        try:
            self._stop_flag = False
            self._is_running = True
            
            service_manager = self._get_service_manager()
            
            # 在开始归档时发送Telegram通知
            start_msg = "🔍 开始归档测试..." if test_mode else "🚀 开始归档处理..."
            logger.info(start_msg)
            await service_manager.telegram_service.send_message(start_msg)
            
            # 检查配置
            logger.info(f"当前配置:")
            logger.info(f"- 本地源目录: {self.settings.archive_source_root}")
            logger.info(f"- Alist源目录: {self.settings.archive_source_alist}")
            logger.info(f"- 目标目录: {self.settings.archive_target_root}")
            
            # 检查本地源目录
            source_dir = Path(self.settings.archive_source_root)
            if not source_dir.exists():
                error_msg = f"本地源目录不存在: {source_dir}"
                logger.error(error_msg)
                await service_manager.telegram_service.send_message(f"❌ {error_msg}")
                return
            if not source_dir.is_dir():
                error_msg = f"本地源目录路径不是目录: {source_dir}"
                logger.error(error_msg)
                await service_manager.telegram_service.send_message(f"❌ {error_msg}")
                return
                
            # 检查目录权限
            try:
                test_file = source_dir / ".archive_test"
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                error_msg = f"本地源目录权限检查失败: {source_dir}, 错误: {str(e)}"
                logger.error(error_msg)
                await service_manager.telegram_service.send_message(f"❌ {error_msg}")
                return
            
            total_processed = 0
            total_size = 0
            test_results = []
            success_results = []
            
            # 检查目标目录
            if self.settings.archive_target_root and self.settings.archive_source_root:
                # 初始化Alist客户端
                self.alist_client = AlistClient(
                    self.settings.alist_url,
                    self.settings.alist_token
                )
                
                # 要处理的目标目录
                target_dir = Path(self.settings.archive_source_root)
                
                # 遍历目标目录下的所有子目录
                for root, dirs, files in os.walk(target_dir):
                    if self._stop_flag:
                        break
                        
                    root_path = Path(root)
                    # 只处理包含文件的目录（叶子目录）
                    if files and not any(d.startswith('.') for d in root_path.parts):
                        logger.info(f"\n处理目录: {root_path}")
                        logger.info(f"- 相对路径: {root_path.relative_to(source_dir)}")
                        logger.info(f"- 包含文件数: {len(files)}")
                        
                        result = await self.process_directory(root_path, test_mode)
                        if result["success"]:
                            total_processed += result["moved_files"]
                            total_size += result["total_size"]
                            if "[归档]" in result["message"]:
                                success_results.append(result["message"])
                        if test_mode:
                            test_results.append(result)
                        
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
                    if size_match := re.search(r'总大小: ([\d\.]+) GB', result):
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
            
            # 如果配置了自动运行STRM扫描且不是测试模式
            if not test_mode and self.settings.archive_auto_strm and total_processed > 0:
                logger.info("开始自动STRM扫描...")
                await service_manager.telegram_service.send_message("🔄 开始自动STRM扫描...")
                await service_manager.strm_service.strm()
            
            # 返回结果
            return {
                "summary": summary,
                "total_processed": total_processed,
                "total_size": total_size,
                "results": test_results if test_mode else success_results
            }
            
        except Exception as e:
            error_msg = f"❌ 归档{'测试' if test_mode else '处理'}出错: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
            raise
        finally:
            self._is_running = False

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
        self._media_types = value
        # 当media_types被更新时，自动保存到文件
        self.save_media_types()
        # 更新阈值配置
        self.thresholds = {
            name: MediaThreshold(
                info["creation_days"],
                info["mtime_days"]
            ) for name, info in self._media_types.items()
        }

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
            
            # 获取媒体类型
            media_type = self.get_media_type(source_path)
            if not media_type:
                return {
                    "success": False,
                    "message": f"❌ {source_path} 未匹配到媒体类型",
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
            
            # 构建目标路径，保持相对路径结构
            relative_path = source_path.relative_to(self.settings.archive_source_root)
            dest_path = Path(self.settings.archive_target_root) / relative_path
            
            # 构建Alist路径
            source_alist_path = str(source_path).replace(str(self.settings.archive_source_root), "").lstrip("/")
            dest_alist_path = str(dest_path).replace(str(self.settings.archive_target_root), "").lstrip("/")
            
            # 如果目标文件已存在，验证文件
            if dest_path.exists():
                if self.verify_files(source_path, dest_path):
                    # 如果配置了删除源文件且验证通过
                    if self.settings.archive_delete_source:
                        self._add_to_pending_deletion(source_path)
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
                else:
                    return {
                        "success": False,
                        "message": f"❌ {source_path} 目标位置存在不同文件",
                        "size": 0
                    }
            
            # 使用Alist API复制文件
            success = await self.alist_client.copy_file(source_alist_path, dest_alist_path)
            
            if not success:
                return {
                    "success": False,
                    "message": f"❌ {source_path} 复制失败",
                    "size": 0
                }
            
            # 验证复制后的文件
            if not self.verify_files(source_path, dest_path):
                # 如果验证失败，删除目标文件
                await self.alist_client.delete(dest_alist_path)
                return {
                    "success": False,
                    "message": f"❌ {source_path} 复制验证失败",
                    "size": 0
                }
            
            # 如果配置了删除源文件
            if self.settings.archive_delete_source:
                self._add_to_pending_deletion(source_path)
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