from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator
from config import Settings
import json
import os
from typing import Optional
from loguru import logger

router = APIRouter(prefix="/api/config", tags=["config"])

class ConfigUpdate(BaseModel):
    run_after_startup: bool = True
    log_level: str = "INFO"
    slow_mode: bool = False
    alist_url: str = "http://localhost:5244"
    alist_token: str = ""
    alist_scan_path: str = "/"
    encode: bool = True
    is_down_sub: bool = False
    is_down_meta: bool = False
    min_file_size: int = 100
    output_dir: str = "data"

    @validator('log_level')
    def validate_log_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
        if v.upper() not in allowed_levels:
            raise ValueError(f'日志级别必须是以下之一: {", ".join(allowed_levels)}')
        return v.upper()

    @validator('alist_url')
    def validate_alist_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Alist服务器地址必须以http://或https://开头')
        return v

    @validator('min_file_size')
    def validate_min_file_size(cls, v):
        if v < 0:
            raise ValueError('最小文件大小不能小于0')
        return v

    @validator('output_dir')
    def validate_output_dir(cls, v):
        if not v:
            raise ValueError('输出目录不能为空')
        return v

def load_env_file():
    """从.env文件加载配置"""
    try:
        with open(".env", "r", encoding="utf-8") as f:
            config = {}
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        key, value = line.split("=", 1)
                        config[key.lower()] = value.strip('"').strip("'")
                    except ValueError:
                        logger.warning(f"忽略无效的配置行: {line}")
            return config
    except FileNotFoundError:
        logger.info(".env文件不存在，将使用默认配置")
        return {}
    except Exception as e:
        logger.error(f"加载.env文件失败: {str(e)}")
        return {}

def save_env_file(config: dict):
    """保存配置到.env文件"""
    try:
        env_content = f"""# 基本配置
RUN_AFTER_STARTUP={str(config['run_after_startup']).lower()}
LOG_LEVEL={config['log_level']}
SLOW_MODE={str(config['slow_mode']).lower()}

# Alist配置
ALIST_URL={config['alist_url']}
ALIST_TOKEN={config['alist_token']}
ALIST_SCAN_PATH={config['alist_scan_path']}

# 文件处理配置
ENCODE={str(config['encode']).lower()}
IS_DOWN_SUB={str(config['is_down_sub']).lower()}
IS_DOWN_META={str(config['is_down_meta']).lower()}
MIN_FILE_SIZE={config['min_file_size']}
OUTPUT_DIR={config['output_dir']}
"""
        # 创建备份
        if os.path.exists(".env"):
            os.rename(".env", ".env.bak")

        # 写入新配置
        with open(".env", "w", encoding="utf-8") as f:
            f.write(env_content)

        # 删除备份
        if os.path.exists(".env.bak"):
            os.remove(".env.bak")

    except Exception as e:
        # 如果写入失败，恢复备份
        if os.path.exists(".env.bak"):
            os.rename(".env.bak", ".env")
        raise Exception(f"保存配置失败: {str(e)}")

@router.get("")
async def get_config():
    """获取当前配置"""
    try:
        # 尝试从.env文件读取配置
        config = load_env_file()
        
        # 如果.env为空或不存在，使用默认配置
        if not config:
            config = Settings().dict()
        
        # 转换布尔值和数字
        bool_fields = ['run_after_startup', 'slow_mode', 'encode', 'is_down_sub', 'is_down_meta']
        for field in bool_fields:
            if field in config:
                config[field] = str(config[field]).lower() == 'true'
        
        if 'min_file_size' in config:
            try:
                config['min_file_size'] = int(config['min_file_size'])
            except ValueError:
                config['min_file_size'] = 100

        return {"code": 200, "data": config}
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def update_config(config: ConfigUpdate):
    """更新配置"""
    try:
        # 保存配置到.env文件
        save_env_file(config.dict())
        
        # 重新加载Settings
        settings = Settings()
        
        return {"code": 200, "message": "配置更新成功"}
    except ValueError as e:
        # 验证错误
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 其他错误
        logger.error(f"更新配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test_connection")
async def test_connection(data: dict):
    """测试Alist连接"""
    from services.strm_service import StrmService
    
    try:
        # 创建临时服务实例进行测试
        temp_settings = Settings()
        temp_settings.alist_url = data.get('url', '')
        temp_settings.alist_token = data.get('token', '')
        
        service = StrmService()
        # 测试获取根目录列表
        files = await service._list_files("/")
        await service.close()
        
        return {"code": 200, "message": "连接测试成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接测试失败: {str(e)}") 