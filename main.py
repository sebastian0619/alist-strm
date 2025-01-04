import os
import asyncio
from loguru import logger
from services.strm_service import StrmService
from config import Settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes import config, strm

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

# 配置日志
settings = Settings()
if settings.log_level:
    logger.remove()
    logger.add(lambda msg: print(msg), level=settings.log_level)

# 挂载静态文件
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
else:
    logger.warning("静态文件目录不存在，前端界面将无法访问")

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

# 健康检查接口
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port) 