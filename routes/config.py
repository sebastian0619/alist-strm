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

def get_env_value(key: str, default: str = "") -> str:
    """获取环境变量值，遵循优先级顺序"""
    # 1. 从系统环境变量获取（包括docker-compose设置的环境变量）
    env_value = os.getenv(key.upper())
    if env_value is not None:
        return env_value
    
    # 2. 从.env文件获取
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        k, v = line.split("=", 1)
                        if k.upper() == key.upper():
                            return v.strip('"').strip("'")
                    except ValueError:
                        continue
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"读取.env文件时出错: {str(e)}")
    
    # 3. 返回默认值
    return default

def load_config():
    """加载配置，遵循优先级顺序"""
    # 获取Settings类的默认值作为基础
    settings = Settings()
    config = settings.dict()
    
    # 定义需要处理的配置项
    config_keys = {
        'run_after_startup': str(config['run_after_startup']).lower(),
        'log_level': config['log_level'],
        'slow_mode': str(config['slow_mode']).lower(),
        'alist_url': config['alist_url'],
        'alist_token': config['alist_token'],
        'alist_scan_path': config['alist_scan_path'],
        'encode': str(config['encode']).lower(),
        'is_down_sub': str(config['is_down_sub']).lower(),
        'is_down_meta': str(config['is_down_meta']).lower(),
        'min_file_size': str(config['min_file_size']),
        'output_dir': config['output_dir']
    }
    
    # 按优先级获取每个配置项的值
    for key, default in config_keys.items():
        value = get_env_value(key, default)
        
        # 转换布尔值和数字
        if key in ['run_after_startup', 'slow_mode', 'encode', 'is_down_sub', 'is_down_meta']:
            config[key] = value.lower() == 'true'
        elif key == 'min_file_size':
            try:
                config[key] = int(value)
            except ValueError:
                config[key] = int(default)
        else:
            config[key] = value
    
    return config

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
        # 按优先级加载配置
        config = load_config()
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