"""
Скрипт для тестирования генерации подписи Robokassa
Помогает проверить правильность формулы подписи
"""

import hashlib
from config import (
    ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN,
    ROBOKASSA_CHANNEL_1_PASSWORD_1,
    ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN,
    ROBOKASSA_CHANNEL_2_PASSWORD_1,
    ROBOKASSA_TEST_MODE
)

def test_signature_calculation():
    """Тестирование расчета подписи"""
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ГЕНЕРАЦИИ ПОДПИСИ ROBOKASSA")
    print("=" * 60)
    
    # Тестовые данные
    test_cases = [
        {
            "channel": "channel_1",
            "merchant_login": ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN,
            "password_1": ROBOKASSA_CHANNEL_1_PASSWORD_1,
            "amount": 1990.00,
            "invoice_id": "1234567890",
            "user_id": 5882350650
        },
        {
            "channel": "channel_2",
            "merchant_login": ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN,
            "password_1": ROBOKASSA_CHANNEL_2_PASSWORD_1,
            "amount": 1990.00,
            "invoice_id": "1234567890",
            "user_id": 5882350650
        }
    ]
    
    for test in test_cases:
        print(f"\n{'=' * 60}")
        print(f"ТЕСТ: {test['channel']}")
        print(f"{'=' * 60}")
        
        merchant_login = test['merchant_login']
        password_1 = test['password_1']
        amount_str = f"{test['amount']:.2f}"
        invoice_id = str(test['invoice_id'])
        user_id = test['user_id']
        
        # Проверка на пустые значения
        if not merchant_login or not merchant_login.strip():
            print(f"❌ ERROR: MerchantLogin пустой!")
            continue
        if not password_1 or not password_1.strip():
            print(f"❌ ERROR: Password1 пустой!")
            continue
        
        merchant_login = merchant_login.strip()
        password_1 = password_1.strip()
        
        print(f"MerchantLogin: '{merchant_login}' (длина: {len(merchant_login)})")
        print(f"OutSum: '{amount_str}'")
        print(f"InvId: '{invoice_id}'")
        print(f"Test mode: {ROBOKASSA_TEST_MODE}")
        print(f"Password1: {'*' * len(password_1)} (длина: {len(password_1)})")
        
        # Формула без shp_
        signature_string_basic = f"{merchant_login}:{amount_str}:{invoice_id}:{password_1}"
        signature_basic = hashlib.md5(signature_string_basic.encode('utf-8')).hexdigest()
        
        print(f"\n📝 Формула БЕЗ shp_ параметров:")
        print(f"   {signature_string_basic.replace(password_1, '***PASSWORD***')}")
        print(f"   Signature: {signature_basic}")
        
        # Формула с shp_
        shp_params = {'Shp_user_id': str(user_id)}
        sorted_shp = sorted(shp_params.items())
        shp_string = ':'.join([f"{key}={value}" for key, value in sorted_shp])
        signature_string_with_shp = f"{merchant_login}:{amount_str}:{invoice_id}:{password_1}:{shp_string}"
        signature_with_shp = hashlib.md5(signature_string_with_shp.encode('utf-8')).hexdigest()
        
        print(f"\n📝 Формула С shp_ параметрами:")
        print(f"   {signature_string_with_shp.replace(password_1, '***PASSWORD***')}")
        print(f"   Signature: {signature_with_shp}")
        
        print(f"\n✅ Используется формула С shp_ (так как передается user_id)")
        print(f"   Финальная подпись: {signature_with_shp}")
        
        # Проверка на возможные проблемы
        issues = []
        if len(password_1) < 10:
            issues.append(f"⚠️  Password1 слишком короткий ({len(password_1)} символов)")
        if ' ' in password_1:
            issues.append("⚠️  Password1 содержит пробелы (убедитесь, что они нужны)")
        if ROBOKASSA_TEST_MODE and len(password_1) > 20:
            issues.append("⚠️  В тестовом режиме используйте тестовые пароли")
        if not ROBOKASSA_TEST_MODE and len(password_1) < 15:
            issues.append("⚠️  В продакшн режиме используйте рабочие пароли")
        
        if issues:
            print(f"\n⚠️  ВОЗМОЖНЫЕ ПРОБЛЕМЫ:")
            for issue in issues:
                print(f"   {issue}")
        else:
            print(f"\n✅ Параметры выглядят корректно")

if __name__ == "__main__":
    test_signature_calculation()

