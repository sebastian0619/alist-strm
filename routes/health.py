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

class HealthScanResult(BaseModel):
    scanTime: float
    scanType: str
    problems: List[HealthProblem]

class RepairRequest(BaseModel):
    paths: List[str]
    type: str

# 存储最近一次扫描结果
_last_scan_result: Optional[HealthScanResult] = None
_is_scanning: bool = False
_scan_progress: int = 0
_scan_status: str = ""
_scan_type: str = "all"

@router.get("/status")
async def get_scan_status():
    """获取当前扫描状态"""
    global _is_scanning, _scan_progress, _scan_status, _last_scan_result, _scan_type
    
    return {
        "isScanning": _is_scanning,
        "progress": _scan_progress,
        "status": _scan_status,
        "lastScanTime": _last_scan_result.scanTime if _last_scan_result else None,
        "lastScanType": _last_scan_result.scanType if _last_scan_result else None,
        "problemCount": len(_last_scan_result.problems) if _last_scan_result else 0
    }

@router.post("/start")
async def start_scan(type: str = Query("all", description="扫描类型: strm_validity(STRM有效性), video_coverage(视频覆盖), all(全部)")):
    """开始健康扫描"""
    global _is_scanning, _scan_progress, _scan_status, _last_scan_result, _scan_type
    
    if _is_scanning:
        raise HTTPException(status_code=400, detail="扫描已在进行中")
    
    if type not in ["strm_validity", "video_coverage", "all"]:
        raise HTTPException(status_code=400, detail="无效的扫描类型")
    
    # 更新扫描类型
    _scan_type = type
    
    # 开启一个异步任务执行扫描
    _is_scanning = True
    _scan_progress = 0
    _scan_status = "正在初始化扫描..."
    
    try:
        # 创建异步任务执行扫描
        asyncio.create_task(perform_health_scan(type))
        
        return {"message": "健康扫描已开始", "status": "scanning", "type": type}
    except Exception as e:
        _is_scanning = False
        logger.error(f"启动健康扫描失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动扫描失败: {str(e)}")

async def perform_health_scan(scan_type: str):
    """执行健康扫描"""
    global _is_scanning, _scan_progress, _scan_status, _last_scan_result
    
    try:
        _scan_progress = 0
        all_problems = []
        
        # 根据扫描类型选择执行的检测
        if scan_type in ["strm_validity", "all"]:
            _scan_status = "正在检查STRM文件有效性..."
            invalid_strm_files = await check_strm_validity()
            all_problems.extend(invalid_strm_files)
            _scan_progress = 50 if scan_type == "all" else 100
            
        if scan_type in ["video_coverage", "all"]:
            _scan_status = "正在检查视频文件覆盖情况..."
            missing_strm_files = await check_video_coverage()
            all_problems.extend(missing_strm_files)
            _scan_progress = 100
        
        # 保存扫描结果
        _last_scan_result = HealthScanResult(
            scanTime=time.time(),
            scanType=scan_type,
            problems=[HealthProblem(**problem) for problem in all_problems]
        )
        
        _scan_status = "扫描完成"
        logger.info(f"健康扫描完成，发现 {len(all_problems)} 个问题")
    
    except Exception as e:
        logger.error(f"健康扫描过程中出错: {str(e)}")
        _scan_status = f"扫描出错: {str(e)}"
    
    finally:
        _is_scanning = False

async def check_strm_validity():
    """检查STRM文件有效性
    
    检查每个STRM文件指向的网盘文件是否存在
    返回无效的STRM文件列表
    """
    global _scan_progress, _scan_status, _scan_type
    
    invalid_strm_files = []
    
    # 获取STRM目录
    strm_dir = service_manager.strm_service.settings.output_dir
    
    # 扫描所有STRM文件
    strm_files = await scan_strm_files(strm_dir)
    total_files = len(strm_files)
    
    for idx, strm_file in enumerate(strm_files):
        # 更新进度
        if _scan_type == "strm_validity":
            _scan_progress = int((idx / total_files) * 100) if total_files > 0 else 100
        else: # all 类型
            _scan_progress = int(((idx / total_files) * 50)) if total_files > 0 else 50
            
        _scan_status = f"正在检查STRM文件有效性 ({idx+1}/{total_files})..."
        
        # 检查STRM文件指向的源文件是否存在
        is_valid, reason = await check_strm_source(strm_file)
        
        if not is_valid:
            file_path = str(strm_file)
            invalid_strm_files.append({
                "id": f"invalid_{len(invalid_strm_files)}",
                "type": "invalid_strm",
                "path": file_path,
                "details": f"STRM文件无效: {reason}",
                "discoveryTime": time.time()
            })
    
    return invalid_strm_files

