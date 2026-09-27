import aiosqlite
from typing import List, Optional, Dict, Any
from config import DB_PATH


async def init_db() -> None:
    """Ініціалізація бази даних: таблиці photos та friends."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                caption TEXT DEFAULT '',
                added_by INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Міграція: додаємо колонку added_by якщо її ще немає
        try:
            await db.execute("ALTER TABLE photos ADD COLUMN added_by INTEGER DEFAULT 0")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                added_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


# ===================== PHOTOS =====================

async def add_photo(file_id: str, caption: str = "", added_by: int = 0) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO photos (file_id, caption, added_by) VALUES (?, ?, ?)",
            (file_id, caption.strip(), added_by)
        )
        await db.commit()
        return cursor.lastrowid


async def get_photos(query: str = "", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.create_function("lower", 1, lambda s: s.lower() if s else "")
        db.row_factory = aiosqlite.Row
        words = [w.lower() for w in query.strip().split() if w]
        if words:
            conditions = ["LOWER(caption) LIKE ?" for _ in words]
            params = [f"%{w}%" for w in words]
            params.extend([limit, offset])
            cursor = await db.execute(
                f"SELECT id, file_id, caption, added_by, created_at FROM photos "
                f"WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT ? OFFSET ?",
                params
            )
        else:
            cursor = await db.execute(
                "SELECT id, file_id, caption, added_by, created_at FROM photos "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        return [dict(row) for row in await cursor.fetchall()]


async def get_photo_by_id(photo_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, file_id, caption, added_by, created_at FROM photos WHERE id = ?",
            (photo_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_photo(photo_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        await db.commit()
        return cursor.rowcount > 0


async def count_photos() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM photos")
        row = await cursor.fetchone()
        return row[0] if row else 0


# ===================== FRIENDS =====================

async def add_friend(user_id: int, username: str = "", first_name: str = "",
                     added_by: int = 0) -> bool:
    """Додає друга. Повертає True якщо успішно, False якщо вже є."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO friends (user_id, username, first_name, added_by) "
                "VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, added_by)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_friend(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM friends WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_friends() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, user_id, username, first_name, added_by, created_at "
            "FROM friends ORDER BY id DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_friend(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM friends WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def is_friend(user_id: int) -> bool:
    return await get_friend(user_id) is not None


async def count_friends() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM friends")
        row = await cursor.fetchone()
        return row[0] if row else 0
