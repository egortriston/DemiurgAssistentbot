from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime, timedelta
from typing import Optional
from database import db
from keyboards import (
    get_main_menu_keyboard, get_payment_keyboard, get_reminder_keyboard,
    get_expired_keyboard, get_back_to_main_keyboard, get_legal_info_keyboard
)
from messages import (
    get_start_message, get_channel_1_info_message, get_channel_2_info_message,
    get_subscriptions_message, get_legal_info_message, get_gift_welcome_message,
    get_reminder_message, get_expired_message, get_payment_success_message,
    get_payment_success_with_bonus_message
)
from robokassa import generate_payment_url
from config import (
    CHANNEL_1_ID, CHANNEL_2_ID, CHANNEL_1_PRICE, CHANNEL_2_PRICE,
    FREE_TRIAL_DAYS, PAID_SUBSCRIPTION_DAYS, ADMIN_IDS
)
from aiogram import Bot

router = Router()

async def add_user_to_channel(bot: Bot, user_id: int, channel_id: str):
    """Add user to channel"""
    try:
        # Разбаниваем пользователя (если был забанен) - это позволяет ему присоединиться
        await bot.unban_chat_member(chat_id=channel_id, user_id=user_id, only_if_banned=False)
        
        # Для приватных каналов создаем одноразовую ссылку-приглашение
        try:
            invite_link = await bot.create_chat_invite_link(
                chat_id=channel_id,
                member_limit=1,  # Одноразовая ссылка
                creates_join_request=False
            )
            # Отправляем ссылку пользователю для автоматического присоединения
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"🔗 Присоединяйтесь к каналу по ссылке:\n{invite_link.invite_link}"
                )
            except:
                # Если не удалось отправить сообщение, ссылка все равно создана
                pass
        except Exception as e:
            # Если не удалось создать ссылку (например, нет прав), просто разбаниваем
            print(f"Note: Could not create invite link for {user_id}: {e}")
    except Exception as e:
        print(f"Error adding user to channel {channel_id}: {e}")

async def remove_user_from_channel(bot: Bot, user_id: int, channel_id: str):
    """Remove user from channel"""
    try:
        await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
    except Exception as e:
        print(f"Error removing user from channel: {e}")

