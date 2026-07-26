import os
import json
import logging
from telegram import Update, InputMediaPhoto, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from downloader import MediaDownloader, make_progress_bar
import database

logger = logging.getLogger(__name__)
downloader = MediaDownloader()


def chunk_list(lst: list, n: int):
    """Вспомогательная функция для разбиения списка на чанки"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def safe_delete_message(message):
    """Безопасное удаление сообщения пользователя"""
    if message:
        try:
            await message.delete()
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение: {e}")


def cleanup_local_file(path: str):
    """Удаление локального файла после отправки в Telegram"""
    if path and os.path.exists(path):
        try:
            os.remove(path)
            logger.info(f"Локальный файл удален: {path}")
        except Exception as e:
            logger.warning(f"Ошибка при удалении локального файла {path}: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (ссылок TikTok и YouTube)"""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user = update.effective_user
    chat_id = update.effective_chat.id

    # 1. Отправляем статусный статус
    status_message = await context.bot.send_message(
        chat_id=chat_id,
        text='⏳ Начинаю скачивание...'
    )

    # 2. Удаляем исходное сообщение с ссылкой пользователя (если возможно)
    await safe_delete_message(update.message)

    # 3. Проверяем кэш
    existing_video = await database.get_video_by_url(text)

    if existing_video:
        await handle_existing_media(context, chat_id, user, text, existing_video, status_message)
    else:
        await handle_new_media(context, chat_id, user, text, status_message)


async def handle_new_media(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, url: str, status_message):
    """Обработка нового медиа - скачивание с прогресс-баром и отправка"""
    try:
        # Колбэк прогресс-бара для редактирования статусного сообщения
        async def progress_cb(percent_or_text, speed=None, eta=None):
            if isinstance(percent_or_text, str):
                text = percent_or_text
            else:
                bar = make_progress_bar(percent_or_text)
                text = (
                    f"⏳ **Скачивание видео...**\n\n"
                    f"`{bar}`\n"
                    f"Скорость: `{speed}` | Осталось: `{eta}`"
                )
            try:
                await status_message.edit_text(text, parse_mode='Markdown')
            except Exception as e:
                logger.debug(f"Progress update skipped: {e}")

        result = await downloader.download_media(url, progress_callback=progress_cb)

        if not result['success']:
            await status_message.edit_text(f"❌ {result.get('error', 'Ошибка скачивания')}")
            return

        media_type = result.get('media_type', 'video')
        title = result.get('title', 'Media')

        if media_type == 'images':
            # === ОБРАБОТКА ИЗОБРАЖЕНИЙ (СЛАЙДШОУ) ===
            await status_message.edit_text('📤 Отправляю фотослайдшоу...')
            image_paths = result.get('image_paths', [])

            # Достаем путь к аудио из ответа загрузчика
            audio_path = result.get('audio_path')

            if not image_paths:
                await status_message.edit_text('❌ Изображения не найдены.')
                return

            saved_file_ids = []

            # === ИЗМЕНЕННАЯ ЛОГИКА ЧАНКОВ ===
            chunks = list(chunk_list(image_paths, 10))
            total_chunks = len(chunks)

            for chunk_idx, chunk in enumerate(chunks):
                media_group = []
                opened_files = []
                try:
                    for idx, img_path in enumerate(chunk):
                        f = open(img_path, 'rb')
                        opened_files.append(f)
                        # Подпись добавляется только к первому фото ПОСЛЕДНЕГО чанка
                        caption = f"🎵 {title}" if (chunk_idx == total_chunks - 1 and idx == 0) else None
                        media_group.append(InputMediaPhoto(media=f, caption=caption))

                    sent_msgs = await context.bot.send_media_group(
                        chat_id=chat_id,
                        media=media_group,
                        read_timeout=60,
                        write_timeout=60
                    )

                    for msg in sent_msgs:
                        if msg.photo:
                            saved_file_ids.append(msg.photo[-1].file_id)
                finally:
                    for f in opened_files:
                        f.close()

            # Отправляем аудио файл отдельным сообщением
            if audio_path and os.path.exists(audio_path):
                try:
                    with open(audio_path, 'rb') as audio_file:
                        await context.bot.send_audio(
                            chat_id=chat_id,
                            audio=audio_file,
                            caption="🎵 Оригинальный звук"
                        )
                    # Очищаем скачанный аудиофайл
                    cleanup_local_file(audio_path)
                except Exception as e:
                    logger.warning(f"Не удалось отправить звук: {e}")

            file_ids_json = json.dumps(saved_file_ids) if saved_file_ids else None
            await database.add_video(
                url=url,
                user_id=user.id,
                username=user.username,
                file_path=image_paths[0] if image_paths else None,
                file_id=file_ids_json,
                title=title,
                media_type='images'
            )

            # Очищаем скачанные изображения с диска
            for img_path in image_paths:
                cleanup_local_file(img_path)

        else:
            # === ОБРАБОТКА ВИДЕО ===
            await status_message.edit_text('📤 Отправляю видео...')
            file_path = result['file_path']

            with open(file_path, 'rb') as video_file:
                sent_message = await context.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    caption=f"🎵 {title}",
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60
                )

            file_id = sent_message.video.file_id if sent_message.video else None

            await database.add_video(
                url=url,
                user_id=user.id,
                username=user.username,
                file_path=file_path,
                file_id=file_id,
                title=title,
                media_type='video'
            )

            # Очищаем скачанный файл с диска
            cleanup_local_file(file_path)

        # Удаляем статусный статус
        await safe_delete_message(status_message)
        logger.info(f"Медиа ({media_type}) для {url} успешно отправлено {user.id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке нового медиа: {e}", exc_info=True)
        await status_message.edit_text(
            '❌ Произошла ошибка при обработке медиа.\n'
            'Попробуйте еще раз позже.'
        )


