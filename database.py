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

    async def close(self):
        """Закрыть пул соединений"""
        if self.pool:
            await self.pool.close()

# Глобальный экземпляр базы данных для использования во всех модулях
db = Database()
