import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio
from loguru import logger
from functools import partial

class StrmFileHandler(FileSystemEventHandler):
    def __init__(self, strm_service, loop):
        self.strm_service = strm_service
        self.logger = logger
        self.loop = loop
        self._moving_files = set()  # 用于跟踪正在移动的文件
        
    def on_moved(self, event):
        """当文件或目录被移动时触发"""
        try:
            if not event.src_path.endswith('.strm'):
                return
                
            # 记录正在移动的文件
            self._moving_files.add(event.src_path)
                
            # 获取相对路径
            src_rel_path = os.path.relpath(event.src_path, self.strm_service.settings.output_dir)
            dest_rel_path = os.path.relpath(event.dest_path, self.strm_service.settings.output_dir)
            
            # 在事件循环中运行异步任务
            asyncio.run_coroutine_threadsafe(
                self._handle_move(src_rel_path, dest_rel_path),
                self.loop
            )
            
        except Exception as e:
            self.logger.error(f"处理文件移动事件时出错: {str(e)}")
        finally:
            # 移动完成后从集合中移除
            self._moving_files.discard(event.src_path)
            
    def on_deleted(self, event):
        """当文件被删除时触发"""
        try:
            if not event.src_path.endswith('.strm'):
                return
                
            # 如果文件正在移动中，不处理删除事件
            if event.src_path in self._moving_files:
                return
                
            # 获取相对路径
            rel_path = os.path.relpath(event.src_path, self.strm_service.settings.output_dir)
            
            # 在事件循环中运行异步任务
            asyncio.run_coroutine_threadsafe(
                self._handle_delete(rel_path),
                self.loop
            )
            
        except Exception as e:
            self.logger.error(f"处理文件删除事件时出错: {str(e)}")
            
    async def _handle_move(self, src_path: str, dest_path: str):
        """处理文件移动
        
        当strm文件被移动时：
        1. 读取源strm文件内容，获取原云盘文件路径
        2. 根据新的strm路径，构建新的云盘文件路径
        3. 移动云盘中的文件到新位置
        4. 更新移动后的strm文件内容
        """
        try:
            # 构建完整的strm文件路径
            src_strm_path = os.path.join(self.strm_service.settings.output_dir, src_path)
            dest_strm_path = os.path.join(self.strm_service.settings.output_dir, dest_path)
            
            if not os.path.exists(dest_strm_path):
                self.logger.error(f"源文件不存在: {src_path}")
                return
                
            # 读取strm文件内容，获取原云盘文件路径
            with open(dest_strm_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            # 从URL中提取云盘路径
            old_cloud_path = content.replace(f"{self.strm_service.settings.alist_url}/d", "")
            if self.strm_service.settings.encode:
                from urllib.parse import unquote
                old_cloud_path = unquote(old_cloud_path)
                
            # 构建新的云盘文件路径
            if not old_cloud_path.startswith(self.strm_service.settings.alist_scan_path):
                self.logger.error(f"云盘路径不在扫描路径下: {old_cloud_path}")
                return
                
            # 获取文件在扫描路径下的相对路径
            rel_cloud_path = old_cloud_path[len(self.strm_service.settings.alist_scan_path):].lstrip('/')
            
            # 根据新的strm路径构建新的云盘路径
            new_rel_path = os.path.dirname(dest_path)
            new_cloud_path = os.path.join(
                self.strm_service.settings.alist_scan_path,
                new_rel_path,
                os.path.basename(old_cloud_path)
            )
            
            # 移动云盘中的文件
            if os.path.isdir(dest_strm_path):
                success = await self.strm_service.alist_client.move_directory(old_cloud_path, new_cloud_path)
            else:
                success = await self.strm_service.alist_client.move_file(old_cloud_path, new_cloud_path)
                
            if success:
                # 更新strm文件内容
                new_content = f"{self.strm_service.settings.alist_url}/d{new_cloud_path}"
                if self.strm_service.settings.encode:
                    from urllib.parse import quote
                    new_content = quote(new_content)
                    
                with open(dest_strm_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                    
                self.logger.info(f"已移动文件并更新strm: {old_cloud_path} -> {new_cloud_path}")
            else:
                self.logger.error(f"移动云盘文件失败: {old_cloud_path}")
                
        except Exception as e:
            self.logger.error(f"处理移动操作时出错: {str(e)}")
            
    async def _handle_delete(self, rel_path: str):
        """处理文件删除
        
        例如：
        - strm文件路径: /data/电影/123/123.strm
        - 源文件路径: /123/video/电影/123.mkv
        - 归档路径: /123/video/archive/电影/123.mkv
        """
        try:
            # 读取strm文件内容（从备份或缓存中）
            strm_path = os.path.join(self.strm_service.settings.output_dir, rel_path)
            if not os.path.exists(strm_path):
                self.logger.warning(f"strm文件已不存在: {strm_path}")
                return
                
            with open(strm_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            # 从URL中提取云盘路径
            cloud_path = content.replace(f"{self.strm_service.settings.alist_url}/d", "")
            if self.strm_service.settings.encode:
                from urllib.parse import unquote
                cloud_path = unquote(cloud_path)
                
            # 获取相对路径（去掉strm后缀）
            rel_dir = os.path.dirname(rel_path)
            rel_name = os.path.splitext(os.path.basename(rel_path))[0]
            
            # 构建归档路径
            # 1. 获取相对于扫描路径的路径
            if not cloud_path.startswith(self.strm_service.settings.alist_scan_path):
                self.logger.error(f"云盘路径不在扫描路径下: {cloud_path}")
                return
                
            rel_cloud_path = cloud_path[len(self.strm_service.settings.alist_scan_path):].lstrip('/')
            
            # 2. 在扫描路径下的archive目录中构建归档路径
            archive_path = os.path.join(
                self.strm_service.settings.alist_scan_path,
                'archive',
                rel_cloud_path
            )
            
            # 移动文件到archive目录
            if os.path.isdir(strm_path):
                success = await self.strm_service.alist_client.move_directory(cloud_path, archive_path)
            else:
                success = await self.strm_service.alist_client.move_file(cloud_path, archive_path)
                
            if success:
                self.logger.info(f"已将文件移动到归档目录: {cloud_path} -> {archive_path}")
            else:
                self.logger.error(f"移动文件到归档目录失败: {cloud_path}")
                
        except Exception as e:
            self.logger.error(f"处理删除操作时出错: {str(e)}")

class StrmMonitorService:
    def __init__(self, strm_service):
        self.strm_service = strm_service
        self.observer = None
        self.logger = logger
        self.loop = None
        
    async def start(self):
        """启动监控服务"""
        try:
            # 获取当前事件循环
            self.loop = asyncio.get_running_loop()
            
            # 创建事件处理器，传入事件循环
            event_handler = StrmFileHandler(self.strm_service, self.loop)
            self.observer = Observer()
            self.observer.schedule(event_handler, self.strm_service.settings.output_dir, recursive=True)
            self.observer.start()
            self.logger.info(f"开始监控strm目录: {self.strm_service.settings.output_dir}")
        except Exception as e:
            self.logger.error(f"启动监控服务时出错: {str(e)}")
            
    async def stop(self):
        """停止监控服务"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.logger.info("已停止监控服务") 