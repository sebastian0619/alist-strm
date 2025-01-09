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
        """处理文件移动"""
        try:
            result = await self.strm_service.move_strm(src_path, dest_path)
            if not result["success"]:
                self.logger.error(f"移动失败: {result['message']}")
            else:
                self.logger.info(result["message"])
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
            # 1. 从cloud_path中获取文件扩展名
            _, ext = os.path.splitext(cloud_path)
            # 2. 在源目录的archive子目录下构建路径
            archive_path = os.path.join(
                self.strm_service.settings.alist_scan_path,
                'archive',
                rel_dir,
                rel_name + ext
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