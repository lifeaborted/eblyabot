import aiohttp
import logging

logger = logging.getLogger(__name__)

async def resolve_url(url: str) -> str:
    """Асинхронно разворачивает мобильные ссылки перед отдачей в парсеры"""
    if 'vm.tiktok.com' in url.lower() or 'vt.tiktok.com' in url.lower():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, allow_redirects=True, timeout=10) as resp:
                    return str(resp.url).split('?')[0]
        except Exception as e:
            logger.warning(f"Не удалось развернуть ссылку {url}: {e}")
    return url.split('?')[0]