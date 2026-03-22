import os
import httpx
import time
import re
import json
import hashlib
from urllib.parse import quote, unquote
from loguru import logger
from config import Settings
from typing import List, Optional
import asyncio
import importlib
from datetime import datetime

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

    def refresh_settings(self):
        """重新加载运行时配置。"""
        self.settings = Settings()
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
        
        # 从配置中获取元数据文件扩展名
        metadata_extensions = set(self.settings.metadata_extensions_list)
        
        # 如果是元数据文件且开启了下载元数据，不跳过
        if self.settings.download_metadata and ext in metadata_extensions:
            return False
        
        # 检查用户配置的模式
        if any(re.search(pattern, filename) for pattern in self.settings.skip_patterns_list):
            logger.info(f"跳过匹配模式的文件: {filename}")
            return True
            
        # 如果不是元数据文件，检查是否在跳过扩展名列表中
        if ext not in metadata_extensions and ext in self.settings.skip_extensions_list:
            logger.info(f"跳过指定扩展名的文件: {filename}")
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
            # 明确启用重定向跟随
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                logger.debug(f"开始下载文件: {url}")
                
                async with client.stream('GET', url) as response:
                    response.raise_for_status()
                    
                    # 记录响应信息
                    logger.debug(f"下载响应状态: {response.status_code}")
                    
                    # 确保目录存在
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    # 写入文件
                    with open(path, 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
            logger.info(f"文件下载成功: {path}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP状态错误: {e.response.status_code} - {url}")
            logger.error(f"响应内容: {e.response.text[:200]}")  # 仅记录前200个字符避免日志过大
            return False
        except Exception as e:
            logger.error(f"文件下载失败: {str(e)}")
            logger.error(f"下载URL: {url}")
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
            metadata_extensions = set(self.settings.metadata_extensions_list)
            
            # 如果是元数据文件且开启了下载元数据
            if self.settings.download_metadata and ext in metadata_extensions:
                # 构建完整的文件路径
                full_file_path = path
                if os.path.basename(path) != filename:
                    full_file_path = f"{path}/{filename}" if not path.endswith('/') else f"{path}{filename}"
                
                # 确保路径以 / 开头
                if not full_file_path.startswith('/'):
                    full_file_path = '/' + full_file_path
                
                # 替换路径前缀：从alist_scan_path替换为output_dir
                if not full_file_path.startswith(self.settings.alist_scan_path):
                    logger.error(f"文件路径不是以扫描路径开头: {full_file_path}")
                    logger.error(f"扫描路径前缀: {self.settings.alist_scan_path}")
                    return False
                
                # 计算相对路径
                relative_path = full_file_path[len(self.settings.alist_scan_path):].lstrip('/')
                download_path = os.path.join(self.settings.output_dir, relative_path)
                
                # 确保目录存在
                os.makedirs(os.path.dirname(download_path), exist_ok=True)
                
                # 构建下载URL
                download_url = f"{self.settings.alist_url}/d{quote(full_file_path)}"
                
                # 下载文件
                success = await self._download_file(download_url, download_path)
                if success:
                    self._processed_files += 1
                    self._total_size += file_info.get('size', 0)
                    logger.info(f"下载元数据文件成功: {download_path}")
                return success
            
            # 只处理视频文件
            if not self._is_video_file(filename):
                return False
                
            # 检查视频文件大小
            if file_info.get('size', 0) < self.settings.min_file_size * 1024 * 1024:
                logger.debug(f"跳过小视频文件: {filename}")
                return False
                
            # 构建完整的文件路径
            full_file_path = path
            if os.path.basename(path) != filename:
                full_file_path = f"{path}/{filename}" if not path.endswith('/') else f"{path}{filename}"
            
            # 确保路径以 / 开头
            if not full_file_path.startswith('/'):
                full_file_path = '/' + full_file_path
            
            # 简化路径转换逻辑
            logger.info(f"原始路径: {full_file_path}")
            logger.info(f"扫描路径前缀: {self.settings.alist_scan_path}")
            
            # 如果路径不是以alist_scan_path开头，记录错误并返回
            if not full_file_path.startswith(self.settings.alist_scan_path):
                logger.error(f"文件路径不是以扫描路径开头: {full_file_path}")
                logger.error(f"扫描路径前缀: {self.settings.alist_scan_path}")
                return False
                
            # 1. 计算相对路径 (从alist_scan_path之后开始)
            relative_path = full_file_path[len(self.settings.alist_scan_path):].lstrip('/')
            logger.info(f"相对路径: {relative_path}")
            
            # 2. 将扩展名修改为.strm，并在文件名后添加@remote(网盘)后缀
            base_path, _ = os.path.splitext(relative_path)
            # 在文件名后添加@remote(网盘)后缀，然后再添加.strm扩展名
            strm_relative_path = f"{base_path}@remote(网盘).strm"
            
            # 3. 根据output_dir构建STRM文件存放路径
            strm_path = os.path.join(self.settings.output_dir, strm_relative_path)
            logger.info(f"STRM文件路径: {strm_path}")
            
            # 确保STRM文件所在目录存在
            os.makedirs(os.path.dirname(strm_path), exist_ok=True)
            
            # 确定使用的URL基础地址（根据use_external_url开关决定是否使用外部地址）
            base_url = self.settings.alist_url
            if hasattr(self.settings, 'use_external_url') and self.settings.use_external_url and self.settings.alist_external_url:
                base_url = self.settings.alist_external_url
            base_url = base_url.rstrip('/')
            
            # 4. 构建STRM文件内容 - 原始文件的URL (base_url + /d + 原始路径)
            if self.settings.encode:
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
                with open(strm_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read().strip()
                if existing_content == strm_url:
                    logger.debug(f"STRM文件已存在且内容相同，跳过: {strm_path}")
                    return False
            
            # 写入strm文件
            with open(strm_path, 'w', encoding='utf-8') as f:
                f.write(strm_url)
            
            self._processed_files += 1
            self._total_size += file_info.get('size', 0)
            
            # 记录到日志
            logger.info(f"生成STRM文件成功: {strm_path} -> {strm_url}")
            
            # 将STRM文件添加到健康状态服务
            service_manager = self._get_service_manager()
            service_manager.health_service.add_strm_file(strm_path, full_file_path)
            
            # 存储原始路径和文件信息，便于后续查询
            media_info = {
                "path": strm_path,
                "source_path": full_file_path,
                "filename": filename,
                "title": os.path.splitext(filename)[0],
                "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 添加到Emby刷新队列，同时传递更多信息
            if hasattr(service_manager, 'emby_service') and service_manager.emby_service:
                service_manager.emby_service.add_to_refresh_queue(strm_path, media_info=media_info)
                logger.debug(f"已将STRM文件添加到Emby刷新队列: {strm_path}")
            
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
            
            # 从URL中提取云盘路径 - 简化提取逻辑
            if "/d" not in content:
                return {"success": False, "message": f"无法从STRM文件中提取云盘路径: {content}"}
                
            # 直接提取/d后面的部分作为云盘路径
            cloud_path = content.split("/d", 1)[1]
            
            # 如果编码了，需要解码
            if self.settings.encode:
                cloud_path = unquote(cloud_path)
            
            logger.info(f"提取的源云盘路径: {cloud_path}")
            
            # 从源文件路径中提取相对路径（去掉@remote(网盘).strm后缀）
            if src_path.endswith('@remote(网盘).strm'):
                src_relative = src_path[:-len('@remote(网盘).strm')]
            elif src_path.endswith('.strm'):
                src_relative = src_path[:-5]
            else:
                src_relative = src_path
                
            if dest_path.endswith('@remote(网盘).strm'):
                dest_relative = dest_path[:-len('@remote(网盘).strm')]
            elif dest_path.endswith('.strm'):
                dest_relative = dest_path[:-5]
            else:
                dest_relative = dest_path
            
            # 构建目标云盘路径 - 简单替换alist_scan_path后的相对路径部分
            dest_cloud_path = self.settings.alist_scan_path + dest_relative.lstrip('/')
            
            logger.info(f"构建的目标云盘路径: {dest_cloud_path}")
            
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
            
            # 确定使用的URL基础地址（根据use_external_url开关决定是否使用外部地址）
            base_url = self.settings.alist_url
            if hasattr(self.settings, 'use_external_url') and self.settings.use_external_url and self.settings.alist_external_url:
                base_url = self.settings.alist_external_url
            base_url = base_url.rstrip('/')
            
            # 更新strm文件内容
            if self.settings.encode:
                encoded_path = quote(dest_cloud_path)
                play_url = f"{base_url}/d{encoded_path}"
            else:
                play_url = f"{base_url}/d{dest_cloud_path}"
            
            # 写入strm文件
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
