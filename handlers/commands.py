import logging
from telegram import Update, WebAppInfo, MenuButtonWebApp, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from config import SERVER_URL
import database

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    # Проверяем, пришел ли пользователь по кнопке из инлайн-режима
    if context.args and context.args[0] == 'new_download':
        await update.message.reply_text(
            f'Привет, {user.first_name}! 🎬\n\n'
            f'Ты пришел сюда, чтобы скачать новое видео.\n'
            f'Просто **вставь ссылку** в чат, и я скачаю её для тебя, '
            f'после чего она станет доступна в твоих инлайн-запросах!',
            parse_mode='Markdown'
        )
        return

    # Стандартная логика старта (если просто написали /start)
    normal_url = f"{SERVER_URL}/?user_id={user.id}&username={user.username or 'unknown'}"

    try:
        await context.bot.set_chat_menu_button(
            chat_id=user.id,
            menu_button=MenuButtonWebApp(
                text="насрать",
                web_app=WebAppInfo(url=normal_url)
            )
        )

        await update.message.reply_text(
            f'Привет, {user.first_name}! 👋\n\n'
            'способы использования:\n\n'
            ' - с помощью кнопки через сайт\n'
            ' - отправить ссылку на тт и шорты в лс\n'
            ' - добавить в чат с правами админа и тегать со ссылкой',
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"Error setting menu button: {e}")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать историю скачиваний пользователя"""
    user = update.effective_user
    videos = await database.get_user_videos(user.id)

    if not videos:
        await update.message.reply_text('📭 У тебя пока нет истории скачиваний.')
        return

    lines = ["**история скачиваний:**"]

    for i, video in enumerate(videos[:10], 1):
        # Оставляем полные названия и ссылки
        title = video.get('title', 'Media Item')
        url = video.get('url', 'Нет ссылки')

        # Форматируем дату (убираем миллисекунды, если они есть)
        raw_date = str(video.get('created_at', ''))
        date_str = raw_date.split('.')[0] if '.' in raw_date else raw_date

        item_text = (
            f"*{i}.* {title}\n"
            f"   📅 {date_str}\n"
            f"   🔗 {url}"
        )
        lines.append(item_text)

    msg = "\n\n".join(lines)

    if len(videos) > 10:
        msg += f"\n\n_...и еще {len(videos) - 10} видео_"

    # Отправляем сообщение, обязательно отключив превью ссылок (disable_web_page_preview)
    await update.message.reply_text(
        msg,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove(),
        disable_web_page_preview=True
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    user = update.effective_user
    user_videos = await database.get_user_videos(user.id)
    total_videos = await database.get_total_videos()

    message = (
        f'дроч на цифры:\n\n'
        f' - твоих скачиваний: {len(user_videos)}\n'
        f' - всего скачиваний в боте: {total_videos}\n'
        f' - деанон: {user.first_name} (id: {user.id})'
    )

    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())


async def raupov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /raupov"""
    await update.message.reply_text('Раупов согласны', reply_markup=ReplyKeyboardRemove())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        '/start - начать работу\n'
        '/history - твоя история скачиваний\n'
        '/stats - статистика\n'
        '/help - помощь',
        reply_markup=ReplyKeyboardRemove()
    )
