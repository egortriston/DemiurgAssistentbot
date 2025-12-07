import hashlib
import time
import random
import logging
from urllib.parse import urlencode
from config import (
    ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN,
    ROBOKASSA_CHANNEL_1_PASSWORD_1,
    ROBOKASSA_CHANNEL_1_PASSWORD_2,
    ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN,
    ROBOKASSA_CHANNEL_2_PASSWORD_1,
    ROBOKASSA_CHANNEL_2_PASSWORD_2,
    ROBOKASSA_BASE_URL,
    ROBOKASSA_TEST_MODE
)

logger = logging.getLogger(__name__)

def generate_payment_url(amount: float, description: str, invoice_id: str = None, user_id: int = None, channel_name: str = None) -> str:
    """
    Generate Robokassa payment URL
    
    Args:
        amount: Payment amount in rubles
        description: Payment description
        invoice_id: Unique invoice ID (if None, will be generated)
        user_id: User telegram ID
        channel_name: Channel name ('channel_1' or 'channel_2') to use correct credentials
    
    Returns:
        Payment URL and invoice_id
    """
    # Select credentials based on channel
    if channel_name == "channel_1":
        merchant_login = ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN
        password_1 = ROBOKASSA_CHANNEL_1_PASSWORD_1
    elif channel_name == "channel_2":
        merchant_login = ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN
        password_1 = ROBOKASSA_CHANNEL_2_PASSWORD_1
    else:
        raise ValueError(f"Unknown channel_name: {channel_name}. Must be 'channel_1' or 'channel_2'")
    
    # Validate credentials
    if not merchant_login or not merchant_login.strip():
        raise ValueError(f"MerchantLogin is empty for {channel_name}")
    if not password_1 or not password_1.strip():
        raise ValueError(f"Password1 is empty for {channel_name}")
    
    # Remove any whitespace from credentials
    merchant_login = merchant_login.strip()
    password_1 = password_1.strip()
    
    if invoice_id is None:
        # Generate unique integer ID (Robokassa requires integer from 1 to 9223372036854775807)
        # Using microseconds timestamp + random component to ensure uniqueness
        timestamp_part = int(time.time() * 1000000)
        random_part = random.randint(100, 999)  # 3-digit random component
        invoice_id_int = timestamp_part + random_part
        invoice_id = str(invoice_id_int)
    else:
        invoice_id_int = int(invoice_id)
    
    # Convert amount to format expected by Robokassa (e.g., 1990.00)
    amount_str = f"{amount:.2f}"
    
    # Build URL parameters
    params = {
        'MerchantLogin': merchant_login,
        'OutSum': amount_str,
        'InvId': invoice_id,
        'Description': description,
    }
    
    # Add shp_ parameters if provided (must be in alphabetical order)
    shp_params = {}
    if user_id:
        shp_params['Shp_user_id'] = str(user_id)
    
    # Add shp_ parameters to URL params (sorted alphabetically)
    for key in sorted(shp_params.keys()):
        params[key] = shp_params[key]
    
    # Create signature according to official documentation:
    # Base: MerchantLogin:OutSum:InvId:Password1
    # With shp_: MerchantLogin:OutSum:InvId:Password1:Shp_param1=value1:Shp_param2=value2
    # Use integer InvId in signature
    signature_string = f"{merchant_login}:{amount_str}:{invoice_id_int}:{password_1}"
    
    # Add shp_ parameters to signature in alphabetical order (if any)
    if shp_params:
        sorted_shp = sorted(shp_params.items())
        shp_string = ':'.join([f"{key}={value}" for key, value in sorted_shp])
        signature_string = f"{signature_string}:{shp_string}"
    
    signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest()
    params['SignatureValue'] = signature
    
    if ROBOKASSA_TEST_MODE:
        params['IsTest'] = 1  # Number, not string (as in working example)
    
    # Log signature calculation for debugging
    logger.info(f"[Robokassa] Generating payment URL for channel: {channel_name}")
    logger.info(f"[Robokassa] MerchantLogin: '{merchant_login}' (length: {len(merchant_login)})")
    logger.info(f"[Robokassa] OutSum: '{amount_str}'")
    logger.info(f"[Robokassa] InvId: '{invoice_id}' (int: {invoice_id_int})")
    logger.info(f"[Robokassa] Test mode: {ROBOKASSA_TEST_MODE}")
    if shp_params:
        logger.info(f"[Robokassa] Shp params: {shp_params}")
    else:
        logger.info(f"[Robokassa] No shp_ parameters")
    logger.info(f"[Robokassa] Signature formula: {signature_string.replace(password_1, '***PASSWORD***')}")
    logger.info(f"[Robokassa] Password1 length: {len(password_1)} chars")
    logger.info(f"[Robokassa] Calculated signature: {signature}")
    if not ROBOKASSA_TEST_MODE:
        logger.warning(f"[Robokassa] ⚠️ ПРОДАКШН РЕЖИМ! Убедитесь, что используются РАБОЧИЕ пароли!")
    
    # Build URL
    url = f"{ROBOKASSA_BASE_URL}?{urlencode(params)}"
    
    logger.info(f"[Robokassa] Payment URL generated successfully (InvId: {invoice_id})")
    
    return url, invoice_id

def verify_payment_signature(amount: str, invoice_id: str, signature: str, password: str, shp_params: dict = None) -> bool:
    """
    Verify Robokassa payment signature for ResultURL
    
    According to Robokassa documentation:
    - Signature formula: md5(OutSum:InvId:Password2[:shp_params in alphabetical order])
    - Used for ResultURL (server-to-server notification)
    - Password #2 is used (not Password #1)
    
    Args:
        amount: Payment amount (OutSum parameter from Robokassa)
        invoice_id: Invoice ID (InvId parameter from Robokassa)
        signature: Signature from Robokassa (SignatureValue parameter)
        password: Password #2 for verification
        shp_params: Dictionary of shp_ parameters (e.g., {'Shp_user_id': '123'})
    
    Returns:
        True if signature is valid
    """
    # Formula according to Robokassa docs: OutSum:InvId:Password2[:shp_params in alphabetical order]
    signature_string = f"{amount}:{invoice_id}:{password}"
    
    # Add shp_ parameters to signature in alphabetical order (required by Robokassa)
    if shp_params:
        sorted_shp = sorted(shp_params.items())
        shp_string = ':'.join([f"{key}={value}" for key, value in sorted_shp])
        signature_string = f"{signature_string}:{shp_string}"
    
    calculated_signature = hashlib.md5(signature_string.encode()).hexdigest()
    # Compare case-insensitive as Robokassa may send uppercase signature
    return calculated_signature.lower() == signature.lower()

def get_result_url_signature(amount: str, invoice_id: str, password: str) -> str:
    """
    Generate signature for ResultURL (notification from Robokassa)
    
    Args:
        amount: Payment amount
        invoice_id: Invoice ID
        password: Password #1 (channel-specific)
    
    Returns:
        Signature string
    """
    signature_string = f"{amount}:{invoice_id}:{password}"
    return hashlib.md5(signature_string.encode()).hexdigest()

