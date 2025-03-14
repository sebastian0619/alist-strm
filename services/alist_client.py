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
            # 安全处理路径中的特殊字符
            src_dir = os.path.dirname(src_path)
            dst_dir = os.path.dirname(dest_path)
            basename = os.path.basename(src_path)
            
            logger.info(f"复制目录请求: 从 {src_dir} 到 {dst_dir}, 文件名: {basename}")
            
            # 构建请求数据
            data = {
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": [basename],
                "override": True  # 添加覆盖选项
            }
            
            # 发送请求
            response = await self.client.post("/api/fs/copy", json=data)
            response.raise_for_status()
            
            # 检查响应类型
            if response.headers.get("content-type", "").startswith("text/html"):
                logger.error(f"复制目录时收到HTML响应，可能是服务器错误。源路径: {src_path}")
                return False
            
            # 解析响应
            try:
                resp_data = response.json()
            except Exception as e:
                logger.error(f"解析复制目录响应时出错: {str(e)}, 响应内容: {response.text[:500]}")
                return False
            
            if resp_data.get("code") == 200:
                # 获取所有任务ID
                task_ids = [task["id"] for task in resp_data.get("data", {}).get("tasks", [])]
                
                if not task_ids:
                    logger.warning(f"复制目录没有生成任务ID: {src_path}")
                    return False
                    
                logger.info(f"等待任务完成: {task_ids}")
                
                # 等待所有任务完成
                if await self.wait_for_tasks(task_ids):
                    logger.info(f"成功复制目录: {src_path} -> {dest_path}")
                    return True
                    
                logger.warning(f"复制任务失败: {src_path}")
                return False
                
            logger.warning(f"复制目录请求失败: {src_path}, 状态码: {resp_data.get('code')}, 消息: {resp_data.get('message')}")
            return False
            
        except Exception as e:
            logger.error(f"复制目录时出错: {src_path}, 错误: {str(e)}", exc_info=True)
            return False

    async def task_status(self, task_id: str):
        """获取任务状态"""
        data = {"id": task_id}
        try:
            response = await self.client.post(
                "/api/admin/task/status",
                json=data
            )
            response.raise_for_status()
            
            # 检查响应类型
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                logger.error(f"收到非JSON响应 ({content_type}): {response.text[:200]}...")
                return {"code": 500, "message": f"Invalid response type: {content_type}", "data": None}
                
            try:
                return response.json()
            except Exception as e:
                logger.error(f"解析任务状态JSON失败: {str(e)}")
                return {"code": 500, "message": f"JSON解析失败: {str(e)}", "data": None}
        except Exception as e:
            logger.error(f"获取任务状态失败: {str(e)}")
            return {"code": 500, "message": str(e), "data": None}
            
    async def wait_for_tasks(self, task_ids: list, timeout: int = 3600, check_interval: int = 2):
        """等待任务完成
        
        Args:
            task_ids: 任务ID列表
            timeout: 超时时间（秒）
            check_interval: 检查间隔（秒）
            
        Returns:
            bool: 所有任务是否成功完成
        """
        if not task_ids:
            logger.warning("没有任务ID需要等待")
            return False
            
        start_time = time.time()
        logger.info(f"开始等待 {len(task_ids)} 个任务完成，超时时间: {timeout}秒")
        
        while time.time() - start_time < timeout:
            all_done = True
            all_successful = True
            
            for task_id in task_ids:
                resp = await self.task_status(task_id)
                
                if resp.get("code") != 200:
                    logger.error(f"获取任务 {task_id} 状态失败: {resp.get('message')}")
                    all_successful = False
                    continue
                    
                task = resp.get("data", {})
                state = task.get("state", 0)
                
                if state == 0:  # 进行中
                    all_done = False
                    progress = task.get("progress", 0)
                    logger.info(f"任务 {task_id} 进度: {progress}%")
                elif state == 2:  # 失败
                    error = task.get("error", "未知错误")
                    logger.error(f"任务 {task_id} 失败: {error}")
                    all_successful = False
                elif state == 1:  # 完成
                    logger.info(f"任务 {task_id} 已完成")
            
            if all_done:
                if all_successful:
                    logger.info(f"所有任务已成功完成，耗时: {time.time() - start_time:.2f}秒")
                    return True
                else:
                    logger.error("部分任务失败")
                    return False
            
            # 等待一段时间再次检查
            await asyncio.sleep(check_interval)
        
        # 超时
        logger.error(f"等待任务完成超时 (>{timeout}秒)")
        return False

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose() 