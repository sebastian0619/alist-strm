from services.scheduler_service import SchedulerService
from services.strm_service import StrmService
from services.copy_service import CopyService
from services.telegram_service import TelegramService
from services.archive_service import ArchiveService
from services.strm_monitor_service import StrmMonitorService
from services.strm_health_service import StrmHealthService
from services.emby_service import EmbyService
from services.strm_assistant_service import StrmAssistantService
from loguru import logger
import asyncio
from config import Settings

class ServiceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if not self.initialized:
            self.settings = Settings()
            self.scheduler_service = None
            self.strm_service = None
            self.copy_service = None
            self.telegram_service = None
            self.archive_service = None
            self.monitor_service = None
            self.health_service = None
            self.emby_service = None
            self.strm_assistant_service = None
            self.initialized = True
    
    def init_services(self):
        """初始化所有服务实例"""
        if not any([self.scheduler_service, self.strm_service, self.copy_service, 
                   self.telegram_service, self.archive_service, self.monitor_service,
                   self.health_service, self.emby_service, self.strm_assistant_service]):
            self.scheduler_service = SchedulerService()
            self.copy_service = CopyService()
            self.strm_service = StrmService()
            self.telegram_service = TelegramService()
            self.archive_service = ArchiveService()
            self.monitor_service = StrmMonitorService(self.strm_service)
            self.health_service = StrmHealthService()
            self.emby_service = EmbyService()
            self.strm_assistant_service = StrmAssistantService()

    def reload_runtime_config(self):
        """重新加载运行时配置并同步到已初始化服务"""
        self.settings = Settings()

        services = [
            self.scheduler_service,
            self.strm_service,
            self.copy_service,
            self.telegram_service,
            self.archive_service,
            self.health_service,
            self.emby_service,
            self.strm_assistant_service,
        ]

        for service in services:
            if service and hasattr(service, "refresh_settings"):
                service.refresh_settings()
            elif service and hasattr(service, "settings"):
                try:
                    service.settings = Settings()
                except AttributeError:
                    logger.debug(f"服务 {service.__class__.__name__} 的 settings 为只读，跳过直接赋值")
    
    async def initialize(self):
        """初始化所有服务"""
        try:
            # 初始化服务实例
            self.init_services()
            
            # 按顺序初始化各个服务
            logger.info("开始初始化服务...")
            
            # 初始化调度器服务
            logger.info("调度器服务初始化完成")
            
            # 初始化复制服务
            logger.info("复制服务初始化完成")
            
            # 初始化STRM服务
            logger.info("STRM服务初始化完成")
            
            # 初始化归档服务
            logger.info("归档服务初始化完成")
            
            # 初始化监控服务
            await self.monitor_service.start()
            logger.info("监控服务初始化完成")
            
            # 初始化Telegram服务
            await self.telegram_service.initialize()
            logger.info("Telegram服务初始化完成")
            
            # 初始化Emby服务
            logger.info("Emby服务初始化完成")
            
            logger.info("所有服务初始化完成")
        except Exception as e:
            logger.error(f"服务初始化失败: {str(e)}")
            raise
    
    async def start(self):
        """启动所有服务"""
        try:
            # 尝试启动Telegram服务
            try:
                await self.telegram_service.start()
            except Exception as e:
                # 记录错误但继续启动其他服务
                logger.error(f"Telegram服务启动失败 (应用将继续运行): {str(e)}")
                # 禁用Telegram服务
                self.settings.tg_enabled = False
            
            # 初始化归档服务
            await self.archive_service.initialize()
            
            # 启动Emby刷新任务
            asyncio.create_task(self.emby_service.start_background_tasks())
            logger.info("Emby刷新任务已启动")
            
            # 如果启用了定时任务，启动定时任务
            if self.settings.schedule_enabled:
                await self._start_schedule()
                
            # 如果启用了归档定时任务，启动归档定时任务
            if self.settings.archive_schedule_enabled:
                await self._start_archive_schedule()
                
            # 如果配置了启动后执行，开始STRM扫描
            if self.settings.run_after_startup:
                asyncio.create_task(self._run_start_scan())
        except Exception as e:
            logger.error(f"服务启动失败: {str(e)}")
            raise
    
    async def _start_schedule(self):
        """启动STRM定时任务"""
        if not self.settings.schedule_enabled:
            logger.info("STRM定时任务未启用")
            return
            
        try:
            # 使用add_cron_job方法添加STRM定时任务
            success = self.scheduler_service.add_cron_job(
                'strm_job', 
                self.settings.schedule_cron, 
                self.strm_service.strm
            )
            
            if success:
                logger.info(f"STRM定时任务已启动，执行计划: {self.settings.schedule_cron}")
                await self.telegram_service.send_message(
                    f"⏰ STRM定时任务已启动\n执行计划: {self.settings.schedule_cron}"
                )
            else:
                raise Exception("添加STRM定时任务失败")
                
        except Exception as e:
            error_msg = f"启动STRM定时任务失败: {str(e)}"
            logger.error(error_msg)
            await self.telegram_service.send_message(f"❌ {error_msg}")
            raise
            
    async def _start_archive_schedule(self):
        """启动归档定时任务"""
        if not self.settings.archive_schedule_enabled or not self.settings.archive_enabled:
            logger.info("归档定时任务未启用")
            return
            
        try:
            # 使用add_cron_job方法添加归档定时任务
            success = self.scheduler_service.add_cron_job(
                'archive_job', 
                self.settings.archive_schedule_cron, 
                self.archive_service.archive
            )
            
            if success:
                logger.info(f"归档定时任务已启动，执行计划: {self.settings.archive_schedule_cron}")
                await self.telegram_service.send_message(
                    f"⏰ 归档定时任务已启动\n执行计划: {self.settings.archive_schedule_cron}"
                )
            else:
                raise Exception("添加归档定时任务失败")
                
        except Exception as e:
            error_msg = f"启动归档定时任务失败: {str(e)}"
            logger.error(error_msg)
            await self.telegram_service.send_message(f"❌ {error_msg}")
            # 不抛出异常，允许应用继续运行
    
    async def _run_start_scan(self):
        """在服务启动后执行一次STRM扫描"""
        try:
            logger.info("正在执行启动时STRM扫描")
            await self.telegram_service.send_message("🔍 执行启动时STRM扫描")
            
            # 延迟几秒，确保其他服务已经完全启动
            await asyncio.sleep(5)
            
            # 执行STRM扫描
            await self.strm_service.strm()
            
            logger.info("启动时STRM扫描完成")
            await self.telegram_service.send_message("✅ 启动时STRM扫描完成")
            
        except Exception as e:
            error_msg = f"启动时STRM扫描失败: {str(e)}"
            logger.error(error_msg)
            await self.telegram_service.send_message(f"❌ {error_msg}")
            # 不抛出异常，允许应用继续运行
    
    async def close(self):
        """关闭所有服务"""
        try:
            if self.strm_service:
                await self.strm_service.close()
            
            if self.copy_service:
                await self.copy_service.close()
            
            if self.telegram_service:
                await self.telegram_service.close()
            
            if self.monitor_service:
                await self.monitor_service.stop()
            
            if self.emby_service:
                self.emby_service.stop_background_tasks()
            
            logger.info("所有服务已关闭")
        except Exception as e:
            logger.error(f"关闭服务时出错: {str(e)}")
            raise

# 全局服务管理器实例
service_manager = ServiceManager() 

# 确保在初始化后导出服务实例
service_manager.init_services()
scheduler_service = service_manager.scheduler_service
strm_service = service_manager.strm_service
copy_service = service_manager.copy_service
tg_service = service_manager.telegram_service
archive_service = service_manager.archive_service
monitor_service = service_manager.monitor_service
health_service = service_manager.health_service
emby_service = service_manager.emby_service
strm_assistant_service = service_manager.strm_assistant_service 
