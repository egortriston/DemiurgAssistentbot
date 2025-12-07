from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from database import db
from keyboards import get_reminder_keyboard, get_expired_keyboard, get_payment_keyboard
from messages import get_reminder_message, get_expired_message
from config import CHANNEL_1_ID, CHANNEL_2_ID, FREE_TRIAL_DAYS
from aiogram import Bot

scheduler = AsyncIOScheduler()

async def check_reminders(bot: Bot):
    """Check and send reminders"""
    reminders = await db.get_pending_reminders()
    
    for reminder in reminders:
        user_id = reminder['telegram_id']
        channel_name = reminder['channel_name']
        
        # Get subscription to get end date
        subscription = await db.get_active_subscription(user_id, channel_name)
        if subscription:
            end_date = datetime.fromisoformat(subscription['end_date'])
            
            # Send reminder
            try:
                await bot.send_message(
                    user_id,
                    get_reminder_message(end_date),
                    reply_markup=get_reminder_keyboard(channel_name)
                )
                await db.mark_reminder_sent(user_id, channel_name)
            except Exception as e:
                print(f"Error sending reminder to {user_id}: {e}")

async def check_expired_subscriptions(bot: Bot):
    """Check and deactivate expired subscriptions"""
    print(f"[SCHEDULER] Checking expired subscriptions at {datetime.now()}")
    expired = await db.get_expired_subscriptions()
    
    if not expired:
        print("[SCHEDULER] No expired subscriptions found")
        return  # Нет истекших подписок
    
    print(f"[SCHEDULER] Found {len(expired)} expired subscriptions")
    
    for subscription in expired:
        user_id = subscription['telegram_id']
        channel_name = subscription['channel_name']
        end_date = subscription['end_date']
        
        # Проверяем, что подписка действительно истекла
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        elif hasattr(end_date, 'replace'):
            # Если это datetime с timezone, конвертируем в naive
            end_date = end_date.replace(tzinfo=None)
        
        now = datetime.now()
        if end_date > now:
            print(f"[SCHEDULER] Skipping user {user_id}: end_date {end_date} > now {now}")
            continue  # Пропускаем, если еще не истекла
        
        print(f"[SCHEDULER] Processing expired subscription: user {user_id}, channel {channel_name}, ended: {end_date}")
        
        # Deactivate subscription
        try:
            await db.deactivate_subscription(user_id, channel_name)
            print(f"[SCHEDULER] Deactivated subscription for user {user_id}")
        except Exception as e:
            print(f"[SCHEDULER] Error deactivating subscription for user {user_id}: {e}")
            continue
        
        # Check if user is whitelisted - don't ban whitelisted users
        is_whitelisted = await db.is_whitelisted(user_id, channel_name)
        if is_whitelisted:
            print(f"[SCHEDULER] ⚠️ User {user_id} is whitelisted for {channel_name}, skipping ban")
        else:
            # Remove from channel (ban user)
            try:
                if channel_name == "channel_1":
                    await bot.ban_chat_member(chat_id=CHANNEL_1_ID, user_id=user_id)
                    print(f"[SCHEDULER] ✅ Banned user {user_id} from channel_1")
                elif channel_name == "channel_2":
                    await bot.ban_chat_member(chat_id=CHANNEL_2_ID, user_id=user_id)
                    print(f"[SCHEDULER] ✅ Banned user {user_id} from channel_2")
                else:
                    print(f"[SCHEDULER] Unknown channel_name: {channel_name}")
            except Exception as e:
                print(f"[SCHEDULER] ❌ Error banning user {user_id} from channel {channel_name}: {e}")
                # Продолжаем обработку, даже если не удалось забанить
        
        # Send expiration message
        try:
            await bot.send_message(
                user_id,
                get_expired_message(),
                reply_markup=get_expired_keyboard(channel_name)
            )
            print(f"[SCHEDULER] Sent expiration message to user {user_id}")
        except Exception as e:
            print(f"[SCHEDULER] Error sending expiration message to {user_id}: {e}")

async def check_unauthorized_members(bot: Bot):
    """Check all channel members and kick those without active subscriptions (unless whitelisted)"""
    print(f"[SCHEDULER] Checking unauthorized members at {datetime.now()}")
    
    channels = [
        ("channel_1", CHANNEL_1_ID),
        ("channel_2", CHANNEL_2_ID)
    ]
    
    for channel_name, channel_id in channels:
        try:
            # Get all administrators (they should be whitelisted separately if needed)
            admins = await bot.get_chat_administrators(chat_id=channel_id)
            admin_ids = {admin.user.id for admin in admins}
            
            # Get all active subscriptions for this channel
            # We'll check each subscription individually
            print(f"[SCHEDULER] Checking channel {channel_name} ({channel_id})")
            
            # Note: Telegram API doesn't provide a direct way to get all members
            # This function should be called manually via admin command or
            # we can check members when they interact with the bot
            # For now, we'll rely on the expired subscription check
            
        except Exception as e:
            print(f"[SCHEDULER] Error checking channel {channel_name}: {e}")

async def kick_unauthorized_user(bot: Bot, user_id: int, channel_name: str, channel_id: str):
    """
    Kick a user from channel if they don't have active subscription and aren't whitelisted
    Returns True if user was kicked, False if they should stay
    """
    # Check if user has active subscription
    active_sub = await db.get_active_subscription(user_id, channel_name)
    if active_sub:
        return False  # User has active subscription, don't kick
    
    # Check if user is whitelisted
    is_whitelisted = await db.is_whitelisted(user_id, channel_name)
    if is_whitelisted:
        print(f"[SCHEDULER] User {user_id} is whitelisted for {channel_name}, not kicking")
        return False  # User is whitelisted, don't kick
    
    # User has no subscription and isn't whitelisted - kick them
    try:
        await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
        print(f"[SCHEDULER] ✅ Kicked unauthorized user {user_id} from {channel_name}")
        return True
    except Exception as e:
        print(f"[SCHEDULER] ❌ Error kicking user {user_id} from {channel_name}: {e}")
        return False

def setup_scheduler(bot: Bot):
    """Setup scheduled tasks"""
    # Check reminders every hour
    scheduler.add_job(
        check_reminders,
        trigger=IntervalTrigger(hours=1),
        args=[bot],
        id='check_reminders',
        replace_existing=True
    )
    
    # Check expired subscriptions every hour (для более точной проверки истечения)
    scheduler.add_job(
        check_expired_subscriptions,
        trigger=IntervalTrigger(hours=1),
        args=[bot],
        id='check_expired',
        replace_existing=True
    )
    
    scheduler.start()
    print("[SCHEDULER] Планировщик запущен. Проверка истекших подписок будет выполняться каждый час.")

