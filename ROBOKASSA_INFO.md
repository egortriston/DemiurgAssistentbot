# Что такое Merchant Login в Robokassa?

## Объяснение простыми словами

**Merchant Login** — это **логин вашего магазина** в системе Robokassa. Это строка (обычно слово или комбинация букв/цифр), которую вы получили при регистрации магазина в Robokassa.

## Где его найти?

1. Зайдите в личный кабинет Robokassa: https://auth.robokassa.ru/
2. Войдите в свой аккаунт
3. Перейдите в раздел "Настройки магазина" или "Технические настройки"
4. Там вы увидите **Merchant Login** (может называться "Идентификатор магазина" или "Login")

## Два варианта

### Вариант 1: Один магазин в Robokassa
Если у вас **один магазин** в Robokassa, но разные пароли для разных каналов:
- Используйте **один и тот же Merchant Login** для обоих каналов
- В `.env` файле:
  ```env
  ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN=ваш_логин
  ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN=ваш_логин  # тот же самый
  ```

### Вариант 2: Два разных магазина
Если у вас **два разных магазина** в Robokassa (каждый со своим логином):
- Используйте **разные Merchant Login** для каждого канала
- В `.env` файле:
  ```env
  ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN=логин_для_ордена
  ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN=логин_для_родителей  # другой логин
  ```

## Пример

Предположим, ваш Merchant Login — `my_shop_12345`

Тогда в `.env` файле нужно указать:
```env
ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN=my_shop_12345
ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN=my_shop_12345
```

Или если разные магазины:
```env
ROBOKASSA_CHANNEL_1_MERCHANT_LOGIN=orden_shop
ROBOKASSA_CHANNEL_2_MERCHANT_LOGIN=roditeli_shop
```

## Важно!

После того как вы укажете Merchant Login в `.env` файле, также нужно настроить в личном кабинете Robokassa:

1. **Result URL** — URL, куда Robokassa будет отправлять уведомления об оплате
   - Пример: `https://ваш-домен.com/robokassa/result`
   
2. **Success URL** — URL, куда перейдет пользователь после успешной оплаты
   - Пример: `https://ваш-домен.com/robokassa/success`
   
3. **Fail URL** — URL, куда перейдет пользователь при ошибке оплаты
   - Пример: `https://ваш-домен.com/robokassa/fail`

Эти URL нужно указать в настройках каждого магазина (если у вас два магазина).


