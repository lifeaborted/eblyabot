import logging
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import DATABASE_NAME, DATABASE_URL, DB_TYPE

if DB_TYPE == 'postgresql':
    import asyncpg
    HAS_ASPG = True
else:
    import aiosqlite
    HAS_ASPG = False

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.db_type = DB_TYPE
        self.pool = None
        
    async def init_db(self):
        """Initialize database connection and create tables"""
        if self.db_type == 'postgresql' and DATABASE_URL:
            self.pool = await asyncpg.create_pool(DATABASE_URL)
            async with self.pool.acquire() as conn:
                await self._create_postgres_tables(conn)
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                await self._create_sqlite_tables(db)
    
    async def _create_sqlite_tables(self, db):
        """Create tables for SQLite database"""
        await db.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                video_id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                file_path TEXT,
                file_id TEXT,
                title TEXT,
                user_id INTEGER NOT NULL,
                username TEXT,
                media_type TEXT DEFAULT 'video',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

        # Check column migration for media_type
        try:
            await db.execute('ALTER TABLE videos ADD COLUMN media_type TEXT DEFAULT "video"')
            await db.commit()
        except Exception:
            pass # Column already exists
        
    async def _create_postgres_tables(self, conn):
        """Create tables for PostgreSQL database"""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                video_id SERIAL PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                file_path TEXT,
                file_id TEXT,
                title TEXT,
                user_id INTEGER NOT NULL,
                username TEXT,
                media_type TEXT DEFAULT 'video',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Postgres migration check
        try:
            await conn.execute('ALTER TABLE videos ADD COLUMN IF NOT EXISTS media_type TEXT DEFAULT \'video\'')
        except Exception as e:
            logger.debug(f"Postgres column check: {e}")
    
    async def add_video(self, url: str, user_id: int, username: str = None,
                       file_path: str = None, file_id: str = None,
                       title: str = None, media_type: str = 'video'):
        """Добавление нового видео или группы фото в базу данных"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(
                    '''INSERT INTO videos
                       (url, user_id, username, file_path, file_id, title, media_type)
                       VALUES ($1, $2, $3, $4, $5, $6, $7) 
                       ON CONFLICT (url) DO UPDATE 
                       SET file_id = EXCLUDED.file_id, file_path = EXCLUDED.file_path, title = EXCLUDED.title, media_type = EXCLUDED.media_type
                       RETURNING video_id''',
                    url, user_id, username, file_path, file_id, title, media_type
                )
                return result
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                cursor = await db.execute(
                    '''INSERT OR REPLACE INTO videos
                       (url, user_id, username, file_path, file_id, title, media_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (url, user_id, username, file_path, file_id, title, media_type)
                )
                await db.commit()
                return cursor.lastrowid

    async def get_user_videos(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение всех видео пользователя"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    'SELECT * FROM videos WHERE user_id = $1 ORDER BY created_at DESC',
                    user_id
                )
                return [dict(row) for row in rows]
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    'SELECT * FROM videos WHERE user_id = ? ORDER BY created_at DESC',
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]

    async def get_video_by_id(self, video_id: int) -> Optional[Dict[str, Any]]:
        """Получение видео по ID"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    'SELECT * FROM videos WHERE video_id = $1',
                    video_id
                )
                return dict(row) if row else None
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    'SELECT * FROM videos WHERE video_id = ?',
                    (video_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None

    async def get_video_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Получение видео по URL"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    'SELECT * FROM videos WHERE url = $1',
                    url
                )
                return dict(row) if row else None
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    'SELECT * FROM videos WHERE url = ?',
                    (url,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None

    async def update_video_file_id(self, url: str, file_id: str):
        """Обновление file_id для видео (для переиспользования в Telegram)"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE videos SET file_id = $1, created_at = $2 WHERE url = $3',
                    file_id, datetime.now().replace(microsecond=0), url
                )
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                await db.execute(
                    'UPDATE videos SET file_id = ?, created_at = ? WHERE url = ?',
                    (file_id, datetime.now().replace(microsecond=0), url)
                )
                await db.commit()
        
        logger.info(f"Обновлен file_id в БД для URL: {url}")

    async def get_total_videos(self) -> int:
        """Получение общего количества видео"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval('SELECT COUNT(*) FROM videos')
                return result
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                async with db.execute('SELECT COUNT(*) FROM videos') as cursor:
                    result = await cursor.fetchone()
                    return result[0]

    async def check_url_exists(self, url: str) -> bool:
        """Проверка существования URL в базе"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(
                    'SELECT video_id FROM videos WHERE url = $1',
                    url
                )
                return result is not None
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                async with db.execute(
                    'SELECT video_id FROM videos WHERE url = ?',
                    (url,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result is not None

    async def get_all_videos(self) -> List[Dict[str, Any]]:
        """Получение всех видео"""
        if self.db_type == 'postgresql' and self.pool:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    'SELECT * FROM videos ORDER BY created_at DESC'
                )
                return [dict(row) for row in rows]
        else:
            async with aiosqlite.connect(DATABASE_NAME) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    'SELECT * FROM videos ORDER BY created_at DESC'
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]

# Create global instance
db_manager = DatabaseManager()

# Module-level functions
async def init_db():
    return await db_manager.init_db()

async def add_video(url: str, user_id: int, username: str = None,
                   file_path: str = None, file_id: str = None,
                   title: str = None, media_type: str = 'video'):
    return await db_manager.add_video(url, user_id, username, file_path, file_id, title, media_type)

async def get_user_videos(user_id: int):
    return await db_manager.get_user_videos(user_id)

async def get_video_by_id(video_id: int):
    return await db_manager.get_video_by_id(video_id)

async def get_video_by_url(url: str):
    return await db_manager.get_video_by_url(url)

async def update_video_file_id(url: str, file_id: str):
    return await db_manager.update_video_file_id(url, file_id)

async def get_total_videos():
    return await db_manager.get_total_videos()

async def check_url_exists(url: str):
    return await db_manager.check_url_exists(url)

async def get_all_videos():
    return await db_manager.get_all_videos()
