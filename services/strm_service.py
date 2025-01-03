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
        self.client = httpx.AsyncClient(
            base_url=self.settings.alist_url,
            headers={"Authorization": self.settings.alist_token} if self.settings.alist_token else {},
            timeout=httpx.Timeout(90.0, connect=90.0, read=90.0, write=90.0)
        )
        self.cache: List[str] = []
    
    def _sanitize_filename(self, filename: str, max_length: int = 250) -> str:
        """清理文件名，移除非法字符并限制长度"""
        # 移除Windows文件系统中的非法字符
        clean_name = re.sub(r'[\\/:*?"<>|]', '', filename)
        # 限制文件名长度
        if len(clean_name) > max_length:
            name, ext = os.path.splitext(clean_name)
            clean_name = name[:max_length-len(ext)] + ext
        return clean_name
    
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
            # 移除扫描路径前缀，只保留后面的路径结构
            relative_path = path.replace(self.settings.alist_scan_path, "").lstrip("/")
            output_path = os.path.join(self.settings.output_dir, relative_path)
            await self._process_directory(path, output_path)
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
    
    def _should_skip_directory(self, path: str) -> bool:
        """检查是否应该跳过某些系统目录"""
        skip_dirs = {
            '@eaDir',  # 群晖缩略图目录
            '#recycle', # 回收站
            '.DS_Store',  # Mac系统文件
            '$RECYCLE.BIN',  # Windows回收站
            'System Volume Information',  # Windows系统目录
            '@Recently-Snapshot'  # 群晖快照目录
        }
        return any(skip_dir in path for skip_dir in skip_dirs)
    
    async def _process_directory(self, path: str, local_path: str):
        """处理目录中的所有文件"""
        try:
            # 检查是否应该跳过此目录
            if self._should_skip_directory(path):
                logger.info(f"跳过系统目录: {path}")
                return

            logger.debug(f"开始处理目录: {path} -> {local_path}")
            # 确保输出目录存在
            os.makedirs(local_path, exist_ok=True)
            
            try:
                files = await self._list_files(path)
                if not files:  # 如果目录为空或获取失败
                    logger.warning(f"目录为空或无法访问: {path}")
                    return
            except Exception as e:
                logger.error(f"获取目录列表失败: {path}, 错误: {str(e)}")
                return  # 继续处理其他目录，而不是抛出异常
            
            for file in files:
                if not file.get("name"):
                    logger.warning(f"跳过无效文件: {file}")
                    continue
                
                name = file.get("name")
                if file.get("is_dir", False):
                    # 处理子目录
                    clean_name = self._sanitize_filename(name)
                    new_path = os.path.join(path, name)
                    new_local_path = os.path.join(local_path, clean_name)
                    # 如果启用了慢速模式，则在处理每个目录后等待
                    if self.settings.slow_mode:
                        await asyncio.sleep(1)
                    await self._process_directory(new_path, new_local_path)
                else:
                    # 检查是否已处理过
                    full_path = os.path.join(path, name)
                    if full_path in self.cache:
                        continue
                    
                    # 处理文件
                    if self._is_video_file(name):
                        try:
                            await self._create_strm_file(file, local_path)
                        except Exception as e:
                            logger.error(f"处理文件失败: {name}, 错误: {str(e)}")
                            continue  # 继续处理其他文件
                    elif self.settings.is_down_sub and self._is_subtitle_file(name):
                        try:
                            await self._download_subtitle(file, local_path)
                        except Exception as e:
                            logger.error(f"下载字幕失败: {name}, 错误: {str(e)}")
                            continue  # 继续处理其他文件
        except Exception as e:
            logger.error(f"处理目录失败: {path}, 错误: {str(e)}")
            # 不再抛出异常，让程序继续处理其他目录
            return
    
    async def _create_strm_file(self, file: dict, local_path: str):
        """创建strm文件"""
        try:
            file_name = file.get("name")
            if not file_name:
                logger.error(f"文件信息缺少name字段: {file}")
                return
            
            # 构建文件路径
            file_path = file.get("path")
            if not file_path:
                # 如果没有path字段，尝试从当前目录和文件名构建
                parent_dir = os.path.dirname(local_path.replace(self.settings.output_dir, ""))
                file_path = os.path.join(parent_dir, file_name)
                logger.debug(f"文件信息缺少path字段，构建路径: {file_path}")
            
            strm_path = os.path.join(local_path, os.path.splitext(file_name)[0] + ".strm")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(strm_path), exist_ok=True)
            
            # 生成播放链接
            play_url = f"{self.settings.alist_url}/d{file_path}"
            if self.settings.encode:
                play_url = quote(play_url)
            
            # 写入strm文件
            with open(strm_path, "w", encoding="utf-8") as f:
                f.write(play_url)
            
            logger.info(f"创建strm文件成功: {strm_path} -> {play_url}")
        except Exception as e:
            logger.error(f"创建strm文件失败: {file_name if 'file_name' in locals() else 'unknown'}, 错误: {str(e)}")
            logger.debug(f"文件信息: {file}")
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
        """获取目录下的文件列表，添加重试机制"""
        for retry in range(3):  # 最多重试3次
            try:
                response = await self.client.post("/api/fs/list", json={
                    "path": path,
                    "password": "",
                    "refresh": self.settings.refresh,
                    "page": 1,
                    "per_page": 0  # 设置为0以获取所有结果
                })
                response.raise_for_status()
                data = response.json()
                if data.get("code") == 200:
                    content = data.get("data", {}).get("content", [])
                    if content is None:
                        logger.warning(f"目录访问被拒绝或不存在: {path}")
                        return []
                    # 确保每个文件对象都有完整的路径信息
                    for file in content:
                        if "path" not in file:
                            file["path"] = os.path.join(path, file.get("name", ""))
                    logger.debug(f"获取完成{path}, 文件数: {len(content)}")
                    return content
                else:
                    logger.warning(f"获取{path}第{retry + 1}次失败: {data}")
                    if retry < 2:  # 如果不是最后一次重试
                        await asyncio.sleep(1)  # 等待1秒后重试
                    continue
            except Exception as e:
                logger.error(f"获取文件列表失败: {str(e)}")
                if retry < 2:  # 如果不是最后一次重试
                    await asyncio.sleep(1)  # 等待1秒后重试
                continue
        logger.error(f"获取文件列表失败，已重试3次: {path}")
        return []  # 返回空列表而不是抛出异常
    
    async def _get_file_info(self, path: str) -> Optional[dict]:
        """获取文件信息，添加重试机制"""
        try:
            response = await self.client.post("/api/fs/get", json={
                "path": path,
                "password": "",
                "page": 1,
                "per_page": 0
            })
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 200:
                logger.debug(f"获取文件完成{path}")
                return data.get("data")
            else:
                logger.warning(f"获取文件失败: {data}")
                return None
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