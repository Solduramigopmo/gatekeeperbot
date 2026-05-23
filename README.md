# gatekeeper-bot

Telegram-бот, который продаёт платный доступ в закрытый канал. Оплата принимается через
[CryptoBot (Crypto Pay API)](https://help.crypt.bot/crypto-pay-api) в **USDT** и **TON**.
Подписки продлеваются автоматически, по истечении срока бот сам кикает пользователя
из канала.

## Возможности

- 📲 Меню `/start` с приветственной картинкой и инлайн-кнопками: «Купить подписку»,
  «INFO», «Поддержка», «Моя подписка».
- 💳 Оплата через CryptoBot двумя способами: прямой инвойс или mini-app —
  ссылки на оба варианта подставляются автоматически.
- 🧾 Гибкие тарифы (срок, цена, название) задаются JSON-конфигом в `.env`.
- 🔐 Одноразовые инвайт-ссылки (`member_limit = 1`) на каждую новую подписку —
  ссылка не «утечёт» в чужой чат.
- ⏰ Шедулер: уведомления за **3 дня** и за **сутки** до окончания (значения настраиваются),
  автоматический кик после истечения подписки.
- 🛡 Защита от абуза: глобальный антифлуд + лимит покупок в минуту, HMAC-проверка
  подписи вебхука Crypto Pay, идемпотентная активация платежей.
- 📊 Админ-панель `/admin`: количество пользователей, активных подписок и оплат, выручка
  по валютам, разбивка по тарифам, последние подписки.
- 💰 **Цены меняются прямо из админки** — без редеплоя и без правок `.env`.
  Сохранённые подписки и уже выставленные счета сохраняют старую цену.
- 🐳 Docker, Docker Compose, Alembic-миграции и юнит-тесты в комплекте.

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Создание и настройка ботов](#создание-и-настройка-ботов)
- [Конфигурация](#конфигурация)
- [Запуск](#запуск)
- [Вебхук Crypto Pay](#вебхук-crypto-pay)
- [Архитектура](#архитектура)
- [Команды бота](#команды-бота)
- [База данных и миграции](#база-данных-и-миграции)
- [Тестирование и стиль](#тестирование-и-стиль)
- [Деплой](#деплой) — кратко; подробный гайд в [DEPLOY.md](DEPLOY.md)
- [FAQ и траблшутинг](#faq-и-траблшутинг)
- [Лицензия](#лицензия)

---

## Быстрый старт

```bash
git clone https://github.com/Solduramigopmo/gatekeeperbot.git
cd gatekeeper-bot

cp .env.example .env
$EDITOR .env   # заполни токены и параметры

python -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

alembic upgrade head
python -m bot
```

Через несколько секунд бот ответит на `/start` в Telegram.

## Создание и настройка ботов

1. **Бот Telegram** — у [@BotFather](https://t.me/BotFather) выполни `/newbot`,
   получи `BOT_TOKEN`.
2. **Канал** — создай приватный канал, добавь бота администратором с правом
   «Добавлять подписчиков по ссылке-приглашению». Узнай числовой `chat_id`
   (например, переслав пост из канала в [@userinfobot](https://t.me/userinfobot)).
3. **CryptoBot** — открой [@CryptoBot](https://t.me/CryptoBot), перейди
   `Crypto Pay → My Apps → Create App`. Получи API-токен и положи в
   `CRYPTO_PAY_TOKEN`. Для тестов используй `https://testnet-pay.crypt.bot`
   и [@CryptoTestnetBot](https://t.me/CryptoTestnetBot).
4. **Админы** — узнай свой `user_id` у [@userinfobot](https://t.me/userinfobot)
   и положи в `ADMIN_IDS` (через запятую).

## Конфигурация

Все параметры читаются из переменных окружения (или `.env`). Полный пример
с комментариями — в [`.env.example`](.env.example).

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `CHANNEL_ID` | Числовой ID закрытого канала (отрицательный) |
| `ADMIN_IDS` | ID администраторов через запятую |
| `CRYPTO_PAY_TOKEN` | Токен Crypto Pay |
| `CRYPTO_PAY_BASE_URL` | `https://pay.crypt.bot` (mainnet) или `https://testnet-pay.crypt.bot` |
| `CRYPTO_PAY_ASSETS` | Валюты для оплаты, через запятую (`USDT,TON`) |
| `SUBSCRIPTION_PLANS` | JSON-массив тарифов (см. ниже) |
| `REMINDER_DAYS` | За сколько дней напоминать о продлении (по умолчанию `3,1`) |
| `WEBHOOK_ENABLED` | `true`, если запускаешь HTTP-вебхук Crypto Pay |
| `WEBHOOK_HOST` / `WEBHOOK_PORT` / `WEBHOOK_PATH` | Параметры вебхук-сервера |
| `POLL_INTERVAL_SECONDS` | Период поллинга счетов, если вебхук выключен |
| `WELCOME_IMAGE` | Путь к приветственной картинке (или пусто) |
| `SUPPORT_URL` / `INFO_URL` | Ссылки для соответствующих кнопок (опционально) |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/bot.sqlite3` или `postgresql+asyncpg://...` |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `THROTTLE_BUY_PER_MINUTE` | Лимит покупок в минуту на пользователя |

### Тарифы

```json
[
  {"id": "1m",  "title": "1 месяц",   "days": 30,  "price": "5.00"},
  {"id": "3m",  "title": "3 месяца",  "days": 90,  "price": "13.00"},
  {"id": "6m",  "title": "6 месяцев", "days": 180, "price": "24.00"},
  {"id": "12m", "title": "12 месяцев","days": 365, "price": "42.00"}
]
```

- `id` уникален и стабилен — он сохраняется в каждой оплате, не меняй у
  существующих тарифов.
- `price` — номинальная сумма в выбранной пользователем валюте. По умолчанию
  одно и то же число используется и для USDT, и для TON. Если хочешь
  отдельную цену для TON, перепиши `SubscriptionService._amount_for`.
- `days` добавляются к текущему сроку, если подписка ещё активна (продление
  не «сжигает» оставшиеся дни).

### Тексты и брендинг

Все строки находятся в `src/bot/texts.py` — меняй прямо там, никаких .po
файлов не нужно. Картинку приветствия положи в `assets/welcome.jpg` и
пропиши путь в `WELCOME_IMAGE`.

## Запуск

### Локально

```bash
pip install -e ".[dev]"
alembic upgrade head
python -m bot
```

### Docker Compose

```bash
cp .env.example .env
# впиши секреты, при необходимости — WEBHOOK_*
docker compose up -d --build
docker compose logs -f
```

Том `./data` маппится в контейнер — там лежит SQLite-база и
другие persisted данные.

## Вебхук Crypto Pay

В проде рекомендуем включить вебхук — это быстрее и дешевле, чем поллинг.

1. Подними бот за HTTPS-прокси (Caddy, nginx, Cloudflare Tunnel).
2. Установи в `.env`:
   ```env
   WEBHOOK_ENABLED=true
   WEBHOOK_HOST=0.0.0.0
   WEBHOOK_PORT=8080
   WEBHOOK_PATH=/cryptopay
   ```
3. В @CryptoBot → Crypto Pay → My Apps → Edit App укажи Webhook URL:
   `https://your-domain.tld/cryptopay`. Включи событие `invoice_paid`.

Если вебхук недоступен, бот всё равно работает: фоновое задание раз в
`POLL_INTERVAL_SECONDS` подтягивает статусы счетов через `getInvoices`.

Подпись каждого запроса проверяется через HMAC-SHA256 от SHA-256-хэша
твоего токена. Эндпоинт отвечает `401`, если подпись не сходится, —
никакие данные при этом не обрабатываются.

## Архитектура

```
src/bot/
├── app.py              — bootstrapping: Dispatcher, scheduler, webhook
├── config.py           — pydantic-settings, тарифы, валидация
├── texts.py            — все пользовательские строки
├── logger.py           — structlog
├── database/           — SQLAlchemy 2 async, репозитории, сессии
├── handlers/           — start, subscription, payment, admin, errors
├── keyboards/          — инлайн-клавиатуры + типизированные CallbackData
├── middlewares/        — throttling, DB session injection
├── filters/            — admin filter
├── services/
│   ├── cryptobot.py    — клиент Crypto Pay + проверка подписи
│   ├── channel.py      — инвайт-ссылки и кик из канала
│   └── subscription.py — бизнес-логика покупки/активации/продления
├── scheduler/          — APScheduler: напоминания, кик, поллинг счетов
└── web/                — aiohttp endpoint для вебхука Crypto Pay
```

Поток покупки:

```
user → /start → «Купить» → тариф → валюта
                                  ↓
                  CryptoPay.create_invoice  → invoice_id + pay_url + mini_app_url
                                  ↓
                       Payment(status=pending)
                                  ↓
          ┌──────── webhook ────────┐    ┌──── ручная кнопка «Проверить»
          ↓                         ↓    ↓
        invoice_paid              poll job
                                  ↓
             SubscriptionService.activate_paid_invoice
                                  ↓
              Subscription(expires_at = now + plan.days)
                                  ↓
               одноразовая invite-link → пользователю
```

## Команды бота

| Команда   | Кто видит | Что делает |
|-----------|-----------|------------|
| `/start`  | все       | Приветствие, картинка, главное меню |
| `/admin`  | админы    | Статистика, разбивки, последние подписки, **редактирование цен** |

Остальное — через инлайн-кнопки.

## База данных и миграции

По умолчанию используется SQLite — файл `data/bot.sqlite3`. Для прода
рекомендуется PostgreSQL:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/gatekeeper
```

Применить миграции:

```bash
alembic upgrade head
```

Создать новую ревизию после правки моделей:

```bash
alembic revision --autogenerate -m "add column foo"
alembic upgrade head
```

При первом запуске бот сам создаёт таблицы, если их нет
(`Base.metadata.create_all`). В проде лучше явно гонять `alembic upgrade head`
и убрать `create_tables=True` из `app.py`, если хочешь жёсткий контроль схемы.

## Тестирование и стиль

```bash
make dev         # установить с extras
make test        # pytest + покрытие
make lint        # ruff + mypy
make format      # автоформат + автофикс
```

Покрыты юнит-тестами:

- загрузка и валидация настроек (плюс защита от дубликатов плана),
- репозитории (создание / продление / истечение подписки, агрегаты по оплатам),
- сервис подписок (идемпотентность активации, расширение, реконсиляция expired),
- HMAC-подпись вебхука Crypto Pay,
- ThrottlingMiddleware (антифлуд, квота покупок, обход для админов).

### Изменение цен на лету

Открой `/admin` → «💰 Цены» → выбери тариф → отправь сообщением новое число
(`7.50`, `12`, `0.5` — точку или запятую, без знака валюты). Если хочется
вернуть значение из `.env`, нажми «↩️ Сбросить к дефолту». Бот хранит
переопределение в таблице `price_overrides`; уже оплаченные подписки и
активные счета сохраняют сумму, по которой их купили.

## Деплой

> Полный гайд (DNS, HTTPS, systemd, Docker, бэкапы, обновление) —
> в [DEPLOY.md](DEPLOY.md). Ниже — короткая выжимка.

### systemd

```ini
# /etc/systemd/system/gatekeeper-bot.service
[Unit]
Description=Gatekeeper Telegram Bot
After=network-online.target

[Service]
User=bot
WorkingDirectory=/opt/gatekeeper-bot
EnvironmentFile=/opt/gatekeeper-bot/.env
ExecStart=/opt/gatekeeper-bot/.venv/bin/python -m bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gatekeeper-bot
```

### Docker

`docker compose up -d --build` — собрать и поднять. Том `./data` сохраняет
SQLite-базу между перезапусками.

### Обратный прокси для вебхука

Минимальный фрагмент nginx:

```nginx
location /cryptopay {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## FAQ и траблшутинг

**Бот не может выдать ссылку — пишет «не удалось создать ссылку».**
Проверь, что бот — администратор канала с правом «Добавлять подписчиков по
ссылке-приглашению» и что `CHANNEL_ID` правильный (отрицательный, формат
`-100…`).

**Оплата прошла, но подписка не активируется.**
Если вебхук выключен — подожди до `POLL_INTERVAL_SECONDS` секунд или
нажми кнопку «Проверить оплату». Если используешь вебхук — посмотри логи
на наличие `cryptobot.webhook.bad_signature` (значит, токены в боте и в
CryptoBot не совпадают).

**Хочу разные цены для USDT и TON.**
Перепиши `SubscriptionService._amount_for` в
`src/bot/services/subscription.py` — это единственное место, где сумма
конвертируется.

**Можно ли поднять несколько ботов на один Crypto Pay аккаунт?**
Да, но каждому нужен свой Crypto Pay App с отдельным токеном — вебхук
привязывается к приложению.

**Где хранятся секреты в Docker?**
Compose читает `.env` рядом. В Kubernetes используй `Secret`-ресурс и
монтируй переменные окружения.

## Лицензия

MIT — см. [LICENSE](LICENSE).
