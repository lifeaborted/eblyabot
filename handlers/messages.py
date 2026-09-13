import os
import re
import json
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile, InputMediaPhoto
from downloaders.factory import DownloaderFactory
from utils.cleanup import temp_files_cleanup
from config import DOWNLOAD_DIR
import database
from utils.url_resolver import resolve_url
from utils.format import format_caption

logger = logging.getLogger(__name__)
router = Router()

URL_REGEX = re.compile(r'https?://(?:www\.|vm\.|vt\.|m\.)?(?:tiktok\.com|youtube\.com|youtu\.be)/[^\s]+', re.IGNORECASE)


def chunk_list(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


@router.message(F.text | F.caption)
async def handle_message(message: Message, bot: Bot):
    text = (message.text or message.caption).strip()
    user_id = message.from_user.id

    logger.info(f"--- [USER: {user_id}] Входящее сообщение: {text} ---")

    is_private = message.chat.type == 'private'
    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot.id
    me = await bot.get_me()
    is_mentioned = me.username and (f"@{me.username.lower()}" in text.lower())
    is_via_bot = message.via_bot and message.via_bot.id == bot.id

    if not (is_private or is_reply_to_bot or is_mentioned or is_via_bot):
        return

    match = URL_REGEX.search(text)
    if not match:
        if is_private:
            await message.answer('Пожалуйста, отправьте ссылку на TikTok или YouTube.')
        return

    url = match.group(0)
    logger.info(f"[USER: {user_id}] Найдена ссылка: {url}")
    status_msg = await message.answer('Начинаю скачивание...')

    try:
        await message.delete()
    except Exception:
        pass

    resolved_url = await resolve_url(url)

    existing = await database.get_video_by_url(resolved_url)
    if existing:
        logger.info(f"[USER: {user_id}] Файл найден в БД. Выгружаем кэш...")
        await send_from_cache(message, bot, resolved_url, existing, status_msg)
        return

    downloader = DownloaderFactory.get(resolved_url, DOWNLOAD_DIR)
    if not downloader:
        logger.error(f"[USER: {user_id}] Загрузчик не найден для {url}")
        return await status_msg.edit_text("Этот сервис не поддерживается.")

    async def progress_cb(percent_or_text, speed=None, eta=None):
        try:
            if isinstance(percent_or_text, str):
                await status_msg.edit_text(percent_or_text)
            else:
                bar_len = 10
                filled = int(round(bar_len * percent_or_text / 100))
                bar = '█' * filled + '░' * (bar_len - filled)
                await status_msg.edit_text(
                    f"Загрузка...\n\n<code>[{bar}] {percent_or_text:.1f}%</code>\nСкорость: <code>{speed}</code> | Осталось: <code>{eta}</code>"
                )
        except Exception:
            pass

    logger.info(f"[USER: {user_id}] Старт скачивания через {type(downloader).__name__}...")
    result = await downloader.download(resolved_url, progress_callback=progress_cb)

    if not result.get('success'):
        error_text = result.get('error', 'неизвестная ошибка')
        logger.error(f"[USER: {user_id}] ОШИБКА ЗАГРУЗКИ: {error_text}")
        return await status_msg.edit_text(f"Не удалось скачать файл: {error_text}", parse_mode=None)

    media_type = result.get('media_type', 'video')

    safe_caption = format_caption(
        result.get('uploader', 'Unknown'),
        result.get('title', ''),
        result.get('description', ''),
        result.get('tags', [])
    )

    logger.info(f"[USER: {user_id}] Скачивание завершено. Тип: {media_type}")

    cleanup_paths = [result.get('file_path')] if media_type == 'video' else result.get('image_paths', [])
    if result.get('audio_path'):
        cleanup_paths.append(result.get('audio_path'))

    async with temp_files_cleanup(cleanup_paths):
        if media_type == 'images':
            logger.info(f"[USER: {user_id}] Отправляю фото-карусель (картинок: {len(result['image_paths'])})...")
            await status_msg.edit_text('Отправляю слайдшоу...')
            saved_file_ids = []

            for chunk_idx, chunk in enumerate(chunk_list(result['image_paths'], 10)):
                media_group = []
                for idx, img_path in enumerate(chunk):
                    caption = safe_caption if (chunk_idx == 0 and idx == 0) else None
                    media_group.append(InputMediaPhoto(type='photo', media=FSInputFile(img_path), caption=caption))

                # === УМНАЯ ОТПРАВКА С ИСКЛЮЧЕНИЕМ БИТЫХ ФОТО ===
                current_group = list(media_group)
                while current_group:
                    try:
                        msgs = await bot.send_media_group(message.chat.id, media=current_group)
                        saved_file_ids.extend([m.photo[-1].file_id for m in msgs if m.photo])
                        break  # Успех, выходим из цикла
                    except Exception as e:
                        err_str = str(e)
                        match = re.search(r'failed to send message #(\d+)', err_str)
                        if match and "IMAGE_PROCESS_FAILED" in err_str:
                            bad_idx = int(match.group(1)) - 1
                            if 0 <= bad_idx < len(current_group):
                                logger.warning(f"Удаляю битое фото (индекс {bad_idx}) из пачки {chunk_idx}")
                                current_group.pop(bad_idx)
                                # Если после удаления осталась 1 картинка, send_media_group выдаст ошибку
                                if len(current_group) == 1:
                                    item = current_group[0]
                                    msg = await bot.send_photo(message.chat.id, photo=item.media, caption=item.caption)
                                    saved_file_ids.append(msg.photo[-1].file_id)
                                    break
                                continue  # Пробуем отправить карусель заново без битого фото

                        logger.error(f"[USER: {user_id}] Критическая ошибка отправки карусели {chunk_idx}: {e}")
                        break

            if result.get('audio_path') and os.path.exists(result['audio_path']):
                try:
                    logger.info(f"[USER: {user_id}] Отправляю аудиодорожку...")
                    await message.answer_audio(audio=FSInputFile(result['audio_path']), caption="Оригинальный звук")
                except Exception as e:
                    logger.error(f"[USER: {user_id}] Ошибка отправки аудио: {e}")

            if saved_file_ids:
                await database.add_video(url=resolved_url, user_id=user_id, username=message.from_user.username,
                                         file_path=result['image_paths'][0] if result['image_paths'] else None,
                                         file_id=json.dumps(saved_file_ids), title=safe_caption, media_type='images')
                logger.info(f"[USER: {user_id}] Слайдшоу успешно отправлено и занесено в БД.")
        else:
            logger.info(f"[USER: {user_id}] Отправляю видеофайл...")
            await status_msg.edit_text('Отправляю видео...')
            sent = await message.answer_video(video=FSInputFile(result['file_path']), caption=safe_caption)

            await database.add_video(url=resolved_url, user_id=user_id, username=message.from_user.username,
                                     file_path=result['file_path'], file_id=sent.video.file_id,
                                     title=safe_caption, media_type='video')
            logger.info(f"[USER: {user_id}] Видео успешно отправлено и занесено в БД.")

    await status_msg.delete()


async def send_from_cache(message: Message, bot: Bot, url: str, media_data: dict, status_msg: Message):
    user_id = message.from_user.id
    safe_caption = media_data.get('title', 'Медиа')
    file_id = media_data.get('file_id')

    try:
        if media_data.get('media_type') == 'images' and file_id:
            logger.info(f"[USER: {user_id}] Выгрузка слайдшоу по File ID...")
            file_ids = json.loads(file_id) if file_id.startswith('[') else [file_id]
            for chunk_idx, chunk in enumerate(chunk_list(file_ids, 10)):
                media_group = [InputMediaPhoto(type='photo', media=fid,
                                               caption=safe_caption if (chunk_idx == 0 and idx == 0) else None) for
                               idx, fid in enumerate(chunk)]

                # Защита для кэша (если в пачке остался 1 элемент)
                if len(media_group) == 1:
                    await bot.send_photo(message.chat.id, photo=media_group[0].media, caption=media_group[0].caption)
                else:
                    await bot.send_media_group(message.chat.id, media=media_group)

            logger.info(f"[USER: {user_id}] Слайдшоу из кэша отправлено.")

        elif file_id:
            logger.info(f"[USER: {user_id}] Выгрузка видео по File ID: {file_id}")
            await message.answer_video(video=file_id, caption=safe_caption)
            await database.update_video_file_id(url, file_id)
            logger.info(f"[USER: {user_id}] Видео из кэша отправлено.")
        else:
            logger.warning(f"[USER: {user_id}] Запись в кэше есть, но File ID отсутствует!")
            return await status_msg.edit_text('Файл не найден. Пожалуйста, отправьте ссылку еще раз.')

        await status_msg.delete()
    except Exception as e:
        logger.error(f"[USER: {user_id}] Ошибка отправки из кэша: {e}")
        await status_msg.edit_text('Произошла ошибка при выгрузке из кэша. Пожалуйста, отправьте ссылку еще раз.')