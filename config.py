import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("tiktok_bot")

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверьте файл .env")

SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:8080')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads_main')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'bot_data.db')
DATABASE_URL = os.getenv('DATABASE_URL')
DB_TYPE = os.getenv('DB_TYPE', 'sqlite').lower()
PORT = int(os.getenv('PORT', 8080))

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
