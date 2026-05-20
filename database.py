import aiosqlite
from datetime import datetime

DATABASE_PATH = "data/airdrops.db"


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                joined_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS airdrops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                link TEXT,
                category TEXT,
                status TEXT DEFAULT 'active',
                end_date TEXT,
                created_at TEXT,
                notified INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER,
                category TEXT,
                PRIMARY KEY (user_id, category)
            )
        """)
        await db.commit()


async def add_user(user_id: int, username: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, joined_at, is_active) VALUES (?, ?, ?, 1)",
            (user_id, username, datetime.now().isoformat())
        )
        await db.commit()


async def toggle_subscription(user_id: int, category: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM subscriptions WHERE user_id = ? AND category = ?",
            (user_id, category)
        )
        exists = await cursor.fetchone()
        if exists:
            await db.execute(
                "DELETE FROM subscriptions WHERE user_id = ? AND category = ?",
                (user_id, category)
            )
        else:
            await db.execute(
                "INSERT INTO subscriptions (user_id, category) VALUES (?, ?)",
                (user_id, category)
            )
        await db.commit()
        return not exists


async def get_user_categories(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT category FROM subscriptions WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def add_airdrop(title, description, link, category, end_date=None):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO airdrops (title, description, link, category, end_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (title, description, link, category, end_date, datetime.now().isoformat())
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0]


async def get_active_airdrops(category=None, limit=20):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if category:
            cursor = await db.execute(
                "SELECT * FROM airdrops WHERE status = 'active' AND category = ? ORDER BY created_at DESC LIMIT ?",
                (category, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM airdrops WHERE status = 'active' ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        return await cursor.fetchall()


async def get_not_notified_airdrops():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM airdrops WHERE notified = 0 AND status = 'active'"
        )
        return await cursor.fetchall()


async def mark_as_notified(airdrop_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE airdrops SET notified = 1 WHERE id = ?",
            (airdrop_id,)
        )
        await db.commit()


async def get_all_active_users():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM users WHERE is_active = 1"
        )
        return [r[0] for r in await cursor.fetchall()]


async def get_users_by_category(category: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT u.user_id FROM users u
               JOIN subscriptions s ON u.user_id = s.user_id
               WHERE s.category = ? AND u.is_active = 1""",
            (category,)
        )
        return [r[0] for r in await cursor.fetchall()]
