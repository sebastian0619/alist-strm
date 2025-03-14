from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update, BotCommand
from loguru import logger
from config import Settings
from datetime import datetime
from typing import Dict, Optional
import importlib
import asyncio
import threading
import httpx
from telegram.error import NetworkError, TimedOut, RetryAfter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time

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
        self._retry_count = 0
        self._max_retries = 3
        self._polling_task = None
        self._is_polling = False
        self._polling_error = None
        
    @property
    def enabled(self) -> bool:
        """检查Telegram功能是否启用"""
        return self.settings.tg_enabled and bool(self.settings.tg_token)
    
    async def initialize(self):
        """初始化Telegram服务"""
        if not self.enabled:
            logger.info("Telegram功能未启用")
            return
            
        # 只做基本检查，不创建application
        logger.info("Telegram服务初始化完成")
    
    def _create_application(self):
        """创建Telegram应用实例"""
        builder = Application.builder().token(self.settings.tg_token)
        
        # 配置代理
        if self.settings.tg_proxy_url:
            builder = builder.proxy_url(self.settings.tg_proxy_url)
            logger.info(f"使用代理: {self.settings.tg_proxy_url}")
            
        # 配置连接参数
        builder = builder.connect_timeout(30.0).read_timeout(30.0).write_timeout(30.0)
        
        return builder.build()
    
    async def _run_polling(self):
        """运行轮询逻辑"""
        try:
            # 初始化应用
            self.application = Application.builder().token(self.settings.tg_token).build()
            
            # 配置代理
            if self.settings.tg_proxy_url:
                proxy_url = self.settings.tg_proxy_url
                logger.info(f"使用代理 {proxy_url}")
                
                # 构建代理参数
                request_kwargs = {'proxy_url': proxy_url}
                
                # 配置应用的请求参数
                self.application.bot._request = HTTPXRequest(
                    proxy=proxy_url, 
                    connection_pool_size=8
                )
            
            # 添加处理程序
            self.application.add_handler(CommandHandler('start', self._start_command))
            self.application.add_handler(CommandHandler('help', self._help_command))
            self.application.add_error_handler(self._error_handler)
            
            # 清除可能存在的未处理更新
            try:
                await self.application.bot.get_updates(offset=-1, timeout=1)
            except Exception as e:
                logger.warning(f"清除旧更新时出错: {e}")
            
            logger.info("开始Telegram轮询...")
            self._is_polling = True
            self._polling_error = None
            
            # 启动轮询
            await self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            self._polling_error = str(e)
            logger.error(f"Telegram轮询出错: {e}")
            self._is_polling = False
            
        finally:
            # 清理资源
            self._is_polling = False
            try:
                if self.application:
                    await self.application.shutdown()
            except Exception as e:
                logger.error(f"清理Telegram轮询资源失败: {e}")

    async def start(self):
        """启动Telegram服务"""
        if not self.settings.tg_enabled or not self.settings.tg_token or not self.settings.tg_chat_id:
            logger.warning("Telegram功能未启用或配置不完整，跳过启动")
            return
            
        try:
            # 记录启动日志
            logger.info("正在启动Telegram服务...")
            
            # 增加超时时间为60秒（原来可能是30秒）
            start_timeout = 60  
            start_time = time.time()
            
            # 创建新的轮询任务
            self._polling_task = asyncio.create_task(self._run_polling())
            
            # 等待轮询任务启动或超时
            while not self._is_polling and time.time() - start_time < start_timeout:
                # 每秒检查一次是否已经启动
                await asyncio.sleep(1)
                
                # 如果在等待过程中发生了错误，提前抛出
                if self._polling_error:
                    error_msg = f"Telegram服务启动失败: {self._polling_error}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            
            # 检查是否成功启动
            if self._is_polling:
                logger.info("Telegram服务启动成功")
            else:
                # 如果超时，尝试取消任务并抛出错误
                if self._polling_task and not self._polling_task.done():
                    self._polling_task.cancel()
                    try:
                        await self._polling_task
                    except asyncio.CancelledError:
                        pass
                
                logger.error("Telegram服务启动超时")
                # 关闭Telegram功能但不抛出异常
                self.settings.tg_enabled = False
                logger.warning("已禁用Telegram功能，应用将继续运行")
                
        except Exception as e:
            logger.error(f"启动Telegram服务时出错: {str(e)}")
            # 关闭Telegram功能但不抛出异常
            self.settings.tg_enabled = False
            logger.warning("已禁用Telegram功能，应用将继续运行")
    
    async def close(self):
        """关闭Telegram服务"""
        if self.initialized:
            try:
                # 发送停止信号
                self._stop_event.set()
                
                # 等待轮询线程结束
                if self._polling_thread and self._polling_thread.is_alive():
                    self._polling_thread.join(timeout=5)
                    
                # 确保应用正确关闭
                if self.application:
                    if hasattr(self.application, 'updater') and self.application.updater.running:
                        await self.application.updater.stop()
                    await self.application.stop()
                    await self.application.shutdown()
                    self.application = None
                    
                self.initialized = False
                logger.info("Telegram服务已关闭")
            except Exception as e:
                logger.error(f"关闭Telegram服务失败: {e}")
                raise

    async def send_message(self, text):
        """发送消息到指定聊天ID
        
        Args:
            text: 消息文本
        """
        if not self.settings.tg_enabled or not self._is_polling:
            # 如果服务未启用或未成功启动，只记录日志不发送
            logger.debug(f"Telegram未启用或未成功启动，消息未发送: {text}")
            return
            
        # 最多尝试3次
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # 分段发送长消息，确保每段不超过4096字符
                # Telegram限制单条消息不超过4096字符
                max_length = 4000  # 留一些余量
                
                if len(text) <= max_length:
                    # 短消息直接发送
                    await self.application.bot.send_message(
                        chat_id=self.settings.tg_chat_id,
                        text=text
                    )
                else:
                    # 长消息分段发送
                    chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]
                    for i, chunk in enumerate(chunks):
                        prefix = f"(消息 {i+1}/{len(chunks)}) " if len(chunks) > 1 else ""
                        await self.application.bot.send_message(
                            chat_id=self.settings.tg_chat_id,
                            text=f"{prefix}{chunk}"
                        )
                        # 避免发送过快
                        if i < len(chunks) - 1:
                            await asyncio.sleep(0.5)
                            
                # 发送成功后退出循环
                return
            except (NetworkError, TimedOut) as e:
                # 网络错误重试
                if attempt < max_attempts - 1:
                    wait_time = (attempt + 1) * 2  # 指数退避
                    logger.warning(f"发送Telegram消息失败，{wait_time}秒后重试: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"发送Telegram消息失败，已达最大重试次数: {e}")
            except Exception as e:
                # 其他错误直接报错
                logger.error(f"发送Telegram消息时出错: {e}")
                break
                
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        await update.message.reply_text("欢迎使用Alist STRM机器人! 输入 /help 获取帮助。")
        
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        help_text = (
            "可用命令:\n"
            "/start - 启动机器人\n"
            "/help - 显示帮助\n"
        )
        await update.message.reply_text(help_text)
        
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理错误"""
        try:
            if update and isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text(
                    "抱歉，处理您的请求时出错了。"
                )
            # 输出错误信息
            logger.error(f"更新 {update} 导致错误 {context.error}")
        except Exception as e:
            logger.error(f"在错误处理程序中出错: {e}")

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