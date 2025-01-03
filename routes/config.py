from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import Settings
import json
import os

router = APIRouter(prefix="/api/config", tags=["config"])

class ConfigUpdate(BaseModel):
    run_after_startup: bool = True
    log_level: str = "INFO"
    slow_mode: bool = False
    alist_url: str = "http://localhost:5244"
    alist_token: str = ""
    alist_scan_path: str = "/115/video"
    encode: bool = True
    is_down_sub: bool = False
    min_file_size: int = 100
    output_dir: str = "data"

@router.get("")
async def get_config():
    """获取当前配置"""
    try:
        with open(".env", "r", encoding="utf-8") as f:
            config = {}
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    config[key.lower()] = value.strip('"').strip("'")
        return config
    except FileNotFoundError:
        return Settings().dict()

@router.post("")
async def update_config(config: ConfigUpdate):
    """更新配置"""
    try:
        # 将配置转换为环境变量格式
        env_content = f"""# 基本配置
RUN_AFTER_STARTUP={str(config.run_after_startup).lower()}
LOG_LEVEL={config.log_level}
SLOW_MODE={str(config.slow_mode).lower()}

# Alist配置
ALIST_URL={config.alist_url}
ALIST_TOKEN={config.alist_token}
ALIST_SCAN_PATH={config.alist_scan_path}

# 文件处理配置
ENCODE={str(config.encode).lower()}
IS_DOWN_SUB={str(config.is_down_sub).lower()}
MIN_FILE_SIZE={config.min_file_size}
OUTPUT_DIR={config.output_dir}
"""
        # 写入.env文件
        with open(".env", "w", encoding="utf-8") as f:
            f.write(env_content)
        return {"message": "配置更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 