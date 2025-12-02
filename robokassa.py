import hashlib
import uuid
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
    
    if invoice_id is None:
        invoice_id = str(uuid.uuid4())
    
    # Convert amount to format expected by Robokassa (e.g., 1990.00)
    amount_str = f"{amount:.2f}"
    
    # Create signature
    signature_string = f"{merchant_login}:{amount_str}:{invoice_id}:{password_1}"
    signature = hashlib.md5(signature_string.encode()).hexdigest()
    
    # Build URL parameters
    params = {
        'MerchantLogin': merchant_login,
        'OutSum': amount_str,
        'InvId': invoice_id,
        'Description': description,
        'SignatureValue': signature,
    }
    
    if ROBOKASSA_TEST_MODE:
        params['IsTest'] = '1'
    
    if user_id:
        params['Shp_user_id'] = str(user_id)
    
    # Build URL
    url = f"{ROBOKASSA_BASE_URL}?{urlencode(params)}"
    return url, invoice_id

def verify_payment_signature(amount: str, invoice_id: str, signature: str, password: str) -> bool:
    """
    Verify Robokassa payment signature
    
    Args:
        amount: Payment amount
        invoice_id: Invoice ID
        signature: Signature from Robokassa
        password: Password for verification (Password #2)
    
    Returns:
        True if signature is valid
    """
    signature_string = f"{amount}:{invoice_id}:{password}"
    calculated_signature = hashlib.md5(signature_string.encode()).hexdigest()
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

