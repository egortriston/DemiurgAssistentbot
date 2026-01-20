from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
from database import db
from keyboards import get_reminder_keyboard, get_expired_keyboard, get_payment_keyboard
from messages import get_reminder_message, get_expired_message, get_subscription_ended_message
from config import CHANNEL_1_ID, CHANNEL_2_ID, FREE_TRIAL_DAYS
from aiogram import Bot
import logging

logger = logging.getLogger(__name__)
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
            end_date = subscription['end_date']
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date)
            
            # Send reminder
            try:
                await bot.send_message(
                    user_id,
                    get_reminder_message(end_date),
                    reply_markup=get_reminder_keyboard(channel_name)
                )
                await db.mark_reminder_sent(user_id, channel_name)
            except Exception as e:
                logger.error(f"Error sending reminder to {user_id}: {e}")

async def check_expired_subscriptions(bot: Bot):
    """Check and deactivate expired subscriptions"""
    logger.info(f"[SCHEDULER] Checking expired subscriptions at {datetime.now()}")
    expired = await db.get_expired_subscriptions()
    
    if not expired:
        logger.info("[SCHEDULER] No expired subscriptions found")
        return  # Нет истекших подписок
    
    logger.info(f"[SCHEDULER] Found {len(expired)} expired subscriptions")
    
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
            logger.info(f"[SCHEDULER] Skipping user {user_id}: end_date {end_date} > now {now}")
            continue  # Пропускаем, если еще не истекла
        
        logger.info(f"[SCHEDULER] Processing expired subscription: user {user_id}, channel {channel_name}, ended: {end_date}")
        
        # Deactivate subscription
        try:
            await db.deactivate_subscription(user_id, channel_name)
            logger.info(f"[SCHEDULER] Deactivated subscription for user {user_id}")
        except Exception as e:
            logger.error(f"[SCHEDULER] Error deactivating subscription for user {user_id}: {e}")
            continue
        
        # Check if user is whitelisted - don't ban whitelisted users
        is_whitelisted = await db.is_whitelisted(user_id, channel_name)
        if is_whitelisted:
            logger.info(f"[SCHEDULER] User {user_id} is whitelisted for {channel_name}, skipping ban")
            await db.set_user_banned(user_id, channel_name, False)
        else:
            # Remove from channel (ban user)
            channel_id = CHANNEL_1_ID if channel_name == "channel_1" else CHANNEL_2_ID
            try:
                await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
                await db.set_user_banned(user_id, channel_name, True)
                logger.info(f"[SCHEDULER] Banned user {user_id} from {channel_name}")
                
                # Send subscription ended message
                try:
                    await bot.send_message(
                        user_id,
                        get_subscription_ended_message(channel_name),
                        reply_markup=get_expired_keyboard(channel_name)
                    )
                    logger.info(f"[SCHEDULER] Sent subscription ended message to user {user_id}")
                except Exception as e:
                    logger.error(f"[SCHEDULER] Error sending message to {user_id}: {e}")
                    
            except Exception as e:
                logger.error(f"[SCHEDULER] Error banning user {user_id} from {channel_name}: {e}")
                # Still mark as banned in DB for tracking
                await db.set_user_banned(user_id, channel_name, True)

