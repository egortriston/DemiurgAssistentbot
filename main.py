import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiohttp import web
from config import BOT_TOKEN
from database import db
from handlers import router
from scheduler import setup_scheduler
from payment_handler import setup_payment_routes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    """
    ИНИЦИАЛИЗАЦИЯ ПРИ ЗАПУСКЕ БОТА
    
    ПОДКЛЮЧЕНИЕ К БД:
    -----------------
    Здесь происходит первичное подключение к PostgreSQL через метод db.init_db().
    Метод создает пул соединений (connection pool) с параметрами:
    - min_size=5: минимум 5 соединений в пуле
    - max_size=20: максимум 20 соединений в пуле
    
    Пул соединений позволяет эффективно переиспользовать соединения к БД,
    избегая создания нового соединения для каждого запроса.
    """
    await db.init_db()
    logger.info("Database initialized and connection pool created")
    
    setup_scheduler(bot)
    logger.info("Scheduler started")
    
    # Выполняем немедленную проверку истекших подписок при запуске
    from scheduler import check_expired_subscriptions
    logger.info("Performing initial check of expired subscriptions...")
    await check_expired_subscriptions(bot)
    logger.info("Initial check completed")

async def main():
    """Main function"""
    try:
        # Initialize bot and dispatcher
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        
        # Register handlers
        dp.include_router(router)
        
        # Enable chat_member updates to detect when users join channels
        # This is required for the whitelist/kick functionality
        
        # Setup payment webhook server
        app = web.Application()
        setup_payment_routes(app, bot)
        
        # Start webhook server for payment callbacks
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        logger.info("Payment webhook server started on port 8080")
        
        # Startup
        await on_startup(bot)
        
        # Start polling
        logger.info("Bot started")
        await dp.start_polling(bot)
    finally:
        # Закрываем пул соединений при завершении работы
        await db.close()
        logger.info("Database connection pool closed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")

