from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal
from pathlib import Path
import os
import logging
import asyncio
import time
import re
import httpx
from datetime import datetime
from services.service_manager import service_manager

router = APIRouter(prefix="/api/health", tags=["health"])
logger = logging.getLogger(__name__)

class HealthProblem(BaseModel):
    id: str
    type: str  # invalid_strm 或 missing_strm
    path: str
    details: str
    discoveryTime: float
    firstDetectedAt: Optional[float] = None

class HealthScanResult(BaseModel):
    scanTime: float
    scanType: str
    problems: List[HealthProblem]
    stats: Dict[str, Any] = {}

class RepairRequest(BaseModel):
    paths: List[str]
    type: str

class ScanRequest(BaseModel):
    type: str = "all"
    mode: str = "full"  # full, incremental, problems_only

# 存储最近一次扫描状态
_is_scanning: bool = False
_scan_progress: int = 0
_scan_status: str = ""
_scan_type: str = "all"
_scan_mode: str = "full"

@router.get("/status")
async def get_scan_status():
    """获取当前扫描状态"""
    global _is_scanning, _scan_progress, _scan_status, _scan_type, _scan_mode
    
    # 获取统计信息
    stats = service_manager.health_service.get_stats()
    last_scan_time = stats.get("lastFullScanTime", 0)
    
    # 格式化上次扫描时间
    last_scan_time_str = datetime.fromtimestamp(last_scan_time).strftime("%Y-%m-%d %H:%M:%S") if last_scan_time > 0 else "从未扫描"
    
    return {
        "isScanning": _is_scanning,
        "progress": _scan_progress,
        "status": _scan_status,
        "scanType": _scan_type,
        "scanMode": _scan_mode,
        "lastScanTime": last_scan_time,
        "lastScanTimeStr": last_scan_time_str,
        "stats": stats
    }

@router.post("/start")
async def start_scan(request: ScanRequest = None):
    """开始健康扫描"""
    global _is_scanning, _scan_progress, _scan_status, _scan_type, _scan_mode
    
    if request is None:
        request = ScanRequest()
    
    if _is_scanning:
        raise HTTPException(status_code=400, detail="扫描已在进行中")
    
    scan_type = request.type
    scan_mode = request.mode
    
    if scan_type not in ["strm_validity", "video_coverage", "all"]:
        raise HTTPException(status_code=400, detail="无效的扫描类型")
    
    if scan_mode not in ["full", "incremental", "problems_only"]:
        raise HTTPException(status_code=400, detail="无效的扫描模式")
    
    # 更新扫描类型和模式
    _scan_type = scan_type
    _scan_mode = scan_mode
    
    # 开启一个异步任务执行扫描
    _is_scanning = True
    _scan_progress = 0
    _scan_status = "正在初始化扫描..."
    
    try:
        # 创建异步任务执行扫描
        asyncio.create_task(perform_health_scan(scan_type, scan_mode))
        
        return {
            "message": "健康扫描已开始", 
            "status": "scanning", 
            "type": scan_type,
            "mode": scan_mode
        }
    except Exception as e:
        _is_scanning = False
        logger.error(f"启动健康扫描失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动扫描失败: {str(e)}")

async def perform_health_scan(scan_type: str, scan_mode: str):
    """执行健康扫描"""
    global _is_scanning, _scan_progress, _scan_status
    
    try:
        _scan_progress = 0
        all_problems = []
        
        # 根据扫描类型和模式选择执行的检测
        if scan_type in ["strm_validity", "all"]:
            _scan_status = "正在检查STRM文件有效性..."
            invalid_strm_files = await check_strm_validity(scan_mode)
            all_problems.extend(invalid_strm_files)
            _scan_progress = 50 if scan_type == "all" else 100
            
        if scan_type in ["video_coverage", "all"]:
            _scan_status = "正在检查视频文件覆盖情况..."
            missing_strm_files = await check_video_coverage(scan_mode)
            all_problems.extend(missing_strm_files)
            _scan_progress = 100
        
        # 更新最后扫描时间（只有完整扫描才更新）
        if scan_mode == "full":
            service_manager.health_service.update_last_full_scan_time()
            
        # 保存健康状态数据
        service_manager.health_service.save_health_data()
        
        # 转换问题列表为返回格式
        problems = [
            HealthProblem(
                id=problem["id"],
                type=problem["type"],
                path=problem["path"],
                details=problem["details"],
                discoveryTime=problem["discoveryTime"],
                firstDetectedAt=problem.get("firstDetectedAt", problem["discoveryTime"])
            ) for problem in all_problems
        ]
        
        _scan_status = f"扫描完成，发现 {len(all_problems)} 个问题"
        logger.info(f"健康扫描完成，发现 {len(all_problems)} 个问题")
    
    except Exception as e:
        logger.error(f"健康扫描过程中出错: {str(e)}")
        _scan_status = f"扫描出错: {str(e)}"
    
    finally:
        _is_scanning = False

