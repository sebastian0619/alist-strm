import os
import httpx
import time
import re
import json
import hashlib
from urllib.parse import quote
from loguru import logger
from config import Settings
from typing import List, Optional
import asyncio
import importlib

class AlistClient:
    def __init__(self, base_url: str, token: str = None):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": token} if token else {},
            timeout=httpx.Timeout(90.0, connect=90.0, read=90.0, write=90.0)
        )
    
    async def list_files(self, path: str) -> list:
        """获取目录下的文件列表"""
        try:
            response = await self.client.post("/api/fs/list", json={
                "path": path,
                "password": "",
                "page": 1,
                "per_page": 0,
                "refresh": False
            })
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 200:
                content = data.get("data", {}).get("content", [])
                if content is None:  # 如果content为None，返回空列表
                    logger.warning(f"目录访问被拒绝或不存在: {path}")
                    return []
                return content
            logger.warning(f"获取目录列表失败: {path}, 状态码: {data.get('code')}")
            return []
        except Exception as e:
            logger.error(f"获取文件列表失败: {path}, 错误: {str(e)}")
            return []
            
    async def move_file(self, src_path: str, dest_path: str) -> bool:
        """移动文件到新位置
        
        Args:
            src_path: 源文件路径
            dest_path: 目标文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            response = await self.client.post("/api/fs/move", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                logger.info(f"成功移动文件: {src_path} -> {dest_path}")
                return True
                
            logger.warning(f"移动文件失败: {src_path}, 状态码: {data.get('code')}")
            return False
            
        except Exception as e:
            logger.error(f"移动文件时出错: {src_path}, 错误: {str(e)}")
            return False
            
    async def move_directory(self, src_path: str, dest_path: str) -> bool:
        """移动目录到新位置
        
        Args:
            src_path: 源目录路径
            dest_path: 目标目录路径
            
        Returns:
            bool: 是否成功
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            response = await self.client.post("/api/fs/move", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                logger.info(f"成功移动目录: {src_path} -> {dest_path}")
                return True
                
            logger.warning(f"移动目录失败: {src_path}, 状态码: {data.get('code')}")
            return False
            
        except Exception as e:
            logger.error(f"移动目录时出错: {src_path}, 错误: {str(e)}")
            return False
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

class StrmService:
    def __init__(self):
        self.settings = Settings()
        self.alist_client = None
        self._stop_flag = False
        self._skip_dirs = {
            '@eaDir',          # 群晖缩略图目录
            '#recycle',        # 回收站
            '.DS_Store',       # Mac系统文件
            '$RECYCLE.BIN',    # Windows回收站
            'System Volume Information',  # Windows系统目录
            '@Recently-Snapshot'  # 群晖快照目录
        }
        self._processed_files = 0
        self._total_size = 0
        self._is_running = False
        self._cache_file = os.path.join(self.settings.cache_dir, 'processed_dirs.json')
        self._processed_dirs = self._load_cache()
    
    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager
    
    def _load_cache(self) -> dict:
        """加载缓存"""
        try:
            os.makedirs(self.settings.cache_dir, exist_ok=True)
            if os.path.exists(self._cache_file):
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载缓存失败: {str(e)}")
        return {}
    
    def _save_cache(self):
        """保存缓存"""
        try:
            os.makedirs(self.settings.cache_dir, exist_ok=True)
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._processed_dirs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {str(e)}")
    
    def _get_dir_hash(self, path: str, files: list) -> str:
        """计算目录内容的哈希值"""
        # 只处理视频文件
        video_files = [
            f for f in files 
            if not f.get('is_dir', False) and self._is_video_file(f['name'])
            and f.get('size', 0) >= self.settings.min_file_size * 1024 * 1024  # 检查文件大小
        ]
        
        # 按名称排序确保一致性
        content = path + ''.join(sorted([
            f"{f['name']}_{f['size']}_{f['modified']}"
            for f in video_files
        ]))
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    async def clear_cache(self):
        """清除缓存"""
        try:
            self._processed_dirs = {}
            if os.path.exists(self._cache_file):
                os.remove(self._cache_file)
            logger.info("缓存已清除")
            return {"status": "success", "message": "缓存已清除"}
        except Exception as e:
            error_msg = f"清除缓存失败: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
    
    def _should_skip_directory(self, path: str) -> bool:
        """检查是否应该跳过某些目录"""
        # 检查系统目录
        if any(skip_dir in path for skip_dir in self._skip_dirs):
            return True
            
        # 检查用户配置的目录
        if any(skip_folder in path for skip_folder in self.settings.skip_folders_list):
            logger.info(f"跳过用户配置的目录: {path}")
            return True
            
        # 检查用户配置的模式
        if any(re.search(pattern, path) for pattern in self.settings.skip_patterns_list):
            logger.info(f"跳过匹配模式的目录: {path}")
            return True
            
        return False
    
    def _should_skip_file(self, filename: str) -> bool:
        """检查是否应该跳过某些文件"""
        # 检查文件扩展名
        ext = os.path.splitext(filename)[1].lower()
        
        # 如果开启了下载元数据，不跳过元数据文件
        if self.settings.download_metadata:
            metadata_extensions = {'.ass', '.ssa', '.srt', '.png', '.nfo', '.jpg', '.jpeg'}
            if ext in metadata_extensions:
                return False
        
        if ext in self.settings.skip_extensions_list:
            logger.info(f"跳过指定扩展名的文件: {filename}")
            return True
            
        # 检查用户配置的模式
        if any(re.search(pattern, filename) for pattern in self.settings.skip_patterns_list):
            logger.info(f"跳过匹配模式的文件: {filename}")
            return True
            
        return False
    
    def stop(self):
        """设置停止标志"""
        if not self._is_running:
            return
        self._stop_flag = True
        logger.info("收到停止信号，正在优雅停止...")
    
    async def strm(self):
        """生成strm文件"""
        if self._is_running:
            logger.warning("扫描任务已在运行中")
            return
            
        try:
            self._stop_flag = False
            self._is_running = True
            self._processed_files = 0
            self._total_size = 0
            
            self.alist_client = AlistClient(
                self.settings.alist_url,
                self.settings.alist_token
            )
            
            # 确保输出目录存在
            os.makedirs(self.settings.output_dir, exist_ok=True)
            
            start_time = time.time()
            logger.info(f"开始扫描: {self.settings.alist_scan_path}")
            
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(f"🚀 开始扫描: {self.settings.alist_scan_path}")
            
            await self._process_directory(self.settings.alist_scan_path)
            
            if self._stop_flag:
                await service_manager.telegram_service.send_message("⏹ 扫描已停止")
                logger.info("扫描已停止")
                return
            
            # 如果启用了删除空文件夹功能，执行清理
            if self.settings.remove_empty_dirs:
                self._remove_empty_directories(self.settings.output_dir)
                logger.info("已清理空文件夹")
            
            duration = time.time() - start_time
            summary = (
                f"✅ 扫描完成\n"
                f"📁 处理文件: {self._processed_files} 个\n"
                f"💾 总大小: {self._format_size(self._total_size)}\n"
                f"⏱ 耗时: {int(duration)}秒"
            )
            logger.info(summary)
            await service_manager.telegram_service.send_message(summary)
            
        except Exception as e:
            error_msg = f"❌ 扫描出错: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
            raise
        finally:
            self._is_running = False
            self._stop_flag = False
            await self.close()
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"
    
    async def close(self):
        """关闭服务"""
        if self.alist_client:
            await self.alist_client.close()
    
    async def _process_directory(self, path):
        """处理目录"""
        if self._stop_flag:
            return

        # 检查是否应该跳过此目录
        if self._should_skip_directory(path):
            logger.info(f"跳过系统目录: {path}")
            return

        try:
            files = await self.alist_client.list_files(path)
            if not files:  # 如果是空列表，直接返回
                logger.debug(f"目录为空或无法访问: {path}")
                return

            # 计算目录哈希
            dir_hash = self._get_dir_hash(path, files)
            
            # 检查缓存
            if not self.settings.refresh and path in self._processed_dirs:
                if self._processed_dirs[path] == dir_hash:
                    logger.info(f"目录未变化，跳过处理: {path}")
                    return
                else:
                    logger.info(f"目录内容已变化，重新处理: {path}")
            
            # 处理文件和子目录
            has_processed_files = False
            for file in files:
                if self._stop_flag:
                    return
                    
                full_path = f"{path}/{file['name']}"
                
                if file.get('is_dir', False):
                    await self._process_directory(full_path)
                else:
                    # 只有成功处理了视频文件才标记为已处理
                    if await self._process_file(full_path, file):
                        has_processed_files = True
                    
                # 添加短暂延时，让出控制权
                await asyncio.sleep(0.01)
            
            # 只有当目录中有处理过的文件时才更新缓存
            if has_processed_files:
                self._processed_dirs[path] = dir_hash
                self._save_cache()
                    
        except Exception as e:
            logger.error(f"处理目录 {path} 时出错: {str(e)}")
            return
    
    async def _download_file(self, url: str, path: str):
        """下载文件
        
        Args:
            url: 文件URL
            path: 保存路径
        """
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream('GET', url) as response:
                    response.raise_for_status()
                    # 确保目录存在
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    # 写入文件
                    with open(path, 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
            logger.info(f"文件下载成功: {path}")
            return True
        except Exception as e:
            logger.error(f"文件下载失败: {str(e)}")
            return False
    
    async def _process_file(self, path, file_info):
        """处理单个文件
        
        Args:
            path: 文件所在目录路径
            file_info: 文件信息
            
        Returns:
            bool: 是否成功处理
        """
        try:
            if self._stop_flag:
                return False
                
            filename = file_info['name']
            if self._should_skip_file(filename):
                return False
                
            ext = os.path.splitext(filename)[1].lower()
            metadata_extensions = {'.ass', '.ssa', '.srt', '.png', '.nfo', '.jpg', '.jpeg'}
            
            # 如果是元数据文件且开启了下载元数据
            if self.settings.download_metadata and ext in metadata_extensions:
                # 构建下载路径
                rel_path = path.replace(self.settings.alist_scan_path, '').lstrip('/')
                download_path = os.path.join(self.settings.output_dir, rel_path)
                
                # 构建下载URL
                file_path = path
                if not file_path.startswith('/'):
                    file_path = '/' + file_path
                download_url = f"{self.settings.alist_url}/d{quote(file_path)}"
                
                # 下载文件
                success = await self._download_file(download_url, download_path)
                if success:
                    self._processed_files += 1
                    self._total_size += file_info.get('size', 0)
                return success
            
            # 检查文件大小（只对视频文件）
            if file_info.get('size', 0) < self.settings.min_file_size * 1024 * 1024:
                logger.debug(f"跳过小文件: {filename}")
                return False
                
            # 只处理视频文件
            if not self._is_video_file(filename):
                return False
                
            # 构建相对路径
            rel_path = path.replace(self.settings.alist_scan_path, '').lstrip('/')
            
            # 构建输出路径，移除.mkv后缀
            output_path = os.path.join(self.settings.output_dir, os.path.splitext(rel_path)[0])
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 构建strm文件路径
            strm_path = output_path + '.strm'
            
            # 构建strm文件内容
            file_path = path
            if not file_path.startswith('/'):
                file_path = '/' + file_path
            strm_url = f"{self.settings.alist_url}/d{quote(file_path)}"
            
            # 检查文件是否已存在且内容相同
            if os.path.exists(strm_path):
                with open(strm_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read().strip()
                if existing_content == strm_url:
                    return False
            
            # 写入strm文件
            with open(strm_path, 'w', encoding='utf-8') as f:
                f.write(strm_url)
            
            self._processed_files += 1
            self._total_size += file_info.get('size', 0)
            
            # 记录STRM文件信息
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(
                f"✅ 生成STRM文件:\n"
                f"源文件: {file_path}\n"
                f"STRM路径: {strm_path}\n"
                f"STRM内容: {strm_url}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"处理文件失败 {filename}: {str(e)}")
            return False
    
    def _is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件"""
        ext = os.path.splitext(filename)[1].lower()
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.rmvb'}
        return ext in video_extensions
    
    def _remove_empty_directories(self, path):
        """递归删除空文件夹"""
        try:
            # 遍历目录
            for root, dirs, files in os.walk(path, topdown=False):
                # 对于每个子目录
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        # 检查目录是否为空
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                            logger.info(f"删除空文件夹: {dir_path}")
                    except Exception as e:
                        logger.error(f"删除文件夹 {dir_path} 失败: {str(e)}")
        except Exception as e:
            logger.error(f"清理空文件夹时出错: {str(e)}") 
    
    async def move_strm(self, src_path: str, dest_path: str) -> dict:
        """移动strm文件和对应的云盘文件
        
        Args:
            src_path: 源文件路径（相对于output_dir的路径）
            dest_path: 目标文件路径（相对于output_dir的路径）
            
        Returns:
            dict: 处理结果
        """
        try:
            # 确保alist客户端已初始化
            if not self.alist_client:
                self.alist_client = AlistClient(
                    self.settings.alist_url,
                    self.settings.alist_token
                )
            
            # 构建完整路径
            src_strm = os.path.join(self.settings.output_dir, src_path)
            dest_strm = os.path.join(self.settings.output_dir, dest_path)
            
            # 检查源文件是否存在
            if not os.path.exists(src_strm):
                return {"success": False, "message": f"源文件不存在: {src_path}"}
            
            # 读取strm文件内容
            with open(src_strm, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # 从URL中提取云盘路径
            cloud_path = content.replace(f"{self.settings.alist_url}/d", "")
            if self.settings.encode:
                from urllib.parse import unquote
                cloud_path = unquote(cloud_path)
            
            # 构建目标云盘路径
            dest_cloud_path = self.settings.alist_scan_path + dest_path[:-5]  # 移除.strm后缀
            
            # 移动云盘文件
            if os.path.isdir(src_strm):
                success = await self.alist_client.move_directory(cloud_path, dest_cloud_path)
            else:
                success = await self.alist_client.move_file(cloud_path, dest_cloud_path)
            
            if not success:
                return {"success": False, "message": "移动云盘文件失败"}
            
            # 确保目标目录存在
            os.makedirs(os.path.dirname(dest_strm), exist_ok=True)
            
            # 移动strm文件
            os.rename(src_strm, dest_strm)
            
            # 更新strm文件内容
            base_url = self.settings.alist_url.rstrip('/')
            if self.settings.encode:
                encoded_path = quote(dest_cloud_path)
                play_url = f"{base_url}/d{encoded_path}"
            else:
                play_url = f"{base_url}/d{dest_cloud_path}"
            
            with open(dest_strm, 'w', encoding='utf-8') as f:
                f.write(play_url)
            
            return {
                "success": True,
                "message": f"成功移动: {src_path} -> {dest_path}"
            }
            
        except Exception as e:
            error_msg = f"移动文件失败: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg} 