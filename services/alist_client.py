import os
import httpx
from loguru import logger
import asyncio
import time
from urllib.parse import quote
import json

class AlistClient:
    def __init__(self, base_url: str, token: str = None):
        """初始化AlistClient

        Args:
            base_url: Alist服务器的基本URL
            token: Alist API的授权令牌
        """
        # 确保base_url没有结尾的斜杠
        base_url = base_url.rstrip('/')
        
        # 创建客户端，设置认证头
        headers = {"Content-Type": "application/json"}
        if token:
            # 检查token是否已经包含"Bearer "前缀
            if not token.startswith("Bearer "):
                token = f"Bearer {token}"
            headers["Authorization"] = token
            
        logger.debug(f"初始化AlistClient: {base_url}, Token: {'已设置' if token else '无'}")
        
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(90.0, connect=90.0, read=90.0, write=90.0)
        )
    
    def _encode_path_if_needed(self, path: str) -> str:
        """如果路径包含非ASCII字符，则进行URL编码，但保留路径分隔符
        
        Args:
            path: 原始路径
            
        Returns:
            str: 编码后的路径
        """
        # 检查路径中是否包含非ASCII字符
        if any(ord(c) > 127 for c in path):
            # 使用safe='/'参数确保不编码路径分隔符
            return quote(path, safe='/')
        return path
    
    async def list_files(self, path: str) -> list:
        """获取目录下的文件列表"""
        try:
            # 首先尝试使用原始路径
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
                
            # 如果失败且是因为路径问题，尝试URL编码
            if data.get("code") == 500 and "storage not found" in data.get("message", ""):
                logger.warning(f"使用原始路径列出文件失败，尝试使用URL编码: {path}")
                
                # 使用URL编码处理路径
                encoded_path = self._encode_path_if_needed(path)
                
                logger.debug(f"使用编码路径重试列出文件: {encoded_path}")
                
                # 重新发送请求
                retry_response = await self.client.post("/api/fs/list", json={
                    "path": encoded_path,
                    "password": "",
                    "page": 1,
                    "per_page": 0,
                    "refresh": False
                })
                retry_response.raise_for_status()
                
                retry_data = retry_response.json()
                if retry_data.get("code") == 200:
                    content = retry_data.get("data", {}).get("content", [])
                    if content is None:
                        logger.warning(f"使用编码路径后目录访问被拒绝或不存在: {path}")
                        return []
                    logger.info(f"使用编码路径成功列出文件: {path}")
                    return content
                    
                logger.warning(f"使用编码路径列出文件失败: {path}, 状态码: {retry_data.get('code')}")
                return []
                
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
            # 获取原始路径
            src_dir = os.path.dirname(src_path)
            dst_dir = os.path.dirname(dest_path)
            basename = os.path.basename(src_path)
            
            data = {
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": [basename]
            }
            
            response = await self.client.post("/api/fs/move", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                logger.info(f"成功移动文件: {src_path} -> {dest_path}")
                return True
            
            # 如果失败且是500错误，可能是因为路径中的中文字符，尝试URL编码
            if data.get("code") == 500 and "storage not found" in data.get("message", ""):
                logger.warning(f"首次请求失败，尝试使用URL编码路径重试")
                
                # 使用URL编码处理路径
                encoded_src_dir = self._encode_path_if_needed(src_dir)
                encoded_dst_dir = self._encode_path_if_needed(dst_dir)
                encoded_basename = self._encode_path_if_needed(basename)
                
                # 构建包含编码路径的请求数据
                encoded_data = {
                    "src_dir": encoded_src_dir,
                    "dst_dir": encoded_dst_dir,
                    "names": [encoded_basename]
                }
                
                logger.debug(f"使用编码路径重试移动文件: 从 {encoded_src_dir} 到 {encoded_dst_dir}, 文件名: {encoded_basename}")
                
                # 重新发送请求
                retry_response = await self.client.post("/api/fs/move", json=encoded_data)
                retry_response.raise_for_status()
                
                retry_data = retry_response.json()
                if retry_data.get("code") == 200:
                    logger.info(f"使用编码路径成功移动文件: {src_path} -> {dest_path}")
                    return True
                
                logger.warning(f"使用编码路径的移动请求失败: {src_path}, 状态码: {retry_data.get('code')}, 消息: {retry_data.get('message')}")
                return False
                
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
            # 获取原始路径
            src_dir = os.path.dirname(src_path)
            dst_dir = os.path.dirname(dest_path)
            basename = os.path.basename(src_path)
            
            data = {
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": [basename]
            }
            
            response = await self.client.post("/api/fs/move", json=data)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200:
                logger.info(f"成功移动目录: {src_path} -> {dest_path}")
                return True
            
            # 如果失败且是500错误，可能是因为路径中的中文字符，尝试URL编码
            if data.get("code") == 500 and "storage not found" in data.get("message", ""):
                logger.warning(f"首次请求失败，尝试使用URL编码路径重试")
                
                # 使用URL编码处理路径
                encoded_src_dir = self._encode_path_if_needed(src_dir)
                encoded_dst_dir = self._encode_path_if_needed(dst_dir)
                encoded_basename = self._encode_path_if_needed(basename)
                
                # 构建包含编码路径的请求数据
                encoded_data = {
                    "src_dir": encoded_src_dir,
                    "dst_dir": encoded_dst_dir,
                    "names": [encoded_basename]
                }
                
                logger.debug(f"使用编码路径重试移动目录: 从 {encoded_src_dir} 到 {encoded_dst_dir}, 文件名: {encoded_basename}")
                
                # 重新发送请求
                retry_response = await self.client.post("/api/fs/move", json=encoded_data)
                retry_response.raise_for_status()
                
                retry_data = retry_response.json()
                if retry_data.get("code") == 200:
                    logger.info(f"使用编码路径成功移动目录: {src_path} -> {dest_path}")
                    return True
                
                logger.warning(f"使用编码路径的移动请求失败: {src_path}, 状态码: {retry_data.get('code')}, 消息: {retry_data.get('message')}")
                return False
                
            logger.warning(f"移动目录失败: {src_path}, 状态码: {data.get('code')}")
            return False
            
        except Exception as e:
            logger.error(f"移动目录时出错: {src_path}, 错误: {str(e)}")
            return False

    async def copy_file(self, src_path: str, dest_path: str) -> dict:
        """复制文件到新位置
        
        Args:
            src_path: 源文件路径
            dest_path: 目标文件路径
            
        Returns:
            dict: 包含操作结果的字典
                 - success: bool，操作是否成功
                 - file_exists: bool，目标文件是否已存在
                 - message: str，详细信息
        """
        try:
            # 构建请求数据 - 使用原始路径，不进行编码
            data = {
                "src_dir": os.path.dirname(src_path),
                "dst_dir": os.path.dirname(dest_path),
                "names": [os.path.basename(src_path)]
            }
            
            logger.info(f"发送复制请求: {data}")
            # 记录完整的原始请求数据
            logger.debug(f"API请求数据: {json.dumps(data, ensure_ascii=False)}")
            
            response = await self.client.post("/api/fs/copy", json=data)
            response.raise_for_status()
            
            # 检查响应类型
            if response.headers.get("content-type", "").startswith("text/html"):
                logger.error(f"复制文件时收到HTML响应，可能是服务器错误或授权问题。源路径: {src_path}")
                logger.debug(f"HTML响应内容预览: {response.text[:200]}...")
                return {"success": False, "file_exists": False, "message": "收到HTML响应"}
            
            try:
                resp_data = response.json()
            except Exception as e:
                logger.error(f"解析复制文件响应时出错: {str(e)}, 响应内容: {response.text[:500]}")
                return {"success": False, "file_exists": False, "message": f"JSON解析错误: {str(e)}"}
            
            # 检查文件是否已存在（状态码403，特定消息）
            if resp_data.get("code") == 403 and "exists" in resp_data.get("message", "").lower():
                logger.info(f"目标文件已存在: {dest_path} (来自源: {src_path})")
                return {"success": True, "file_exists": True, "message": resp_data.get("message", "文件已存在")}
            
            if resp_data.get("code") == 200:
                # 获取所有任务ID
                task_ids = [task["id"] for task in resp_data.get("data", {}).get("tasks", [])]
                logger.info(f"等待任务完成: {task_ids}")
                
                # 等待所有任务完成
                if await self.wait_for_tasks(task_ids):
                    logger.info(f"成功复制文件: {src_path} -> {dest_path}")
                    return {"success": True, "file_exists": False, "message": "复制成功"}
                    
                logger.warning(f"复制任务失败: {src_path}")
                return {"success": False, "file_exists": False, "message": "任务执行失败"}
                
            logger.warning(f"复制文件失败: {src_path}, 状态码: {resp_data.get('code')}, 消息: {resp_data.get('message')}")
            return {"success": False, "file_exists": False, "message": f"请求失败: {resp_data.get('code')}, {resp_data.get('message', '未知错误')}"}
            
        except Exception as e:
            logger.error(f"复制文件时出错: {src_path}, 错误: {str(e)}")
            return {"success": False, "file_exists": False, "message": f"异常: {str(e)}"}

    async def copy_directory(self, src_path: str, dest_path: str) -> dict:
        """复制目录到新位置
        
        Args:
            src_path: 源目录路径
            dest_path: 目标目录路径
            
        Returns:
            dict: 包含操作结果的字典
                 - success: bool，操作是否成功
                 - file_exists: bool，目标文件是否已存在
                 - message: str，详细信息
        """
        try:
            # 获取原始路径
            src_dir = os.path.dirname(src_path)
            dst_dir = os.path.dirname(dest_path)
            basename = os.path.basename(src_path)
            
            logger.debug(f"复制目录请求: 从 {src_dir} 到 {dst_dir}, 文件名: {basename}")
            
            # 构建请求数据 - 使用原始路径，不进行编码
            data = {
                "src_dir": src_dir,
                "dst_dir": dst_dir,
                "names": [basename],
                "override": True  # 添加覆盖选项
            }
            
            # 记录完整的原始请求数据
            logger.debug(f"API请求数据: {json.dumps(data, ensure_ascii=False)}")
            
            # 发送请求
            response = await self.client.post("/api/fs/copy", json=data)
            response.raise_for_status()
            
            # 检查响应类型
            if response.headers.get("content-type", "").startswith("text/html"):
                logger.error(f"复制目录时收到HTML响应，可能是服务器错误或授权问题。源路径: {src_path}")
                logger.debug(f"HTML响应内容预览: {response.text[:200]}...")
                return {"success": False, "file_exists": False, "message": "收到HTML响应"}
            
            # 解析响应
            try:
                resp_data = response.json()
            except Exception as e:
                logger.error(f"解析复制目录响应时出错: {str(e)}, 响应内容: {response.text[:500]}")
                return {"success": False, "file_exists": False, "message": f"JSON解析错误: {str(e)}"}
            
            # 检查文件是否已存在（状态码403，特定消息）
            if resp_data.get("code") == 403 and "exists" in resp_data.get("message", "").lower():
                logger.info(f"目标文件已存在: {dest_path} (来自源: {src_path})")
                return {"success": True, "file_exists": True, "message": resp_data.get("message", "文件已存在")}
            
            if resp_data.get("code") == 200:
                # 获取所有任务ID
                task_ids = [task["id"] for task in resp_data.get("data", {}).get("tasks", [])]
                
                if not task_ids:
                    logger.warning(f"复制目录没有生成任务ID: {src_path}")
                    return {"success": False, "file_exists": False, "message": "没有生成任务ID"}
                    
                logger.debug(f"等待任务完成: {task_ids}")
                
                # 等待所有任务完成
                if await self.wait_for_tasks(task_ids):
                    logger.info(f"成功复制目录: {src_path} -> {dest_path}")
                    return {"success": True, "file_exists": False, "message": "复制成功"}
                    
                logger.warning(f"复制任务失败: {src_path}")
                return {"success": False, "file_exists": False, "message": "任务执行失败"}
                
            logger.warning(f"复制目录请求失败: {src_path}, 状态码: {resp_data.get('code')}, 消息: {resp_data.get('message')}")
            return {"success": False, "file_exists": False, "message": f"请求失败: {resp_data.get('code')}, {resp_data.get('message', '未知错误')}"}
            
        except Exception as e:
            logger.error(f"复制目录时出错: {src_path}, 错误: {str(e)}", exc_info=True)
            return {"success": False, "file_exists": False, "message": f"异常: {str(e)}"}

    async def task_status(self, task_id: str):
        """获取任务状态"""
        data = {"id": task_id}
        try:
            # 记录发送的请求数据
            logger.debug(f"获取任务状态请求: {task_id}")
            
            # 确保我们有正确的授权头
            current_headers = dict(self.client.headers)
            logger.debug(f"当前授权: {current_headers.get('Authorization', '无')[:10]}{'...' if current_headers.get('Authorization', '') else ''}")
            
            # 尝试使用正确的API路径获取任务状态
            api_path = "/api/admin/task/status"
            logger.debug(f"API路径: {api_path}")
            
            response = await self.client.post(
                api_path,
                json=data
            )
            response.raise_for_status()
            
            # 检查响应类型
            content_type = response.headers.get("content-type", "")
            logger.debug(f"响应内容类型: {content_type}")
            
            if "application/json" not in content_type:
                logger.error(f"收到非JSON响应 ({content_type}): {response.text[:200]}...")
                
                # 检查是否是授权问题
                if "login" in response.text.lower() or "401" in response.text or "unauthorized" in response.text.lower():
                    logger.error("可能是授权问题，检查token是否有效或已过期")
                
                # 尝试提取更多有用信息
                if "<title>" in response.text:
                    import re
                    title_match = re.search(r"<title>([^<]+)</title>", response.text)
                    if title_match:
                        logger.error(f"页面标题: {title_match.group(1)}")
                
                # 尝试请求服务器信息以检查连接性
                try:
                    info_response = await self.client.get("/api/public/settings")
                    if info_response.status_code == 200:
                        logger.debug(f"服务器信息响应: {info_response.text[:100]}...")
                    else:
                        logger.error(f"获取服务器信息失败: {info_response.status_code}")
                except Exception as e:
                    logger.error(f"请求服务器信息失败: {e}")
                
                return {"code": 500, "message": f"Invalid response type: {content_type}", "data": None}
                
            try:
                json_data = response.json()
                logger.debug(f"任务状态响应: {json.dumps(json_data, ensure_ascii=False)[:200]}...")
                return json_data
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
        logger.debug(f"开始等待 {len(task_ids)} 个任务完成，超时时间: {timeout}秒")
        
        # 临时保存失败次数，允许一定程度的失败后继续尝试
        error_counts = {task_id: 0 for task_id in task_ids}
        max_error_attempts = 5
        
        while time.time() - start_time < timeout:
            all_done = True
            all_successful = True
            
            for task_id in list(task_ids):  # 使用列表副本以便可以移除元素
                resp = await self.task_status(task_id)
                
                if resp.get("code") != 200:
                    error_counts[task_id] += 1
                    logger.error(f"获取任务 {task_id} 状态失败: {resp.get('message')} (尝试 {error_counts[task_id]}/{max_error_attempts})")
                    
                    # 如果连续失败次数超过阈值，认为任务失败
                    if error_counts[task_id] >= max_error_attempts:
                        all_successful = False
                        logger.error(f"任务 {task_id} 状态获取连续失败 {max_error_attempts} 次，视为失败")
                    else:
                        # 如果未达到最大尝试次数，暂不认为完成
                        all_done = False
                    continue
                    
                task = resp.get("data", {})
                state = task.get("state", 0)
                
                if state == 0:  # 进行中
                    all_done = False
                    progress = task.get("progress", 0)
                    logger.debug(f"任务 {task_id} 进度: {progress}%")
                elif state == 2:  # 失败
                    error = task.get("error", "未知错误")
                    logger.error(f"任务 {task_id} 失败: {error}")
                    all_successful = False
                elif state == 1:  # 完成
                    logger.debug(f"任务 {task_id} 已完成")
                    # 任务完成后从列表中移除，不再检查
                    if task_id in error_counts:
                        del error_counts[task_id]
            
            # 如果所有任务都已完成或超过尝试次数
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