async def check_strm_validity(scan_mode: str):
    """检查STRM文件有效性
    
    检查每个STRM文件指向的网盘文件是否存在
    返回无效的STRM文件列表
    """
    global _scan_progress, _scan_status, _scan_type
    
    invalid_strm_files = []
    
    # 获取STRM目录
    strm_dir = service_manager.strm_service.settings.output_dir
    
    if scan_mode == "problems_only":
        # 只检查已知问题文件
        _scan_status = "正在检查已知的无效STRM文件..."
        invalid_files = service_manager.health_service.get_all_invalid_strm_files()
        
        total_files = len(invalid_files)
        for idx, file_info in enumerate(invalid_files):
            # 更新进度
            _scan_progress = int((idx / total_files) * (50 if _scan_type == "all" else 100)) if total_files > 0 else (50 if _scan_type == "all" else 100)
            _scan_status = f"正在重新检查已知的无效STRM文件 ({idx+1}/{total_files})..."
            
            strm_path = file_info["path"]
            # 检查文件是否仍然存在
            if not os.path.exists(strm_path):
                # 文件已被删除，从数据中移除
                service_manager.health_service.remove_strm_file(strm_path)
                continue
                
            # 重新检查STRM文件指向的源文件是否存在
            is_valid, reason = await check_strm_source(strm_path)
            
            if is_valid:
                # 文件现在有效，更新状态
                target_path = extract_target_path(strm_path)
                service_manager.health_service.update_strm_status(strm_path, {
                    "status": "valid",
                    "issueDetails": None,
                    "targetPath": target_path
                })
            else:
                # 文件仍然无效，添加到问题列表
                invalid_strm_files.append({
                    "id": f"invalid_{len(invalid_strm_files)}",
                    "type": "invalid_strm",
                    "path": strm_path,
                    "details": f"STRM文件无效: {reason}",
                    "discoveryTime": time.time(),
                    "firstDetectedAt": file_info.get("firstDetectedAt", time.time())
                })
                
                # 更新健康状态
                service_manager.health_service.update_strm_status(strm_path, {
                    "status": "invalid",
                    "issueDetails": reason
                })
    else:
        # 扫描所有STRM文件或增量扫描
        # 扫描所有STRM文件
        strm_files = await scan_strm_files(strm_dir)
        total_files = len(strm_files)
        
        # 获取上次扫描时间
        last_scan_time = service_manager.health_service.get_last_full_scan_time()
        
        for idx, strm_file in enumerate(strm_files):
            # 更新进度
            if _scan_type == "strm_validity":
                _scan_progress = int((idx / total_files) * 100) if total_files > 0 else 100
            else: # all 类型
                _scan_progress = int(((idx / total_files) * 50)) if total_files > 0 else 50
                
            str_strm_file = str(strm_file)
            _scan_status = f"正在检查STRM文件有效性 ({idx+1}/{total_files})..."
            
            # 如果是增量扫描，检查文件是否需要重新扫描
            if scan_mode == "incremental":
                file_status = service_manager.health_service.get_strm_status(str_strm_file)
                
                # 如果文件上次检查时间晚于最后全量扫描时间，且状态为有效，则跳过
                if file_status.get("lastCheckTime", 0) > last_scan_time and file_status.get("status") == "valid":
                    continue
            
            # 检查STRM文件指向的源文件是否存在
            is_valid, reason = await check_strm_source(strm_file)
            
            # 提取STRM文件指向的目标路径
            target_path = await extract_target_path_from_file(strm_file)
            
            if not is_valid:
                file_path = str(strm_file)
                invalid_strm_files.append({
                    "id": f"invalid_{len(invalid_strm_files)}",
                    "type": "invalid_strm",
                    "path": file_path,
                    "details": f"STRM文件无效: {reason}",
                    "discoveryTime": time.time(),
                    "firstDetectedAt": time.time()
                })
                
                # 更新健康状态
                service_manager.health_service.update_strm_status(file_path, {
                    "status": "invalid",
                    "issueDetails": reason,
                    "targetPath": target_path
                })
            else:
                # 文件有效，更新健康状态
                service_manager.health_service.update_strm_status(str_strm_file, {
                    "status": "valid",
                    "issueDetails": None,
                    "targetPath": target_path
                })
    
    return invalid_strm_files

