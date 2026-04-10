# Frontend

Vue-приложение с двумя основными сценариями:

- пользовательский веб-кабинет;
- админ-панель.

## Зависимости

```bash
cd /Users/qerenny/Documents/VPN_TG-WEB_system/frontend
npm install
```

## Разработка

```bash
cd /Users/qerenny/Documents/VPN_TG-WEB_system/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Либо из корня:

```bash
make frontend
```

## Сборка

```bash
cd /Users/qerenny/Documents/VPN_TG-WEB_system/frontend
npm run build
```

## Runtime-зависимости от backend

Frontend опирается на:

- `/api/user/public-config` — product config и feature flags;
- `/api/me/...` — кабинет пользователя;
- `/api/admin/...` — админ-панель.

Если модуль выключен в `FEATURES__...`, соответствующие секции интерфейса скрываются.

Особенно важно:

- `FEATURES__STANDARD_CONFIG_ENABLED`
- `FEATURES__TRAFFIC_LIMITED_CONFIG_ENABLED`
- `FEATURES__COMMERCE_ENABLED`
- `FEATURES__WEB_PURCHASE_ENABLED`
- `FEATURES__REFERRALS_ENABLED`
- `FEATURES__PROMOS_ENABLED`

## Что настраивается через env backend

Frontend не читает `.env` напрямую как источник продуктовой логики. Канонический источник — backend public config.

Через backend-конфиг задаются:

- имя продукта;
- support links;
- client app links;
- payment method labels;
- feature flags модулей.
