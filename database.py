import aiosqlite
from typing import Optional, List, Dict, Any
from config import DB_PATH, DEFAULT_PROMPTS


async def init_db() -> None:
    """Инициализация базы данных и таблиц."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                active_promo TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                filename TEXT NOT NULL UNIQUE,
                price INTEGER NOT NULL,
                description TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                discount_percent INTEGER DEFAULT 0,
                discount_stars INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT -1,
                used_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                prompt_id TEXT NOT NULL,
                price_paid INTEGER NOT NULL,
                promo_code TEXT DEFAULT NULL,
                charge_id TEXT DEFAULT NULL,
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_prompts_filename ON prompts(filename)")

        # Проверяем и накатываем дефолтные промты без создания дублей
        seed_list = DEFAULT_PROMPTS
        names_file = BASE_DIR / "names.json"
        if names_file.exists():
            try:
                import json
                with open(names_file, "r", encoding="utf-8") as f:
                    seed_list = json.load(f)
            except Exception:
                seed_list = DEFAULT_PROMPTS

        for item in seed_list:
            cursor = await db.execute(
                "SELECT id FROM prompts WHERE filename = ? OR id = ?",
                (item["filename"], item["id"])
            )
            row = await cursor.fetchone()
            if not row:
                await db.execute(
                    """
                    INSERT INTO prompts (id, title, filename, price, description, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (item["id"], item["title"], item["filename"], int(item["price"]), item["description"])
                )

        await db.commit()


async def upsert_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_seen)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = CURRENT_TIMESTAMP
        """, (user_id, username, first_name))
        await db.commit()


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_user_ids() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def get_all_prompts(active_only: bool = True) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM prompts" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY price ASC"
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_prompt(prompt_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_prompt_price(prompt_id: str, new_price: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE prompts SET price = ? WHERE id = ?", (new_price, prompt_id))
        await db.commit()
        return cursor.rowcount > 0


async def toggle_prompt_status(prompt_id: str) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT is_active FROM prompts WHERE id = ?", (prompt_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        new_status = 0 if row[0] == 1 else 1
        await db.execute("UPDATE prompts SET is_active = ? WHERE id = ?", (new_status, prompt_id))
        await db.commit()
        return new_status


async def has_user_purchased(user_id: int, prompt_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM purchases WHERE user_id = ? AND prompt_id = ?",
            (user_id, prompt_id)
        )
        return (await cursor.fetchone()) is not None


async def get_user_purchased_prompts(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT p.*, pur.purchased_at, pur.price_paid, pur.charge_id
            FROM purchases pur
            JOIN prompts p ON p.id = pur.prompt_id
            WHERE pur.user_id = ?
            ORDER BY pur.purchased_at DESC
        """, (user_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def record_purchase(
    user_id: int,
    prompt_id: str,
    price_paid: int,
    promo_code: Optional[str] = None,
    charge_id: Optional[str] = None
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO purchases (user_id, prompt_id, price_paid, promo_code, charge_id)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, prompt_id, price_paid, promo_code, charge_id))
        await db.commit()
        return cursor.lastrowid


async def set_user_active_promo(user_id: int, code: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET active_promo = ? WHERE user_id = ?", (code, user_id))
        await db.commit()


async def get_user_active_promo(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT active_promo FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def create_promo_code(
    code: str,
    discount_percent: int = 0,
    discount_stars: int = 0,
    max_uses: int = -1
) -> bool:
    code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO promo_codes (code, discount_percent, discount_stars, max_uses, used_count, is_active)
                VALUES (?, ?, ?, ?, 0, 1)
                ON CONFLICT(code) DO UPDATE SET
                    discount_percent = excluded.discount_percent,
                    discount_stars = excluded.discount_stars,
                    max_uses = excluded.max_uses,
                    is_active = 1
            """, (code, discount_percent, discount_stars, max_uses))
            await db.commit()
            return True
        except Exception:
            return False


async def get_promo_code(code: str) -> Optional[Dict[str, Any]]:
    code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_promo_codes() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_promo_code(code: str) -> bool:
    code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM promo_codes WHERE code = ?", (code,))
        await db.commit()
        return cursor.rowcount > 0


async def check_promo_eligibility(user_id: int, code: str) -> tuple[bool, str, Optional[Dict[str, Any]]]:
    """Проверка валидности промокода для пользователя."""
    promo = await get_promo_code(code)
    if not promo:
        return False, "Промокод не найден.", None
    if promo["is_active"] != 1:
        return False, "Промокод деактивирован.", None
    if promo["max_uses"] != -1 and promo["used_count"] >= promo["max_uses"]:
        return False, "Лимит активаций этого промокода исчерпан.", None

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM promo_uses WHERE code = ? AND user_id = ?", (code.upper(), user_id))
        if await cursor.fetchone():
            return False, "Вы уже использовали этот промокод.", None

    return True, "OK", promo


async def apply_promo_usage(code: str, user_id: int) -> None:
    code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO promo_uses (code, user_id) VALUES (?, ?)", (code, user_id))
        await db.execute("""
            UPDATE promo_codes
            SET used_count = used_count + 1
            WHERE code = ?
        """, (code,))
        # Проверяем лимит
        cursor = await db.execute("SELECT max_uses, used_count FROM promo_codes WHERE code = ?", (code,))
        row = await cursor.fetchone()
        if row and row[0] != -1 and row[1] >= row[0]:
            await db.execute("UPDATE promo_codes SET is_active = 0 WHERE code = ?", (code,))
        await db.commit()


async def get_stats() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Пользователи
        c1 = await db.execute("SELECT COUNT(*) AS total_users FROM users")
        total_users = (await c1.fetchone())[0]

        # Покупки и выручка
        c2 = await db.execute("SELECT COUNT(*) AS total_sales, COALESCE(SUM(price_paid), 0) AS total_revenue FROM purchases")
        row_sales = await c2.fetchone()
        total_sales = row_sales[0]
        total_revenue = row_sales[1]

        # Активные промокоды
        c3 = await db.execute("SELECT COUNT(*) AS active_promos FROM promo_codes WHERE is_active = 1")
        active_promos = (await c3.fetchone())[0]

        # Всего промтов
        c4 = await db.execute("SELECT COUNT(*) AS total_prompts FROM prompts")
        total_prompts = (await c4.fetchone())[0]

        # Последние 5 покупок
        c5 = await db.execute("""
            SELECT pur.*, p.title, u.username
            FROM purchases pur
            LEFT JOIN prompts p ON p.id = pur.prompt_id
            LEFT JOIN users u ON u.user_id = pur.user_id
            ORDER BY pur.purchased_at DESC
            LIMIT 5
        """)
        recent_purchases = [dict(r) for r in await c5.fetchall()]

        return {
            "total_users": total_users,
            "total_sales": total_sales,
            "total_revenue": total_revenue,
            "active_promos": active_promos,
            "total_prompts": total_prompts,
            "recent_purchases": recent_purchases,
        }
