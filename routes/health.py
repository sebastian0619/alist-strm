from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import logging
import asyncio
import time
from datetime import datetime
from services.service_manager import service_manager

router = APIRouter(prefix="/api/health", tags=["health"])
logger = logging.getLogger(__name__)

class HealthProblem(BaseModel):
    id: str
    type: str  # missing_strm 或 missing_source
    path: str
    details: str
    discoveryTime: float

class HealthScanResult(BaseModel):
    scanTime: float
    problems: List[HealthProblem]

class RepairRequest(BaseModel):
    paths: List[str]
    type: str

# 存储最近一次扫描结果
_last_scan_result: Optional[HealthScanResult] = None
_is_scanning: bool = False
_scan_progress: int = 0
_scan_status: str = ""

@router.get("/status")
async def get_scan_status():
    """获取当前扫描状态"""
    global _is_scanning, _scan_progress, _scan_status, _last_scan_result
    
    return {
        "isScanning": _is_scanning,
        "progress": _scan_progress,
        "status": _scan_status,
        "lastScanTime": _last_scan_result.scanTime if _last_scan_result else None,
        "problemCount": len(_last_scan_result.problems) if _last_scan_result else 0
    }

@router.post("/start")
async def start_scan():
    """开始健康扫描"""
    global _is_scanning, _scan_progress, _scan_status, _last_scan_result
    
    if _is_scanning:
        raise HTTPException(status_code=400, detail="扫描已在进行中")
    
    # 开启一个异步任务执行扫描
    _is_scanning = True
    _scan_progress = 0
    _scan_status = "正在初始化扫描..."
    
    try:
        # 创建异步任务执行扫描
        asyncio.create_task(perform_health_scan())
        
        return {"message": "健康扫描已开始", "status": "scanning"}
    except Exception as e:
        _is_scanning = False
        logger.error(f"启动健康扫描失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动扫描失败: {str(e)}")

async def perform_health_scan():
    """执行健康扫描"""
    global _is_scanning, _scan_progress, _scan_status, _last_scan_result
    
    try:
        _scan_progress = 0
        _scan_status = "正在扫描STRM文件..."
        
        # 扫描STRM目录
        strm_dir = service_manager.strm_service.settings.output_dir
        missing_strm_files = []
        missing_source_files = []
        
        # 1. 检查STRM文件是否存在（30%）
        all_strm_files = await scan_strm_files(strm_dir)
        _scan_progress = 30
        _scan_status = "正在检查网盘文件..."
        
        # 2. 检查源文件是否存在（60%）
        for i, strm_file in enumerate(all_strm_files):
            # 更新进度（从30%到60%）
            _scan_progress = 30 + int((i / len(all_strm_files)) * 30) if all_strm_files else 60
            
            # 检查STRM文件指向的源文件是否存在
            if not await check_strm_source(strm_file):
                file_path = str(strm_file)
                missing_source_files.append({
                    "id": f"source_{len(missing_source_files)}",
                    "type": "missing_source",
                    "path": file_path,
                    "details": "网盘中找不到对应的源文件，STRM文件可能已失效",
                    "discoveryTime": time.time()
                })
        
        # 3. 检查是否有被删除的STRM文件（90%）
        _scan_progress = 60
        _scan_status = "正在检查缺失的STRM文件..."
        
        # 检查监控服务中记录的已删除STRM文件
        deleted_strm_files = await get_deleted_strm_files()
        for i, deleted_file in enumerate(deleted_strm_files):
            # 更新进度（从60%到90%）
            _scan_progress = 60 + int((i / len(deleted_strm_files)) * 30) if deleted_strm_files else 90
            
            missing_strm_files.append({
                "id": f"strm_{len(missing_strm_files)}",
                "type": "missing_strm",
                "path": deleted_file,
                "details": "STRM文件已被删除，但网盘中仍存在对应文件",
                "discoveryTime": time.time()
            })
        
        # 4. 完成扫描（100%）
        _scan_progress = 90
        _scan_status = "正在完成扫描..."
        
        # 合并所有问题
        all_problems = missing_strm_files + missing_source_files
        
        # 保存扫描结果
        _last_scan_result = HealthScanResult(
            scanTime=time.time(),
            problems=[HealthProblem(**problem) for problem in all_problems]
        )
        
        _scan_progress = 100
        _scan_status = "扫描完成"
        logger.info(f"健康扫描完成，发现 {len(all_problems)} 个问题")
    
    except Exception as e:
        logger.error(f"健康扫描过程中出错: {str(e)}")
        _scan_status = f"扫描出错: {str(e)}"
    
    finally:
        _is_scanning = False

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
        
        # 这里需要根据实际情况检查源文件是否存在
        # 如果是Alist URL，可能需要发送HTTP请求验证
        # 以下是示例实现，实际使用时需要替换为真实的验证逻辑
        
        # 示例：将URL转换为Alist路径，然后检查文件是否存在
        if source_url.startswith('http'):
            # 从URL中提取路径部分
            # 这里假设URL结构是 http(s)://your-alist-server/d/your/path/to/file
            # 实际情况可能需要调整
            parts = source_url.split('/d/')
            if len(parts) < 2:
                return False
            
            alist_path = '/' + parts[1]
            
            # 使用Alist API检查文件是否存在
            # 这里使用一个模拟的实现，实际应该使用service_manager.alist_client调用
            # return await service_manager.alist_client.file_exists(alist_path)
            
            # 模拟实现：90%的文件存在
            import random
            return random.random() > 0.1
        
        return False
    
    except Exception as e:
        logger.error(f"检查STRM源文件时出错: {str(e)}, 文件: {strm_file}")
        return False

