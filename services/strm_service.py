import os
import httpx
from urllib.parse import quote
from loguru import logger
from config import Settings
from typing import List, Optional

class StrmService:
    def __init__(self):
        self.settings = Settings()
        self.client = httpx.AsyncClient(
            base_url=self.settings.alist_url,
            headers={"Authorization": self.settings.alist_token} if self.settings.alist_token else {}
        )
        self.cache: List[str] = []
    
    async def strm(self):
        """处理流媒体服务的主要逻辑"""
        try:
            logger.info("开始处理流媒体服务")
            await self.strm_dir(self.settings.alist_scan_path)
            logger.info("流媒体服务处理完成")
        except Exception as e:
            logger.error(f"流媒体服务处理失败: {str(e)}")
            raise
    
    async def strm_dir(self, path: str):
        """处理指定目录的流媒体文件"""
        try:
            logger.info(f"处理目录: {path}")
            await self._process_directory(path, os.path.join(self.settings.output_dir, path.lstrip("/")))
        except Exception as e:
            logger.error(f"处理目录失败: {path}, 错误: {str(e)}")
            raise
    
    async def strm_one_file(self, path: str):
        """处理单个文件"""
        try:
            logger.info(f"处理文件: {path}")
            file_info = await self._get_file_info(path)
            if file_info and self._is_video_file(file_info.get("name", "")):
                await self._create_strm_file(file_info, os.path.dirname(path))
        except Exception as e:
            logger.error(f"处理文件失败: {path}, 错误: {str(e)}")
            raise
    
    async def _process_directory(self, path: str, local_path: str):
        """处理目录中的所有文件"""
        try:
            files = await self._list_files(path)
            for file in files:
                if file.get("is_dir", False):
                    # 处理子目录
                    new_path = os.path.join(path, file["name"])
                    new_local_path = os.path.join(local_path, file["name"])
                    await self._process_directory(new_path, new_local_path)
                else:
                    # 处理文件
                    if self._is_video_file(file["name"]):
                        await self._create_strm_file(file, local_path)
                    elif self.settings.is_down_sub and self._is_subtitle_file(file["name"]):
                        await self._download_subtitle(file, local_path)
        except Exception as e:
            logger.error(f"处理目录失败: {path}, 错误: {str(e)}")
            raise
    
    async def _create_strm_file(self, file: dict, local_path: str):
        """创建strm文件"""
        try:
            file_name = file["name"]
            strm_path = os.path.join(local_path, os.path.splitext(file_name)[0] + ".strm")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(strm_path), exist_ok=True)
            
            # 生成播放链接
            play_url = f"{self.settings.alist_url}/d{file['path']}"
            if self.settings.encode:
                play_url = quote(play_url)
            
            # 写入strm文件
            with open(strm_path, "w", encoding="utf-8") as f:
                f.write(play_url)
            
            logger.info(f"创建strm文件成功: {strm_path}")
        except Exception as e:
            logger.error(f"创建strm文件失败: {file_name}, 错误: {str(e)}")
            raise
    
    async def _download_subtitle(self, file: dict, local_path: str):
        """下载字幕文件"""
        try:
            file_name = file["name"]
            save_path = os.path.join(local_path, file_name)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # 下载字幕文件
            response = await self.client.get(f"/d{file['path']}")
            response.raise_for_status()
            
            with open(save_path, "wb") as f:
                f.write(response.content)
            
            logger.info(f"下载字幕文件成功: {save_path}")
        except Exception as e:
            logger.error(f"下载字幕文件失败: {file_name}, 错误: {str(e)}")
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
    
    def _is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件"""
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.rmvb'}
        return os.path.splitext(filename)[1].lower() in video_extensions
    
    def _is_subtitle_file(self, filename: str) -> bool:
        """判断是否为字幕文件"""
        subtitle_extensions = {'.srt', '.ass', '.ssa', '.sub'}
        return os.path.splitext(filename)[1].lower() in subtitle_extensions
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose() 