async def check_video_coverage(scan_mode: str):
    """检查视频文件覆盖情况
    
    扫描Alist网盘中的视频文件，检查是否都有对应的STRM文件
    返回缺失STRM文件的列表
    """
    global _scan_progress, _scan_status, _scan_type
    
    missing_strm_files = []
    
    # 如果是只检查问题文件模式
    if scan_mode == "problems_only":
        # 只检查已知问题文件
        _scan_status = "正在检查已知的缺失STRM文件..."
        missing_files = service_manager.health_service.get_all_missing_strm_files()
        
        total_files = len(missing_files)
        for idx, file_info in enumerate(missing_files):
            # 更新进度
            _scan_progress = 50 + int((idx / total_files) * 50) if total_files > 0 else 100
            _scan_status = f"正在重新检查已知的缺失STRM文件 ({idx+1}/{total_files})..."
            
            video_path = file_info["path"]
            
            # 检查视频文件是否存在
            exists = await check_alist_file_exists(video_path)
            if not exists:
                # 视频文件已不存在，从数据中移除
                if "videoFiles" in service_manager.health_service._health_data and video_path in service_manager.health_service._health_data["videoFiles"]:
                    del service_manager.health_service._health_data["videoFiles"][video_path]
                continue
            
            # 检查是否有了对应的STRM文件
            # 构建应该存在的STRM文件路径
            strm_file = build_strm_path(video_path)
            
            if os.path.exists(strm_file):
                # 已经生成了STRM文件，更新状态
                service_manager.health_service.update_video_status(video_path, {
                    "hasStrm": True,
                    "strmPath": strm_file
                })
            else:
                # 仍然缺少STRM文件，添加到问题列表
                missing_strm_files.append({
                    "id": f"missing_{len(missing_strm_files)}",
                    "type": "missing_strm",
                    "path": video_path,
                    "details": f"网盘中的视频文件没有对应的STRM文件",
                    "discoveryTime": time.time(),
                    "firstDetectedAt": file_info.get("firstDetectedAt", time.time())
                })
                
                # 更新健康状态
                service_manager.health_service.update_video_status(video_path, {
                    "hasStrm": False,
                    "strmPath": None
                })
        
        return missing_strm_files
    
    # 获取STRM目录和Alist扫描路径
    strm_dir = Path(service_manager.strm_service.settings.output_dir)
    alist_scan_path = service_manager.strm_service.settings.alist_scan_path
    
    # 获取所有已生成的STRM文件的目标路径
    _scan_status = "正在收集已存在的STRM文件信息..."
    existing_strm_files = await scan_strm_files(strm_dir)
    existing_strm_targets = set()
    
    # 提取STRM文件内容，获取它们指向的路径
    for strm_file in existing_strm_files:
        try:
            target_path = await extract_target_path_from_file(strm_file)
            if target_path:
                existing_strm_targets.add(target_path)
                
                # 更新STRM文件状态
                service_manager.health_service.update_strm_status(str(strm_file), {
                    "targetPath": target_path,
                    "status": "valid"  # 默认为有效，后续会检查
                })
                
                # 更新视频文件状态
                service_manager.health_service.update_video_status(target_path, {
                    "hasStrm": True,
                    "strmPath": str(strm_file)
                })
        except Exception as e:
            logger.warning(f"读取STRM文件失败: {strm_file}, 错误: {str(e)}")
    
    # 获取Alist网盘中的所有视频文件
    try:
        # 递归扫描Alist路径下的视频文件
        _scan_status = "正在扫描Alist网盘视频文件..."
        video_files = await scan_alist_videos(alist_scan_path)
        total_files = len(video_files)
        
        # 获取上次扫描时间
        last_scan_time = service_manager.health_service.get_last_full_scan_time()
        
        for idx, video_file in enumerate(video_files):
            # 更新进度
            if _scan_type == "video_coverage":
                _scan_progress = int((idx / total_files) * 100) if total_files > 0 else 100
            else: # all 类型
                _scan_progress = 50 + int(((idx / total_files) * 50)) if total_files > 0 else 100
                
            _scan_status = f"正在检查视频文件覆盖情况 ({idx+1}/{total_files})..."
            
            # 记录当前检查的路径，便于调试
            logger.debug(f"检查视频文件是否有STRM: {video_file}")
            
            # 如果是增量扫描，检查文件是否需要重新扫描
            if scan_mode == "incremental":
                file_status = service_manager.health_service.get_video_status(video_file)
                
                # 如果文件上次检查时间晚于最后全量扫描时间，且已有STRM，则跳过
                if file_status.get("lastCheckTime", 0) > last_scan_time and file_status.get("hasStrm") == True:
                    continue
            
            # 如果没有对应的STRM文件
            if video_file not in existing_strm_targets:
                missing_strm_files.append({
                    "id": f"missing_{len(missing_strm_files)}",
                    "type": "missing_strm",
                    "path": video_file,
                    "details": f"网盘中的视频文件没有对应的STRM文件",
                    "discoveryTime": time.time()
                })
                
                # 更新健康状态
                service_manager.health_service.update_video_status(video_file, {
                    "hasStrm": False,
                    "strmPath": None
                })
            else:
                # 更新健康状态
                strm_path = build_strm_path(video_file)
                service_manager.health_service.update_video_status(video_file, {
                    "hasStrm": True,
                    "strmPath": strm_path
                })
    
    except Exception as e:
        logger.error(f"扫描Alist视频文件时出错: {str(e)}")
        _scan_status = f"扫描Alist视频文件出错: {str(e)}"
    
    return missing_strm_files

