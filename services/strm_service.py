import os
import httpx
import time
import re
import json
import hashlib
from urllib.parse import quote
from loguru import logger
from config import Settings
from typing import List, Optional
import asyncio
from services.telegram_service import TelegramService

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
        self.telegram = TelegramService()
        self._stop_flag = False
        self._skip_dirs = {
            '@eaDir',          # 群晖缩略图目录
            '#recycle',        # 回收站
            '.DS_Store',       # Mac系统文件
            '$RECYCLE.BIN',    # Windows回收站
            'System Volume Information',  # Windows系统目录
            '@Recently-Snapshot'  # 群晖快照目录
        }
        self._processed_files = 0
        self._total_size = 0
        self._is_running = False
        self._cache_file = os.path.join(self.settings.cache_dir, 'processed_dirs.json')
        self._processed_dirs = self._load_cache()
    
    def _load_cache(self) -> dict:
        """加载缓存"""
        try:
            os.makedirs(self.settings.cache_dir, exist_ok=True)
            if os.path.exists(self._cache_file):
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载缓存失败: {str(e)}")
        return {}
    
    def _save_cache(self):
        """保存缓存"""
        try:
            os.makedirs(self.settings.cache_dir, exist_ok=True)
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._processed_dirs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {str(e)}")
    
    def _get_dir_hash(self, path: str, files: list) -> str:
        """计算目录内容的哈希值"""
        content = path + ''.join(sorted([
            f"{f['name']}_{f['size']}_{f['modified']}"
            for f in files if not f.get('is_dir', False)
        ]))
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    async def clear_cache(self):
        """清除缓存"""
        try:
            self._processed_dirs = {}
            if os.path.exists(self._cache_file):
                os.remove(self._cache_file)
            logger.info("缓存已清除")
            return {"status": "success", "message": "缓存已清除"}
        except Exception as e:
            error_msg = f"清除缓存失败: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
    
    def _should_skip_directory(self, path: str) -> bool:
        """检查是否应该跳过某些目录"""
        # 检查系统目录
        if any(skip_dir in path for skip_dir in self._skip_dirs):
            return True
            
        # 检查用户配置的目录
        if any(skip_folder in path for skip_folder in self.settings.skip_folders_list):
            logger.info(f"跳过用户配置的目录: {path}")
            return True
            
        # 检查用户配置的模式
        if any(re.search(pattern, path) for pattern in self.settings.skip_patterns_list):
            logger.info(f"跳过匹配模式的目录: {path}")
            return True
            
        return False
    
    def _should_skip_file(self, filename: str) -> bool:
        """检查是否应该跳过某些文件"""
        # 检查文件扩展名
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.settings.skip_extensions_list:
            logger.info(f"跳过指定扩展名的文件: {filename}")
            return True
            
        # 检查用户配置的模式
        if any(re.search(pattern, filename) for pattern in self.settings.skip_patterns_list):
            logger.info(f"跳过匹配模式的文件: {filename}")
            return True
            
        return False
    
    def stop(self):
        """设置停止标志"""
        if not self._is_running:
            return
        self._stop_flag = True
        logger.info("收到停止信号，正在优雅停止...")
    
    async def strm(self):
        """生成strm文件"""
        if self._is_running:
            logger.warning("扫描任务已在运行中")
            return
            
        try:
            self._stop_flag = False
            self._is_running = True
            self._processed_files = 0
            self._total_size = 0
            
            self.alist_client = AlistClient(
                self.settings.alist_url,
                self.settings.alist_token
            )
            
            # 确保输出目录存在
            os.makedirs(self.settings.output_dir, exist_ok=True)
            
            start_time = time.time()
            logger.info(f"开始扫描: {self.settings.alist_scan_path}")
            await self.telegram.send_message(f"🚀 开始扫描: {self.settings.alist_scan_path}")
            
            await self._process_directory(self.settings.alist_scan_path)
            
            if self._stop_flag:
                await self.telegram.send_message("⏹ 扫描已停止")
                logger.info("扫描已停止")
                return
            
            # 如果启用了删除空文件夹功能，执行清理
            if self.settings.remove_empty_dirs:
                self._remove_empty_directories(self.settings.output_dir)
                logger.info("已清理空文件夹")
            
            duration = time.time() - start_time
            summary = (
                f"✅ 扫描完成\n"
                f"📁 处理文件: {self._processed_files} 个\n"
                f"💾 总大小: {self._format_size(self._total_size)}\n"
                f"⏱ 耗时: {int(duration)}秒"
            )
            logger.info(summary)
            await self.telegram.send_message(summary)
            
        except Exception as e:
            error_msg = f"❌ 扫描出错: {str(e)}"
            logger.error(error_msg)
            await self.telegram.send_message(error_msg)
            raise
        finally:
            self._is_running = False
            self._stop_flag = False
            await self.close()
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"
    
    async def close(self):
        """关闭服务"""
        if self.alist_client:
            await self.alist_client.close()
        await self.telegram.close()
    
    async def _process_directory(self, path):
        """处理目录"""
        if self._stop_flag:
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

            # 计算目录哈希
            dir_hash = self._get_dir_hash(path, files)
            
            # 检查缓存
            if not self.settings.refresh and path in self._processed_dirs:
                if self._processed_dirs[path] == dir_hash:
                    logger.info(f"目录未变化，跳过处理: {path}")
                    return
            
            # 处理文件和子目录
            for file in files:
                if self._stop_flag:
                    return
                    
                full_path = f"{path}/{file['name']}"
                
                if file.get('is_dir', False):
                    if self._stop_flag:  # 每次处理子目录前检查停止标志
                        return
                    await self._process_directory(full_path)
                else:
                    if self._stop_flag:  # 每次处理文件前检查停止标志
                        return
                    await self._process_file(full_path, file)
                    
                # 添加短暂延时，让出控制权
                await asyncio.sleep(0.01)
            
            # 更新缓存
            self._processed_dirs[path] = dir_hash
            self._save_cache()
                    
        except Exception as e:
            logger.error(f"处理目录 {path} 时出错: {str(e)}")
            return
    
    async def _process_file(self, path, file_info):
        """处理文件"""
        if self._stop_flag:
            return
            
        try:
            filename = file_info['name']
            
            # 检查是否应该跳过此文件
            if self._should_skip_file(filename):
                return
                
            if self._is_video_file(filename):
                # 更新统计信息
                self._processed_files += 1
                self._total_size += file_info.get('size', 0)
                
                # 构建STRM文件路径
                relative_path = path.replace(self.settings.alist_scan_path, "").lstrip("/")
                strm_path = os.path.join(self.settings.output_dir, relative_path)
                strm_path = os.path.splitext(strm_path)[0] + ".strm"
                
                # 确保目录存在
                os.makedirs(os.path.dirname(strm_path), exist_ok=True)
                
                # 生成播放链接
                base_url = self.settings.alist_url.rstrip('/')
                encoded_path = '/d' + quote(path)  # 只对路径部分进行编码
                play_url = f"{base_url}{encoded_path}" if self.settings.encode else f"{base_url}/d{path}"
                
                # 写入strm文件
                with open(strm_path, "w", encoding="utf-8") as f:
                    f.write(play_url)
                
                logger.info(f"创建STRM文件: {strm_path}")
                
        except Exception as e:
            error_msg = f"处理文件失败: {path}, 错误: {str(e)}"
            logger.error(error_msg)
            await self.telegram.send_message(f"⚠️ {error_msg}")
    
    def _is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件"""
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.rmvb'}
        return os.path.splitext(filename)[1].lower() in video_extensions 
    
    def _remove_empty_directories(self, path):
        """递归删除空文件夹"""
        try:
            # 遍历目录
            for root, dirs, files in os.walk(path, topdown=False):
                # 对于每个子目录
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        # 检查目录是否为空
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                            logger.info(f"删除空文件夹: {dir_path}")
                    except Exception as e:
                        logger.error(f"删除文件夹 {dir_path} 失败: {str(e)}")
        except Exception as e:
            logger.error(f"清理空文件夹时出错: {str(e)}") 