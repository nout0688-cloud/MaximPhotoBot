import aiosqlite
from typing import List, Optional, Dict, Any
from config import DB_PATH


async def init_db() -> None:
    """Инициализация базы данных и создание таблиц, если они не существуют."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                caption TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def add_photo(file_id: str, caption: str = "") -> int:
    """Добавляет новую фотографию в базу и возвращает её ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO photos (file_id, caption) VALUES (?, ?)",
            (file_id, caption.strip())
        )
        await db.commit()
        return cursor.lastrowid


async def get_photos(query: str = "", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Возвращает список фотографий.
    Если query передан, фильтрует по описанию (без учета регистра).
    Сортировка: самые новые сначала.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.create_function("lower", 1, lambda s: s.lower() if s else "")
        db.row_factory = aiosqlite.Row
        cleaned_query = query.strip()
        words = [w.lower() for w in cleaned_query.split() if w]
        if words:
            conditions = ["LOWER(caption) LIKE ?" for _ in words]
            params = [f"%{w}%" for w in words]
            params.extend([limit, offset])
            cursor = await db.execute(
                f"""
                SELECT id, file_id, caption, created_at
                FROM photos
                WHERE {" AND ".join(conditions)}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                params
            )
        else:
            cursor = await db.execute(
                """
                SELECT id, file_id, caption, created_at
                FROM photos
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_photo_by_id(photo_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает фото по его ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, file_id, caption, created_at FROM photos WHERE id = ?",
            (photo_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_photo(photo_id: int) -> bool:
    """Удаляет фотографию по ID. Возвращает True, если фото было удалено."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM photos WHERE id = ?",
            (photo_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def count_photos() -> int:
    """Возвращает общее количество сохраненных фотографий."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM photos")
        row = await cursor.fetchone()
        return row[0] if row else 0
