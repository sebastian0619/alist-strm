import os
import httpx
import time
import re
from urllib.parse import quote
from loguru import logger
from config import Settings
from typing import List, Optional
import asyncio

class AlistClient:
    def __init__(self, base_url: str, token: str = None):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": token} if token else {},
            timeout=httpx.Timeout(90.0, connect=90.0, read=90.0, write=90.0)
        )
    
    async def list_files(self, path: str) -> list:
        """获取目录下的文件列表"""
        try:
            response = await self.client.post("/api/fs/list", json={
                "path": path,
                "password": "",
                "page": 1,
                "per_page": 0,
                "refresh": False
            })
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 200:
                content = data.get("data", {}).get("content", [])
                if content is None:  # 如果content为None，返回空列表
                    logger.warning(f"目录访问被拒绝或不存在: {path}")
                    return []
                return content
            logger.warning(f"获取目录列表失败: {path}, 状态码: {data.get('code')}")
            return []
        except Exception as e:
            logger.error(f"获取文件列表失败: {path}, 错误: {str(e)}")
            return []
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

class StrmService:
    def __init__(self):
        self.settings = Settings()
        self.alist_client = None
        self._stop_flag = False
        self._skip_dirs = {
            '@eaDir',          # 群晖缩略图目录
            '#recycle',        # 回收站
            '.DS_Store',       # Mac系统文件
            '$RECYCLE.BIN',    # Windows回收站
            'System Volume Information',  # Windows系统目录
            '@Recently-Snapshot'  # 群晖快照目录
        }
    
    def _should_skip_directory(self, path: str) -> bool:
        """检查是否应该跳过某些系统目录"""
        return any(skip_dir in path for skip_dir in self._skip_dirs)
    
    def stop(self):
        """设置停止标志"""
        self._stop_flag = True
        logger.info("收到停止信号，正在优雅停止...")
    
    async def strm(self):
        """生成strm文件"""
        try:
            self._stop_flag = False
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
    
    async def close(self):
        """关闭服务"""
        if self.alist_client:
            await self.alist_client.close()
    
    async def _process_directory(self, path):
        """处理目录"""
        if self._stop_flag:
            logger.info("检测到停止信号，正在结束扫描...")
            return

        # 检查是否应该跳过此目录
        if self._should_skip_directory(path):
            logger.info(f"跳过系统目录: {path}")
            return

        try:
            files = await self.alist_client.list_files(path)
            if not files:  # 如果是空列表，直接返回
                logger.debug(f"目录为空或无法访问: {path}")
                return
            
            for file in files:
                if self._stop_flag:
                    return
                    
                full_path = f"{path}/{file['name']}"
                
                if file.get('is_dir', False):
                    await self._process_directory(full_path)
                else:
                    await self._process_file(full_path, file)
                    
        except Exception as e:
            logger.error(f"处理目录 {path} 时出错: {str(e)}")
            return  # 出错时继续处理其他目录，而不是抛出异常
    
    async def _process_file(self, path, file_info):
        """处理文件"""
        if self._stop_flag:
            return
            
        try:
            if self._is_video_file(file_info['name']):
                # 构建STRM文件路径
                relative_path = path.replace(self.settings.alist_scan_path, "").lstrip("/")
                strm_path = os.path.join(self.settings.output_dir, relative_path)
                strm_path = os.path.splitext(strm_path)[0] + ".strm"
                
                # 确保目录存在
                os.makedirs(os.path.dirname(strm_path), exist_ok=True)
                
                # 生成播放链接
                play_url = f"{self.settings.alist_url}/d{path}"
                if self.settings.encode:
                    play_url = quote(play_url)
                
                # 写入strm文件
                with open(strm_path, "w", encoding="utf-8") as f:
                    f.write(play_url)
                
                logger.info(f"创建STRM文件: {strm_path}")
                
        except Exception as e:
            logger.error(f"处理文件失败: {path}, 错误: {str(e)}")
    
    def _is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件"""
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.rmvb'}
        return os.path.splitext(filename)[1].lower() in video_extensions 