async def scan_strm_files(directory):
    """扫描指定目录中的所有STRM文件"""
    directory = Path(directory)
    if not directory.exists():
        return []
    
    strm_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.strm'):
                strm_files.append(Path(root) / file)
    
    return strm_files

async def check_strm_source(strm_file):
    """检查STRM文件指向的源文件是否存在"""
    try:
        # 读取STRM文件内容（通常是URL或路径）
        with open(strm_file, 'r', encoding='utf-8') as f:
            source_url = f.read().strip()
        
        # 如果URL为空，则无效
        if not source_url:
            return False, "STRM文件内容为空"
        
        # 检查URL格式
        if not source_url.startswith('http'):
            return False, "STRM文件URL格式无效"
        
        # 从URL中提取Alist路径
        try:
            # 提取/d/后面的路径部分
            parts = source_url.split('/d/')
            if len(parts) < 2:
                return False, "URL格式不正确，无法提取路径"
            
            alist_path = parts[1]  # 直接获取/d/后面的路径，不需要再加/d前缀
            
            # 调用Alist API检查文件是否存在
            exists = await check_alist_file_exists(alist_path)
            if not exists:
                return False, "网盘中找不到对应的源文件"
            
            return True, ""
            
        except Exception as e:
            return False, f"检查文件存在性时出错: {str(e)}"
        
    except Exception as e:
        logger.error(f"检查STRM源文件时出错: {str(e)}, 文件: {strm_file}")
        return False, f"检查源文件时出错: {str(e)}"

async def extract_target_path_from_file(strm_file):
    """从STRM文件中提取目标路径"""
    try:
        with open(strm_file, 'r', encoding='utf-8') as f:
            source_url = f.read().strip()
        
        if not source_url.startswith('http'):
            return None
        
        parts = source_url.split('/d/')
        if len(parts) < 2:
            return None
        
        path = parts[1]  # 直接获取/d/后面的路径
        
        # 处理可能存在的文件名重复问题
        filename = os.path.basename(path)
        parent_dir = os.path.dirname(path)
        if os.path.basename(parent_dir) == filename:
            # 路径中有重复的文件名，使用父路径
            path = parent_dir
            logger.debug(f"从STRM文件中提取路径时检测到重复的文件名，使用修正后的路径: {path}")
        
        return path
    except Exception as e:
        logger.error(f"从STRM文件提取目标路径失败: {str(e)}, 文件: {strm_file}")
        return None

def extract_target_path(strm_path):
    """从STRM文件路径构建可能的目标路径（用于已知的问题文件）"""
    # 这个函数不直接读取文件内容，而是通过健康状态数据获取目标路径
    return service_manager.health_service.get_strm_status(strm_path).get("targetPath")

def build_strm_path(video_path):
    """从视频文件路径构建STRM文件路径"""
    output_dir = service_manager.strm_service.settings.output_dir
    
    # 处理可能存在的文件名重复问题
    filename = os.path.basename(video_path)
    parent_dir = os.path.dirname(video_path)
    if os.path.basename(parent_dir) == filename:
        # 路径中有重复的文件名，使用父路径
        rel_path = os.path.dirname(parent_dir)
        logger.debug(f"构建STRM路径时检测到重复的文件名，使用修正后的路径: {parent_dir}")
    else:
        rel_path = parent_dir
    
    name, _ = os.path.splitext(filename)
    
    return os.path.join(output_dir, rel_path.lstrip('/'), f"{name}.strm")

