from services.scheduler_service import SchedulerService
from services.strm_service import StrmService
from services.copy_service import CopyService
from services.telegram_service import TelegramService
from services.archive_service import ArchiveService
from services.strm_monitor_service import StrmMonitorService
from loguru import logger

class ServiceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if not self.initialized:
            self.scheduler_service = None
            self.strm_service = None
            self.copy_service = None
            self.telegram_service = None
            self.archive_service = None
            self.monitor_service = None
            self.initialized = True
    
    def init_services(self):
        """初始化所有服务实例"""
        if not any([self.scheduler_service, self.strm_service, self.copy_service, 
                   self.telegram_service, self.archive_service, self.monitor_service]):
            self.scheduler_service = SchedulerService()
            self.copy_service = CopyService()
            self.strm_service = StrmService()
            self.telegram_service = TelegramService()
            self.archive_service = ArchiveService()
            self.monitor_service = StrmMonitorService(self.strm_service)
    
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
            
            logger.info("所有服务初始化完成")
        except Exception as e:
            logger.error(f"服务初始化失败: {str(e)}")
            raise
    
    async def start(self):
        """启动所有服务"""
        try:
            # 启动Telegram服务
            await self.telegram_service.start()
            
            logger.info("所有服务启动完成")
        except Exception as e:
            logger.error(f"服务启动失败: {str(e)}")
            raise
    
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