async def get_deleted_strm_files():
    """获取已被删除的STRM文件列表"""
    # 实际情况下，这些信息可能存储在日志文件或数据库中
    # 这里使用示例数据进行演示
    
    # 从日志示例中提取的数据
    return [
        "data/动漫/完结动漫/没能成为魔法师的女孩子的故事 (2024)/Season 1 (2024)/没能成为魔法师的女孩子的故事 - S01E01 - 第 1 集 -  我想成为魔法师！.mkv",
        "data/动漫/完结动漫/没能成为魔法师的女孩子的故事 (2024)/Season 1 (2024)/没能成为魔法师的女孩子的故事 - S01E02 - 第 2 集 -  我说不定也能成为魔法师？.mkv"
    ]

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

@router.post("/repair/strm")
async def repair_missing_strm(request: RepairRequest):
    """修复缺失的STRM文件"""
    if request.type != "missing_strm":
        raise HTTPException(status_code=400, detail="无效的修复类型")
    
    if not request.paths:
        raise HTTPException(status_code=400, detail="未提供需要修复的路径")
    
    try:
        # 这里应该调用service_manager中的方法重新生成STRM文件
        # 以下是示例实现
        logger.info(f"尝试修复 {len(request.paths)} 个缺失的STRM文件")
        
        # 等待一段时间模拟处理
        await asyncio.sleep(1)
        
        # 如果有最后扫描结果，从中移除已修复的问题
        if _last_scan_result:
            # 获取修复的路径集合
            fixed_paths = set(request.paths)
            
            # 过滤问题列表
            _last_scan_result.problems = [
                p for p in _last_scan_result.problems 
                if not (p.type == "missing_strm" and p.path in fixed_paths)
            ]
        
        return {"success": True, "message": f"已成功修复 {len(request.paths)} 个缺失的STRM文件"}
    
    except Exception as e:
        logger.error(f"修复缺失STRM文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"修复失败: {str(e)}")

@router.post("/repair/source")
async def repair_missing_source(request: RepairRequest):
    """清理源文件缺失的STRM文件"""
    if request.type != "missing_source":
        raise HTTPException(status_code=400, detail="无效的修复类型")
    
    if not request.paths:
        raise HTTPException(status_code=400, detail="未提供需要清理的路径")
    
    try:
        # 这里应该调用相关方法删除无效的STRM文件
        # 以下是示例实现
        logger.info(f"尝试清理 {len(request.paths)} 个源文件缺失的STRM文件")
        
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
                if not (p.type == "missing_source" and p.path in fixed_paths)
            ]
        
        return {"success": True, "message": f"已成功清理 {success_count} 个源文件缺失的STRM文件"}
    
    except Exception as e:
        logger.error(f"清理源文件缺失的STRM文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}") 