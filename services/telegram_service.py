import httpx
from loguru import logger
from config import Settings
from urllib.parse import urlparse

class TelegramService:
    def __init__(self):
        self.settings = Settings()
        self.client = None
        if self.settings.tg_enabled and self.settings.tg_token and self.settings.tg_chat_id:
            # 设置代理
            proxies = None
            if self.settings.tg_proxy_url:
                proxies = {"all://": self.settings.tg_proxy_url}
            
            self.client = httpx.AsyncClient(
                base_url="https://api.telegram.org",
                proxies=proxies,
                timeout=30.0
            )
    
    async def send_message(self, message: str):
        """发送消息到Telegram"""
        if not self.client:
            return
            
        try:
            response = await self.client.post(
                f"/bot{self.settings.tg_token}/sendMessage",
                json={
                    "chat_id": self.settings.tg_chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }
            )
            response.raise_for_status()
            logger.debug(f"Telegram消息发送成功: {message}")
        except Exception as e:
            logger.error(f"Telegram消息发送失败: {str(e)}")
    
    async def close(self):
        """关闭HTTP客户端"""
        if self.client:
            await self.client.aclose() 