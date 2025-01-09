import os
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Dict, Optional
import asyncio
import logging
import json

class StrmFileHandler(FileSystemEventHandler):
    def __init__(self, strm_service, alist_service):
        self.strm_service = strm_service
        self.alist_service = alist_service
        self.logger = logging.getLogger(__name__)
        
    def on_moved(self, event):
        if not event.is_directory and event.src_path.endswith('.strm'):
            asyncio.create_task(self._handle_strm_move(event.src_path, event.dest_path))
        elif event.is_directory:
            asyncio.create_task(self._handle_directory_move(event.src_path, event.dest_path))
            
    async def _handle_strm_move(self, src_path: str, dest_path: str):
        try:
            # 读取strm文件内容
            with open(dest_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            # 解析云盘路径
            if not content.startswith('http'):
                return
                
            # 获取相对路径
            src_rel_path = os.path.relpath(src_path, self.strm_service.strm_root)
            dest_rel_path = os.path.relpath(dest_path, self.strm_service.strm_root)
            
            # 更新云盘中的文件位置
            src_cloud_path = self._get_cloud_path(src_rel_path)
            dest_cloud_path = self._get_cloud_path(dest_rel_path)
            
            # 调用alist服务移动文件
            await self.alist_service.move_file(src_cloud_path, dest_cloud_path)
            
            # 更新strm文件内容中的路径
            new_content = content.replace(src_cloud_path, dest_cloud_path)
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            self.logger.info(f"已同步移动文件: {src_cloud_path} -> {dest_cloud_path}")
            
        except Exception as e:
            self.logger.error(f"处理strm文件移动时出错: {str(e)}")
            
    async def _handle_directory_move(self, src_path: str, dest_path: str):
        try:
            # 获取相对路径
            src_rel_path = os.path.relpath(src_path, self.strm_service.strm_root)
            dest_rel_path = os.path.relpath(dest_path, self.strm_service.strm_root)
            
            # 更新云盘中的目录位置
            src_cloud_path = self._get_cloud_path(src_rel_path)
            dest_cloud_path = self._get_cloud_path(dest_rel_path)
            
            # 调用alist服务移动目录
            await self.alist_service.move_directory(src_cloud_path, dest_cloud_path)
            
            # 更新目录下所有strm文件的内容
            for root, _, files in os.walk(dest_path):
                for file in files:
                    if file.endswith('.strm'):
                        file_path = os.path.join(root, file)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                        
                        if content.startswith('http'):
                            new_content = content.replace(src_cloud_path, dest_cloud_path)
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(new_content)
            
            self.logger.info(f"已同步移动目录: {src_cloud_path} -> {dest_cloud_path}")
            
        except Exception as e:
            self.logger.error(f"处理目录移动时出错: {str(e)}")
            
    def _get_cloud_path(self, rel_path: str) -> str:
        """将相对路径转换为云盘路径"""
        return '/' + rel_path.replace('\\', '/')

class StrmMonitorService:
    def __init__(self, strm_service, alist_service):
        self.strm_service = strm_service
        self.alist_service = alist_service
        self.observer = None
        self.logger = logging.getLogger(__name__)
        
    async def start(self):
        """启动监控服务"""
        try:
            event_handler = StrmFileHandler(self.strm_service, self.alist_service)
            self.observer = Observer()
            self.observer.schedule(event_handler, self.strm_service.strm_root, recursive=True)
            self.observer.start()
            self.logger.info(f"开始监控strm目录: {self.strm_service.strm_root}")
        except Exception as e:
            self.logger.error(f"启动监控服务时出错: {str(e)}")
            
    async def stop(self):
        """停止监控服务"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.logger.info("已停止监控服务") 