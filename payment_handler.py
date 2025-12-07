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
import logging

logger = logging.getLogger(__name__)

async def robokassa_result_handler(request):
    """Handle Robokassa ResultURL (notification) - supports both GET and POST"""
    bot = request.app['bot']
    
    logger.info(f"[Robokassa Result] Received callback request, method: {request.method}")
    logger.info(f"[Robokassa Result] Headers: {dict(request.headers)}")
    
    # Get parameters from request (support both GET and POST)
    if request.method == 'POST':
        data = await request.post()
    else:
        data = request.query
    logger.info(f"[Robokassa Result] Data: {dict(data)}")
    
    OutSum = data.get('OutSum', '')
    InvId = data.get('InvId', '')
    SignatureValue = data.get('SignatureValue', '')
    
    logger.info(f"[Robokassa Result] OutSum={OutSum}, InvId={InvId}, Signature={SignatureValue}")
    
    if not all([OutSum, InvId, SignatureValue]):
        logger.error(f"[Robokassa Result] Missing parameters!")
        return web.Response(text="ERROR: Missing parameters")
    
    # Extract all shp_ parameters (must be in alphabetical order for signature)
    shp_params = {}
    for key, value in data.items():
        if key.startswith('Shp_'):
            shp_params[key] = value
    logger.info(f"[Robokassa Result] Shp params: {shp_params}")
    
    # Get payment record to determine channel
    payment = await db.get_payment(InvId)
    if not payment:
        logger.error(f"[Robokassa Result] Payment not found for InvId={InvId}")
        return web.Response(text="ERROR: Payment not found")
    
    logger.info(f"[Robokassa Result] Found payment: {payment}")
    
    # Verify payment amount matches (security check)
    expected_amount = float(payment['amount'])
    received_amount = float(OutSum)
    if abs(expected_amount - received_amount) > 0.01:  # Allow small floating point differences
        logger.error(f"[Robokassa Result] Amount mismatch! Expected {expected_amount}, received {received_amount}")
        return web.Response(text="ERROR: Amount mismatch")
    
    # Select correct password based on channel
    channel_name = payment['channel_name']
    if channel_name == "channel_1":
        password_2 = ROBOKASSA_CHANNEL_1_PASSWORD_2
    elif channel_name == "channel_2":
        password_2 = ROBOKASSA_CHANNEL_2_PASSWORD_2
    else:
        logger.error(f"[Robokassa Result] Unknown channel: {channel_name}")
        return web.Response(text="ERROR: Unknown channel")
    
    # Verify signature with channel-specific password and shp_ parameters
    if not verify_payment_signature(OutSum, InvId, SignatureValue, password_2, shp_params):
        logger.error(f"[Robokassa Result] Invalid signature! Expected password2 for {channel_name}")
        return web.Response(text="ERROR: Invalid signature")
    
    
    # Check if already processed
    if payment['status'] == 'success':
        logger.info(f"[Robokassa Result] Payment already processed, returning OK{InvId}")
        return web.Response(text=f"OK{InvId}")
    
    # Process payment success FIRST (before updating status)
    # This way if processing fails, we can retry later
    user_id = payment['telegram_id']
    
    try:
        await process_payment_success(user_id, channel_name, bot)
        logger.info(f"[Robokassa Result] Payment processed successfully for user {user_id}")
        
        # Only update status to success AFTER successful processing
        await db.update_payment_status(InvId, 'success')
    except Exception as e:
        logger.error(f"[Robokassa Result] Error processing payment: {e}")
        # Don't update status to success if processing failed
        # Robokassa will retry the callback
        return web.Response(text="ERROR: Processing failed")
    
    logger.info(f"[Robokassa Result] Returning OK{InvId}")
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
    # Support both GET and POST for ResultURL (Robokassa can use either)
    app.router.add_post('/robokassa/result', robokassa_result_handler)
    app.router.add_get('/robokassa/result', robokassa_result_handler)
    app.router.add_get('/robokassa/success', robokassa_success_handler)
    app.router.add_get('/robokassa/fail', robokassa_fail_handler)

