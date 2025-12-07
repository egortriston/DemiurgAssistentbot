from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import SUPPORT_LINK, OFFER_LINK

def get_main_menu_keyboard():
    """Main menu keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📖 Канал "Орден Демиургов"', callback_data='channel_1_info')],
        [InlineKeyboardButton(text='👨‍👩‍👧 Канал "Родители Демиурга"', callback_data='channel_2_info')],
        [InlineKeyboardButton(text='Мои подписки', callback_data='my_subscriptions')],
        [InlineKeyboardButton(text='❓ Помощь и поддержка', url=SUPPORT_LINK)],
        [InlineKeyboardButton(text='Юридическая информация', callback_data='legal_info')],
    ])
    return keyboard

def get_payment_keyboard(channel_name: str):
    """Payment keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 Оплатить доступ', callback_data=f'pay_{channel_name}')],
        [InlineKeyboardButton(text='Главное меню', callback_data='main_menu')],
    ])
    return keyboard

def get_reminder_keyboard(channel_name: str):
    """Reminder keyboard (3 days before expiration)"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 Оплатить доступ на месяц (1990 ₽)', callback_data=f'pay_{channel_name}')],
        [InlineKeyboardButton(text='Главное меню', callback_data='main_menu')],
    ])
    return keyboard

def get_expired_keyboard(channel_name: str):
    """Keyboard for expired subscription"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 Оплатить', callback_data=f'pay_{channel_name}')],
    ])
    return keyboard

def get_back_to_main_keyboard():
    """Back to main menu keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='На главную', callback_data='main_menu')],
    ])
    return keyboard

def get_legal_info_keyboard():
    """Legal info keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Договор оферты', url=OFFER_LINK)],
        [InlineKeyboardButton(text='На главную', callback_data='main_menu')],
    ])
    return keyboard