async def check_alist_file_exists(path):
    """检查Alist中的文件是否存在"""
    try:
        # 处理可能存在的文件名重复问题
        filename = os.path.basename(path)
        parent_dir = os.path.dirname(path)
        if os.path.basename(parent_dir) == filename:
            # 路径中有重复的文件名，使用父路径
            path = parent_dir
            logger.debug(f"检测到路径中有重复的文件名，使用修正后的路径: {path}")
        
        # 使用Alist API检查文件是否存在
        # 不需要额外处理/d前缀，因为path已经是从URL中提取的纯路径
        
        # 使用Alist API查询文件信息
        alist_url = service_manager.strm_service.settings.alist_url
        alist_token = service_manager.strm_service.settings.alist_token
        
        # 记录当前检查的路径，便于调试
        logger.debug(f"检查Alist文件是否存在: {path}")
        
        # 使用httpx发送请求
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": alist_token,
                "Content-Type": "application/json"
            }
            
            response = await client.post(
                f"{alist_url}/api/fs/get", 
                json={"path": path},
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    return True
            
            # 记录调试信息
            logger.debug(f"Alist API返回: status={response.status_code}, data={response.text[:200]}")
            return False
                
    except Exception as e:
        logger.error(f"检查Alist文件存在性时出错: {str(e)}, 路径: {path}")
        return False

async def scan_alist_videos(path):
    """递归扫描Alist网盘中的视频文件"""
    video_files = []
    
    try:
        # 使用Alist API列出路径下的所有文件
        files = await list_alist_files(path)
        
        for file in files:
            if file.get("is_dir"):
                # 递归扫描子目录
                sub_files = await scan_alist_videos(file.get("path"))
                video_files.extend(sub_files)
            else:
                # 检查是否是视频文件
                file_name = file.get("name", "")
                if is_video_file(file_name):
                    # 获取文件路径
                    file_path = file.get("path")
                    
                    # 处理可能存在的文件名重复问题
                    filename = os.path.basename(file_path)
                    parent_dir = os.path.dirname(file_path)
                    if os.path.basename(parent_dir) == filename:
                        # 路径中有重复的文件名，使用父路径
                        file_path = parent_dir
                        logger.debug(f"扫描视频文件时检测到重复的文件名，使用修正后的路径: {file_path}")
                    
                    # 保存不带/d前缀的路径
                    video_files.append(file_path)
                    
    except Exception as e:
        logger.error(f"扫描Alist视频文件时出错: {str(e)}, 路径: {path}")
        
    return video_files
        
async def list_alist_files(path):
    """列出Alist路径下的所有文件"""
    try:
        # 使用Alist API列出路径下的所有文件
        alist_url = service_manager.strm_service.settings.alist_url
        alist_token = service_manager.strm_service.settings.alist_token
        
        # 使用httpx发送请求
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": alist_token,
                "Content-Type": "application/json"
            }
            
            response = await client.post(
                f"{alist_url}/api/fs/list", 
                json={"path": path, "refresh": False},
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    return data.get("data", {}).get("content", [])
            
            return []
                
    except Exception as e:
        logger.error(f"列出Alist文件时出错: {str(e)}, 路径: {path}")
        return []
        
def is_video_file(filename):
    """检查文件是否是视频文件"""
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpeg', '.mpg', '.ts']
    _, ext = os.path.splitext(filename.lower())
    return ext in video_extensions

@router.get("/problems")
async def get_health_problems(type: str = None):
    """获取健康问题列表"""
    # 使用健康服务获取问题
    problems = []
    
    if type == "invalid_strm" or type is None:
        invalid_files = service_manager.health_service.get_all_invalid_strm_files()
        for idx, file in enumerate(invalid_files):
            problems.append({
                "id": f"invalid_{idx}",
                "type": "invalid_strm",
                "path": file["path"],
                "details": file.get("issueDetails", "STRM文件无效"),
                "discoveryTime": file["lastCheckTime"],
                "firstDetectedAt": file.get("firstDetectedAt", file["lastCheckTime"])
            })
    
    if type == "missing_strm" or type is None:
        missing_files = service_manager.health_service.get_all_missing_strm_files()
        for idx, file in enumerate(missing_files):
            problems.append({
                "id": f"missing_{idx}",
                "type": "missing_strm",
                "path": file["path"],
                "details": "网盘中的视频文件没有对应的STRM文件",
                "discoveryTime": file["lastCheckTime"],
                "firstDetectedAt": file.get("firstDetectedAt", file["lastCheckTime"])
            })
    
    # 获取统计信息
    stats = service_manager.health_service.get_stats()
    
    return {
        "problems": problems,
        "scanTime": stats.get("lastFullScanTime", 0),
        "stats": stats
    }

@router.post("/repair/invalid_strm")
async def repair_invalid_strm(request: RepairRequest):
    """清理无效的STRM文件"""
    if request.type != "invalid_strm":
        raise HTTPException(status_code=400, detail="无效的修复类型")
    
    if not request.paths:
        raise HTTPException(status_code=400, detail="未提供需要清理的路径")
    
    try:
        # 删除无效的STRM文件
        logger.info(f"尝试清理 {len(request.paths)} 个无效的STRM文件")
        
        success_count = 0
        for path in request.paths:
            try:
                # 删除STRM文件
                file_path = Path(path)
                if file_path.exists() and file_path.is_file():
                    file_path.unlink()
                    success_count += 1
                    
                    # 从健康状态数据中移除
                    service_manager.health_service.remove_strm_file(str(file_path))
            except Exception as e:
                logger.error(f"删除文件失败: {path}, 错误: {str(e)}")
        
        # 保存健康状态数据
        service_manager.health_service.save_health_data()
        
        return {"success": True, "message": f"已成功清理 {success_count} 个无效的STRM文件"}
    
    except Exception as e:
        logger.error(f"清理无效的STRM文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")

@router.post("/repair/missing_strm")
async def repair_missing_strm(request: RepairRequest):
    """为缺失的视频生成STRM文件"""
    if request.type != "missing_strm":
        raise HTTPException(status_code=400, detail="无效的修复类型")
    
    if not request.paths:
        raise HTTPException(status_code=400, detail="未提供需要生成STRM的路径")
    
    try:
        # 这里调用service_manager中的方法重新生成STRM文件
        logger.info(f"尝试为 {len(request.paths)} 个缺失的视频生成STRM文件")
        
        # 调用strm_service处理这些文件
        success_count = 0
        for video_path in request.paths:
            try:
                # 构建Alist URL
                alist_url = service_manager.strm_service.settings.alist_url
                
                # 确保video_path不包含重复的文件名
                filename = os.path.basename(video_path)
                if os.path.basename(os.path.dirname(video_path)) == filename:
                    # 路径结尾有重复的文件名，移除最后一个
                    video_path = os.path.dirname(video_path)
                
                video_url = f"{alist_url}/d/{video_path}"
                
                # 获取文件名和扩展名
                filename = os.path.basename(video_path)
                name, _ = os.path.splitext(filename)
                
                # 计算输出路径 - 需要保持目录结构
                output_dir = service_manager.strm_service.settings.output_dir
                rel_path = os.path.dirname(video_path)
                
                # 创建输出目录
                full_output_dir = os.path.join(output_dir, rel_path.lstrip('/'))
                os.makedirs(full_output_dir, exist_ok=True)
                
                # 生成STRM文件
                strm_path = os.path.join(full_output_dir, f"{name}.strm")
                
                # 日志记录，便于调试
                logger.info(f"生成STRM文件: {strm_path} -> {video_url}")
                
                with open(strm_path, 'w', encoding='utf-8') as f:
                    f.write(video_url)
                    
                success_count += 1
                
                # 更新健康状态数据
                service_manager.health_service.add_strm_file(strm_path, video_path)
                
            except Exception as e:
                logger.error(f"为视频生成STRM文件失败: {video_path}, 错误: {str(e)}")
        
        # 保存健康状态数据
        service_manager.health_service.save_health_data()
        
        return {"success": True, "message": f"已成功为 {success_count} 个视频生成STRM文件"}
    
    except Exception as e:
        logger.error(f"生成STRM文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

@router.post("/clear_data")
async def clear_health_data():
    """清空健康状态数据"""
    try:
        service_manager.health_service.clear_data()
        return {"success": True, "message": "健康状态数据已清空"}
    except Exception as e:
        logger.error(f"清空健康状态数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")

@router.get("/stats")
async def get_health_stats():
    """获取健康状态统计信息"""
    try:
        stats = service_manager.health_service.get_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"获取健康状态统计信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}") 