import os
from typing import Optional
import httpx
from loguru import logger
from config import Settings
import importlib

class CopyService:
    def __init__(self):
        self.settings = Settings()
        self.client = httpx.AsyncClient(
            base_url=self.settings.alist_url,
            headers={"Authorization": self.settings.alist_token} if self.settings.alist_token else {}
        )
    
    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager
    
    async def sync_files(self, relative_path: str = ""):
        """同步文件夹中的所有文件"""
        try:
            logger.info(f"开始同步文件夹: {relative_path}")
            if not self.settings.src_dir or not self.settings.dst_dir:
                logger.warning("源目录或目标目录未配置")
                return
            
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(f"🔄 开始同步文件夹: {relative_path}")
                
            files = await self._list_files(os.path.join(self.settings.src_dir, relative_path))
            processed_files = 0
            total_size = 0
            
            for file in files:
                if self._should_copy_file(file):
                    await self._copy_file(file, relative_path)
                    processed_files += 1
                    total_size += file.get("size", 0)
            
            summary = (
                f"✅ 文件夹同步完成\n"
                f"📁 处理文件: {processed_files} 个\n"
                f"💾 总大小: {self._format_size(total_size)}"
            )
            logger.info(summary)
            await service_manager.telegram_service.send_message(summary)
                    
        except Exception as e:
            error_msg = f"❌ 同步文件夹失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
            raise
    
    async def sync_one_file(self, relative_path: str):
        """同步单个文件"""
        try:
            logger.info(f"开始同步文件: {relative_path}")
            if not self.settings.src_dir or not self.settings.dst_dir:
                logger.warning("源目录或目标目录未配置")
                return
            
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(f"🔄 开始同步文件: {relative_path}")
                
            file_info = await self._get_file_info(os.path.join(self.settings.src_dir, relative_path))
            if file_info and self._should_copy_file(file_info):
                await self._copy_file(file_info, os.path.dirname(relative_path))
                summary = (
                    f"✅ 文件同步完成\n"
                    f"📁 文件: {file_info.get('name')}\n"
                    f"💾 大小: {self._format_size(file_info.get('size', 0))}"
                )
                logger.info(summary)
                await service_manager.telegram_service.send_message(summary)
                
        except Exception as e:
            error_msg = f"❌ 同步文件失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
            raise
    
    async def _list_files(self, path: str) -> list:
        """获取目录下的文件列表"""
        try:
            response = await self.client.post("/api/fs/list", json={
                "path": path,
                "password": "",
                "refresh": self.settings.refresh,
                "page": 1,
                "per_page": 100
            })
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("content", [])
        except Exception as e:
            logger.error(f"获取文件列表失败: {str(e)}")
            raise
    
    async def _get_file_info(self, path: str) -> Optional[dict]:
        """获取文件信息"""
        try:
            response = await self.client.post("/api/fs/get", json={
                "path": path,
                "password": ""
            })
            response.raise_for_status()
            data = response.json()
            return data.get("data")
        except Exception as e:
            logger.error(f"获取文件信息失败: {str(e)}")
            return None
    
    def _should_copy_file(self, file: dict) -> bool:
        """判断文件是否需要复制"""
        if not file.get("is_dir", True):  # 是文件
            size_mb = file.get("size", 0) / (1024 * 1024)  # 转换为MB
            return size_mb >= self.settings.min_file_size
        return False
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"
    
    async def _copy_file(self, file: dict, relative_path: str):
        """复制文件"""
        try:
            src_path = os.path.join(self.settings.src_dir, relative_path, file.get("name", ""))
            dst_path = os.path.join(self.settings.dst_dir, relative_path, file.get("name", ""))
            
            response = await self.client.post("/api/fs/copy", json={
                "src_dir": src_path,
                "dst_dir": dst_path,
                "create_dir": True
            })
            response.raise_for_status()
            logger.info(f"文件复制成功: {src_path} -> {dst_path}")
        except Exception as e:
            logger.error(f"复制文件失败: {str(e)}")
            raise
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose() 