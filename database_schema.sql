-- =====================================================
-- СХЕМА БАЗЫ ДАННЫХ ДЛЯ TELEGRAM БОТА "ОРДЕН ДЕМИУРГОВ"
-- PostgreSQL
-- =====================================================

-- Таблица пользователей
-- Хранит основную информацию о пользователях бота
CREATE TABLE IF NOT EXISTS users (
    -- PRIMARY KEY: Уникальный идентификатор пользователя в Telegram
    telegram_id BIGINT PRIMARY KEY,

-- Имя пользователя в Telegram (может быть NULL)
username VARCHAR(255),

-- Имя пользователя (может быть NULL)
first_name VARCHAR(255),

-- Фамилия пользователя (может быть NULL)
last_name VARCHAR(255),

-- Флаг получения подарка из мастер-класса
-- FALSE = подарок еще не получен, TRUE = подарок получен
gift_received BOOLEAN DEFAULT FALSE,

-- Дата и время регистрации пользователя в системе
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP );

-- Таблица подписок
-- Хранит информацию о подписках пользователей на каналы
CREATE TABLE IF NOT EXISTS subscriptions (
    -- PRIMARY KEY: Автоинкрементный идентификатор подписки
    id SERIAL PRIMARY KEY,

-- FOREIGN KEY: Ссылка на пользователя (users.telegram_id)
telegram_id BIGINT NOT NULL REFERENCES users (telegram_id) ON DELETE CASCADE,

-- Название канала: 'channel_1' (Орден Демиургов) или 'channel_2' (Родители Демиурга)
channel_name VARCHAR(50) NOT NULL,

-- Статус подписки: TRUE = активна, FALSE = неактивна
is_active BOOLEAN DEFAULT FALSE,

-- Метод оплаты: 'gift' (подарок), 'paid' (оплачено)
payment_method VARCHAR(50) NOT NULL,

-- Дата начала подписки
start_date TIMESTAMP NOT NULL,

-- Дата окончания подписки
end_date TIMESTAMP NOT NULL,

-- Дата и время создания записи
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

-- Уникальный индекс: один пользователь может иметь только одну активную подписку на канал
UNIQUE(telegram_id, channel_name) );

-- Таблица платежей
-- Хранит информацию о платежах через Robokassa
CREATE TABLE IF NOT EXISTS payments (
    -- PRIMARY KEY: Автоинкрементный идентификатор платежа
    id SERIAL PRIMARY KEY,

-- FOREIGN KEY: Ссылка на пользователя (users.telegram_id)
telegram_id BIGINT NOT NULL REFERENCES users (telegram_id) ON DELETE CASCADE,

-- Название канала, за который произведена оплата
channel_name VARCHAR(50) NOT NULL,

-- Сумма платежа в рублях
amount INTEGER NOT NULL,

-- Уникальный идентификатор платежа от Robokassa (InvId)
payment_id VARCHAR(255) UNIQUE NOT NULL,

-- Статус платежа: 'pending' (ожидает), 'success' (успешно), 'failed' (неудачно)
status VARCHAR(50) DEFAULT 'pending',

-- Дата и время создания платежа
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP );

-- Таблица напоминаний
-- Хранит информацию о напоминаниях пользователям об окончании подписки
CREATE TABLE IF NOT EXISTS reminders (
    -- PRIMARY KEY: Автоинкрементный идентификатор напоминания
    id SERIAL PRIMARY KEY,

-- FOREIGN KEY: Ссылка на пользователя (users.telegram_id)
telegram_id BIGINT NOT NULL REFERENCES users (telegram_id) ON DELETE CASCADE,

-- Название канала, по которому нужно отправить напоминание
channel_name VARCHAR(50) NOT NULL,

-- Флаг отправки напоминания: FALSE = не отправлено, TRUE = отправлено
reminder_sent BOOLEAN DEFAULT FALSE,

-- Дата и время, когда нужно отправить напоминание
reminder_date TIMESTAMP NOT NULL,

-- Уникальный индекс: одно напоминание на пользователя и канал
UNIQUE(telegram_id, channel_name) );

-- =====================================================
-- ИНДЕКСЫ ДЛЯ ОПТИМИЗАЦИИ ЗАПРОСОВ
-- =====================================================

-- Индекс для быстрого поиска активных подписок
CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON subscriptions (
    telegram_id,
    channel_name,
    is_active
)
WHERE
    is_active = TRUE;

-- Индекс для поиска подписок по дате окончания
CREATE INDEX IF NOT EXISTS idx_subscriptions_end_date ON subscriptions (end_date)
WHERE
    is_active = TRUE;

-- Индекс для поиска платежей по статусу
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments (status);

-- Индекс для поиска платежей по пользователю
CREATE INDEX IF NOT EXISTS idx_payments_telegram_id ON payments (telegram_id);

-- Индекс для поиска неотправленных напоминаний
CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders (reminder_date, reminder_sent)
WHERE
    reminder_sent = FALSE;

-- =====================================================
-- КОММЕНТАРИИ К ТАБЛИЦАМ
-- =====================================================

COMMENT ON
TABLE users IS 'Основная информация о пользователях Telegram бота';

COMMENT ON
TABLE subscriptions IS 'Подписки пользователей на каналы (Орден Демиургов, Родители Демиурга)';

COMMENT ON TABLE payments IS 'Записи о платежах через Robokassa';

COMMENT ON
TABLE reminders IS 'Напоминания пользователям об окончании подписки';

-- Комментарии к полям таблицы users
COMMENT ON COLUMN users.telegram_id IS 'Уникальный ID пользователя в Telegram (используется как PRIMARY KEY)';

COMMENT ON COLUMN users.gift_received IS 'Получил ли пользователь подарок из мастер-класса (2 недели бесплатного доступа)';

-- Комментарии к полям таблицы subscriptions
COMMENT ON COLUMN subscriptions.channel_name IS 'Название канала: channel_1 (Орден Демиургов) или channel_2 (Родители Демиурга)';

COMMENT ON COLUMN subscriptions.payment_method IS 'Метод получения подписки: gift (подарок) или paid (оплачено)';

COMMENT ON COLUMN subscriptions.is_active IS 'Активна ли подписка в данный момент';

-- Комментарии к полям таблицы payments
COMMENT ON COLUMN payments.payment_id IS 'Уникальный идентификатор платежа от Robokassa (InvId)';

COMMENT ON COLUMN payments.status IS 'Статус платежа: pending, success, failed';

-- Комментарии к полям таблицы reminders
COMMENT ON COLUMN reminders.reminder_date IS 'Дата и время отправки напоминания (обычно за 3 дня до окончания подписки)';

COMMENT ON COLUMN reminders.reminder_sent IS 'Отправлено ли напоминание пользователю';