from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from loguru import logger
from config import Settings

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

async def setup_telegram_bot():
    """设置和启动Telegram机器人"""
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
        await application.run_polling()
        
        logger.info("Telegram机器人启动成功")
    except Exception as e:
        logger.error(f"Telegram机器人启动失败: {str(e)}")
        raise 