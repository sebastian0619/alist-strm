import os
import httpx
import time
import re
from urllib.parse import quote
from loguru import logger
from config import Settings
from typing import List, Optional
import asyncio

class StrmService:
    def __init__(self):
        self.settings = Settings()
        self.alist_client = None
        self._stop_flag = False  # 添加停止标志
    
    def stop(self):
        """设置停止标志"""
        self._stop_flag = True
        logger.info("收到停止信号，正在优雅停止...")
    
    async def strm(self):
        """生成strm文件"""
        try:
            self._stop_flag = False  # 重置停止标志
            self.alist_client = AlistClient(
                self.settings.alist_url,
                self.settings.alist_token
            )
            
            # 确保输出目录存在
            os.makedirs(self.settings.output_dir, exist_ok=True)
            
            logger.info(f"开始扫描: {self.settings.alist_scan_path}")
            await self._process_directory(self.settings.alist_scan_path)
            logger.info("扫描完成")
            
        except Exception as e:
            logger.error(f"扫描过程出错: {str(e)}")
            raise
        finally:
            await self.close()
    
    async def _process_directory(self, path):
        """处理目录"""
        if self._stop_flag:  # 检查停止标志
            logger.info("检测到停止信号，正在结束扫描...")
            return

        try:
            files = await self.alist_client.list_files(path)
            
            for file in files:
                if self._stop_flag:  # 每个文件处理前检查停止标志
                    return
                    
                full_path = f"{path}/{file['name']}"
                
                if file['is_dir']:
                    await self._process_directory(full_path)
                else:
                    await self._process_file(full_path, file)
                    
        except Exception as e:
            logger.error(f"处理目录 {path} 时出错: {str(e)}")
            raise
    
    async def _process_file(self, path, file_info):
        """处理文件"""
        if self._stop_flag:  # 检查停止标志
            return
            
        # ... 其余代码保持不变 ... 