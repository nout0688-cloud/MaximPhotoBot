import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Поддержка одного или нескольких ID администраторов (через запятую или один ID)
raw_admin_ids = os.getenv("ADMIN_ID", "").strip()
ADMIN_IDS = set()
if raw_admin_ids:
    for part in raw_admin_ids.split(","):
        part = part.strip()
        if part.isdigit():
            ADMIN_IDS.add(int(part))

CACHE_TIME = int(os.getenv("CACHE_TIME", "1"))
DB_PATH = BASE_DIR / "photos.db"


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    if not ADMIN_IDS:
        # Если ADMIN_ID не задан в .env, разрешаем первому, кто напишет, или предупреждаем
        return True
    return user_id in ADMIN_IDS
