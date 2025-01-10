import os
import httpx
from loguru import logger
from config import Settings

class AListService:
    def __init__(self):
        self.settings = Settings()
        self.client = None
        self.base_url = self.settings.alist_url
        self.logger = logger
        
    async def initialize(self):
        """初始化服务"""
        self.client = httpx.AsyncClient()
        
    async def close(self):
        """关闭服务"""
        if self.client:
            await self.client.aclose()
            
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
            
            response = await self.client.post(f"{self.base_url}/api/fs/move", json=data)
            if response.status_code != 200:
                raise Exception(f"移动文件失败: {response.text}")
                    
            self.logger.info(f"成功移动文件: {src_path} -> {dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"移动文件时出错: {str(e)}")
            return False
            
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
            
            response = await self.client.post(f"{self.base_url}/api/fs/move", json=data)
            if response.status_code != 200:
                raise Exception(f"移动目录失败: {response.text}")
                    
            self.logger.info(f"成功移动目录: {src_path} -> {dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"移动目录时出错: {str(e)}")
            return False
            
    async def delete_file(self, path: str):
        """删除文件
        
        Args:
            path: 文件路径
        """
        try:
            data = {
                "dir": os.path.dirname(path),
                "names": [os.path.basename(path)]
            }
            
            response = await self.client.post(f"{self.base_url}/api/fs/remove", json=data)
            if response.status_code != 200:
                raise Exception(f"删除文件失败: {response.text}")
                    
            self.logger.info(f"成功删除文件: {path}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除文件时出错: {str(e)}")
            return False
            
    async def delete_directory(self, path: str):
        """删除目录
        
        Args:
            path: 目录路径
        """
        try:
            data = {
                "dir": os.path.dirname(path),
                "names": [os.path.basename(path)]
            }
            
            response = await self.client.post(f"{self.base_url}/api/fs/remove", json=data)
            if response.status_code != 200:
                raise Exception(f"删除目录失败: {response.text}")
                    
            self.logger.info(f"成功删除目录: {path}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除目录时出错: {str(e)}")
            return False 