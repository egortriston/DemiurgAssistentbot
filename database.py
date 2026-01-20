import asyncpg
from datetime import datetime, timedelta
from typing import Optional, List
from config import DB_URL

class Database:
    """
    Класс для работы с базой данных PostgreSQL.
    
    ПОДКЛЮЧЕНИЕ К БД:
    -----------------
    Подключение происходит через connection pool в методе get_connection().
    Каждый метод получает соединение из пула, выполняет запрос и возвращает соединение в пул.
    
    Инициализация пула происходит в методе init_db() при первом запуске бота.
    """
    
    def __init__(self):
        self.db_url = DB_URL
        self.pool: Optional[asyncpg.Pool] = None

    async def init_db(self):
        """
        ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ И СОЗДАНИЕ ПУЛА СОЕДИНЕНИЙ
        
        Этот метод вызывается при запуске бота (см. main.py, функция on_startup).
        Создает пул соединений к PostgreSQL и инициализирует таблицы.
        """
        # Создаем пул соединений
        self.pool = await asyncpg.create_pool(
            self.db_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        
        # Инициализируем таблицы
        async with self.pool.acquire() as conn:
            # Users table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    gift_received BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Subscriptions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    channel_name VARCHAR(50) NOT NULL,
                    is_active BOOLEAN DEFAULT FALSE,
                    payment_method VARCHAR(50) NOT NULL,
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(telegram_id, channel_name)
                )
            """)
            
            # Payments table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    channel_name VARCHAR(50) NOT NULL,
                    amount INTEGER NOT NULL,
                    payment_id VARCHAR(255) UNIQUE NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Reminders table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    channel_name VARCHAR(50) NOT NULL,
                    reminder_sent BOOLEAN DEFAULT FALSE,
                    reminder_date TIMESTAMP NOT NULL,
                    UNIQUE(telegram_id, channel_name)
                )
            """)
            
            # Whitelist table - users who should never be kicked from channels
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                    channel_name VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(telegram_id, channel_name)
                )
            """)
            
            # Channel memberships table - tracks user ban and whitelist status per channel
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS channel_memberships (
                    telegram_id BIGINT NOT NULL,
                    channel_name VARCHAR(50) NOT NULL,
                    is_banned BOOLEAN DEFAULT FALSE,
                    is_whitelisted BOOLEAN DEFAULT FALSE,
                    banned_at TIMESTAMP,
                    last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, channel_name)
                )
            """)
            
            # Add is_whitelisted column if it doesn't exist (migration for existing tables)
            await conn.execute("""
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='channel_memberships' AND column_name='is_whitelisted') THEN
                        ALTER TABLE channel_memberships ADD COLUMN is_whitelisted BOOLEAN DEFAULT FALSE;
                    END IF;
                END $$;
            """)
            
            # Создаем индексы для оптимизации
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_active 
                ON subscriptions(telegram_id, channel_name, is_active) 
                WHERE is_active = TRUE
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_end_date 
                ON subscriptions(end_date) 
                WHERE is_active = TRUE
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_payments_status 
                ON payments(status)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_payments_telegram_id 
                ON payments(telegram_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminders_pending 
                ON reminders(reminder_date, reminder_sent) 
                WHERE reminder_sent = FALSE
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_whitelist_telegram_id 
                ON whitelist(telegram_id, channel_name)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_memberships_banned 
                ON channel_memberships(channel_name, is_banned)
                WHERE is_banned = TRUE
            """)

    async def get_connection(self):
        """Получить соединение из пула"""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call init_db() first.")
        return await self.pool.acquire()

    async def add_user(self, telegram_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """
        Добавить или обновить пользователя
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет INSERT ... ON CONFLICT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (telegram_id) 
                DO UPDATE SET 
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
            """, telegram_id, username, first_name, last_name)

    async def get_user(self, telegram_id: int) -> Optional[dict]:
        """
        Получить пользователя по telegram_id
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
            return dict(row) if row else None

    async def import_users_from_masterclass(self, telegram_ids: List[int]):
        """
        Импортировать пользователей из мастер-класса
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет несколько запросов,
        возвращает соединение в пул.
        """
        users_to_gift = []
        async with self.pool.acquire() as conn:
            for telegram_id in telegram_ids:
                # Check if user exists and hasn't received gift
                user = await self.get_user(telegram_id)
                if not user or not user.get('gift_received', False):
                    # Add user if doesn't exist
                    if not user:
                        await self.add_user(telegram_id)
                    users_to_gift.append(telegram_id)
        return users_to_gift

    async def mark_gift_received(self, telegram_id: int):
        """
        Отметить подарок как полученный
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет UPDATE,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET gift_received = TRUE WHERE telegram_id = $1", telegram_id)

    async def create_subscription(self, telegram_id: int, channel_name: str, payment_method: str, 
                                 start_date: datetime, end_date: datetime, is_active: bool = True):
        """
        Создать или обновить подписку
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет INSERT ... ON CONFLICT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            # Check if subscription exists
            existing = await conn.fetchrow("""
                SELECT id FROM subscriptions 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)
            
            if existing:
                # Update existing subscription
                await conn.execute("""
                    UPDATE subscriptions 
                    SET is_active = $1, payment_method = $2, start_date = $3, end_date = $4
                    WHERE telegram_id = $5 AND channel_name = $6
                """, is_active, payment_method, start_date, end_date, telegram_id, channel_name)
            else:
                # Create new subscription
                await conn.execute("""
                    INSERT INTO subscriptions (telegram_id, channel_name, is_active, payment_method, start_date, end_date)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, telegram_id, channel_name, is_active, payment_method, start_date, end_date)

    async def get_active_subscription(self, telegram_id: int, channel_name: str) -> Optional[dict]:
        """
        Получить активную подписку пользователя на канал
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM subscriptions 
                WHERE telegram_id = $1 AND channel_name = $2 AND is_active = TRUE
                ORDER BY end_date DESC LIMIT 1
            """, telegram_id, channel_name)
            return dict(row) if row else None

    async def get_user_subscriptions(self, telegram_id: int) -> List[dict]:
        """
        Получить все подписки пользователя
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM subscriptions 
                WHERE telegram_id = $1
                ORDER BY end_date DESC
            """, telegram_id)
            return [dict(row) for row in rows]

    async def deactivate_subscription(self, telegram_id: int, channel_name: str):
        """
        Деактивировать подписку
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет UPDATE,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE subscriptions 
                SET is_active = FALSE 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)

    async def has_ever_had_subscription(self, telegram_id: int, channel_name: str) -> bool:
        """
        Проверить, была ли у пользователя когда-либо подписка на канал
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM subscriptions 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)
            return count > 0

    async def create_payment(self, telegram_id: int, channel_name: str, amount: int, payment_id: str, status: str = "pending"):
        """
        Создать запись о платеже
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет INSERT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO payments (telegram_id, channel_name, amount, payment_id, status)
                VALUES ($1, $2, $3, $4, $5)
            """, telegram_id, channel_name, amount, payment_id, status)

    async def update_payment_status(self, payment_id: str, status: str):
        """
        Обновить статус платежа
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет UPDATE,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE payments SET status = $1 WHERE payment_id = $2
            """, status, payment_id)

    async def get_payment(self, payment_id: str) -> Optional[dict]:
        """
        Получить платеж по payment_id
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM payments WHERE payment_id = $1", payment_id)
            return dict(row) if row else None

    async def create_reminder(self, telegram_id: int, channel_name: str, reminder_date: datetime):
        """
        Создать напоминание
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет INSERT ... ON CONFLICT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO reminders (telegram_id, channel_name, reminder_date, reminder_sent)
                VALUES ($1, $2, $3, FALSE)
                ON CONFLICT (telegram_id, channel_name) 
                DO UPDATE SET reminder_date = EXCLUDED.reminder_date, reminder_sent = FALSE
            """, telegram_id, channel_name, reminder_date)

    async def mark_reminder_sent(self, telegram_id: int, channel_name: str):
        """
        Отметить напоминание как отправленное
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет UPDATE,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE reminders SET reminder_sent = TRUE 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)

    async def get_pending_reminders(self) -> List[dict]:
        """
        Получить все неотправленные напоминания
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM reminders 
                WHERE reminder_sent = FALSE AND reminder_date <= $1
            """, datetime.now())
            return [dict(row) for row in rows]

    async def get_expiring_subscriptions(self) -> List[dict]:
        """
        Получить подписки, истекающие в ближайшее время
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            now = datetime.now()
            end_date = now + timedelta(days=3)
            rows = await conn.fetch("""
                SELECT * FROM subscriptions 
                WHERE is_active = TRUE 
                AND end_date BETWEEN $1 AND $2
                AND payment_method = 'gift'
            """, now, end_date)
            return [dict(row) for row in rows]

    async def get_expired_subscriptions(self) -> List[dict]:
        """
        Получить истекшие подписки (все активные подписки, у которых end_date прошла)
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            now = datetime.now()
            
            # Сначала проверим все активные подписки для отладки
            all_active = await conn.fetch("""
                SELECT telegram_id, channel_name, end_date, is_active 
                FROM subscriptions 
                WHERE is_active = TRUE
                ORDER BY end_date ASC
            """)
            print(f"[DB] Всего активных подписок: {len(all_active)}")
            for sub in all_active:
                sub_dict = dict(sub)
                end_date = sub_dict['end_date']
                if isinstance(end_date, str):
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                elif hasattr(end_date, 'replace'):
                    end_date = end_date.replace(tzinfo=None)
                print(f"  - User {sub_dict['telegram_id']}, channel {sub_dict['channel_name']}, end_date: {end_date} (now: {now}, expired: {end_date < now})")
            
            # Теперь ищем истекшие
            rows = await conn.fetch("""
                SELECT * FROM subscriptions 
                WHERE is_active = TRUE 
                AND end_date < $1
                ORDER BY end_date ASC
            """, now)
            result = [dict(row) for row in rows]
            
            # Логируем для отладки
            if result:
                print(f"[DB] ✅ Found {len(result)} expired subscriptions (current time: {now})")
                for sub in result:
                    end_date = sub['end_date']
                    if isinstance(end_date, str):
                        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    elif hasattr(end_date, 'replace'):
                        end_date = end_date.replace(tzinfo=None)
                    print(f"  - User {sub['telegram_id']}, channel {sub['channel_name']}, end_date: {end_date}")
            else:
                print(f"[DB] ❌ No expired subscriptions found (current time: {now})")
            return result

    async def add_whitelist_user(self, telegram_id: int, channel_name: str):
        """
        Добавить пользователя в whitelist (никогда не будет исключен из канала)
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет INSERT ... ON CONFLICT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            # Ensure user exists first
            await conn.execute("""
                INSERT INTO users (telegram_id)
                VALUES ($1)
                ON CONFLICT (telegram_id) DO NOTHING
            """, telegram_id)
            
            # Add to whitelist
            await conn.execute("""
                INSERT INTO whitelist (telegram_id, channel_name)
                VALUES ($1, $2)
                ON CONFLICT (telegram_id, channel_name) DO NOTHING
            """, telegram_id, channel_name)
            
            # Sync with channel_memberships - mark as whitelisted and not banned
            now = datetime.now()
            await conn.execute("""
                INSERT INTO channel_memberships (telegram_id, channel_name, is_banned, is_whitelisted, last_verified)
                VALUES ($1, $2, FALSE, TRUE, $3)
                ON CONFLICT (telegram_id, channel_name) 
                DO UPDATE SET 
                    is_whitelisted = TRUE,
                    is_banned = FALSE,
                    banned_at = NULL,
                    last_verified = EXCLUDED.last_verified
            """, telegram_id, channel_name, now)

    async def remove_whitelist_user(self, telegram_id: int, channel_name: str):
        """
        Удалить пользователя из whitelist
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет DELETE,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM whitelist 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)
            
            # Sync with channel_memberships - mark as not whitelisted
            now = datetime.now()
            await conn.execute("""
                UPDATE channel_memberships 
                SET is_whitelisted = FALSE, last_verified = $3
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name, now)

    async def is_whitelisted(self, telegram_id: int, channel_name: str) -> bool:
        """
        Проверить, находится ли пользователь в whitelist
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM whitelist 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)
            return count > 0

    async def get_whitelist_users(self, channel_name: str = None) -> List[dict]:
        """
        Получить всех пользователей из whitelist
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        
        Args:
            channel_name: Если указан, возвращает только для этого канала. Если None, возвращает всех.
        """
        async with self.pool.acquire() as conn:
            if channel_name:
                rows = await conn.fetch("""
                    SELECT w.*, u.username, u.first_name, u.last_name
                    FROM whitelist w
                    LEFT JOIN users u ON w.telegram_id = u.telegram_id
                    WHERE w.channel_name = $1
                    ORDER BY w.created_at DESC
                """, channel_name)
            else:
                rows = await conn.fetch("""
                    SELECT w.*, u.username, u.first_name, u.last_name
                    FROM whitelist w
                    LEFT JOIN users u ON w.telegram_id = u.telegram_id
                    ORDER BY w.channel_name, w.created_at DESC
                """)
            return [dict(row) for row in rows]

    # ==================== CHANNEL MEMBERSHIPS (BAN STATUS) ====================
    
    async def set_user_banned(self, telegram_id: int, channel_name: str, is_banned: bool):
        """
        Set user ban status for a channel. Also syncs whitelist status.
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет INSERT ... ON CONFLICT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            now = datetime.now()
            # Check if user is whitelisted
            is_whitelisted = await self.is_whitelisted(telegram_id, channel_name)
            
            await conn.execute("""
                INSERT INTO channel_memberships (telegram_id, channel_name, is_banned, is_whitelisted, banned_at, last_verified)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (telegram_id, channel_name) 
                DO UPDATE SET 
                    is_banned = EXCLUDED.is_banned,
                    is_whitelisted = EXCLUDED.is_whitelisted,
                    banned_at = CASE WHEN EXCLUDED.is_banned = TRUE THEN EXCLUDED.banned_at ELSE NULL END,
                    last_verified = EXCLUDED.last_verified
            """, telegram_id, channel_name, is_banned, is_whitelisted, now if is_banned else None, now)

    async def is_user_banned(self, telegram_id: int, channel_name: str) -> bool:
        """
        Check if user is banned from a channel
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT is_banned FROM channel_memberships 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)
            return result if result is not None else False

    async def get_user_channel_status(self, telegram_id: int, channel_name: str) -> Optional[dict]:
        """
        Get user's channel membership status
        
        ПОДКЛЮЧЕНИЕ: Получает соединение из пула, выполняет SELECT,
        возвращает соединение в пул.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM channel_memberships 
                WHERE telegram_id = $1 AND channel_name = $2
            """, telegram_id, channel_name)
            return dict(row) if row else None

    async def get_all_users_for_verification(self) -> List[dict]:
        """
        Get all users who have ever had a subscription (need verification on startup)
        
        Returns users with their subscription and whitelist status for each channel.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT 
                    s.telegram_id, 
                    s.channel_name,
                    s.is_active,
                    s.end_date,
                    CASE WHEN w.telegram_id IS NOT NULL THEN TRUE ELSE FALSE END as is_whitelisted,
                    COALESCE(cm.is_banned, FALSE) as is_banned
                FROM subscriptions s
                LEFT JOIN whitelist w ON s.telegram_id = w.telegram_id AND s.channel_name = w.channel_name
                LEFT JOIN channel_memberships cm ON s.telegram_id = cm.telegram_id AND s.channel_name = cm.channel_name
                ORDER BY s.telegram_id, s.channel_name
            """)
            return [dict(row) for row in rows]

    async def get_banned_users(self, channel_name: str = None) -> List[dict]:
        """
        Get all banned users, optionally filtered by channel
        """
        async with self.pool.acquire() as conn:
            if channel_name:
                rows = await conn.fetch("""
                    SELECT cm.*, u.username, u.first_name, u.last_name
                    FROM channel_memberships cm
                    LEFT JOIN users u ON cm.telegram_id = u.telegram_id
                    WHERE cm.channel_name = $1 AND cm.is_banned = TRUE
                    ORDER BY cm.banned_at DESC
                """, channel_name)
            else:
                rows = await conn.fetch("""
                    SELECT cm.*, u.username, u.first_name, u.last_name
                    FROM channel_memberships cm
                    LEFT JOIN users u ON cm.telegram_id = u.telegram_id
                    WHERE cm.is_banned = TRUE
                    ORDER BY cm.channel_name, cm.banned_at DESC
                """)
            return [dict(row) for row in rows]

    async def close(self):
        """Закрыть пул соединений"""
        if self.pool:
            await self.pool.close()

# Глобальный экземпляр базы данных для использования во всех модулях
db = Database()
