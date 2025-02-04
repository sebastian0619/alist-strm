import os
import httpx
from loguru import logger
import asyncio
import time

class AlistClient:
    def __init__(self, base_url: str, token: str = None):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": token,  # 直接使用原始token
                "Content-Type": "application/json"
            } if token else {},
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
            
    async def move_file(self, src_path: str, dest_path: str) -> bool:
        """移动文件到新位置
        
        Args:
            src_path: 源文件路径
            dest_path: 目标文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            response = await self.client.post("/api/fs/move", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                logger.info(f"成功移动文件: {src_path} -> {dest_path}")
                return True
                
            logger.warning(f"移动文件失败: {src_path}, 状态码: {data.get('code')}")
            return False
            
        except Exception as e:
            logger.error(f"移动文件时出错: {src_path}, 错误: {str(e)}")
            return False
            
    async def move_directory(self, src_path: str, dest_path: str) -> bool:
        """移动目录到新位置
        
        Args:
            src_path: 源目录路径
            dest_path: 目标目录路径
            
        Returns:
            bool: 是否成功
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            response = await self.client.post("/api/fs/move", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                logger.info(f"成功移动目录: {src_path} -> {dest_path}")
                return True
                
            logger.warning(f"移动目录失败: {src_path}, 状态码: {data.get('code')}")
            return False
            
        except Exception as e:
            logger.error(f"移动目录时出错: {src_path}, 错误: {str(e)}")
            return False

    async def copy_file(self, src_path: str, dest_path: str) -> bool:
        """复制文件到新位置
        
        Args:
            src_path: 源文件路径
            dest_path: 目标文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            logger.info(f"发送复制请求: {data}")
            response = await self.client.post("/api/fs/copy", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                # 获取所有任务ID
                task_ids = [task["id"] for task in data.get("data", {}).get("tasks", [])]
                logger.info(f"等待任务完成: {task_ids}")
                
                # 等待所有任务完成
                if await self.wait_for_tasks(task_ids):
                    logger.info(f"成功复制文件: {src_path} -> {dest_path}")
                    return True
                    
                logger.warning(f"复制任务失败: {src_path}")
                return False
                
            logger.warning(f"复制文件失败: {src_path}, 状态码: {data.get('code')}")
            return False
            
        except Exception as e:
            logger.error(f"复制文件时出错: {src_path}, 错误: {str(e)}")
            return False

    async def copy_directory(self, src_path: str, dest_path: str) -> bool:
        """复制目录到新位置
        
        Args:
            src_path: 源目录路径
            dest_path: 目标目录路径
            
        Returns:
            bool: 是否成功
        """
        try:
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            response = await self.client.post("/api/fs/copy", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                # 获取所有任务ID
                task_ids = [task["id"] for task in data.get("data", {}).get("tasks", [])]
                logger.info(f"等待任务完成: {task_ids}")
                
                # 等待所有任务完成
                if await self.wait_for_tasks(task_ids):
                    logger.info(f"成功复制目录: {src_path} -> {dest_path}")
                    return True
                    
                logger.warning(f"复制任务失败: {src_path}")
                return False
                
            logger.warning(f"复制目录失败: {src_path}, 状态码: {data.get('code')}")
            return False
            
        except Exception as e:
            logger.error(f"复制目录时出错: {src_path}, 错误: {str(e)}")
            return False

    async def task_status(self, task_id: str):
        """获取任务状态"""
        data = {"id": task_id}  # 使用id作为参数名
        try:
            response = await self.client.post(
                "/api/admin/task/status",  # 使用admin/task/status API
                json=data
            )
            response.raise_for_status()
            if response.headers.get("content-type", "").startswith("text/html"):
                logger.error(f"收到HTML响应而不是JSON: {response.text}")
                return {"code": 500, "message": "Invalid response type", "data": None}
            return response.json()
        except Exception as e:
            logger.error(f"获取任务状态失败: {str(e)}")
            return {"code": 500, "message": str(e), "data": None}
            
    async def wait_for_tasks(self, task_ids: list, timeout: int = 3600):
        """等待任务完成"""
        start_time = time.time()
        while True:
            all_done = True
            for task_id in task_ids:
                resp = await self.task_status(task_id)
                logger.debug(f"任务 {task_id} 状态: {resp}")
                
                if resp.get("code") == 200:
                    task = resp.get("data", {})
                    state = task.get("state", 0)
                    if state == 0:  # 进行中
                        all_done = False
                        progress = task.get("progress", 0)
                        logger.info(f"任务 {task_id} 进度: {progress}%")
                    elif state == 2:  # 失败
                        error = task.get("error", "未知错误")
                        logger.error(f"任务 {task_id} 失败: {error}")
                        return False
                    elif state == 1:  # 完成
                        logger.info(f"任务 {task_id} 已完成")
                else:
                    logger.error(f"获取任务状态失败: {resp}")
                    return False
            
            if all_done:
                logger.info("所有任务完成")
                return True
                
            if time.time() - start_time > timeout:
                logger.error("等待任务完成超时")
                return False
                
            # 对于大文件，增加检查间隔时间，避免频繁请求
            await asyncio.sleep(2)
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose() 