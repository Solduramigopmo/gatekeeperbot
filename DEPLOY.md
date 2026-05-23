# Деплой gatekeeper-bot

Подробная инструкция по запуску бота в production. Если просто хочешь
попробовать локально — смотри [README.md](README.md#быстрый-старт).

## Содержание

1. [Что нужно подготовить](#1-что-нужно-подготовить)
2. [Создание Telegram-бота и канала](#2-создание-telegram-бота-и-канала)
3. [Подключение CryptoBot (Crypto Pay)](#3-подключение-cryptobot-crypto-pay)
4. [Подготовка сервера](#4-подготовка-сервера)
5. [Деплой через Docker Compose (рекомендуется)](#5-деплой-через-docker-compose-рекомендуется)
6. [Деплой через systemd](#6-деплой-через-systemd)
7. [HTTPS-вебхук CryptoBot](#7-https-вебхук-cryptobot)
8. [PostgreSQL вместо SQLite](#8-postgresql-вместо-sqlite)
9. [Бэкапы и восстановление](#9-бэкапы-и-восстановление)
10. [Обновление до новой версии](#10-обновление-до-новой-версии)
11. [Мониторинг и логи](#11-мониторинг-и-логи)
12. [Проверка безопасности перед публикацией](#12-проверка-безопасности-перед-публикацией)
13. [Частые проблемы](#13-частые-проблемы)

---

## 1. Что нужно подготовить

| Что | Где взять | Зачем |
|---|---|---|
| VPS с Linux | Hetzner / DigitalOcean / Selectel / любой другой | На нём будет крутиться бот |
| Доменное имя | RegRu / NameCheap / Cloudflare Registrar | Только если включаешь вебхук CryptoBot (для HTTPS) |
| Telegram-аккаунт | — | Для общения с @BotFather и @CryptoBot |

Минимальная конфигурация VPS: **1 vCPU, 512 MB RAM, 5 GB диска**, Ubuntu 22.04+
или Debian 12+. Для PostgreSQL — добавь 1 GB RAM.

## 2. Создание Telegram-бота и канала

### 2.1. Бот

1. Открой [@BotFather](https://t.me/BotFather), нажми `/newbot`.
2. Придумай имя (отображаемое) и username (заканчивается на `bot`).
3. Сохрани токен вида `12345:ABCDEF...` — это `BOT_TOKEN`.
4. По желанию: `/setdescription`, `/setabouttext`, `/setuserpic` —
   текст профиля и аватарка бота.

### 2.2. Канал

1. В Telegram создай **приватный** канал. Тип «Приватный» обязателен —
   к публичным каналам присоединяются по @username без приглашений.
2. Открой канал → ⚙️ → «Управление каналом» → «Администраторы» → «Добавить
   администратора» → найди своего бота по username.
3. Дай боту минимум право «**Пригласительные ссылки**». Желательно убрать
   всё лишнее (постинг и т. д.) — бот в канал ничего не пишет.
4. Узнай числовой ID канала:
   - Перешли любой пост из канала в [@userinfobot](https://t.me/userinfobot)
     — он покажет `Origin chat: -100…`.
   - Либо запусти `python -m bot` без `CHANNEL_ID`, попробуй командой бота
     `getChat` — но проще через userinfobot.
5. Сохрани этот числовой ID (он отрицательный, формат `-100…`) — это `CHANNEL_ID`.

### 2.3. Свой user_id

Узнай свой Telegram ID у [@userinfobot](https://t.me/userinfobot) и положи в
`ADMIN_IDS`. Несколько админов — через запятую: `ADMIN_IDS=111,222,333`.

## 3. Подключение CryptoBot (Crypto Pay)

### 3.1. Создание приложения

1. Открой [@CryptoBot](https://t.me/CryptoBot) (mainnet) или
   [@CryptoTestnetBot](https://t.me/CryptoTestnetBot) (для тестов).
2. `/start` → **Crypto Pay** → **Create App**.
3. Дай приложению любое имя (его увидит только ты).
4. Сохрани **API Token** — это `CRYPTO_PAY_TOKEN`.

> ⚠️ Mainnet и testnet — это разные приложения с разными токенами и разными
> сайтами API (`pay.crypt.bot` vs `testnet-pay.crypt.bot`). Не перепутай.

### 3.2. Активы

В `.env` укажи валюты, которые предлагать пользователю:

```env
CRYPTO_PAY_ASSETS=USDT,TON
```

Полный список поддерживаемых: USDT, TON, BTC, ETH, BNB, TRX, LTC и другие
(смотри [help.crypt.bot](https://help.crypt.bot/crypto-pay-api)).

## 4. Подготовка сервера

```bash
# Под root или sudo
apt update && apt upgrade -y
apt install -y git curl ca-certificates ufw

# Файрвол: только SSH (и 443, если будет вебхук)
ufw allow 22/tcp
ufw allow 443/tcp     # пропустить, если без вебхука
ufw enable
```

Создай непривилегированного пользователя для бота:

```bash
adduser --disabled-password --gecos "" bot
mkdir -p /opt/gatekeeper-bot
chown bot:bot /opt/gatekeeper-bot
```

Дальше — выбирай один из двух способов запуска: Docker или systemd.

## 5. Деплой через Docker Compose (рекомендуется)

### 5.1. Установка Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker bot
```

Перелогинься как `bot`, чтобы группа применилась.

### 5.2. Клон репозитория и конфиг

```bash
su - bot
git clone https://github.com/<owner>/gatekeeper-bot.git /opt/gatekeeper-bot
cd /opt/gatekeeper-bot

cp .env.example .env
nano .env       # заполни BOT_TOKEN, CHANNEL_ID, ADMIN_IDS, CRYPTO_PAY_TOKEN
```

### 5.3. Запуск

```bash
docker compose up -d --build
docker compose logs -f
```

Контейнер сам:

- ставит зависимости из `pyproject.toml`,
- создаёт SQLite-файл в `./data/bot.sqlite3` (том пробрасывается на хост),
- запускает long-polling и шедулер.

`--restart unless-stopped` уже в `docker-compose.yml`, после ребута сервера
бот поднимется сам.

### 5.4. Обновление

```bash
cd /opt/gatekeeper-bot
git pull
docker compose up -d --build
```

## 6. Деплой через systemd

Если не хочешь Docker:

```bash
su - bot
git clone https://github.com/<owner>/gatekeeper-bot.git /opt/gatekeeper-bot
cd /opt/gatekeeper-bot

apt install -y python3.12 python3.12-venv      # под root, если не стоит
python3.12 -m venv .venv
.venv/bin/pip install -e .

cp .env.example .env
nano .env

mkdir -p data
.venv/bin/alembic upgrade head
```

Создай unit-файл (под root):

```ini
# /etc/systemd/system/gatekeeper-bot.service
[Unit]
Description=Gatekeeper Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=bot
Group=bot
WorkingDirectory=/opt/gatekeeper-bot
EnvironmentFile=/opt/gatekeeper-bot/.env
ExecStart=/opt/gatekeeper-bot/.venv/bin/python -m bot
Restart=always
RestartSec=5
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=/opt/gatekeeper-bot/data

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now gatekeeper-bot
systemctl status gatekeeper-bot
journalctl -u gatekeeper-bot -f
```

## 7. HTTPS-вебхук CryptoBot

Поллинг работает «из коробки» — но это +1 HTTP-запрос в минуту. Для прода
лучше включить вебхук: оплата активируется мгновенно, лишних запросов нет.

### 7.1. Что нужно

- Доменное имя, указывающее A-записью на твой сервер.
- Открытый 443 порт.
- Сертификат — проще всего получить через
  [Caddy](https://caddyserver.com/) (он сам берёт Let's Encrypt и
  обновляет), либо вручную через [acme.sh](https://github.com/acmesh-official/acme.sh).

### 7.2. Caddy + Docker

`/opt/gatekeeper-bot/Caddyfile`:

```
bot.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

`docker-compose.override.yml`:

```yaml
services:
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
volumes:
  caddy_data:
  caddy_config:
```

Включи вебхук в `.env`:

```env
WEBHOOK_ENABLED=true
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
WEBHOOK_PATH=/cryptopay
```

Перезапусти контейнеры:

```bash
docker compose up -d --build
```

В @CryptoBot → Crypto Pay → My Apps → **Edit App** → впиши
`https://bot.example.com/cryptopay`, включи событие `invoice_paid`.

### 7.3. Проверка вебхука

```bash
curl -i https://bot.example.com/health
# должно быть HTTP/2 200 и {"status":"ok"}
```

Если CryptoBot шлёт запросы — увидишь в логах строки `cryptobot.webhook.*`.
При неверной подписи — `cryptobot.webhook.bad_signature` (значит, токен
в `.env` не совпадает с токеном приложения).

## 8. PostgreSQL вместо SQLite

SQLite ок для одного экземпляра бота, но для бэкапов и репликации удобнее
PostgreSQL.

### 8.1. Запуск в Docker Compose

Дополни `docker-compose.override.yml`:

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: gatekeeper
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: gatekeeper
    volumes:
      - pgdata:/var/lib/postgresql/data
  bot:
    depends_on:
      - db

volumes:
  pgdata:
```

В `.env`:

```env
POSTGRES_PASSWORD=придумай-длинный-пароль
DATABASE_URL=postgresql+asyncpg://gatekeeper:${POSTGRES_PASSWORD}@db:5432/gatekeeper
```

Применить миграции:

```bash
docker compose run --rm bot alembic upgrade head
docker compose up -d
```

### 8.2. Миграция данных с SQLite

Если уже работаешь на SQLite и хочешь перейти на Postgres:

```bash
# дамп
docker compose run --rm bot python -c "
import sqlite3, csv
con = sqlite3.connect('/app/data/bot.sqlite3')
for table in ('users', 'subscriptions', 'payments', 'price_overrides'):
    with open(f'/app/data/{table}.csv', 'w', newline='') as f:
        w = csv.writer(f)
        cur = con.execute(f'SELECT * FROM {table}')
        w.writerow([d[0] for d in cur.description])
        w.writerows(cur.fetchall())
"
# импорт в Postgres стандартным COPY
```

## 9. Бэкапы и восстановление

### SQLite

```bash
# Делать раз в сутки кроном
0 3 * * * sqlite3 /opt/gatekeeper-bot/data/bot.sqlite3 ".backup '/var/backups/bot.$(date +\%F).sqlite3'"
```

### PostgreSQL

```bash
# В Docker Compose
docker compose exec db pg_dump -U gatekeeper gatekeeper | gzip > /var/backups/bot-$(date +%F).sql.gz
```

Восстановление:

```bash
gunzip -c /var/backups/bot-2026-05-23.sql.gz | docker compose exec -T db psql -U gatekeeper -d gatekeeper
```

## 10. Обновление до новой версии

```bash
cd /opt/gatekeeper-bot
git fetch && git log --oneline HEAD..origin/main      # посмотреть что меняется
git pull
# Docker:
docker compose run --rm bot alembic upgrade head
docker compose up -d --build
# systemd:
.venv/bin/pip install -e .
.venv/bin/alembic upgrade head
systemctl restart gatekeeper-bot
```

`alembic upgrade head` идемпотентен — если миграций нет, ничего не сделает.

## 11. Мониторинг и логи

### Логи

- Docker: `docker compose logs -f bot`
- systemd: `journalctl -u gatekeeper-bot -f`

Формат логов структурированный (structlog). Уровень меняется через
`LOG_LEVEL` в `.env` (`DEBUG` / `INFO` / `WARNING` / `ERROR`).

Полезные строки в логах:

| Сообщение | Что значит |
|---|---|
| `bot.starting` | Старт |
| `scheduler.started` | Шедулер поднял свои джобы |
| `subscription.checkout_created` | Пользователь нажал «оплатить», создан счёт |
| `subscription.activated` | Оплата проведена, подписка создана/продлена |
| `cryptobot.webhook.bad_signature` | Кто-то стучится на вебхук с неверной подписью |
| `scheduler.kick_skipped` | Бот не смог кикнуть юзера (нет прав в канале) |

### Healthcheck (если включён вебхук)

```bash
curl -fs https://bot.example.com/health || systemctl restart gatekeeper-bot
```

Можно сунуть в Uptime Kuma, Healthchecks.io или внешний мониторинг.

## 12. Проверка безопасности перед публикацией

- [ ] `.env` **не** закоммичен (`.gitignore` уже его исключает, но проверь:
      `git status` и `git ls-files | grep env`)
- [ ] Токены, попавшие в чаты или скриншоты, отозваны: @BotFather → `/revoke`,
      @CryptoBot → My Apps → Reset Token
- [ ] `ADMIN_IDS` содержит только реальные ID — `0` и тестовые удалить
- [ ] У бота в канале права **только** на инвайт-ссылки, ничего лишнего
- [ ] На сервере включён ufw, открыты только нужные порты
- [ ] HTTPS-сертификат свежий, авто-обновление работает

## 13. Частые проблемы

**`createChatInviteLink: Bad Request: not enough rights`** — бот не админ
канала или у него снято право «Пригласительные ссылки». Иди в настройки
канала и проверь.

**После оплаты подписка не активируется минутами.** Если вебхук выключен —
бот опрашивает счета раз в `POLL_INTERVAL_SECONDS` (по умолчанию 60). Либо
поставь меньше, либо включи вебхук.

**`Conflict: terminated by other getUpdates request`** — запущено сразу
два экземпляра бота с одним токеном. Останови второй (`systemctl status`,
`docker ps`).

**`alembic upgrade head` падает с `target database is not up to date`** —
у тебя в БД ревизия, которой нет в `alembic/versions`. Скорее всего,
кто-то откатил миграцию или ты переключился между ветками. Посмотри
`alembic current` и `alembic history`.

**Цены в админке поменял, а пользователю всё равно показывает старую.**
Если у пользователя уже открыт счёт — сумма зафиксирована в момент
выставления. Новый счёт будет с новой ценой.

**Бот не отвечает после деплоя**, но процесс жив. Проверь логи —
скорее всего, неверный `BOT_TOKEN` или Telegram заблокировал IP.
`curl https://api.telegram.org` с сервера — должно работать.

---

Если столкнулся с проблемой, которой нет в этом списке —
[создай issue](https://github.com/<owner>/gatekeeper-bot/issues/new) с
логами (без секретов!).
