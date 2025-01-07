from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update, BotCommand
from loguru import logger
from config import Settings
from datetime import datetime
from typing import Dict, Optional
import importlib

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
        self.state = ProcessState()
        
    def _get_service_manager(self):
        """动态获取service_manager以避免循环依赖"""
        module = importlib.import_module('services.service_manager')
        return module.service_manager
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/start命令"""
        await update.message.reply_text('欢迎使用Alist流媒体服务机器人！\n使用 /help 查看可用命令。')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/help命令"""
        help_text = """
可用命令列表：

STRM文件管理：
/strm_scan - 开始扫描生成STRM文件
/strm_stop - 停止扫描
/strm_clear_cache - 清除STRM缓存

文件同步：
/sync - 触发文件同步
/sync_one <路径> - 同步单个文件

系统控制：
/status - 查看系统状态
/pause - 暂停所有任务
/resume - 恢复所有任务

任务管理：
/tasks - 查看定时任务列表
/task_add - 添加定时任务
/task_remove - 删除定时任务

基础命令：
/start - 开始使用机器人
/help - 显示本帮助信息
        """
        await update.message.reply_text(help_text)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/status命令 - 查看系统状态"""
        await update.message.reply_text(self.state.status)

    async def strm_scan_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/strm_scan命令 - 开始扫描生成STRM文件"""
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

    async def strm_clear_cache_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/strm_clear_cache命令 - 清除缓存"""
        service_manager = self._get_service_manager()
        result = await service_manager.strm_service.clear_cache()
        await update.message.reply_text(f"缓存清理: {result['message']}")

    async def sync_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/sync命令 - 触发同步"""
        if self.state.is_paused:
            await update.message.reply_text("系统当前处于暂停状态，请先使用 /resume 恢复运行")
            return
        await update.message.reply_text("开始同步文件...")
        service_manager = self._get_service_manager()
        await service_manager.copy_service.sync_files()
        self.state.update_stats(sync=True)
        await update.message.reply_text("文件同步完成")

    async def sync_one_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/sync_one命令 - 同步单个文件"""
        if not context.args:
            await update.message.reply_text("请指定要同步的文件路径")
            return
            
        if self.state.is_paused:
            await update.message.reply_text("系统当前处于暂停状态，请先使用 /resume 恢复运行")
            return
            
        path = ' '.join(context.args)
        await update.message.reply_text(f"开始同步文件: {path}")
        service_manager = self._get_service_manager()
        await service_manager.copy_service.sync_one_file(path)
        self.state.update_stats(sync=True)
        await update.message.reply_text(f"文件同步完成: {path}")

    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/pause命令 - 暂停任务"""
        if self.state.pause():
            await update.message.reply_text("系统已暂停")
        else:
            await update.message.reply_text("系统已经处于暂停状态")

    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/resume命令 - 恢复任务"""
        if self.state.resume():
            await update.message.reply_text("系统已恢复运行")
        else:
            await update.message.reply_text("系统已经在运行中")

    async def tasks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/tasks命令 - 查看定时任务"""
        service_manager = self._get_service_manager()
        jobs = service_manager.scheduler_service.get_jobs()
        if not jobs:
            await update.message.reply_text("当前没有定时任务")
            return
            
        tasks_text = "当前定时任务列表：\n\n"
        for job in jobs:
            tasks_text += f"- {job.name}: {job.trigger}\n"
        await update.message.reply_text(tasks_text)

    async def task_add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/task_add命令 - 添加定时任务"""
        # TODO: 实现添加定时任务的交互逻辑
        await update.message.reply_text("添加定时任务功能开发中...")

    async def task_remove_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/task_remove命令 - 删除定时任务"""
        # TODO: 实现删除定时任务的交互逻辑
        await update.message.reply_text("删除定时任务功能开发中...")

    async def update_bot_commands(self):
        """更新bot命令菜单"""
        if not self.application:
            return
            
        commands = [
            BotCommand("start", "开始使用机器人"),
            BotCommand("help", "显示帮助信息"),
            BotCommand("strm_scan", "开始扫描生成STRM文件"),
            BotCommand("strm_stop", "停止扫描"),
            BotCommand("strm_clear_cache", "清除STRM缓存"),
            BotCommand("sync", "触发文件同步"),
            BotCommand("sync_one", "同步单个文件"),
            BotCommand("status", "查看系统状态"),
            BotCommand("pause", "暂停所有任务"),
            BotCommand("resume", "恢复所有任务"),
            BotCommand("tasks", "查看定时任务列表"),
            BotCommand("task_add", "添加定时任务"),
            BotCommand("task_remove", "删除定时任务")
        ]
        
        try:
            await self.application.bot.set_my_commands(commands)
            logger.info("Bot命令菜单更新成功")
        except Exception as e:
            logger.error(f"Bot命令菜单更新失败: {str(e)}")

    async def initialize(self):
        """初始化Telegram机器人"""
        if not self.settings.tg_enabled or not self.settings.tg_token:
            logger.warning("Telegram bot未启用或token未配置")
            return

        try:
            # 设置代理
            proxy_url = None
            if self.settings.tg_proxy_url:
                proxy_url = self.settings.tg_proxy_url

            # 创建机器人应用
            self.application = (
                Application.builder()
                .token(self.settings.tg_token)
                .proxy_url(proxy_url)
                .build()
            )

            # 添加命令处理器
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("strm_scan", self.strm_scan_command))
            self.application.add_handler(CommandHandler("strm_stop", self.strm_stop_command))
            self.application.add_handler(CommandHandler("strm_clear_cache", self.strm_clear_cache_command))
            self.application.add_handler(CommandHandler("sync", self.sync_command))
            self.application.add_handler(CommandHandler("sync_one", self.sync_one_command))
            self.application.add_handler(CommandHandler("pause", self.pause_command))
            self.application.add_handler(CommandHandler("resume", self.resume_command))
            self.application.add_handler(CommandHandler("tasks", self.tasks_command))
            self.application.add_handler(CommandHandler("task_add", self.task_add_command))
            self.application.add_handler(CommandHandler("task_remove", self.task_remove_command))

            # 初始化机器人
            await self.application.initialize()
            # 更新命令菜单
            await self.update_bot_commands()
            logger.info("Telegram机器人初始化成功")
            
        except Exception as e:
            logger.error(f"Telegram机器人初始化失败: {str(e)}")
            raise

    async def start(self):
        """启动机器人"""
        if not self.application:
            return
            
        try:
            await self.application.start()
            logger.info("Telegram机器人启动成功")
        except Exception as e:
            logger.error(f"Telegram机器人启动失败: {str(e)}")
            raise

    async def send_message(self, message: str):
        """发送消息到Telegram"""
        if not self.application or not self.settings.tg_chat_id:
            return
            
        try:
            await self.application.bot.send_message(
                chat_id=self.settings.tg_chat_id,
                text=message,
                parse_mode="HTML"
            )
            logger.debug(f"Telegram消息发送成功: {message}")
        except Exception as e:
            logger.error(f"Telegram消息发送失败: {str(e)}")

    async def close(self):
        """关闭机器人"""
        if self.application:
            await self.application.stop()
            await self.application.shutdown() 