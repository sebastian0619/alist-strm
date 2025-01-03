from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.strm_service import StrmService
from loguru import logger

class ScheduledTasks:
    def __init__(self, scheduler: AsyncIOScheduler):
        self.scheduler = scheduler
        self.strm_service = StrmService()
        self._setup_jobs()
    
    def _setup_jobs(self):
        """设置定时任务"""
        # 每天凌晨2点执行
        self.scheduler.add_job(
            self.strm_task,
            'cron',
            hour=2,
            minute=0,
            id='strm_task'
        )
        logger.info("定时任务已设置")
    
    async def strm_task(self):
        """定时执行的流媒体处理任务"""
        try:
            await self.strm_service.strm()
        except Exception as e:
            logger.error(f"定时任务执行失败: {str(e)}")
    
    async def cleanup(self):
        """清理资源"""
        await self.strm_service.close() 