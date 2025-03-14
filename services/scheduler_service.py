from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from config import Settings
import importlib
from typing import List, Dict, Callable, Any

class SchedulerService:
    def __init__(self):
        self.settings = Settings()
        self.scheduler = AsyncIOScheduler()
        self.strm_job = None
        self.archive_job = None
    
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
            error_msg = f"❌ 定时STRM任务执行失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
    
    async def _run_archive_job(self):
        """执行归档任务"""
        try:
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message("⏰ 开始执行定时归档任务")
            await service_manager.archive_service.archive()
        except Exception as e:
            error_msg = f"❌ 定时归档任务执行失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(error_msg)
    
    def add_cron_job(self, job_id: str, cron_expression: str, func: Callable[..., Any], **kwargs) -> bool:
        """添加一个新的cron定时任务
        
        Args:
            job_id: 任务ID
            cron_expression: Cron表达式，例如 "0 */6 * * *"
            func: 要执行的函数
            **kwargs: 传递给函数的参数
            
        Returns:
            bool: 是否成功添加任务
        """
        try:
            # 确保调度器已启动
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("调度器已启动")
            
            # 添加任务
            job = self.scheduler.add_job(
                func,
                CronTrigger.from_crontab(cron_expression),
                id=job_id,
                replace_existing=True,
                kwargs=kwargs
            )
            
            logger.info(f"已添加定时任务 {job_id}，执行计划: {cron_expression}")
            return True
            
        except Exception as e:
            error_msg = f"添加定时任务 {job_id} 失败: {str(e)}"
            logger.error(error_msg)
            return False
    
    async def start(self):
        """启动调度器"""
        if self.scheduler.running:
            logger.warning("调度器已在运行")
            return
            
        try:
            # 添加STRM定时任务
            if self.settings.schedule_enabled:
                self.strm_job = self.scheduler.add_job(
                    self._run_strm_job,
                    CronTrigger.from_crontab(self.settings.schedule_cron),
                    id='strm_job',
                    replace_existing=True
                )
                logger.info(f"STRM定时任务已启动，执行计划: {self.settings.schedule_cron}")
                
                # 发送通知
                service_manager = self._get_service_manager()
                await service_manager.telegram_service.send_message(
                    f"⏰ STRM定时任务已启动\n执行计划: {self.settings.schedule_cron}"
                )
            
            # 添加归档定时任务
            if self.settings.archive_schedule_enabled and self.settings.archive_enabled:
                self.archive_job = self.scheduler.add_job(
                    self._run_archive_job,
                    CronTrigger.from_crontab(self.settings.archive_schedule_cron),
                    id='archive_job',
                    replace_existing=True
                )
                logger.info(f"归档定时任务已启动，执行计划: {self.settings.archive_schedule_cron}")
                
                # 发送通知
                service_manager = self._get_service_manager()
                await service_manager.telegram_service.send_message(
                    f"⏰ 归档定时任务已启动\n执行计划: {self.settings.archive_schedule_cron}"
                )
            
            # 启动调度器
            if not self.scheduler.running and (self.strm_job or self.archive_job):
                self.scheduler.start()
                logger.info("调度器已启动")
            
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
    
    def get_jobs(self) -> List[Dict]:
        """获取所有定时任务"""
        jobs = []
        if self.strm_job:
            jobs.append({
                "name": "STRM扫描",
                "trigger": str(self.strm_job.trigger),
                "enabled": self.settings.schedule_enabled
            })
        if self.archive_job:
            jobs.append({
                "name": "归档处理",
                "trigger": str(self.archive_job.trigger),
                "enabled": self.settings.archive_schedule_enabled
            })
        return jobs
    
    async def update_schedule(self, strm_enabled: bool = None, strm_cron: str = None,
                            archive_enabled: bool = None, archive_cron: str = None):
        """更新定时任务配置"""
        try:
            if self.scheduler.running:
                await self.stop()
            
            # 更新STRM定时任务配置
            if strm_enabled is not None:
                self.settings.schedule_enabled = strm_enabled
            if strm_cron:
                self.settings.schedule_cron = strm_cron
                
            # 更新归档定时任务配置
            if archive_enabled is not None:
                self.settings.archive_schedule_enabled = archive_enabled
            if archive_cron:
                self.settings.archive_schedule_cron = archive_cron
            
            # 重启调度器
            await self.start()
            
        except Exception as e:
            error_msg = f"更新定时任务失败: {str(e)}"
            logger.error(error_msg)
            service_manager = self._get_service_manager()
            await service_manager.telegram_service.send_message(f"❌ {error_msg}")
            raise 