from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from telegram.error import Conflict, NetworkError, RetryAfter
from loguru import logger
from config import Settings
import asyncio

settings = Settings()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('欢迎使用Alist流媒体服务机器人！')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    可用命令列表：
    /start - 开始使用机器人
    /help - 显示帮助信息
    """
    await update.message.reply_text(help_text)

async def setup_telegram_bot(max_retries=3, retry_delay=5):
    """设置和启动Telegram机器人，支持错误重试"""
    for attempt in range(max_retries):
        try:
            # 创建机器人应用
            proxy_url = None
            if settings.telegram_bot_proxy_host and settings.telegram_bot_proxy_port:
                proxy_url = f"http://{settings.telegram_bot_proxy_host}:{settings.telegram_bot_proxy_port}"
            
            application = (
                Application.builder()
                .token(settings.tg_token)
                .proxy_url(proxy_url)
                .build()
            )

            # 添加命令处理器
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("help", help_command))

            # 启动机器人
            await application.initialize()
            await application.start()
            logger.info(f"Telegram机器人启动成功（尝试 {attempt + 1}/{max_retries}）")
            
            await application.run_polling(
                drop_pending_updates=True,  # 丢弃之前未处理的更新
                stop_on_sigint=True,
                stop_on_sigterm=True
            )
            
        except Conflict as e:
            logger.warning(f"检测到机器人冲突（尝试 {attempt + 1}/{max_retries}）: {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("多次尝试后仍无法启动机器人")
                raise
        
        except (NetworkError, RetryAfter) as e:
            logger.warning(f"网络错误（尝试 {attempt + 1}/{max_retries}）: {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("多次尝试后仍无法启动机器人")
                raise
        
        except Exception as e:
            logger.error(f"Telegram机器人启动失败: {str(e)}")
            raise 