async def handle_existing_media(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, url: str, media_data: dict, status_message):
    """Обработка существующего медиа из кэша"""
    try:
        media_type = media_data.get('media_type', 'video')
        title = media_data.get('title', 'Media Item')
        file_id = media_data.get('file_id')

        if media_type == 'images':
            if file_id:
                try:
                    file_ids = json.loads(file_id) if file_id.startswith('[') else [file_id]
                    for chunk_idx, chunk in enumerate(chunk_list(file_ids, 10)):
                        media_group = []
                        for idx, fid in enumerate(chunk):
                            caption = f"🎵 {title}" if (chunk_idx == 0 and idx == 0) else None
                            media_group.append(InputMediaPhoto(media=fid, caption=caption))
                        await context.bot.send_media_group(chat_id=chat_id, media=media_group)

                    await safe_delete_message(status_message)
                    logger.info(f"Фотослайдшоу отправлено из кэша (file_ids) пользователю {user.id}")
                    return
                except Exception as e:
                    logger.warning(f"Не удалось отправить фото из кэша file_ids: {e}")

        else:
            if file_id:
                try:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=file_id,
                        caption=f"🎵 {title}",
                        supports_streaming=True
                    )
                    await database.update_video_file_id(url, file_id)
                    await safe_delete_message(status_message)
                    logger.info(f"Видео отправлено из кэша (file_id) пользователю {user.id}")
                    return
                except Exception as e:
                    logger.warning(f"Не удалось отправить видео через file_id: {e}")

            file_path = media_data.get('file_path')
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as video_file:
                    sent_message = await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption=f"🎵 {title}",
                        supports_streaming=True
                    )

                if sent_message.video:
                    await database.update_video_file_id(url, sent_message.video.file_id)

                cleanup_local_file(file_path)
                await safe_delete_message(status_message)
                logger.info(f"Видео отправлено из локального файла пользователю {user.id}")
                return

        await status_message.edit_text('⚠️ Файл не найден в кэше. Скачиваю заново...')
        await handle_new_media(context, chat_id, user, url, status_message)

    except Exception as e:
        logger.error(f"Ошибка при отправке кэшированного медиа: {e}", exc_info=True)
        await handle_new_media(context, chat_id, user, url, status_message)
