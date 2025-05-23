import os
import uvicorn
from loguru import logger
from config import Settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes import config, strm, health, archive, tmdb
from contextlib import asynccontextmanager
from services.service_manager import service_manager, scheduler_service, strm_service
from services.strm_monitor_service import StrmMonitorService

settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("应用启动...")
    
    # 设置日志级别
    logger.remove()
    # 添加控制台输出
    logger.add(lambda msg: print(msg), level=settings.log_level)
    # 添加文件输出
    logger.add(
        "logs/alist-strm.log",
        rotation="10 MB",  # 每10MB切割一次
        retention="1 week",  # 保留1周的日志
        compression="zip",  # 压缩旧日志
        encoding="utf-8",
        level=settings.log_level
    )
    
    # 设置更详细的日志 - 针对特定模块
    import logging
    # 设置Emby服务日志为更详细级别
    logging.getLogger("services.emby_service").setLevel(logging.DEBUG if settings.log_level == "DEBUG" else logging.INFO)
    # 设置HTTP客户端日志
    logging.getLogger("httpx").setLevel(logging.INFO)
    
    # 初始化和启动服务管理器
    await service_manager.initialize()
    await service_manager.start()
    
    # 启动定时任务
    if settings.schedule_enabled:
        await scheduler_service.start()
    
    # 如果配置了启动时运行，则启动扫描
    if settings.run_after_startup:
        logger.info("配置为启动时运行，开始扫描...")
        await strm_service.strm()
    else:
        logger.info("等待通过Web界面手动触发STRM生成")
    
    yield
    
    # 关闭时
    logger.info("应用关闭...")
    await service_manager.close()
    await strm_service.close()
    await scheduler_service.stop()

app = FastAPI(lifespan=lifespan)

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
app.include_router(archive.router)
app.include_router(tmdb.router)

# 挂载静态文件
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port) 