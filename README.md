# Remote Access Service

Монорепозиторий сервиса защищённого удалённого доступа с управлением через Telegram-бота и веб-панель.

Проект ориентирован на open-source поставку и дипломный сценарий: бренд и коммерческие провайдеры убраны, а продуктовые возможности включаются через feature flags и env-конфигурацию.

## Состав репозитория

- `backend` — FastAPI API, web auth, admin API, public config.
- `telegram_bot` — Telegram-бот и фоновые воркеры.
- `shared` — общая конфигурация, модели, инфраструктурные сервисы, Alembic.
- `frontend` — веб-кабинет и админ-панель на Vue.
- `.github/workflows` — CI/CD.
- `ansible` — инфраструктурный deploy-слой.

## Конфигурация

Проект читает конфиг из env-файлов.

Базовые служебные переменные:

- `REMOTE_ACCESS_CONFIG_PATH` — путь к базовому env-файлу.
- `REMOTE_ACCESS_CONFIG_OVERRIDE_PATH` — путь к override-файлу поверх базового.
- `REMOTE_ACCESS_RUN_INTEGRATION` — включение integration-тестов.
- `REMOTE_ACCESS_ALLOW_TOPOLOGY_DESTRUCTIVE_SYNC` — разрешение destructive topology sync в seed-скриптах.

Данные приложения задаются групповыми переменными:

- `PRODUCT__...`
- `FEATURES__...`
- `SERVERS__...`
- `TRAFFIC_LIMITED_SERVERS__...`
- `BOT__...`
- `DB__...`
- `MAIL__...`

Порядок загрузки:

1. файл из `REMOTE_ACCESS_CONFIG_PATH` или автонайденный `.env.local/.env/.env.production`;
2. `.env.override` рядом с ним, либо файл из `REMOTE_ACCESS_CONFIG_OVERRIDE_PATH`;
3. переменные процесса.

Шаблоны:

- [.env.example](/Users/qerenny/Documents/VPN_TG-WEB_system/.env.example)
- [.env.override.example](/Users/qerenny/Documents/VPN_TG-WEB_system/.env.override.example)
- [.env.local](/Users/qerenny/Documents/VPN_TG-WEB_system/.env.local)
- [.env.production](/Users/qerenny/Documents/VPN_TG-WEB_system/.env.production)

## Модульная схема

Основные модули:

- `FEATURES__STANDARD_CONFIG_ENABLED` — базовые конфигурации, ограниченные сроком.
- `FEATURES__TRAFFIC_LIMITED_CONFIG_ENABLED` — конфигурации, ограниченные сроком и трафиком.
- `FEATURES__ACCESS_REQUESTS_ENABLED` — модуль заявок на получение доступа.
- `FEATURES__ACCESS_REGISTRY_ENABLED` — реестр разрешённых пользователей для авто-одобрения заявок.
- `FEATURES__ACCESS_ADMIN_OVERRIDE_ENABLED` — вспомогательная ручная выдача доступа из админки.
- `FEATURES__COMMERCE_ENABLED` — платежный контур.
- `FEATURES__WEB_PURCHASE_ENABLED` — web checkout.
- `FEATURES__REFERRALS_ENABLED` — приглашения.
- `FEATURES__PROMOS_ENABLED` — промокоды.
- `FEATURES__TELEGRAM_BOT_ENABLED` — runtime бота.
- `FEATURES__MAIL_ENABLED` — пользовательский mail-модуль в кабинете и public config.

Допустимые режимы:

- только `standard`;
- только `traffic_limited`;
- `standard/traffic_limited` + `access_requests`;
- оба контура сразу.

UI и backend-роуты скрывают или отклоняют функции для выключенных модулей. Админка тоже подстраивается под эти флаги.

## Серверы и inbound'ы

Базовые конфигурации используют `SERVERS__...`.

Пример:

```env
SERVERS__GERMANY__USERNAME="user"
SERVERS__GERMANY__PASSWORD="pass"
SERVERS__GERMANY__DOMAIN="example.com"
SERVERS__GERMANY__PORT="592"
SERVERS__GERMANY__PATH="panel"
SERVERS__GERMANY__SUBSCRIPTION_PORT="764"
SERVERS__GERMANY__SUBSCRIPTION_PATH="subscription"
SERVERS__GERMANY__INBOUNDS__1="germany"
SERVERS__GERMANY__INBOUNDS__2="estonia"
```

Трафиковые конфигурации используют `TRAFFIC_LIMITED_SERVERS__...`.

Пример:

```env
TRAFFIC_LIMITED_SERVERS__GERMANY__USERNAME="user"
TRAFFIC_LIMITED_SERVERS__GERMANY__PASSWORD="pass"
TRAFFIC_LIMITED_SERVERS__GERMANY__DOMAIN="example.com"
TRAFFIC_LIMITED_SERVERS__GERMANY__PORT="592"
TRAFFIC_LIMITED_SERVERS__GERMANY__PATH="panel"
TRAFFIC_LIMITED_SERVERS__GERMANY__SUBSCRIPTION_PORT="764"
TRAFFIC_LIMITED_SERVERS__GERMANY__SUBSCRIPTION_PATH="subscription"
TRAFFIC_LIMITED_SERVERS__GERMANY__INBOUNDS__5="germany"
TRAFFIC_LIMITED_SERVERS__GERMANY__INBOUNDS__6="estonia"
```

Если на одном сервере несколько inbound'ов, добавляй новые ключи `INBOUNDS__<id>`. Loader подхватит их без правки кода.

## Планы доступа

Планы задаются через `PLANS__<index>__...`.

Обязательные поля записи:

- `CODE`
- `PAYLOAD`
- `NAME`
- `KIND`
- `SCOPE`
- `ENTITLEMENT_KIND`
- `DURATION_DAYS`
- `IS_ACTIVE`

Для платных планов также нужны:

- `PRICE_AMOUNT`
- `CURRENCY`

Для трафиковых планов:

- `QUOTA_BYTES`
- `SCOPE=traffic_limited`
- `ENTITLEMENT_KIND=traffic`

Новый план добавляется новым индексом, например `PLANS__10__...`.

## Обязательные поля для первого запуска

Минимально нужно заполнить:

- серверные креды и адреса в `SERVERS__...` и/или `TRAFFIC_LIMITED_SERVERS__...`;
- `BOT__TG_ID`, `BOT__API`, `BOT__SUPPORT`;
- `DB__USERNAME`, `DB__PASSWORD`;
- `FRONTEND__ADMIN_PATH`;
- `ADMIN__TOKEN`;
- `PAYMENTS__WEBHOOK_TOKEN`;
- `JWT__SECRET`.

Почтовый модуль optional. `FEATURES__MAIL_ENABLED` управляет пользовательским поведением и UI. `MAIL__ENABLED` и `MAIL__PROVIDER` управляют самой доставкой писем. Effective mail-контур включается только когда разрешены оба слоя.

Картинки в сообщениях тоже optional. Пустые `IMAGES__...` не ломают runtime.

Информационный канал optional. Для публичного канала укажи `BOT__INFO_CHANNEL` как username без пробелов, например `remote_access_news`, и `BOT__INFO_CHANNEL_ID` как `@remote_access_news` или numeric id. Для приватного канала укажи `BOT__INFO_CHANNEL_ID` как numeric id и `BOT__INFO_CHANNEL_LINK` как invite-ссылку вида `https://t.me/+...`. Если ссылка/username и id пустые, проверка подписки на канал и кнопка канала в боте отключаются.

FAQ, ссылки на инструкции по устройствам и страница "О сервисе" тоже optional. Если `PRODUCT__DOCS_LINKS__...` и `FRONTEND__INSTRUCTION_LINK_...` пустые, соответствующие кнопки и ссылки не показываются.

Для кнопок из Telegram на web-кабинет используй публичный `FRONTEND__TELEGRAM_LINK`. Если он не задан или указывает на локальный/placeholder host, бот не будет показывать кнопку кабинета.

## Локальный запуск

Установка:

```bash
make install-shared
make install-backend
make install-bot
make install-frontend
```

Запуск по частям:

```bash
make backend
make bot
make frontend
```

Или через Docker Compose:

```bash
docker compose up --build
```

Перед первым запуском БД:

```bash
make alembic-upgrade
```

## Проверки

Основные команды:

```bash
cd backend && poetry run pytest -q ../tests -m "not integration"
cd frontend && npm run build
docker compose config --quiet
docker compose -f docker-compose.prod.yml config --quiet
```

Integration-тесты запускаются только при установленном `REMOTE_ACCESS_RUN_INTEGRATION=1`.

## Deploy

Для production используй отдельный env-файл и при необходимости override:

```bash
REMOTE_ACCESS_CONFIG_PATH=/app/.env.production
REMOTE_ACCESS_CONFIG_OVERRIDE_PATH=/app/.env.override
```

CI/CD и compose уже работают через env-модель, без YAML-конфига приложения.

Open-source поставка должна содержать только шаблоны env-файлов и секреты GitHub Actions вне репозитория.
