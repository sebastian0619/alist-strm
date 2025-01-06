from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from config import Settings
import importlib

class SchedulerService:
    def __init__(self):
        self.settings = Settings()
        self.scheduler = AsyncIOScheduler()
        self.job = None
    
    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager
    
    async def _run_strm_job(self):
        """执行STRM扫描任务"""
        try:
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message("⏰ 开始执行定时STRM扫描任务")
            await service_manager.strm_service.strm()
        except Exception as e:
            error_msg = f"❌ 定时任务执行失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
    
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
                self._run_strm_job,
                CronTrigger.from_crontab(self.settings.schedule_cron),
                id='strm_job',
                replace_existing=True
            )
            
            # 启动调度器
            self.scheduler.start()
            logger.info(f"定时任务已启动，执行计划: {self.settings.schedule_cron}")
            
            # 发送通知
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(
                f"⏰ 定时任务已启动\n执行计划: {self.settings.schedule_cron}"
            )
            
        except Exception as e:
            error_msg = f"启动定时任务失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(f"❌ {error_msg}")
            raise
    
    async def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("定时任务已停止")
            
            # 发送通知
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message("⏹ 定时任务已停止")
    
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
                
                # 发送通知
                service_manager = self._get_service_manager()
                await service_manager.telegram_service.send_message("⏸ 定时任务已禁用")
            
        except Exception as e:
            error_msg = f"更新定时任务失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(f"❌ {error_msg}")
            raise
    
    def get_jobs(self):
        """获取所有定时任务"""
        return self.scheduler.get_jobs() 