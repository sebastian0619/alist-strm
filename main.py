import os
import asyncio
from loguru import logger
from services.strm_service import StrmService
from config import Settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes import config, strm, health

app = FastAPI()

# 添加CORS支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(config.router)
app.include_router(strm.router)
app.include_router(health.router)

# 配置日志
settings = Settings()
if settings.log_level:
    logger.remove()
    logger.add(lambda msg: print(msg), level=settings.log_level)

# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    logger.info(f"挂载静态文件目录: {static_dir}")
    try:
        # 检查目录内容
        files = os.listdir(static_dir)
        logger.info(f"静态文件目录内容: {files}")
        
        # 检查是否存在 index.html
        if "index.html" in files:
            app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
            logger.info("静态文件挂载成功")
        else:
            logger.warning("静态文件目录中没有找到 index.html")
    except Exception as e:
        logger.error(f"挂载静态文件失败: {str(e)}")
else:
    logger.warning(f"静态文件目录不存在: {static_dir}")

@app.on_event("startup")
async def startup_event():
    """启动事件"""
    # 确保输出目录存在
    os.makedirs(settings.output_dir, exist_ok=True)
    
    # 检查配置
    logger.debug(f"当前配置: run_after_startup={settings.run_after_startup}")
    
    if settings.run_after_startup:
        logger.info("配置了自动运行，开始生成STRM文件")
        strm_service = StrmService()
        try:
            await strm_service.strm()
            logger.info("STRM文件生成完成")
        except Exception as e:
            logger.error(f"STRM生成失败: {str(e)}")
        finally:
            await strm_service.close()
    else:
        logger.info("等待通过Web界面手动触发STRM生成")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port) 