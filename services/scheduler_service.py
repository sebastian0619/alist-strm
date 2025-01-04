from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from config import Settings
from services.strm_service import StrmService

class SchedulerService:
    def __init__(self):
        self.settings = Settings()
        self.scheduler = AsyncIOScheduler()
        self.strm_service = StrmService()
        self.job = None
    
    async def start(self):
        """启动调度器"""
        if not self.settings.schedule_enabled:
            logger.info("定时任务未启用")
            return
            
        if self.scheduler.running:
            logger.warning("调度器已在运行")
            return
            
        try:
            # 添加定时任务
            self.job = self.scheduler.add_job(
                self.strm_service.strm,
                CronTrigger.from_crontab(self.settings.schedule_cron),
                id='strm_job',
                replace_existing=True
            )
            
            # 启动调度器
            self.scheduler.start()
            logger.info(f"定时任务已启动，执行计划: {self.settings.schedule_cron}")
            
        except Exception as e:
            logger.error(f"启动定时任务失败: {str(e)}")
            raise
    
    async def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("定时任务已停止")
    
    async def update_schedule(self, enabled: bool, cron: str = None):
        """更新定时任务配置"""
        try:
            if self.scheduler.running:
                await self.stop()
            
            if enabled:
                if cron:
                    self.settings.schedule_cron = cron
                self.settings.schedule_enabled = True
                await self.start()
            else:
                self.settings.schedule_enabled = False
                logger.info("定时任务已禁用")
            
        except Exception as e:
            logger.error(f"更新定时任务失败: {str(e)}")
            raise 