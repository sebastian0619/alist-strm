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
        
        # 从配置加载要排除的文件扩展名
        self.excluded_extensions = set(
            ext.strip().lower() for ext in self.settings.archive_excluded_extensions.split(',')
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
        
        # 由于self.media_types的顺序已经由前端排序确定优先级
        # 所以这里直接按顺序匹配，找到的第一个匹配就是优先级最高的
        for media_type, info in self.media_types.items():
            dir_path = info['dir'].replace('\\', '/').strip('/')
            dir_parts = dir_path.split('/')
            
            logger.debug(f"尝试匹配类型 {media_type} (目录: {dir_path})")
            
            # 检查目录是否匹配
            # 1. 配置的目录部分必须完全匹配路径的开始部分
            # 2. 配置的目录层级必须小于等于实际路径的层级
            if (len(dir_parts) <= len(path_parts) and 
                all(dp == pp for dp, pp in zip(dir_parts, path_parts))):
                logger.debug(f"匹配成功: {media_type}")
                return media_type
            else:
                logger.debug(f"匹配失败: 路径部分={path_parts[:len(dir_parts)]}, 配置部分={dir_parts}")
                
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
    
    async def process_directory(self, directory: Path, test_mode: bool = False) -> Dict:
        """处理单个目录的归档
        
        Args:
            directory: 要处理的目录路径
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
            # 检查目录中的文件修改时间
            recent_files = []
            for root, _, files in os.walk(directory):
                root_path = Path(root)
                for file in files:
                    # 检查文件扩展名是否在排除列表中
                    if any(file.lower().endswith(ext.strip().lower()) for ext in self.excluded_extensions):
                        continue
                        
                    file_path = root_path / file
                    stats = file_path.stat()
                    mtime = stats.st_mtime
                    ctime = stats.st_ctime
                    
                    # 计算文件的创建时间和修改时间距今的天数
                    mtime_days = (time.time() - mtime) / 86400
                    ctime_days = (time.time() - ctime) / 86400
                    
                    # 如果文件的创建时间或修改时间在阈值内，添加到最近文件列表
                    if mtime_days < 30 or ctime_days < 30:  # 使用30天作为默认阈值
                        recent_files.append((file_path, min(mtime_days, ctime_days)))

            if recent_files:
                # 按时间排序，展示最近的3个文件
                recent_files.sort(key=lambda x: x[1])
                example_files = []
                for f, days in recent_files[:3]:
                    example_files.append(f"{f.name} ({days:.1f}天)")
                
                result["message"] = (
                    f"[跳过] {directory.name}\n"
                    f"原因: 存在近期创建或修改的文件\n"
                    f"文件: {', '.join(example_files)}"
                )
                return result

            if test_mode:
                result["message"] = f"[测试] {directory.name} 可以归档，无近期文件"
                result["success"] = True
                return result
            
            # 准备归档
            target_dir = Path(self.settings.archive_target_root)
            relative_path = directory.relative_to(self.settings.archive_source_root)
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
                        # 跳过排除的文件格式
                        if any(src_file.name.lower().endswith(ext.strip().lower()) for ext in self.excluded_extensions):
                            continue
                            
                        dst_file = destination / src_file.relative_to(directory)
                        if not self.verify_files(src_file, dst_file):
                            all_verified = False
                            break
                        result["total_size"] += src_file.stat().st_size
                        result["moved_files"] += 1
                
                if all_verified:
                    # 验证成功后删除源文件
                    shutil.rmtree(str(directory))
                    result["message"] = (
                        f"[归档] {directory.name} -> {destination.name}\n"
                        f"已验证并删除源文件"
                    )
                else:
                    result["message"] = f"[错误] {directory.name} 文件验证失败"
                    return result
            else:
                # 如果不需要删除源文件，直接复制
                # 使用自定义的copytree来排除特定格式的文件
                def custom_copy(src, dst):
                    if not dst.exists():
                        dst.mkdir(parents=True, exist_ok=True)
                    for item in src.iterdir():
                        if item.is_file():
                            # 跳过排除的文件格式
                            if any(item.name.lower().endswith(ext.strip().lower()) for ext in self.excluded_extensions):
                                continue
                            shutil.copy2(str(item), str(dst / item.name))
                            result["total_size"] += item.stat().st_size
                            result["moved_files"] += 1
                        elif item.is_dir():
                            custom_copy(item, dst / item.name)
                
                custom_copy(directory, destination)
                result["message"] = (
                    f"[归档] {directory.name} -> {destination.name}"
                )

            result["success"] = True
            
        except Exception as e:
            result["message"] = f"[错误] 归档失败 {directory.name}: {str(e)}"
            logger.error(f"处理目录失败 {directory}: {e}")
            
        return result
    
    async def archive(self, test_mode: bool = False):
        """执行归档处理
        
        Args:
            test_mode: 是否为测试模式（只识别不执行）
            
        Returns:
            Dict: 如果是测试模式，返回测试结果
        """
        if self._is_running:
            logger.warning("归档任务已在运行中")
            return
            
        try:
            self._stop_flag = False
            self._is_running = True
            
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(
                "🔍 开始归档测试..." if test_mode else "🚀 开始归档处理..."
            )
            
            source_dir = Path(self.settings.archive_source_root)
            if not source_dir.exists():
                error_msg = f"源目录不存在: {source_dir}"
                logger.error(error_msg)
                await service_manager.telegram_service.send_message(f"❌ {error_msg}")
                return
                
            total_processed = 0
            total_size = 0
            test_results = []
            all_results = []
            
            # 只遍历配置的目录
            for media_type, info in self.media_types.items():
                if self._stop_flag:
                    break
                    
                target_dir = source_dir / info['dir'].lstrip('/')
                if not target_dir.exists():
                    logger.warning(f"配置的目录不存在: {target_dir}")
                    continue
                    
                logger.info(f"\n开始处理媒体类型 {media_type} 的目录: {target_dir}")
                
                # 遍历目标目录下的所有子目录
                for root, dirs, files in os.walk(target_dir):
                    if self._stop_flag:
                        break
                        
                    root_path = Path(root)
                    # 只处理包含文件的目录（叶子目录）
                    if files and not any(d.startswith('.') for d in root_path.parts):
                        logger.info(f"\n处理目录: {root_path}")
                        
                        result = await self.process_directory(root_path, test_mode)
                        if result["success"]:
                            total_processed += result["moved_files"]
                            total_size += result["total_size"]
                        if test_mode:
                            test_results.append(result)
                            
                        # 只收集有意义的结果（跳过、归档或错误）
                        if "[跳过]" in result["message"] or "[归档]" in result["message"] or "[错误]" in result["message"]:
                            all_results.append(result["message"])
                        
                        # 让出控制权
                        await asyncio.sleep(0)
            
            # 生成汇总消息
            if all_results:
                summary_message = "归档处理结果:\n\n" + "\n\n".join(all_results)
                # 如果消息太长，只保留前20个结果
                if len(summary_message) > 3000:
                    all_results = all_results[:20]
                    summary_message = "归档处理结果（仅显示前20个）:\n\n" + "\n\n".join(all_results)
                await service_manager.telegram_service.send_message(summary_message)
            
            summary = (
                f"✅ 归档{'测试' if test_mode else ''}完成\n"
                f"📁 {'识别' if test_mode else '处理'}文件: {total_processed} 个\n"
                f"💾 总大小: {total_size / 1024 / 1024:.2f} MB"
            )
            logger.info(summary)
            await service_manager.telegram_service.send_message(summary)
            
            # 如果配置了自动运行STRM扫描且不是测试模式
            if not test_mode and self.settings.archive_auto_strm and total_processed > 0:
                logger.info("开始自动STRM扫描...")
                await service_manager.telegram_service.send_message("🔄 开始自动STRM扫描...")
                await service_manager.strm_service.strm()
            
            if test_mode:
                return {
                    "summary": summary,
                    "results": test_results
                }
            
        except Exception as e:
            error_msg = f"❌ 归档{'测试' if test_mode else '处理'}出错: {str(e)}"
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
            
            # 确保目标目录存在
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 如果目标文件已存在，验证文件
            if dest_path.exists():
                if self.verify_files(source_path, dest_path):
                    # 如果配置了删除源文件且验证通过
                    if self.settings.archive_delete_source:
                        source_path.unlink()
                        return {
                            "success": True,
                            "message": f"🗑️ {source_path} 已存在于目标位置，删除源文件",
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
            
            # 复制文件
            shutil.copy2(source_path, dest_path)
            
            # 验证复制后的文件
            if not self.verify_files(source_path, dest_path):
                # 如果验证失败，删除目标文件
                if dest_path.exists():
                    dest_path.unlink()
                return {
                    "success": False,
                    "message": f"❌ {source_path} 复制验证失败",
                    "size": 0
                }
            
            # 如果配置了删除源文件
            if self.settings.archive_delete_source:
                source_path.unlink()
                return {
                    "success": True,
                    "message": f"✅ {source_path} -> {dest_path} (已删除源文件)",
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