@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    """Handle /start command"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # Add user to database (если еще не добавлен)
    await db.add_user(user_id, username, first_name, last_name)
    
    # Показываем главное меню (подарок отправляется ТОЛЬКО через /import_users)
    await message.answer(
        get_start_message(),
        reply_markup=get_main_menu_keyboard()
    )

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery):
    """Handle main menu callback"""
    await callback.message.edit_text(
        get_start_message(),
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "channel_1_info")
async def callback_channel_1_info(callback: CallbackQuery):
    """Handle channel 1 info callback"""
    await callback.message.edit_text(
        get_channel_1_info_message(),
        reply_markup=get_payment_keyboard("channel_1")
    )
    await callback.answer()

@router.callback_query(F.data == "channel_2_info")
async def callback_channel_2_info(callback: CallbackQuery):
    """Handle channel 2 info callback"""
    await callback.message.edit_text(
        get_channel_2_info_message(),
        reply_markup=get_payment_keyboard("channel_2")
    )
    await callback.answer()

@router.callback_query(F.data == "my_subscriptions")
async def callback_my_subscriptions(callback: CallbackQuery):
    """Handle my subscriptions callback"""
    user_id = callback.from_user.id
    subscriptions = await db.get_user_subscriptions(user_id)
    
    await callback.message.edit_text(
        get_subscriptions_message(subscriptions),
        reply_markup=get_back_to_main_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "legal_info")
async def callback_legal_info(callback: CallbackQuery):
    """Handle legal info callback"""
    await callback.message.edit_text(
        get_legal_info_message(),
        reply_markup=get_legal_info_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def callback_payment(callback: CallbackQuery, bot: Bot):
    """Handle payment callback"""
    user_id = callback.from_user.id
    # Extract channel_name from "pay_channel_1" or "pay_channel_2"
    channel_name = callback.data.replace("pay_", "")  # channel_1 or channel_2
    
    # Determine price and description
    if channel_name == "channel_1":
        amount = CHANNEL_1_PRICE
        description = "Орден Демиургов - 1 месяц"
    else:
        amount = CHANNEL_2_PRICE
        description = "Родители Демиурги - 1 месяц"
    
    # Generate payment URL with channel-specific credentials
    payment_url, invoice_id = generate_payment_url(amount, description, user_id=user_id, channel_name=channel_name)
    
    # Create payment record
    await db.create_payment(user_id, channel_name, amount, invoice_id, "pending")
    
    # Send payment button directly (according to TZ: button immediately redirects to payment)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
        [InlineKeyboardButton(text="На главную", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(
        f"{description}\nСумма: {amount} ₽",
        reply_markup=payment_keyboard
    )
    await callback.answer()

async def process_payment_success(user_id: int, channel_name: str, bot: Bot):
    """Process successful payment"""
    # Determine price and period
    if channel_name == "channel_1":
        amount = CHANNEL_1_PRICE
        channel_id = CHANNEL_1_ID
    else:
        amount = CHANNEL_2_PRICE
        channel_id = CHANNEL_2_ID
    
    start_date = datetime.now()
    end_date = start_date + timedelta(days=PAID_SUBSCRIPTION_DAYS)
    
    # Create subscription
    await db.create_subscription(
        user_id, channel_name, "paid", start_date, end_date, is_active=True
    )
    
    # Add user to channel
    await add_user_to_channel(bot, user_id, channel_id)
    
    # Create invite link for the paid channel
    try:
        invite_link = await bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,  # Single-use invite
            name=f"Payment {user_id}"
        )
        channel_invite_url = invite_link.invite_link
    except Exception as e:
        logger.error(f"Failed to create invite link for channel {channel_id}: {e}")
        channel_invite_url = None
    
    # Special case: if user paid for channel_2 and never had channel_1, give bonus
    if channel_name == "channel_2":
        has_ever_had_channel_1 = await db.has_ever_had_subscription(user_id, "channel_1")
        if not has_ever_had_channel_1:
            # Give bonus gift
            bonus_start = datetime.now()
            bonus_end = bonus_start + timedelta(days=FREE_TRIAL_DAYS)
            await db.create_subscription(
                user_id, "channel_1", "gift", bonus_start, bonus_end, is_active=True
            )
            await add_user_to_channel(bot, user_id, CHANNEL_1_ID)
            
            # Create invite link for bonus channel
            try:
                bonus_invite = await bot.create_chat_invite_link(
                    chat_id=CHANNEL_1_ID,
                    member_limit=1,
                    name=f"Bonus {user_id}"
                )
                bonus_invite_url = bonus_invite.invite_link
            except Exception as e:
                logger.error(f"Failed to create bonus invite link: {e}")
                bonus_invite_url = None
            
            # Send message with bonus and invite links
            await bot.send_message(
                user_id,
                get_payment_success_with_bonus_message(
                    start_date, end_date, bonus_start, bonus_end,
                    channel_invite_url, bonus_invite_url
                ),
                reply_markup=get_back_to_main_keyboard()
            )
            return
    
    # Regular payment success message with invite link
    await bot.send_message(
        user_id,
        get_payment_success_message(channel_name, start_date, end_date, channel_invite_url),
        reply_markup=get_back_to_main_keyboard()
    )

# Admin handlers
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Admin panel entry point"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к админ-панели.")
        return
    
    await message.answer(
        "Админ-панель\n\n"
        "Доступные команды:\n"
        "/import_users - Импорт пользователей из мастер-класса\n"
        "Формат: /import_users 123456789 @username1 @username2\n"
        "Можно использовать telegram_id или @username\n\n"
        "/check_expired - Проверить истекшие подписки (ручная проверка)"
    )

async def resolve_user_identifier(bot: Bot, identifier: str) -> Optional[int]:
    """
    Разрешить идентификатор пользователя (ID или @username) в telegram_id
    
    Args:
        bot: Экземпляр бота
        identifier: telegram_id (число) или @username (строка)
    
    Returns:
        telegram_id или None, если не удалось разрешить
    
    Примечание: Для получения telegram_id по username требуется, чтобы:
    - Пользователь хотя бы раз писал боту (/start)
    - ИЛИ пользователь находится в общем чате/канале с ботом
    - ИЛИ бот является администратором канала, где находится пользователь
    """
    # Если это число, возвращаем как есть
    if identifier.isdigit():
        return int(identifier)
    
    # Если это username (начинается с @), убираем @
    if identifier.startswith('@'):
        username = identifier[1:]
    else:
        username = identifier
    
    # Пробуем разные варианты получения информации о пользователе
    variants = [
        f"@{username}",  # С @
        username,        # Без @
    ]
    
    for variant in variants:
        try:
            # Пытаемся получить информацию о пользователе по username
            # Это работает только если:
            # - Пользователь хотя бы раз писал боту (/start)
            # - ИЛИ пользователь находится в общем чате/канале с ботом
            chat = await bot.get_chat(variant)
            if hasattr(chat, 'id'):
                return chat.id
        except Exception:
            continue
    
    # Если не удалось, значит пользователь не взаимодействовал с ботом
    print(f"Не удалось разрешить username {identifier}: пользователь не найден или не взаимодействовал с ботом")
    return None

@router.message(Command("import_users"))
async def cmd_import_users(message: Message, bot: Bot):
    """Import users from masterclass"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return
    
    # Parse user identifiers from command (ID или @username)
    parts = message.text.split()[1:]
    if not parts:
        await message.answer("Укажите telegram_id или @username пользователей через пробел.\nПример: /import_users 123456789 @username1 @username2")
        return
    
    # Разрешаем все идентификаторы в telegram_id
    telegram_ids = []
    unresolved = []
    
    for identifier in parts:
        user_id = await resolve_user_identifier(bot, identifier)
        if user_id:
            telegram_ids.append(user_id)
        else:
            unresolved.append(identifier)
    
    if unresolved:
        unresolved_str = ', '.join(unresolved)
        warning_msg = (
            f"⚠️ Не удалось найти пользователей: {unresolved_str}\n\n"
            f"📋 Ограничение Telegram Bot API:\n"
            f"Для импорта по username (@username) требуется, чтобы пользователь:\n"
            f"• Хотя бы раз написал боту /start\n"
            f"• ИЛИ находится в общем канале/чате, где есть бот\n\n"
            f"💡 Решение:\n"
            f"• Используйте telegram_id для новых пользователей\n"
            f"• ID можно узнать через @userinfobot или Telegram Desktop\n"
            f"• После того как пользователь напишет /start, можно использовать @username"
        )
        await message.answer(warning_msg)
        if not telegram_ids:
            return
    
    # Import users
    users_to_gift = await db.import_users_from_masterclass(telegram_ids)
    
    # Send gift messages to eligible users
    for user_id in users_to_gift:
        start_date = datetime.now()
        end_date = start_date + timedelta(days=FREE_TRIAL_DAYS)
        
        # Create subscription
        await db.create_subscription(
            user_id, "channel_1", "gift", start_date, end_date, is_active=True
        )
        
        # Mark gift as received
        await db.mark_gift_received(user_id)
        
        # Create reminder
        reminder_date = start_date + timedelta(days=FREE_TRIAL_DAYS - 3)
        await db.create_reminder(user_id, "channel_1", reminder_date)
        
        # Добавляем пользователя в канал и создаем ссылку для перехода
        try:
            # Разбаниваем пользователя (если был забанен) - это позволяет ему присоединиться
            await bot.unban_chat_member(chat_id=CHANNEL_1_ID, user_id=user_id, only_if_banned=False)
            
            # Пытаемся получить публичную ссылку на канал или создать приглашение
            channel_link = None
            try:
                # Пытаемся получить информацию о канале
                chat = await bot.get_chat(chat_id=CHANNEL_1_ID)
                # Если есть публичная ссылка (username), используем её
                if chat.username:
                    channel_link = f"https://t.me/{chat.username.lstrip('@')}"
                else:
                    # Если канал приватный, создаем ссылку-приглашение
                    invite_link = await bot.create_chat_invite_link(
                        chat_id=CHANNEL_1_ID,
                        member_limit=1,
                        creates_join_request=False
                    )
                    channel_link = invite_link.invite_link
            except Exception as e:
                # Если не удалось получить ссылку, создаем приглашение
                try:
                    invite_link = await bot.create_chat_invite_link(
                        chat_id=CHANNEL_1_ID,
                        member_limit=1,
                        creates_join_request=False
                    )
                    channel_link = invite_link.invite_link
                except:
                    pass
            
            # Создаем клавиатуру с кнопкой для перехода в канал
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            if channel_link:
                gift_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📖 Перейти в канал «Орден Демиургов»", url=channel_link)],
                    [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
                ])
            else:
                # Если не удалось создать ссылку, используем обычное меню
                gift_keyboard = get_main_menu_keyboard()
            
            # Отправляем сообщение с кнопкой для перехода в канал
            await bot.send_message(
                user_id,
                get_gift_welcome_message(start_date, end_date),
                reply_markup=gift_keyboard
            )
        except Exception as e:
            # Если произошла ошибка, отправляем сообщение без кнопки
            print(f"Error adding user to channel {user_id}: {e}")
            try:
                await bot.send_message(
                    user_id,
                    get_gift_welcome_message(start_date, end_date),
                    reply_markup=get_main_menu_keyboard()
                )
            except Exception as e2:
                print(f"Error sending message to {user_id}: {e2}")
    
    await message.answer(
        f"Импорт завершен.\n"
        f"Всего пользователей: {len(telegram_ids)}\n"
        f"Получили подарок: {len(users_to_gift)}"
    )

@router.message(Command("check_expired"))
async def cmd_check_expired(message: Message, bot: Bot):
    """Проверить истекшие подписки (ручная проверка)"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return
    
    await message.answer("Проверяю истекшие подписки...")
    
    # Импортируем функцию проверки из scheduler
    from scheduler import check_expired_subscriptions
    await check_expired_subscriptions(bot)
    
    await message.answer("✅ Проверка завершена. Результаты в логах.")