async def check_video_coverage():
    """检查视频文件覆盖情况
    
    扫描Alist网盘中的视频文件，检查是否都有对应的STRM文件
    返回缺失STRM文件的列表
    """
    global _scan_progress, _scan_status, _scan_type
    
    missing_strm_files = []
    
    # 获取STRM目录和Alist扫描路径
    strm_dir = Path(service_manager.strm_service.settings.output_dir)
    alist_scan_path = service_manager.strm_service.settings.alist_scan_path
    
    # 获取所有已生成的STRM文件
    existing_strm_files = await scan_strm_files(strm_dir)
    existing_strm_paths = set()
    
    # 提取STRM文件内容，获取它们指向的路径
    for strm_file in existing_strm_files:
        try:
            with open(strm_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
                # 从URL中提取Alist路径
                if content.startswith('http'):
                    parts = content.split('/d/')
                    if len(parts) >= 2:
                        alist_path = '/d/' + parts[1]
                        existing_strm_paths.add(alist_path)
        except Exception as e:
            logger.warning(f"读取STRM文件失败: {strm_file}, 错误: {str(e)}")
    
    # 获取Alist网盘中的所有视频文件
    try:
        # 递归扫描Alist路径下的视频文件
        _scan_status = "正在扫描Alist网盘视频文件..."
        video_files = await scan_alist_videos(alist_scan_path)
        total_files = len(video_files)
        
        for idx, video_file in enumerate(video_files):
            # 更新进度
            if _scan_type == "video_coverage":
                _scan_progress = int((idx / total_files) * 100) if total_files > 0 else 100
            else: # all 类型
                _scan_progress = 50 + int(((idx / total_files) * 50)) if total_files > 0 else 100
                
            _scan_status = f"正在检查视频文件覆盖情况 ({idx+1}/{total_files})..."
            
            # 构建Alist URL路径
            video_url_path = f"/d{video_file}" if not video_file.startswith('/d') else video_file
            
            # 如果没有对应的STRM文件
            if video_url_path not in existing_strm_paths:
                missing_strm_files.append({
                    "id": f"missing_{len(missing_strm_files)}",
                    "type": "missing_strm",
                    "path": video_file,
                    "details": f"网盘中的视频文件没有对应的STRM文件",
                    "discoveryTime": time.time()
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
        
        # 使用Alist API检查文件是否存在
        # 先从URL中提取Alist路径
        try:
            parts = source_url.split('/d/')
            if len(parts) < 2:
                return False, "URL格式不正确"
            
            alist_path = '/d/' + parts[1]
            
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

async def check_alist_file_exists(path):
    """检查Alist中的文件是否存在"""
    try:
        # 使用Alist API检查文件是否存在
        # 这里使用模拟实现，实际应该使用service_manager中的Alist客户端
        # 从/d/path格式中提取实际路径
        real_path = path.replace('/d', '', 1) if path.startswith('/d') else path
        
        # 使用Alist API查询文件信息
        alist_url = service_manager.strm_service.settings.alist_url
        alist_token = service_manager.strm_service.settings.alist_token
        
        # 使用httpx发送请求
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": alist_token,
                "Content-Type": "application/json"
            }
            
            response = await client.post(
                f"{alist_url}/api/fs/get", 
                json={"path": real_path},
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    return True
                    
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
                    video_files.append(file.get("path"))
                    
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
async def get_health_problems():
    """获取健康问题列表"""
    global _last_scan_result
    
    if not _last_scan_result:
        return {"problems": [], "scanTime": None}
    
    return {
        "problems": [problem.dict() for problem in _last_scan_result.problems],
        "scanTime": _last_scan_result.scanTime
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
            except Exception as e:
                logger.error(f"删除文件失败: {path}, 错误: {str(e)}")
        
        # 如果有最后扫描结果，从中移除已修复的问题
        if _last_scan_result:
            # 获取修复的路径集合
            fixed_paths = set(request.paths)
            
            # 过滤问题列表
            _last_scan_result.problems = [
                p for p in _last_scan_result.problems 
                if not (p.type == "invalid_strm" and p.path in fixed_paths)
            ]
        
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
                video_url = f"{alist_url}/d{video_path}"
                
                # 获取文件名和扩展名
                filename = os.path.basename(video_path)
                name, _ = os.path.splitext(filename)
                
                # 计算输出路径
                output_dir = service_manager.strm_service.settings.output_dir
                rel_path = os.path.dirname(video_path)
                
                # 创建输出目录
                full_output_dir = os.path.join(output_dir, rel_path.lstrip('/'))
                os.makedirs(full_output_dir, exist_ok=True)
                
                # 生成STRM文件
                strm_path = os.path.join(full_output_dir, f"{name}.strm")
                with open(strm_path, 'w', encoding='utf-8') as f:
                    f.write(video_url)
                    
                success_count += 1
                
            except Exception as e:
                logger.error(f"为视频生成STRM文件失败: {video_path}, 错误: {str(e)}")
        
        # 如果有最后扫描结果，从中移除已修复的问题
        if _last_scan_result:
            # 获取修复的路径集合
            fixed_paths = set(request.paths)
            
            # 过滤问题列表
            _last_scan_result.problems = [
                p for p in _last_scan_result.problems 
                if not (p.type == "missing_strm" and p.path in fixed_paths)
            ]
        
        return {"success": True, "message": f"已成功为 {success_count} 个视频生成STRM文件"}
    
    except Exception as e:
        logger.error(f"生成STRM文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}") 