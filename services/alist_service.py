import os
import aiohttp
from loguru import logger
from config import Settings

class AListService:
    def __init__(self):
        self.settings = Settings()
        self.session = None
        self.base_url = self.settings.alist_url
        self.logger = logger
        
    async def initialize(self):
        """初始化服务"""
        self.session = aiohttp.ClientSession()
        
    async def close(self):
        """关闭服务"""
        if self.session:
            await self.session.close()
            
    async def move_file(self, src_path: str, dest_path: str):
        """移动文件到新位置
        
        Args:
            src_path: 源文件路径
            dest_path: 目标文件路径
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            async with self.session.post(f"{self.base_url}/api/fs/move", json=data) as response:
                if response.status != 200:
                    raise Exception(f"移动文件失败: {await response.text()}")
                    
            self.logger.info(f"成功移动文件: {src_path} -> {dest_path}")
            
        except Exception as e:
            self.logger.error(f"移动文件时出错: {str(e)}")
            raise
            
    async def move_directory(self, src_path: str, dest_path: str):
        """移动目录到新位置
        
        Args:
            src_path: 源目录路径
            dest_path: 目标目录路径
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            async with self.session.post(f"{self.base_url}/api/fs/move", json=data) as response:
                if response.status != 200:
                    raise Exception(f"移动目录失败: {await response.text()}")
                    
            self.logger.info(f"成功移动目录: {src_path} -> {dest_path}")
            
        except Exception as e:
            self.logger.error(f"移动目录时出错: {str(e)}")
            raise 