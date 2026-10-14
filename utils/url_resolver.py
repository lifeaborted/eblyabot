import re
import aiohttp
import logging

logger = logging.getLogger(__name__)


async def resolve_url(url: str) -> str:
    """Асинхронно разворачивает мобильные ссылки перед отдачей в парсеры"""
    url_lower = url.lower()
    needs_resolve = any(x in url_lower for x in [
        'vm.tiktok.com', 'vt.tiktok.com', 'tt.site', 'instagram.com/share', 'ig.me'
    ])
    if needs_resolve:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, allow_redirects=True, timeout=10) as resp:
                    url = str(resp.url)
        except Exception as e:
            logger.warning(f"Не удалось развернуть ссылку {url}: {e}")

    if 'youtube.com/watch' in url.lower():
        clean_url = url.split('&')[0]
    else:
        clean_url = url.split('?')[0]

    # Если tt.site не сделал редирект на tiktok.com, меняем домен вручную
    clean_url = re.sub(r'https?://(?:www\.)?tt\.site/', 'https://www.tiktok.com/', clean_url, flags=re.IGNORECASE)
    return clean_url