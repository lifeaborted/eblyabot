import aiosqlite
from datetime import datetime

DATABASE_NAME = 'bot_data.db'

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                video_id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

async def add_video(url: str, user_id: int, username: str = None):
    """Добавление нового видео в базу данных"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute(
            'INSERT INTO videos (url, user_id, username) VALUES (?, ?, ?)',
            (url, user_id, username)
        )
        await db.commit()
        return cursor.lastrowid

async def get_user_videos(user_id: int):
    """Получение всех видео пользователя"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM videos WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_video_by_id(video_id: int):
    """Получение видео по ID"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM videos WHERE video_id = ?',
            (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_total_videos():
    """Получение общего количества видео"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute('SELECT COUNT(*) FROM videos') as cursor:
            result = await cursor.fetchone()
            return result[0]

async def check_url_exists(url: str, user_id: int):
    """Проверка, скачивал ли пользователь это видео ранее"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute(
            'SELECT video_id FROM videos WHERE url = ? AND user_id = ?',
            (url, user_id)
        ) as cursor:
            result = await cursor.fetchone()
            return result is not None