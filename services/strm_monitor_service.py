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
        
    def on_moved(self, event):
        """当文件或目录被移动时触发"""
        try:
            if not event.src_path.endswith('.strm'):
                return
                
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