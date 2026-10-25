import asyncio
import html
import json
import logging
import os
import re
import uuid
from curl_cffi import requests as cffi_requests
from typing import Optional, Callable, Dict, Any, List, Tuple
from .base import BaseDownloader

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)


class InstagramDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        opts = {
            'outtmpl': f'{self.download_dir}/ig_%(id)s.%(ext)s',
            'quiet': False,
            'merge_output_format': 'mp4',
            'ignore_no_formats_error': True,
            'format': (
                'bestvideo[filesize<42M]+bestaudio[filesize<6M]/'
                'bestvideo[vbr<=3500]+bestaudio/'
                'best[filesize<48M]/'
                'bestvideo[height<=720]+bestaudio/'
                'best'
            ),
            'http_headers': {
                'User-Agent': USER_AGENT,
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        for cookie_path in ['/etc/secrets/cookies.txt', 'cookies.txt']:
            if os.path.exists(cookie_path) and os.path.getsize(cookie_path) > 0:
                opts['cookiefile'] = cookie_path
                break
        return opts

    def _extract_shortcode(self, url: str) -> Optional[str]:
        match = re.search(r'/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)', url)
        return match.group(1) if match else None

    async def download(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        logger.info(f"Instagram Попытка 1: Запуск yt-dlp для {url}")
        result = await super().download(url, progress_callback)
        if result.get('success'):
            return result

        logger.info(f"yt-dlp не справился ({result.get('error')}). Переход к резервному парсеру...")
        if progress_callback:
            try:
                await progress_callback("⏳ Обрабатываю публикацию Instagram...")
            except Exception:
                pass

        return await asyncio.to_thread(self._sync_fallback_download, url)

    def _sync_fallback_download(self, url: str) -> Dict[str, Any]:
        shortcode = self._extract_shortcode(url)
        if not shortcode:
            return {'success': False, 'error': 'Не удалось распознать ID публикации Instagram.'}

        run_id = uuid.uuid4().hex[:6]
        active_proxies = self.proxies
        video_url, image_urls, author, caption = self._get_post_data(shortcode, active_proxies)

        headers = {
            'User-Agent': USER_AGENT,
            'Referer': 'https://www.instagram.com/'
        }

        if video_url and not image_urls:
            try:
                video_path = os.path.join(self.download_dir, f"ig_{shortcode}_{run_id}.mp4")
                if self._download_file(video_url, video_path, headers, active_proxies, 20):
                    thumb_path = self._generate_thumbnail(video_path)
                    return {
                        'success': True,
                        'media_type': 'video',
                        'file_path': video_path,
                        'thumbnail_path': thumb_path,
                        'title': caption,
                        'description': caption,
                        'uploader': author,
                        'tags': []
                    }
            except Exception as e:
                logger.error(f"Ошибка скачивания видео Instagram напрямую: {e}")

        if image_urls:
            downloaded_imgs = []
            for idx, img_url in enumerate(image_urls, 1):
                try:
                    path = os.path.join(self.download_dir, f"ig_{shortcode}_{run_id}_{idx}.jpg")
                    if self._download_file(img_url, path, headers, active_proxies, 15):
                        if self._fix_image(path):
                            downloaded_imgs.append(path)
                        elif os.path.exists(path):
                            os.remove(path)
                except Exception as e:
                    logger.error(f"Ошибка скачивания фото Instagram {idx}: {e}")

            if downloaded_imgs:
                return {
                    'success': True,
                    'media_type': 'images',
                    'image_paths': downloaded_imgs,
                    'audio_path': None,
                    'title': caption,
                    'description': caption,
                    'uploader': author,
                    'tags': []
                }

        return {
            'success': False,
            'error': 'Не удалось получить медиа из Instagram. Возможно, аккаунт приватный или имеет возрастные ограничения.'
        }

    def _get_post_data(self, shortcode: str, active_proxies: Optional[dict]) -> Tuple[Optional[str], List[str], str, str]:
        logger.info(f"Instagram Попытка 2: Запрос к GraphQL для {shortcode}...")
        try:
            gql_headers = {
                'User-Agent': USER_AGENT,
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-IG-App-ID': '936619743392459',
                'X-FB-LSD': 'AVqbxe3J_YA',
                'X-ASBD-ID': '129477',
                'Origin': 'https://www.instagram.com',
                'Referer': f'https://www.instagram.com/p/{shortcode}/',
            }
            payload = {
                'lsd': 'AVqbxe3J_YA',
                'variables': json.dumps({
                    'shortcode': shortcode,
                    'fetch_tagged_user_count': None,
                    'hoisted_comment_id': None,
                    'hoisted_reply_id': None
                }),
                'doc_id': '8845758582119845'
            }
            resp = cffi_requests.post(
                'https://www.instagram.com/graphql/query',
                headers=gql_headers,
                data=payload,
                proxies=active_proxies,
                impersonate='chrome',
                timeout=15
            )
            if resp.status_code == 200:
                media = resp.json().get('data', {}).get('xdt_shortcode_media')
                if media:
                    parsed = self._parse_media_dict(media)
                    if parsed[0] or parsed[1]:
                        logger.info("Успех: Данные получены через Instagram GraphQL.")
                        return parsed
        except Exception as e:
            logger.warning(f"Ошибка Instagram GraphQL: {e}")

        logger.info(f"Instagram Попытка 3: Парсинг Embed-страницы для {shortcode}...")
        try:
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
            resp = cffi_requests.get(
                embed_url,
                headers={'User-Agent': USER_AGENT, 'Accept-Language': 'en-US,en;q=0.9'},
                proxies=active_proxies,
                impersonate='chrome',
                timeout=15
            )
            if resp.status_code == 200:
                text = resp.text

                ctx_match = re.search(r'"contextJSON":\s*(".*?")', text)
                if ctx_match:
                    context_str = json.loads(ctx_match.group(1))
                    context_data = json.loads(context_str)
                    media = context_data.get('gql_data', {}).get('shortcode_media')
                    if media:
                        parsed = self._parse_media_dict(media)
                        if parsed[0] or parsed[1]:
                            logger.info("Успех: Данные получены из contextJSON (Embed).")
                            return parsed

                author_match = re.search(r'class="UsernameText"[^>]*>([^<]+)<', text)
                author = author_match.group(1).strip() if author_match else "Instagram User"

                caption = ""
                cap_match = re.search(r'class="Caption"(.*?)</div>', text, re.DOTALL)
                if cap_match:
                    raw_cap = re.sub(r'<[^>]+>', ' ', cap_match.group(1))
                    caption = html.unescape(re.sub(r'\s+', ' ', raw_cap)).strip()

                video_match = re.search(r'\\?"video_url\\?":\s*\\?"([^"\\]+)', text)
                if video_match:
                    v_url = video_match.group(1).encode('utf-8').decode('unicode_escape').replace(r'\/', '/')
                    return v_url, [], author, caption

                img_matches = re.findall(r'class="EmbeddedMediaImage"[^>]+src="([^"]+)"', text)
                if img_matches:
                    clean_imgs = [html.unescape(u) for u in img_matches]
                    return None, clean_imgs, author, caption

        except Exception as e:
            logger.warning(f"Ошибка парсинга Instagram Embed: {e}")

        return None, [], "Unknown", ""

    def _parse_media_dict(self, media: dict) -> Tuple[Optional[str], List[str], str, str]:
        author = media.get('owner', {}).get('username', 'Unknown')
        caption_edges = media.get('edge_media_to_caption', {}).get('edges', [])
        caption = caption_edges[0].get('node', {}).get('text', '') if caption_edges else ''

        sidecar = media.get('edge_sidecar_to_children', {}).get('edges', [])
        if sidecar:
            images = []
            first_video = None
            for edge in sidecar:
                node = edge.get('node', {})
                if node.get('is_video') and node.get('video_url') and not first_video:
                    first_video = node['video_url']
                elif node.get('display_url'):
                    images.append(node['display_url'])
            if images:
                return None, images, author, caption
            if first_video:
                return first_video, [], author, caption

        if media.get('is_video') and media.get('video_url'):
            return media['video_url'], [], author, caption

        if media.get('display_url'):
            return None, [media['display_url']], author, caption

        return None, [], author, caption