async def verify_all_subscriptions_on_startup(bot: Bot):
    """
    Verify all users on bot startup.
    Ban users who don't have active subscriptions and aren't whitelisted.
    Send them a message that their subscription has ended.
    """
    logger.info("[STARTUP] Starting subscription verification...")
    
    users_to_verify = await db.get_all_users_for_verification()
    logger.info(f"[STARTUP] Found {len(users_to_verify)} user-channel combinations to verify")
    
    banned_count = 0
    skipped_count = 0
    already_ok_count = 0
    
    for user_data in users_to_verify:
        user_id = user_data['telegram_id']
        channel_name = user_data['channel_name']
        is_active = user_data['is_active']
        is_whitelisted = user_data['is_whitelisted']
        is_currently_banned = user_data['is_banned']
        end_date = user_data['end_date']
        
        # Parse end_date if needed
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        elif hasattr(end_date, 'replace') and end_date.tzinfo:
            end_date = end_date.replace(tzinfo=None)
        
        now = datetime.now()
        subscription_valid = is_active and end_date and end_date > now
        
        # Determine if user should be in channel
        should_be_in_channel = subscription_valid or is_whitelisted
        
        if should_be_in_channel:
            # User should be in channel - mark as not banned
            if is_currently_banned:
                await db.set_user_banned(user_id, channel_name, False)
                logger.info(f"[STARTUP] User {user_id} marked as not banned for {channel_name} (subscription valid or whitelisted)")
            already_ok_count += 1
            continue
        
        # User should NOT be in channel
        if is_currently_banned:
            # Already banned, skip
            skipped_count += 1
            continue
        
        # Need to ban this user
        channel_id = CHANNEL_1_ID if channel_name == "channel_1" else CHANNEL_2_ID
        
        try:
            await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
            await db.set_user_banned(user_id, channel_name, True)
            banned_count += 1
            logger.info(f"[STARTUP] Banned user {user_id} from {channel_name} (no active subscription)")
            
            # Send message to user
            try:
                await bot.send_message(
                    user_id,
                    get_subscription_ended_message(channel_name),
                    reply_markup=get_expired_keyboard(channel_name)
                )
            except Exception as e:
                logger.warning(f"[STARTUP] Could not send message to user {user_id}: {e}")
                
        except Exception as e:
            logger.error(f"[STARTUP] Error banning user {user_id} from {channel_name}: {e}")
            # Still mark as banned in DB for tracking
            await db.set_user_banned(user_id, channel_name, True)
    
    logger.info(f"[STARTUP] Verification complete: {banned_count} banned, {skipped_count} already banned, {already_ok_count} OK")


async def check_unauthorized_members(bot: Bot):
    """Check all channel members and kick those without active subscriptions (unless whitelisted)"""
    logger.info(f"[SCHEDULER] Checking unauthorized members at {datetime.now()}")
    
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
            logger.info(f"[SCHEDULER] Checking channel {channel_name} ({channel_id})")
            
            # Note: Telegram API doesn't provide a direct way to get all members
            # This function should be called manually via admin command or
            # we can check members when they interact with the bot
            # For now, we'll rely on the expired subscription check
            
        except Exception as e:
            logger.error(f"[SCHEDULER] Error checking channel {channel_name}: {e}")

async def kick_unauthorized_user(bot: Bot, user_id: int, channel_name: str, channel_id: str):
    """
    Kick a user from channel if they don't have active subscription and aren't whitelisted
    Returns True if user was kicked, False if they should stay
    """
    # Check if user has active subscription
    active_sub = await db.get_active_subscription(user_id, channel_name)
    if active_sub:
        await db.set_user_banned(user_id, channel_name, False)
        return False  # User has active subscription, don't kick
    
    # Check if user is whitelisted
    is_whitelisted = await db.is_whitelisted(user_id, channel_name)
    if is_whitelisted:
        logger.info(f"[SCHEDULER] User {user_id} is whitelisted for {channel_name}, not kicking")
        await db.set_user_banned(user_id, channel_name, False)
        return False  # User is whitelisted, don't kick
    
    # User has no subscription and isn't whitelisted - kick them
    try:
        await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
        await db.set_user_banned(user_id, channel_name, True)
        logger.info(f"[SCHEDULER] Kicked unauthorized user {user_id} from {channel_name}")
        return True
    except Exception as e:
        logger.error(f"[SCHEDULER] Error kicking user {user_id} from {channel_name}: {e}")
        await db.set_user_banned(user_id, channel_name, True)  # Still track as banned
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
    logger.info("[SCHEDULER] Scheduler started. Expired subscription check runs every hour.")

