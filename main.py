from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import Settings
from services.strm_service import StrmService
from services.copy_service import CopyService
from bot.telegram_bot import setup_telegram_bot
from routes import notify, config, strm

app = FastAPI()

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = Settings()
scheduler = AsyncIOScheduler()
strm_service = StrmService()
copy_service = CopyService()

# 注册路由
app.include_router(notify.router)
app.include_router(config.router)
app.include_router(strm.router)

@app.on_event("startup")
async def startup_event():
    # 设置日志级别
    if settings.log_level:
        logger.level(settings.log_level)
    
    # 设置并发度
    if not settings.slow_mode:
        import multiprocessing
        import os
        os.environ["PYTHONASYNCIODEBUG"] = "1"
        multiprocessing.cpu_count()
    
    # 初始化定时任务
    scheduler.start()
    
    # 如果配置为启动时执行
    if settings.run_after_startup:
        await strm_service.strm()
        if settings.src_dir and settings.dst_dir:
            await copy_service.sync_files()
    else:
        logger.info("启动立即执行任务未启用，等待定时任务处理")
    
    # 设置Telegram机器人
    if settings.tg_user_id and settings.tg_token:
        await setup_telegram_bot()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    await strm_service.close()
    await copy_service.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8081, reload=True) 