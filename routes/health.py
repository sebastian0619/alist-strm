from fastapi import APIRouter, HTTPException, Query, Body
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
from urllib.parse import unquote, quote
import shutil

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
    type: str  # 修复类型
    paths: List[str]  # 需要修复的路径列表

class ScanRequest(BaseModel):
    type: str = "all"
    mode: str = "full"  # full, incremental, problems_only

class ReplaceRequest(BaseModel):
    search_text: str = Body(..., description="要查找的文本")
    replace_text: str = Body(..., description="替换的文本")
    target_paths: Optional[List[str]] = Body(None, description="指定要处理的STRM文件路径（为空则处理所有STRM文件）")
    preview_only: bool = Body(False, description="是否仅预览更改而不实际执行")

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
        logger.info(f"开始检查 {total_files} 个已知的无效STRM文件")
        
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
                
        # 保存健康状态数据
        service_manager.health_service.save_health_data()
    else:
        # 扫描所有STRM文件或增量扫描
        # 扫描所有STRM文件
        strm_files = await scan_strm_files(strm_dir)
        total_files = len(strm_files)
        
        logger.info(f"开始检查 {total_files} 个STRM文件的有效性")
        
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
                
                logger.info(f"发现无效STRM文件: {file_path}, 原因: {reason}")
            else:
                # 文件有效，更新健康状态
                service_manager.health_service.update_strm_status(str_strm_file, {
                    "status": "valid",
                    "issueDetails": None,
                    "targetPath": target_path
                })
        
        # 保存健康状态数据
        service_manager.health_service.save_health_data()
        
        logger.info(f"完成STRM文件有效性检查，发现 {len(invalid_strm_files)} 个无效文件")
    
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
        
        # 提取路径但不对其进行解码
        # 注意：我们保留编码状态，因为健康检测在其他地方需要这个编码版本
        # 解码会在check_alist_file_exists函数中进行
        encoded_path = parts[1]
        
        # 处理可能存在的文件名重复问题（在编码状态下）
        filename = os.path.basename(encoded_path)
        parent_dir = os.path.dirname(encoded_path)
        if os.path.basename(parent_dir) == filename:
            # 路径中有重复的文件名，使用父路径
            encoded_path = parent_dir
            logger.debug(f"从STRM文件中提取路径时检测到重复的文件名，使用修正后的路径: {encoded_path}")
        
        return encoded_path
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
    
    # 确保我们处理的是解码后的路径
    # 注意：此函数可能接收已编码或未编码的路径，需处理两种情况
    try:
        # 尝试解码，如果已是解码状态，不会有变化
        decoded_path = unquote(video_path)
    except Exception:
        # 解码失败，保持原样
        decoded_path = video_path
    
    # 处理可能存在的文件名重复问题
    filename = os.path.basename(decoded_path)
    parent_dir = os.path.dirname(decoded_path)
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
        # 先进行URL解码，确保我们使用的是原始路径而非URL编码后的路径
        decoded_path = unquote(path)
        
        # 处理可能存在的文件名重复问题
        filename = os.path.basename(decoded_path)
        parent_dir = os.path.dirname(decoded_path)
        if os.path.basename(parent_dir) == filename:
            # 路径中有重复的文件名，使用父路径
            decoded_path = parent_dir
            logger.debug(f"检测到路径中有重复的文件名，使用修正后的路径: {decoded_path}")
        
        # 使用Alist API检查文件是否存在
        # 使用解码后的路径进行查询
        alist_url = service_manager.strm_service.settings.alist_url
        alist_token = service_manager.strm_service.settings.alist_token
        
        # 记录当前检查的路径，便于调试
        logger.debug(f"检查Alist文件是否存在: {decoded_path} (原始编码路径: {path})")
        
        # 使用httpx发送请求
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": alist_token,
                "Content-Type": "application/json"
            }
            
            response = await client.post(
                f"{alist_url}/api/fs/get", 
                json={"path": decoded_path},
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
                    # 获取文件路径 - 这里得到的是未编码的原始路径
                    original_path = file.get("path")
                    
                    # 处理可能存在的文件名重复问题
                    filename = os.path.basename(original_path)
                    parent_dir = os.path.dirname(original_path)
                    if os.path.basename(parent_dir) == filename:
                        # 路径中有重复的文件名，使用父路径
                        original_path = parent_dir
                        logger.debug(f"扫描视频文件时检测到重复的文件名，使用修正后的路径: {original_path}")
                    
                    # 保存原始路径（未编码）
                    video_files.append(original_path)
                    
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
    
    try:
        if type == "invalid_strm" or type is None:
            invalid_files = service_manager.health_service.get_all_invalid_strm_files()
            logger.info(f"获取到 {len(invalid_files)} 个无效STRM文件")
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
            logger.info(f"获取到 {len(missing_files)} 个缺失STRM文件")
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
        
        logger.info(f"返回 {len(problems)} 个健康问题，统计: {stats}")
        
        # 确保返回的问题列表不为空，与统计数据一致
        if (stats.get("invalidStrmFiles", 0) > 0 or stats.get("missingStrmFiles", 0) > 0) and len(problems) == 0:
            logger.warning(f"统计显示有问题文件，但问题列表为空。强制重新扫描...")
            
            # 尝试重新读取数据
            service_manager.health_service.load_health_data()
            
            # 重新获取问题列表
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
            
            logger.info(f"重新读取后返回 {len(problems)} 个健康问题")
        
        return {
            "problems": problems,
            "scanTime": stats.get("lastFullScanTime", 0),
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取健康问题列表失败: {str(e)}", exc_info=True)
        return {
            "problems": [],
            "scanTime": 0,
            "stats": service_manager.health_service.get_stats()
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
                # 先解码视频路径，确保处理的是原始路径
                decoded_path = unquote(video_path)
                filename = os.path.basename(decoded_path)
                if os.path.basename(os.path.dirname(decoded_path)) == filename:
                    # 路径结尾有重复的文件名，移除最后一个
                    decoded_path = os.path.dirname(decoded_path)
                
                # 需要重新编码路径用于URL
                encoded_path = quote(decoded_path)
                video_url = f"{alist_url}/d/{encoded_path}"
                
                # 获取文件名和扩展名
                filename = os.path.basename(decoded_path)
                name, _ = os.path.splitext(filename)
                
                # 计算输出路径 - 需要保持目录结构
                output_dir = service_manager.strm_service.settings.output_dir
                rel_path = os.path.dirname(decoded_path)
                
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
                service_manager.health_service.add_strm_file(strm_path, decoded_path)
                
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

# 添加Emby刷新队列状态API

@router.get("/emby/refresh/status")
async def get_emby_refresh_status():
    """获取Emby刷新队列状态"""
    try:
        # 检查服务是否开启
        if not service_manager.emby_service.emby_enabled:
            logger.info("Emby刷库功能未启用，返回disabled状态")
            return {
                "enabled": False,
                "message": "Emby刷库功能未启用",
                "queue_stats": {"total": 0, "pending": 0, "processing": 0, "success": 0, "failed": 0},
                "recent_success": [],
                "recent_failed": [],
                "queue_items": [],
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        # 获取刷新队列状态
        queue = service_manager.emby_service.refresh_queue
        logger.info(f"获取Emby刷新队列状态，当前队列长度: {len(queue)}")
        
        # 统计队列状态
        total = len(queue)
        pending = sum(1 for item in queue if item.status == "pending")
        processing = sum(1 for item in queue if item.status == "processing")
        success = sum(1 for item in queue if item.status == "success")
        failed = sum(1 for item in queue if item.status == "failed")
        
        # 获取成功项目和失败项目（扩展返回信息，提供更多细节）
        success_items = []
        for item in queue:
            if item.status == "success":
                try:
                    emby_item = await service_manager.emby_service.find_emby_item(item.strm_path)
                    # 只处理存在的项目
                    if emby_item:
                        try:
                            emby_details = {
                                "path": item.strm_path,
                                "name": emby_item.get("Name", "未知"),
                                "type": emby_item.get("Type", "未知"),
                                "id": emby_item.get("Id", ""),
                                "year": emby_item.get("ProductionYear", ""),
                                "refresh_time": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                                "image_tag": emby_item.get("ImageTags", {}).get("Primary", "")
                            }
                            
                            # 获取父级信息（针对剧集）
                            if emby_item.get("Type") == "Episode" and emby_item.get("SeriesId"):
                                try:
                                    series_id = emby_item.get("SeriesId")
                                    series = await service_manager.emby_service.get_item(series_id)
                                    if series:  # 确保系列存在
                                        emby_details["series_name"] = series.get("Name", "")
                                        emby_details["season_number"] = emby_item.get("ParentIndexNumber", 0)
                                        emby_details["episode_number"] = emby_item.get("IndexNumber", 0)
                                        emby_details["display_name"] = f"{emby_details['series_name']} S{emby_details['season_number']:02d}E{emby_details['episode_number']:02d} - {emby_details['name']}"
                                except Exception as e:
                                    logger.warning(f"获取剧集父级信息失败: {str(e)}")
                                    # 使用默认显示名称
                                    emby_details["display_name"] = emby_details['name']
                            
                            # 设置显示名称
                            if "display_name" not in emby_details:
                                if emby_details["type"] == "Movie" and emby_details["year"]:
                                    emby_details["display_name"] = f"{emby_details['name']} ({emby_details['year']})"
                                else:
                                    emby_details["display_name"] = emby_details['name']
                            
                            success_items.append(emby_details)
                        except Exception as e:
                            logger.warning(f"处理Emby项目详情失败: {str(e)}")
                            # 添加基本信息
                            success_items.append({
                                "path": item.strm_path,
                                "name": os.path.basename(item.strm_path),
                                "display_name": os.path.basename(item.strm_path),
                                "type": emby_item.get("Type", "未知"),
                                "refresh_time": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                            })
                    else:
                        # 项目不存在但刷新成功的情况
                        # 可能是刷新后被删除的项目
                        filename = os.path.basename(item.strm_path)
                        name, _ = os.path.splitext(filename)
                        success_items.append({
                            "path": item.strm_path,
                            "name": name,
                            "display_name": name,
                            "type": "已删除",
                            "refresh_time": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                        })
                except Exception as e:
                    # 如果获取详情失败，添加基本信息
                    logger.warning(f"获取Emby项目详情失败: {str(e)}")
                    filename = os.path.basename(item.strm_path)
                    name, _ = os.path.splitext(filename)
                    success_items.append({
                        "path": item.strm_path,
                        "name": name,
                        "display_name": name,
                        "type": "未知",
                        "refresh_time": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    })
        
        # 获取失败项目
        failed_items = []
        for item in queue:
            if item.status == "failed":
                try:
                    # 基本信息
                    filename = os.path.basename(item.strm_path)
                    name, _ = os.path.splitext(filename)
                    
                    failed_info = {
                        "path": item.strm_path,
                        "display_name": name,
                        "error": item.last_error or "未知错误",
                        "retry_count": item.retry_count,
                        "max_retries": service_manager.emby_service.max_retries,
                        "next_retry": datetime.fromtimestamp(item.next_retry_time).strftime("%Y-%m-%d %H:%M:%S") if hasattr(item, "next_retry_time") and item.retry_count < service_manager.emby_service.max_retries else "不再重试",
                        "failed_time": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # 尝试解析文件名获取更多信息
                    # 尝试匹配电视剧模式 (例如: "Show Name S01E02")
                    tv_match = re.search(r'^(.+?)[.\s]+S(\d+)E(\d+)', name, re.IGNORECASE)
                    movie_match = re.search(r'^(.+?)(?:\s*\((\d{4})\))?$', name)
                    
                    if tv_match:
                        failed_info["type"] = "Episode"
                        failed_info["series_name"] = tv_match.group(1).replace(".", " ").strip()
                        failed_info["season_number"] = int(tv_match.group(2))
                        failed_info["episode_number"] = int(tv_match.group(3))
                        failed_info["display_name"] = f"{failed_info['series_name']} S{failed_info['season_number']:02d}E{failed_info['episode_number']:02d}"
                    elif movie_match:
                        failed_info["type"] = "Movie"
                        failed_info["movie_name"] = movie_match.group(1).replace(".", " ").strip()
                        failed_info["year"] = movie_match.group(2) if movie_match.group(2) else ""
                        if failed_info["year"]:
                            failed_info["display_name"] = f"{failed_info['movie_name']} ({failed_info['year']})"
                        else:
                            failed_info["display_name"] = failed_info['movie_name']
                    
                    failed_items.append(failed_info)
                except Exception as e:
                    logger.warning(f"处理失败项目信息时出错: {str(e)}")
                    # 添加基本信息作为回退
                    failed_items.append({
                        "path": item.strm_path,
                        "display_name": os.path.basename(item.strm_path),
                        "error": str(e),
                        "retry_count": getattr(item, "retry_count", 0),
                        "max_retries": service_manager.emby_service.max_retries,
                        "failed_time": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    })
        
        # 按时间排序
        success_items.sort(key=lambda x: x.get("refresh_time", ""), reverse=True)
        failed_items.sort(key=lambda x: x.get("failed_time", ""), reverse=True)
        
        # 获取所有队列项（可选择提供更多详细列表或分页功能）
        # 注意：这里只返回基本信息，前端可以提供专门的接口来获取完整队列
        queue_items = []
        for item in queue:
            try:
                filename = os.path.basename(item.strm_path)
                name, _ = os.path.splitext(filename)
                queue_items.append({
                    "path": item.strm_path,
                    "name": name,
                    "status": item.status,
                    "timestamp": item.timestamp,
                    "time_str": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                    "retry_count": item.retry_count if hasattr(item, "retry_count") else 0,
                    "error": item.last_error if item.status == "failed" else None
                })
            except Exception as e:
                logger.warning(f"处理队列项信息时出错: {str(e)}")
        
        # 按状态和时间排序
        status_order = {"processing": 0, "pending": 1, "failed": 2, "success": 3}
        queue_items.sort(key=lambda x: (status_order.get(x["status"], 999), -x["timestamp"]))
        
        logger.info(f"成功获取Emby刷新队列状态: 共{total}个项目, 待处理{pending}个, 成功{success}个, 失败{failed}个")
        return {
            "enabled": True,
            "is_processing": service_manager.emby_service._is_processing,
            "queue_stats": {
                "total": total,
                "pending": pending,
                "processing": processing,
                "success": success,
                "failed": failed
            },
            "recent_success": success_items[:10],  # 返回最近10个成功项目
            "recent_failed": failed_items[:10],    # 返回最近10个失败项目
            "queue_items": queue_items[:20],       # 返回最近20个队列项目
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logger.error(f"获取Emby刷新队列状态失败: {str(e)}")
        # 详细记录异常信息
        import traceback
        logger.error(f"异常详情: {traceback.format_exc()}")
        
        # 返回基本信息而不是抛出异常
        return {
            "enabled": True,
            "is_processing": False,
            "error": str(e),
            "queue_stats": {"total": 0, "pending": 0, "processing": 0, "success": 0, "failed": 0},
            "recent_success": [],
            "recent_failed": [],
            "queue_items": [],
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
@router.post("/emby/refresh/force")
async def force_refresh_emby_item(path: str = Query(..., description="STRM文件路径")):
    """强制刷新指定的STRM文件对应的Emby项目"""
    try:
        logger.info(f"强制刷新Emby项目请求: 路径={path}")
        
        # 检查服务是否开启
        if not service_manager.emby_service.emby_enabled:
            logger.warning("Emby刷库功能未启用，拒绝刷新请求")
            return {
                "success": False,
                "message": "Emby刷库功能未启用"
            }
        
        # 检查文件是否存在
        if not os.path.exists(path):
            logger.warning(f"文件不存在: {path}")
            return {
                "success": False,
                "message": f"文件不存在: {path}"
            }
            
        # 添加到刷新队列，设置为立即刷新
        item = next((item for item in service_manager.emby_service.refresh_queue if item.strm_path == path), None)
        
        if item:
            # 如果已在队列中，更新时间戳为当前时间
            item.timestamp = time.time()
            item.status = "pending"
            item.retry_count = 0
            message = "已将项目移至队列前端，将立即刷新"
            logger.info(f"项目已在队列中，更新为立即刷新: {path}")
        else:
            # 如果不在队列中，添加到队列
            service_manager.emby_service.add_to_refresh_queue(path)
            # 修改时间戳为当前时间（立即刷新）
            for queue_item in service_manager.emby_service.refresh_queue:
                if queue_item.strm_path == path:
                    queue_item.timestamp = time.time()
                    break
            message = "已添加到刷新队列，将立即刷新"
            logger.info(f"新项目已添加到队列并设置为立即刷新: {path}")
            
        # 保存队列
        service_manager.emby_service._save_refresh_queue()
            
        return {
            "success": True,
            "message": message
        }
    except Exception as e:
        logger.error(f"强制刷新Emby项目失败: {path}, 错误: {str(e)}")
        # 详细记录异常信息
        import traceback
        logger.error(f"异常详情: {traceback.format_exc()}")
        return {
            "success": False,
            "message": f"强制刷新失败: {str(e)}"
        }

@router.post("/emby/test_search")
async def test_emby_search(name: str = Query(...)):
    """测试Emby搜索功能"""
    try:
        # 检查服务是否开启
        if not service_manager.emby_service.emby_enabled:
            return {
                "success": False,
                "message": "Emby刷库功能未启用"
            }
        
        # 使用名称搜索
        items = await service_manager.emby_service.search_by_name(name)
        
        # 提取结果
        results = []
        for item in items:
            results.append({
                "id": item.get("Id"),
                "name": item.get("Name"),
                "type": item.get("Type"),
                "path": item.get("Path", ""),
                "year": item.get("ProductionYear", None)
            })
        
        # 默认值
        media_type = "Unknown"
        media_info = {}
        
        # 判断是电视剧还是电影
        # 提取剧集信息
        tv_match = re.search(r'^(.+?)\s+S(\d+)E(\d+)', name)
        movie_match = re.search(r'^(.+?)(?:\s*\((\d{4})\))?$', name)
        
        if tv_match:
            # 电视剧
            media_type = "TV"
            series_name = tv_match.group(1).strip()
            season_num = int(tv_match.group(2))
            episode_num = int(tv_match.group(3))
            
            # 尝试使用剧集信息查找
            episode = await service_manager.emby_service.find_episode_by_info(
                series_name, season_num, episode_num
            )
            
            media_info = {
                "series_name": series_name,
                "season": season_num,
                "episode": episode_num,
                "episode_found": episode is not None,
                "episode_id": episode.get("Id") if episode else None,
                "episode_name": episode.get("Name") if episode else None
            }
        else:
            # 假设是电影
            media_type = "Movie"
            movie_title = movie_match.group(1).strip() if movie_match else name
            movie_year = int(movie_match.group(2)) if movie_match and movie_match.group(2) else None
            
            # 尝试查找电影
            movie = None
            for item in items:
                if item.get("Type") == "Movie" and item.get("Name", "").lower() == movie_title.lower():
                    if movie_year and item.get("ProductionYear") == movie_year:
                        movie = item
                        break
            
            # 如果没找到完全匹配的，取第一个电影类型
            if not movie:
                for item in items:
                    if item.get("Type") == "Movie":
                        movie = item
                        break
            
            media_info = {
                "title": movie_title,
                "year": movie_year,
                "movie_found": movie is not None,
                "movie_id": movie.get("Id") if movie else None,
                "movie_name": movie.get("Name") if movie else None,
                "movie_year": movie.get("ProductionYear") if movie else None
            }
        
        return {
            "success": True,
            "search_results": results,
            "media_type": media_type,
            "media_info": media_info
        }
    except Exception as e:
        logger.error(f"测试Emby搜索失败: {str(e)}")
        return {
            "success": False,
            "message": f"测试失败: {str(e)}"
        }

@router.post("/emby/refresh/batch")
async def batch_refresh_emby_items(paths: List[str] = Body(..., description="STRM文件路径列表")):
    """批量刷新指定的STRM文件对应的Emby项目"""
    try:
        # 检查服务是否开启
        if not service_manager.emby_service.emby_enabled:
            return {
                "success": False,
                "message": "Emby刷库功能未启用"
            }
            
        # 记录成功和失败的项目
        success_count = 0
        failed_paths = []
            
        for path in paths:
            try:
                # 添加到刷新队列，设置为立即刷新
                item = next((item for item in service_manager.emby_service.refresh_queue if item.strm_path == path), None)
                
                if item:
                    # 如果已在队列中，更新时间戳为当前时间
                    item.timestamp = time.time()
                    item.status = "pending"
                    item.retry_count = 0
                else:
                    # 如果不在队列中，添加到队列
                    service_manager.emby_service.add_to_refresh_queue(path)
                    # 修改时间戳为当前时间（立即刷新）
                    for queue_item in service_manager.emby_service.refresh_queue:
                        if queue_item.strm_path == path:
                            queue_item.timestamp = time.time()
                            break
                
                success_count += 1
            except Exception as e:
                logger.error(f"添加项目到刷新队列失败: {path}, 错误: {str(e)}")
                failed_paths.append(path)
                
        # 保存队列
        service_manager.emby_service._save_refresh_queue()
            
        # 如果全部成功
        if success_count == len(paths):
            return {
                "success": True,
                "message": f"已添加 {success_count} 个项目到刷新队列，将立即刷新"
            }
        # 部分成功
        elif success_count > 0:
            return {
                "success": True,
                "message": f"已添加 {success_count}/{len(paths)} 个项目到刷新队列，有 {len(failed_paths)} 个项目添加失败"
            }
        # 全部失败
        else:
            return {
                "success": False,
                "message": f"添加刷新队列失败，所有 {len(paths)} 个项目均添加失败"
            }
    except Exception as e:
        logger.error(f"批量刷新Emby项目失败: {str(e)}")
        return {
            "success": False,
            "message": f"批量刷新失败: {str(e)}"
        }

@router.post("/emby/refresh/clear")
async def clear_emby_refresh_queue():
    """清空Emby刷新队列"""
    service_manager.emby_service.clear_refresh_queue()
    return {"status": "success", "message": "Emby刷新队列已清空"}

@router.get("/emby/refresh/queue")
async def get_emby_refresh_queue(
    status: Optional[str] = Query(None, description="过滤状态: pending, processing, success, failed"),
    page: int = Query(1, description="页码，从1开始"),
    page_size: int = Query(20, description="每页项目数量"),
    sort_by: str = Query("timestamp", description="排序字段: timestamp, path, status"),
    sort_order: str = Query("desc", description="排序方向: asc, desc")
):
    """获取完整的Emby刷新队列"""
    try:
        # 检查服务是否开启
        if not service_manager.emby_service.emby_enabled:
            return {
                "enabled": False,
                "message": "Emby刷库功能未启用"
            }
            
        # 获取刷新队列
        queue = service_manager.emby_service.refresh_queue
        
        # 转换为可读格式
        queue_items = []
        for item in queue:
            # 基本文件信息
            filename = os.path.basename(item.strm_path)
            name, _ = os.path.splitext(filename)
            
            # 创建项目信息
            queue_item = {
                "path": item.strm_path,
                "name": name,
                "filename": filename,
                "status": item.status,
                "timestamp": item.timestamp,
                "time_str": datetime.fromtimestamp(item.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                "retry_count": item.retry_count if hasattr(item, "retry_count") else 0,
                "max_retries": service_manager.emby_service.max_retries
            }
            
            # 添加状态特定信息
            if item.status == "failed":
                queue_item["error"] = item.last_error
                # 计算下次重试时间
                if hasattr(item, "next_retry_time"):
                    queue_item["next_retry_time"] = item.next_retry_time
                    queue_item["next_retry_str"] = datetime.fromtimestamp(item.next_retry_time).strftime("%Y-%m-%d %H:%M:%S") if item.retry_count < service_manager.emby_service.max_retries else "不再重试"
            
            # 尝试从文件名解析媒体信息
            # 尝试匹配电视剧模式 (例如: "Show Name S01E02")
            tv_match = re.search(r'^(.+?)[.\s]+S(\d+)E(\d+)', name, re.IGNORECASE)
            movie_match = re.search(r'^(.+?)(?:\s*\((\d{4})\))?$', name)
            
            if tv_match:
                queue_item["media_type"] = "Episode"
                queue_item["series_name"] = tv_match.group(1).replace(".", " ").strip()
                queue_item["season_number"] = int(tv_match.group(2))
                queue_item["episode_number"] = int(tv_match.group(3))
                queue_item["display_name"] = f"{queue_item['series_name']} S{queue_item['season_number']:02d}E{queue_item['episode_number']:02d}"
            elif movie_match:
                queue_item["media_type"] = "Movie"
                queue_item["movie_name"] = movie_match.group(1).replace(".", " ").strip()
                queue_item["year"] = movie_match.group(2) if movie_match.group(2) else ""
                if queue_item["year"]:
                    queue_item["display_name"] = f"{queue_item['movie_name']} ({queue_item['year']})"
                else:
                    queue_item["display_name"] = queue_item['movie_name']
            else:
                queue_item["display_name"] = name
            
            # 如果是成功状态，尝试获取Emby中的实际信息
            if item.status == "success":
                try:
                    emby_item = await service_manager.emby_service.find_emby_item(item.strm_path)
                    if emby_item:
                        queue_item["emby_id"] = emby_item.get("Id")
                        queue_item["emby_name"] = emby_item.get("Name")
                        queue_item["emby_type"] = emby_item.get("Type")
                        queue_item["emby_year"] = emby_item.get("ProductionYear", "")
                        
                        # 更新显示名称
                        if emby_item.get("Type") == "Episode":
                            try:
                                series_id = emby_item.get("SeriesId")
                                if series_id:
                                    series = await service_manager.emby_service.get_item(series_id)
                                    queue_item["series_name"] = series.get("Name", "")
                                    queue_item["season_number"] = emby_item.get("ParentIndexNumber", 0)
                                    queue_item["episode_number"] = emby_item.get("IndexNumber", 0)
                                    queue_item["display_name"] = f"{queue_item['series_name']} S{queue_item['season_number']:02d}E{queue_item['episode_number']:02d} - {emby_item.get('Name')}"
                            except Exception as e:
                                logger.warning(f"获取剧集详情失败: {str(e)}")
                        elif emby_item.get("Type") == "Movie" and emby_item.get("ProductionYear"):
                            queue_item["display_name"] = f"{emby_item.get('Name')} ({emby_item.get('ProductionYear')})"
                        else:
                            queue_item["display_name"] = emby_item.get("Name")
                except Exception as e:
                    logger.warning(f"获取Emby项目详情失败: {str(e)}")
            
            queue_items.append(queue_item)
        
        # 过滤
        if status:
            queue_items = [item for item in queue_items if item["status"] == status]
        
        # 排序
        reverse = sort_order.lower() == "desc"
        if sort_by == "timestamp":
            queue_items.sort(key=lambda x: x["timestamp"], reverse=reverse)
        elif sort_by == "path":
            queue_items.sort(key=lambda x: x["path"], reverse=reverse)
        elif sort_by == "status":
            status_order = {"processing": 0, "pending": 1, "failed": 2, "success": 3}
            if reverse:
                queue_items.sort(key=lambda x: (-status_order.get(x["status"], 999), -x["timestamp"]))
            else:
                queue_items.sort(key=lambda x: (status_order.get(x["status"], 999), x["timestamp"]))
        
        # 分页
        total = len(queue_items)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_items = queue_items[start:end]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": paginated_items,
            "status_filter": status,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
    except Exception as e:
        logger.error(f"获取Emby刷新队列详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取刷新队列详情失败: {str(e)}")

@router.post("/strm/delete")
async def delete_strm_files(paths: List[str] = Body(..., description="要删除的STRM文件路径列表")):
    """删除指定的STRM文件"""
    deleted_files = []
    failed_files = []
    
    for path in paths:
        try:
            # 确保路径存在且是一个文件
            if os.path.isfile(path):
                # 从健康状态数据中移除记录
                service_manager.health_service.remove_strm_file(path)
                
                # 物理删除文件
                os.remove(path)
                deleted_files.append(path)
                logger.info(f"成功删除STRM文件: {path}")
            else:
                failed_files.append({"path": path, "reason": "文件不存在或不是一个有效的文件"})
                logger.warning(f"删除STRM文件失败: {path} - 文件不存在或不是一个有效的文件")
        except Exception as e:
            failed_files.append({"path": path, "reason": str(e)})
            logger.error(f"删除STRM文件时出错: {path} - {str(e)}")
    
    # 保存健康状态数据
    service_manager.health_service.save_health_data()
    
    return {
        "status": "success" if not failed_files else "partial_success",
        "deleted": deleted_files,
        "failed": failed_files,
        "message": f"成功删除 {len(deleted_files)} 个文件，失败 {len(failed_files)} 个文件"
    }

@router.post("/strm/replace")
async def batch_replace_strm_content(request: ReplaceRequest):
    """批量查找替换STRM文件的内容"""
    if not request.search_text:
        raise HTTPException(status_code=400, detail="查找的文本不能为空")
    
    try:
        # 获取STRM文件列表
        strm_dir = service_manager.strm_service.settings.output_dir
        
        # 处理指定文件列表或扫描整个目录
        if request.target_paths and len(request.target_paths) > 0:
            strm_files = [Path(path) for path in request.target_paths if os.path.isfile(path) and path.endswith('.strm')]
        else:
            strm_files = await scan_strm_files(strm_dir)
        
        total_files = len(strm_files)
        replaced_files = []
        failed_files = []
        unchanged_files = []
        
        logger.info(f"开始批量替换，共 {total_files} 个STRM文件")
        
        # 预览模式下收集的替换预览
        preview_results = []
        
        for strm_file in strm_files:
            try:
                # 读取STRM文件内容
                with open(strm_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查是否需要替换
                if request.search_text in content:
                    new_content = content.replace(request.search_text, request.replace_text)
                    
                    # 预览模式下只收集信息，不实际修改
                    if request.preview_only:
                        preview_results.append({
                            "path": str(strm_file),
                            "original": content,
                            "new": new_content
                        })
                    else:
                        # 写入新内容
                        with open(strm_file, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        
                        # 添加到已替换列表
                        replaced_files.append(str(strm_file))
                        
                        # 更新健康状态数据
                        target_path = await extract_target_path_from_file(strm_file)
                        service_manager.health_service.update_strm_status(str(strm_file), {
                            "status": "valid",  # 假设替换后文件有效
                            "targetPath": target_path
                        })
                        
                        logger.info(f"成功替换STRM文件内容: {strm_file}")
                else:
                    unchanged_files.append(str(strm_file))
            except Exception as e:
                failed_files.append({"path": str(strm_file), "reason": str(e)})
                logger.error(f"替换STRM文件内容失败: {strm_file}, 错误: {str(e)}")
        
        # 如果不是预览模式，保存健康状态数据
        if not request.preview_only:
            service_manager.health_service.save_health_data()
            
            return {
                "status": "success",
                "total": total_files,
                "replaced": len(replaced_files),
                "unchanged": len(unchanged_files),
                "failed": len(failed_files),
                "replaced_files": replaced_files[:10],  # 限制返回的文件数量
                "failed_details": failed_files[:10],
                "message": f"共处理 {total_files} 个文件，替换 {len(replaced_files)} 个，未变更 {len(unchanged_files)} 个，失败 {len(failed_files)} 个"
            }
        else:
            # 预览模式下返回预览结果
            return {
                "status": "preview",
                "total": total_files,
                "matches": len(preview_results),
                "unchanged": total_files - len(preview_results),
                "preview_results": preview_results[:10],  # 限制预览数量
                "message": f"共 {total_files} 个文件，其中 {len(preview_results)} 个匹配替换条件"
            }
            
    except Exception as e:
        logger.error(f"批量替换STRM文件内容失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量替换失败: {str(e)}") 