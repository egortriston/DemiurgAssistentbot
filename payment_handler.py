from aiohttp import web
from database import db
from robokassa import verify_payment_signature
from handlers import process_payment_success
from config import (
    ROBOKASSA_CHANNEL_1_PASSWORD_2,
    ROBOKASSA_CHANNEL_2_PASSWORD_2
)
from aiogram import Bot
import os

async def robokassa_result_handler(request):
    """Handle Robokassa ResultURL (notification)"""
    bot = request.app['bot']
    
    # Get parameters from request
    data = await request.post()
    
    OutSum = data.get('OutSum', '')
    InvId = data.get('InvId', '')
    SignatureValue = data.get('SignatureValue', '')
    
    if not all([OutSum, InvId, SignatureValue]):
        return web.Response(text="ERROR: Missing parameters")
    
    # Extract all shp_ parameters (must be in alphabetical order for signature)
    shp_params = {}
    for key, value in data.items():
        if key.startswith('Shp_'):
            shp_params[key] = value
    
    # Get payment record to determine channel
    payment = await db.get_payment(InvId)
    if not payment:
        return web.Response(text="ERROR: Payment not found")
    
    # Select correct password based on channel
    channel_name = payment['channel_name']
    if channel_name == "channel_1":
        password_2 = ROBOKASSA_CHANNEL_1_PASSWORD_2
    elif channel_name == "channel_2":
        password_2 = ROBOKASSA_CHANNEL_2_PASSWORD_2
    else:
        return web.Response(text="ERROR: Unknown channel")
    
    # Verify signature with channel-specific password and shp_ parameters
    if not verify_payment_signature(OutSum, InvId, SignatureValue, password_2, shp_params):
        return web.Response(text="ERROR: Invalid signature")
    
    
    # Check if already processed
    if payment['status'] == 'success':
        return web.Response(text=f"OK{InvId}")
    
    # Update payment status
    await db.update_payment_status(InvId, 'success')
    
    # Process payment success
    user_id = payment['telegram_id']
    
    try:
        await process_payment_success(user_id, channel_name, bot)
    except Exception as e:
        print(f"Error processing payment: {e}")
    
    return web.Response(text=f"OK{InvId}")

async def robokassa_success_handler(request):
    """Handle Robokassa SuccessURL (user redirect after payment)"""
    # This is just a redirect page, payment is processed via ResultURL
    return web.Response(
        text="<html><body><h1>Оплата успешно обработана!</h1><p>Вы можете закрыть эту страницу и вернуться в бот.</p></body></html>",
        content_type="text/html"
    )

async def robokassa_fail_handler(request):
    """Handle Robokassa FailURL (user redirect if payment failed)"""
    return web.Response(
        text="<html><body><h1>Оплата не была завершена</h1><p>Вы можете закрыть эту страницу и вернуться в бот.</p></body></html>",
        content_type="text/html"
    )

def setup_payment_routes(app: web.Application, bot: Bot):
    """Setup payment webhook routes"""
    app['bot'] = bot
    app.router.add_post('/robokassa/result', robokassa_result_handler)
    app.router.add_get('/robokassa/success', robokassa_success_handler)
    app.router.add_get('/robokassa/fail', robokassa_fail_handler)

