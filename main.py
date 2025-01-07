import os
import asyncio
import uvicorn
from loguru import logger
from config import Settings
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes import config, strm, health, archive
from contextlib import asynccontextmanager
from services.service_manager import service_manager, scheduler_service, strm_service

settings = Settings()

async def run_telegram_polling():
    """运行Telegram轮询"""
    max_retries = 5  # 最大重试次数
    retry_delay = 5  # 重试延迟（秒）
    current_retry = 0
    
    while True:  # 永久循环，确保轮询不会停止
        try:
            if service_manager.telegram_service.application:
                current_retry = 0  # 重置重试计数
                await service_manager.telegram_service.application.updater.start_polling(
                    drop_pending_updates=True,  # 丢弃积压的更新
                    allowed_updates=["message", "callback_query"],  # 只接收消息和回调查询
                    read_timeout=30,  # 读取超时时间
                    write_timeout=30,  # 写入超时时间
                    connect_timeout=30,  # 连接超时时间
                    pool_timeout=30  # 连接池超时时间
                )
            else:
                await asyncio.sleep(10)  # 如果应用未初始化，等待10秒
                continue
                
        except Exception as e:
            logger.error(f"Telegram轮询出错: {str(e)}")
            
            if current_retry < max_retries:
                current_retry += 1
                wait_time = retry_delay * current_retry
                logger.info(f"等待 {wait_time} 秒后进行第 {current_retry} 次重试...")
                await asyncio.sleep(wait_time)
                
                # 尝试重新初始化和启动服务
                try:
                    await service_manager.telegram_service.close()
                    await service_manager.telegram_service.initialize()
                    await service_manager.telegram_service.start()
                except Exception as init_error:
                    logger.error(f"重新初始化Telegram服务失败: {str(init_error)}")
            else:
                logger.error("达到最大重试次数，等待60秒后重置重试计数...")
                current_retry = 0
                await asyncio.sleep(60)

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
    
    # 初始化和启动服务管理器
    await service_manager.initialize()
    await service_manager.start()
    
    # 启动Telegram轮询
    asyncio.create_task(run_telegram_polling())
    
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
    if service_manager.telegram_service.application:
        await service_manager.telegram_service.application.updater.stop()
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

# 挂载静态文件
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port) 