from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update, BotCommand
from loguru import logger
from config import Settings
from datetime import datetime
from typing import Dict, Optional
import importlib
import asyncio
import threading

class ProcessState:
    """进程状态管理"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProcessState, cls).__new__(cls)
            cls._instance.is_paused = False
            cls._instance.stats = {
                "processed_files": 0,
                "total_size": 0,
                "last_sync": None,
                "last_strm_scan": None
            }
        return cls._instance
    
    @property
    def status(self) -> str:
        """获取当前状态描述"""
        state = "暂停中" if self.is_paused else "运行中"
        last_sync = self.stats["last_sync"] or "从未同步"
        last_scan = self.stats["last_strm_scan"] or "从未扫描"
        return f"""系统状态: {state}
上次同步: {last_sync}
上次扫描: {last_scan}
处理文件: {self.stats['processed_files']} 个
总大小: {self.stats['total_size'] / 1024 / 1024:.2f} MB"""

    def pause(self) -> bool:
        """暂停处理"""
        if self.is_paused:
            return False
        self.is_paused = True
        return True

    def resume(self) -> bool:
        """恢复处理"""
        if not self.is_paused:
            return False
        self.is_paused = False
        return True

    def update_stats(self, files: int = 0, size: int = 0, sync: bool = False, scan: bool = False):
        """更新统计信息"""
        self.stats["processed_files"] += files
        self.stats["total_size"] += size
        if sync:
            self.stats["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if scan:
            self.stats["last_strm_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class TelegramService:
    def __init__(self):
        self.settings = Settings()
        self.application = None
        self.initialized = False
        self._polling_thread = None
        self.state = ProcessState()
        self._stop_event = threading.Event()
        self._init_event = threading.Event()
        
    async def initialize(self):
        """初始化Telegram服务"""
        if not self.settings.tg_enabled:
            logger.info("Telegram功能未启用")
            return
            
        if not self.settings.tg_token:
            logger.error("未配置Telegram Bot Token")
            return
            
        # 只做基本检查，不创建application
        logger.info("Telegram服务初始化完成")
    
    def _run_polling(self):
        """运行轮询的后台线程函数"""
        app = None
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 在新的事件循环中创建和初始化 application
            app = Application.builder().token(self.settings.tg_token).build()
            
            # 注册命令处理器
            app.add_handler(CommandHandler("start", self.start_command))
            app.add_handler(CommandHandler("help", self.help_command))
            app.add_handler(CommandHandler("status", self.status_command))
            app.add_handler(CommandHandler("strm", self.strm_command))
            app.add_handler(CommandHandler("strm_stop", self.strm_stop_command))
            app.add_handler(CommandHandler("archive", self.archive_command))
            app.add_handler(CommandHandler("archive_stop", self.archive_stop_command))
            
            # 初始化和启动应用
            loop.run_until_complete(app.initialize())
            loop.run_until_complete(app.start())
            
            # 设置初始化完成标志
            self.application = app
            self.initialized = True
            self._init_event.set()
            
            # 启动轮询
            loop.run_until_complete(app.updater.start_polling())
            
            # 运行事件循环，直到收到停止信号
            while not self._stop_event.is_set():
                loop.run_until_complete(asyncio.sleep(1))
                
        except Exception as e:
            logger.error(f"Telegram轮询出错: {e}")
        finally:
            try:
                # 清理资源
                if app:
                    # 先停止updater
                    if hasattr(app, 'updater'):
                        loop.run_until_complete(app.updater.stop())
                    # 然后停止和关闭应用
                    loop.run_until_complete(app.stop())
                    loop.run_until_complete(app.shutdown())
                loop.close()
                self.initialized = False
                self.application = None
            except Exception as e:
                logger.error(f"清理Telegram轮询资源失败: {e}")

    async def start(self):
        """启动Telegram服务"""
        if not self.settings.tg_enabled:
            return
            
        try:
            # 重置事件
            self._stop_event.clear()
            self._init_event.clear()
            
            # 启动轮询线程
            self._polling_thread = threading.Thread(
                target=self._run_polling,
                daemon=True
            )
            self._polling_thread.start()
            
            # 等待初始化完成
            if self._init_event.wait(timeout=30):
                logger.info("Telegram服务已启动")
            else:
                raise TimeoutError("Telegram服务启动超时")
                
        except Exception as e:
            logger.error(f"启动Telegram服务失败: {e}")
            raise
    
    async def close(self):
        """关闭Telegram服务"""
        if self.initialized:
            try:
                # 发送停止信号
                self._stop_event.set()
                
                # 等待轮询线程结束
                if self._polling_thread and self._polling_thread.is_alive():
                    self._polling_thread.join(timeout=5)
                    
                logger.info("Telegram服务已关闭")
            except Exception as e:
                logger.error(f"关闭Telegram服务失败: {e}")
                raise

    async def send_message(self, message: str) -> bool:
        """发送Telegram消息
        
        Args:
            message: 要发送的消息内容
            
        Returns:
            bool: 是否发送成功
        """
        if not self.settings.tg_enabled:
            logger.debug("Telegram功能未启用，跳过发送消息")
            return False
            
        if not self.settings.tg_chat_id:
            logger.warning("未配置Telegram chat_id，无法发送消息")
            return False
            
        if not self.initialized or not self.application:
            logger.warning("Telegram服务未初始化，无法发送消息")
            return False
            
        try:
            await self.application.bot.send_message(
                chat_id=self.settings.tg_chat_id,
                text=message
            )
            return True
        except Exception as e:
            logger.error(f"发送Telegram消息失败: {e}")
            return False

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/start命令"""
        await update.message.reply_text('欢迎使用Alist流媒体服务机器人！\n使用 /help 查看可用命令。')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/help命令"""
        help_text = """
可用命令列表：

STRM文件管理：
/strm - 开始扫描生成STRM文件
/strm_stop - 停止扫描

归档管理：
/archive - 开始归档处理
/archive_stop - 停止归档处理

系统控制：
/status - 查看系统状态
/start - 开始使用机器人
/help - 显示本帮助信息
        """
        await update.message.reply_text(help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/status命令"""
        await update.message.reply_text(self.state.status)

    async def strm_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/strm命令 - 开始扫描生成STRM文件"""
        if self.state.is_paused:
            await update.message.reply_text("系统当前处于暂停状态，请先使用 /resume 恢复运行")
            return
        await update.message.reply_text("开始扫描生成STRM文件...")
        service_manager = self._get_service_manager()
        await service_manager.strm_service.strm()

    async def strm_stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/strm_stop命令 - 停止扫描"""
        service_manager = self._get_service_manager()
        service_manager.strm_service.stop()
        await update.message.reply_text("已发送停止扫描信号")

    async def archive_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/archive命令 - 开始归档处理"""
        if not self.settings.archive_enabled:
            await update.message.reply_text("归档功能未启用")
            return
            
        if self.state.is_paused:
            await update.message.reply_text("系统当前处于暂停状态，请先使用 /resume 恢复运行")
            return
            
        await update.message.reply_text("开始归档处理...")
        service_manager = self._get_service_manager()
        await service_manager.archive_service.archive()

    async def archive_stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/archive_stop命令 - 停止归档"""
        if not self.settings.archive_enabled:
            await update.message.reply_text("归档功能未启用")
            return
            
        service_manager = self._get_service_manager()
        service_manager.archive_service.stop()
        await update.message.reply_text("已发送停止归档信号")

    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager