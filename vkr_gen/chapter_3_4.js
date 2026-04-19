const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  ImageRun,
  Packer,
  PageNumber,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  VerticalAlign,
  WidthType,
} = require("docx");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

const mm = (v) => Math.round((v / 25.4) * 1440);
const LEFT = mm(30);
const RIGHT = mm(15);
const TOP = mm(20);
const BOTTOM = mm(20);
const INDENT = mm(12.5);
const PAGE_WIDTH = 11906;
const PAGE_HEIGHT = 16838;
const CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT;
const FONT = "Times New Roman";
const MONO = "Courier New";
const BODY_SIZE = 28;
const TABLE_SIZE = 24;
const LISTING_SIZE = 24;
const SP = { line: 360, lineRule: "auto", before: 0, after: 0 };
const SP_SINGLE = { line: 240, lineRule: "auto", before: 0, after: 0 };

function r(text, opts = {}) {
  return new TextRun({
    text,
    font: opts.font ?? FONT,
    size: opts.size ?? BODY_SIZE,
    bold: opts.bold,
    italics: opts.italics,
    allCaps: opts.allCaps,
  });
}

function p(text, opts = {}) {
  const children = Array.isArray(text) ? text : [r(text, opts.run ?? {})];
  return new Paragraph({
    children,
    spacing: opts.spacing ?? SP,
    indent: { firstLine: opts.noIndent ? 0 : INDENT },
    alignment: opts.alignment ?? AlignmentType.JUSTIFIED,
    heading: opts.heading,
    pageBreakBefore: opts.pageBreakBefore,
  });
}

function h2(text) {
  return p([r(text, { bold: true })], { heading: HeadingLevel.HEADING_2 });
}

function h3(text) {
  return p([r(text, { bold: true })], { heading: HeadingLevel.HEADING_3 });
}

function caption(text, opts = {}) {
  return p(text, {
    noIndent: true,
    alignment: opts.alignment ?? AlignmentType.LEFT,
  });
}

function figurePlaceholder(text) {
  return new Paragraph({
    children: [r(text, { italics: true })],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
  });
}

function pngSize(filePath) {
  const buf = fs.readFileSync(filePath);
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

function findScreenshot(fileName, dir = path.join(ROOT, "docs", "screenshots"), isRoot = true) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const nested = findScreenshot(fileName, fullPath, false);
      if (nested) return nested;
    } else if (entry.isFile() && entry.name === fileName) {
      return fullPath;
    }
  }
  if (isRoot) {
    throw new Error(`Screenshot not found: ${fileName}`);
  }
  return null;
}

function figureImage(fileName, opts = {}) {
  const filePath = findScreenshot(fileName);
  const data = fs.readFileSync(filePath);
  const { width, height } = pngSize(filePath);
  const maxWidth = opts.maxWidth ?? 620;
  const maxHeight = opts.maxHeight ?? 520;
  const scale = Math.min(maxWidth / width, maxHeight / height, 1);
  return new Paragraph({
    children: [new ImageRun({
      data,
      type: "png",
      transformation: {
        width: Math.round(width * scale),
        height: Math.round(height * scale),
      },
    })],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
  });
}

function figureCaption(text) {
  return new Paragraph({
    children: [r(text)],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
  });
}

function cellParagraph(text, isHeader) {
  return new Paragraph({
    children: [r(text, { size: TABLE_SIZE, bold: isHeader })],
    spacing: SP_SINGLE,
    indent: { firstLine: 0 },
    alignment: isHeader ? AlignmentType.CENTER : AlignmentType.LEFT,
  });
}

function makeTable(rows, widths) {
  const border = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((row, rowIndex) => new TableRow({
      tableHeader: rowIndex === 0,
      children: row.map((value, colIndex) => new TableCell({
        borders: { top: border, bottom: border, left: border, right: border },
        verticalAlign: rowIndex === 0 ? VerticalAlign.CENTER : VerticalAlign.TOP,
        width: { size: widths[colIndex], type: WidthType.DXA },
        margins: { top: 60, bottom: 60, left: 90, right: 90 },
        children: [cellParagraph(value, rowIndex === 0)],
      })),
    })),
  });
}

function listingLine(text) {
  return new Paragraph({
    children: [r(text || " ", { font: MONO, size: LISTING_SIZE })],
    spacing: SP_SINGLE,
    indent: { firstLine: 0 },
    alignment: AlignmentType.LEFT,
  });
}

// ── Таблица 14: контуры серверного API ─────────────────────────────────────
const T14_WIDTHS = [
  Math.round(CONTENT_WIDTH * 0.18),
  Math.round(CONTENT_WIDTH * 0.22),
  Math.round(CONTENT_WIDTH * 0.18),
  Math.round(CONTENT_WIDTH * 0.22),
  CONTENT_WIDTH
    - Math.round(CONTENT_WIDTH * 0.18)
    - Math.round(CONTENT_WIDTH * 0.22)
    - Math.round(CONTENT_WIDTH * 0.18)
    - Math.round(CONTENT_WIDTH * 0.22),
];
const T14_ROWS = [
  [
    "Контур API",
    "Основной роутер",
    "Защита доступа",
    "Связанные сервисы",
    "Роль в прикладных каналах",
  ],
  [
    "Публичный",
    "user_routes, subscription_routes, public_link_routes",
    "Не требует сессии",
    "Выдача подписочного профиля, публичная конфигурация",
    "Технический вход для просмотра подписочной конфигурации и получения параметров клиентом",
  ],
  [
    "Аутентификация",
    "auth_routes",
    "Сессионные cookie выдаются при успешном входе",
    "AuthService, WebSessionService, WebAuthChallengeService",
    "Вход, регистрация, восстановление пароля, связывание Telegram с веб-аккаунтом",
  ],
  [
    "Пользовательский защищённый",
    "me_routes",
    "require_web_user через HTTP-only cookie",
    "AccountService, SubscriptionManagerService, AccessRequestService, WebCheckoutService",
    "Доступ веб-кабинета к профилю, подпискам, платежам, заявкам и промокодам",
  ],
  [
    "Административный",
    "admin_routes",
    "require_superadmin через admin-cookie и проверку роли",
    "AdminService, AccessRequestService, AccessRegistryService",
    "Управленческие операции над пользователями, заявками, журналом и реестром",
  ],
  [
    "Платёжный webhook",
    "payment_webhook_routes",
    "HMAC-сравнение токена в пути запроса",
    "PaymentWebhookService, очередь и dedupe в Redis",
    "Внешний технический вход для получения уведомлений от платёжных провайдеров",
  ],
];

// ── Таблица 15: группы обработчиков Telegram-бота ──────────────────────────
const T15_WIDTHS = [
  Math.round(CONTENT_WIDTH * 0.20),
  Math.round(CONTENT_WIDTH * 0.18),
  Math.round(CONTENT_WIDTH * 0.22),
  Math.round(CONTENT_WIDTH * 0.18),
  CONTENT_WIDTH
    - Math.round(CONTENT_WIDTH * 0.20)
    - Math.round(CONTENT_WIDTH * 0.18)
    - Math.round(CONTENT_WIDTH * 0.22)
    - Math.round(CONTENT_WIDTH * 0.18),
];
const T15_ROWS = [
  [
    "Группа сценариев",
    "Триггер",
    "Обработчик",
    "Связанный сервис",
    "Роль в пользовательском канале",
  ],
  [
    "Стартовый контур и главное меню",
    "/start, menu_*",
    "StartHandler, ProfileHandler, HelpHandler, SupportHandler",
    "UserRegistrationService, SubscriptionFlowService",
    "Вход пользователя и навигация к базовым сценариям",
  ],
  [
    "Подписки и заявки на доступ",
    "profile_subscriptions, sub_*",
    "SubscriptionMenuHandler, SubscriptionAccessRequestHandler, PaymentCommandHandler",
    "StandardUserSubscriptionService, TrafficLimitedService, AccessRequestService",
    "Самообслуживание по стандартному и трафиковому доступу",
  ],
  [
    "Пробные сценарии",
    "sub_trial, sub_traffic_limited_trial",
    "SubscriptionTrialHandler",
    "AccessIssuanceService",
    "Разовое предоставление пробного доступа",
  ],
  [
    "Промокоды",
    "/promo",
    "SubscriptionPromoHandler",
    "AccessIssuanceService, репозиторий промокодов",
    "Активация промокодов как самостоятельного основания выдачи",
  ],
  [
    "Реферальные механики",
    "referrals_*",
    "ReferralMenuHandler, ReferralStartHandler",
    "ReferralStatsService, ReferralBonusService",
    "Просмотр статистики и приглашение по реферальной ссылке",
  ],
  [
    "Административные команды",
    "/admin_panel, admin_*",
    "AdminCommandHandler",
    "JWTEncoder для bootstrap-ссылки, AccessRequestService",
    "Быстрый административный доступ и переход в веб-интерфейс",
  ],
  [
    "Платёжные callback-сценарии",
    "после оформления платежа",
    "PaymentCommandHandler",
    "PaymentQueueService, PaymentProcessingService",
    "Отслеживание статуса оформленной оплаты",
  ],
];

// ── Таблица 16: страницы веб-кабинета ─────────────────────────────────────
const T16_WIDTHS = [
  Math.round(CONTENT_WIDTH * 0.22),
  Math.round(CONTENT_WIDTH * 0.18),
  Math.round(CONTENT_WIDTH * 0.25),
  CONTENT_WIDTH
    - Math.round(CONTENT_WIDTH * 0.22)
    - Math.round(CONTENT_WIDTH * 0.18)
    - Math.round(CONTENT_WIDTH * 0.25),
];
const T16_ROWS = [
  [
    "Страница веб-кабинета",
    "API-модуль frontend",
    "Backend-маршруты",
    "Поддерживаемый сценарий",
  ],
  [
    "AppOverviewPage",
    "api/account.ts",
    "/me, /me/subscriptions, /me/links, /me/access-grants",
    "Агрегированный обзор аккаунта, привязок и активного доступа",
  ],
  [
    "AppSubscriptionsPage",
    "api/account.ts, api/publicConfig.ts",
    "/me/subscriptions, /subscription/build, /subscription/traffic_limited/build",
    "Состояние стандартного и трафикового доступа, получение подписочной конфигурации",
  ],
  [
    "AppPurchasePage",
    "api/account.ts",
    "/me/plans, /me/payments/checkout, /me/access-requests",
    "Выбор плана, оформление платежа или подача заявки на доступ",
  ],
  [
    "AppPaymentsPage",
    "api/account.ts",
    "/me/payments",
    "История платежей и обновление статуса незавершённых операций",
  ],
  [
    "AppProfilePage",
    "api/account.ts, api/linking.ts, api/auth.ts",
    "/me/profile, /me/links/telegram/start, /me/promo/apply",
    "Профиль, изменение данных, привязка Telegram, активация промокода",
  ],
  [
    "AppHelpPage",
    "api/publicConfig.ts",
    "/user/public-config",
    "Инструкции по подключению и ссылки на поддержку",
  ],
];

// ── Таблица 17: административные операции ─────────────────────────────────
const T17_WIDTHS = [
  Math.round(CONTENT_WIDTH * 0.28),
  Math.round(CONTENT_WIDTH * 0.25),
  Math.round(CONTENT_WIDTH * 0.22),
  CONTENT_WIDTH
    - Math.round(CONTENT_WIDTH * 0.28)
    - Math.round(CONTENT_WIDTH * 0.25)
    - Math.round(CONTENT_WIDTH * 0.22),
];
const T17_ROWS = [
  [
    "Операция",
    "Функция в api/admin.ts",
    "Backend-маршрут",
    "Сервисный слой",
  ],
  [
    "Вход в административный контур",
    "loginAdmin, logoutAdmin",
    "POST /admin/session/login, POST /admin/session/logout",
    "create_admin_session, проверка роли, lockout",
  ],
  [
    "Обзор состояния",
    "fetchAdminOverview",
    "GET /admin/overview",
    "AdminService",
  ],
  [
    "Поиск и карточка пользователя",
    "searchAdminUsers, fetchAdminUser",
    "GET /admin/users, GET /admin/users/{id}",
    "AdminService",
  ],
  [
    "Журнал действий",
    "fetchAdminAudit",
    "GET /admin/audit",
    "AdminService, репозиторий журнала",
  ],
  [
    "Выполнение действия",
    "runAdminAction",
    "POST /admin/actions",
    "AdminService совместно с профильными сервисами доступа",
  ],
  [
    "Работа с заявками",
    "fetchAdminAccessRequests, reviewAdminAccessRequest",
    "GET /admin/access-requests, POST /admin/access-requests/{id}/review",
    "AccessRequestService",
  ],
  [
    "Реестр разрешённых субъектов",
    "fetchAdminAccessRegistry, upsertAdminAccessRegistry, batch-операции",
    "/admin/access-registry и связанные маршруты",
    "AccessRegistryService",
  ],
  [
    "Управление промокодами",
    "fetchAdminPromos, createAdminPromo, toggleAdminPromo",
    "/admin/promos, PATCH /admin/promos/{id}",
    "WebPromoService, репозиторий промокодов",
  ],
];

// ── Листинг 4: include_router из backend/main.py ──────────────────────────
const LISTING4 = [
  "def create_app() -> FastAPI:",
  "    app = FastAPI(",
  "        title=f\"{runtime_settings.product_name} API\",",
  "        lifespan=_create_lifespan(runtime_settings),",
  "    )",
  "",
  "    app.add_middleware(",
  "        CORSMiddleware,",
  "        allow_origins=runtime_settings.frontend_allowed_origins,",
  "        allow_credentials=True,",
  "        allow_methods=[\"*\"],",
  "        allow_headers=[\"*\"],",
  "    )",
  "",
  "    app.include_router(user_routes.router, prefix=runtime_settings.backend_prefix)",
  "    app.include_router(auth_routes.router, prefix=runtime_settings.backend_prefix)",
  "    app.include_router(me_routes.router, prefix=runtime_settings.backend_prefix)",
  "    app.include_router(public_link_routes.router,",
  "                       prefix=runtime_settings.backend_prefix)",
  "    app.include_router(subscription_routes.router,",
  "                       prefix=runtime_settings.backend_prefix)",
  "    app.include_router(payment_webhook_routes.router,",
  "                       prefix=runtime_settings.backend_prefix)",
  "    app.include_router(admin_routes.router,",
  "                       prefix=runtime_settings.backend_prefix)",
  "    return app",
];

// ── Листинг 5: фрагмент subscription_router.py ────────────────────────────
const LISTING5 = [
  "def register_subscription_routes(",
  "    bot: AsyncTeleBot,",
  "    *,",
  "    menu_handler,",
  "    access_request_handler,",
  "    payment_handler,",
  "    commerce_enabled: bool,",
  "    standard_config_enabled: bool,",
  "    traffic_limited_config_enabled: bool,",
  "    access_requests_enabled: bool,",
  ") -> None:",
  "    @bot.callback_query_handler(",
  "        func=lambda call: call.data == \"profile_subscriptions\"",
  "    )",
  "    async def _open_subscriptions_menu(call):",
  "        await menu_handler.show_menu(call)",
  "",
  "    @bot.callback_query_handler(",
  "        func=lambda call: call.data.startswith(\"sub_\")",
  "    )",
  "    async def _dispatch_subscription_callback(call):",
  "        data = call.data",
  "        if data == \"sub_trial\":",
  "            if not standard_config_enabled:",
  "                await bot.answer_callback_query(",
  "                    call.id, \"Базовые конфигурации отключены\")",
  "                return",
  "            await menu_handler.run_trial(call)",
  "            return",
  "        if data.startswith(\"sub_access_request\"):",
  "            if not access_requests_enabled:",
  "                await bot.answer_callback_query(",
  "                    call.id, \"Заявки на доступ отключены\")",
  "                return",
  "            await access_request_handler.handle(call)",
  "            return",
  "        if data in PAID_PRODUCTS:",
  "            if not commerce_enabled:",
  "                await bot.answer_callback_query(",
  "                    call.id, \"Оплата отключена\")",
  "                return",
  "            await payment_handler.ask_payment_method(call, data)",
];

// ── Листинг 6: guard защищённой зоны веб-кабинета ─────────────────────────
const LISTING6 = [
  "router.beforeEach(async (to) => {",
  "  const requiresAuth = to.matched.some(",
  "    (record) => record.meta?.requiresAuth,",
  "  )",
  "  const guestOnly = to.matched.some(",
  "    (record) => record.meta?.guestOnly,",
  "  )",
  "",
  "  if (!requiresAuth && !guestOnly) {",
  "    return true",
  "  }",
  "",
  "  let me = null",
  "  try {",
  "    me = await ensureSession()",
  "  } catch (error) {",
  "    if (guestOnly) return true",
  "    return {",
  "      path: '/auth/login',",
  "      query: { next: to.fullPath, session_error: '1' },",
  "    }",
  "  }",
  "",
  "  if (requiresAuth && !me) {",
  "    return { path: '/auth/login', query: { next: to.fullPath } }",
  "  }",
  "",
  "  if (guestOnly && me && typeof to.query.link_token !== 'string') {",
  "    const next = typeof to.query.next === 'string'",
  "      && to.query.next.startsWith('/') ? to.query.next : '/app'",
  "    return next",
  "  }",
  "",
  "  return true",
  "})",
];

// ── Листинг Д.1: require_web_user ────────────────────────────────────────
const LISTING_D1 = [
  "async def require_web_user(",
  "    request: Request,",
  "    web_session_id: str | None = Cookie(",
  "        default=None,",
  "        alias=WEB_SESSION_COOKIE_NAME,",
  "    ),",
  "    auth_service: AuthService = Depends(get_auth_service),",
  ") -> AuthenticatedWebUser:",
  "    return await auth_service.get_current_user(web_session_id)",
  "",
  "",
  "RequireWebUser = Depends(require_web_user)",
];

// ── Листинг Д.2: require_superadmin и create_admin_session ───────────────
const LISTING_D2 = [
  "async def _assert_login_not_locked(request: Request) -> None:",
  "    fingerprint = _client_fingerprint(request)",
  "    lock_key = f\"{_LOGIN_LOCK_KEY_PREFIX}:{fingerprint}\"",
  "    lock_payload = await _store_get_json(request, lock_key)",
  "    if not lock_payload:",
  "        return",
  "    locked_until = float(lock_payload.get(\"locked_until\", 0))",
  "    retry_after_seconds = max(1, int(locked_until - time.time()))",
  "    if retry_after_seconds <= 0:",
  "        await _store_delete(request, lock_key)",
  "        return",
  "    raise HTTPException(",
  "        status_code=status.HTTP_429_TOO_MANY_REQUESTS,",
  "        detail={",
  "            \"message\": \"Too many admin login attempts\",",
  "            \"retry_after_seconds\": retry_after_seconds,",
  "        },",
  "    )",
  "",
  "",
  "async def create_admin_session(",
  "    request: Request, *, token: str, actor: str | None,",
  ") -> AdminPrincipal:",
  "    admin_settings = get_backend_deps(request).settings.admin",
  "    if not admin_settings.enabled:",
  "        raise HTTPException(status_code=404, detail=\"Not found\")",
  "    await _assert_login_not_locked(request)",
  "    expected = str(admin_settings.token or \"\").strip().encode(\"utf-8\")",
  "    provided = str(token or \"\").strip().encode(\"utf-8\")",
  "    if not expected or not provided or not secrets.compare_digest(",
  "        provided, expected,",
  "    ):",
  "        await _record_failed_login(request)",
  "        raise HTTPException(status_code=404, detail=\"Not found\")",
  "    await _clear_failed_login_state(request)",
  "    return await create_admin_session_for_actor(",
  "        request, actor=_normalize_actor(actor), role=\"superadmin\",",
  "    )",
  "",
  "",
  "async def require_superadmin(",
  "    request: Request,",
  "    admin_session_id: str | None = Cookie(",
  "        default=None, alias=ADMIN_SESSION_COOKIE_NAME,",
  "    ),",
  ") -> AdminPrincipal:",
  "    return await _require_role(",
  "        request=request,",
  "        minimum_role=\"superadmin\",",
  "        session_id=admin_session_id,",
  "    )",
];

// ── Листинг Е.1: build_bot ───────────────────────────────────────────────
const LISTING_E1 = [
  "TELEGRAM_API_CONNECT_TIMEOUT_SECONDS = 20",
  "TELEGRAM_API_REQUEST_TIMEOUT_SECONDS = 60",
  "TELEGRAM_API_TRANSIENT_RETRIES = 2",
  "",
  "",
  "def _configure_telegram_api_timeouts() -> None:",
  "    asyncio_helper.CONNECT_TIMEOUT = (",
  "        TELEGRAM_API_CONNECT_TIMEOUT_SECONDS",
  "    )",
  "    asyncio_helper.READ_TIMEOUT = (",
  "        TELEGRAM_API_REQUEST_TIMEOUT_SECONDS",
  "    )",
  "    asyncio_helper.REQUEST_TIMEOUT = (",
  "        TELEGRAM_API_REQUEST_TIMEOUT_SECONDS",
  "    )",
  "",
  "",
  "def build_bot() -> AsyncTeleBot:",
  "    logger.info(\"Building new Telegram Bot instance...\")",
  "    _configure_telegram_api_timeouts()",
  "    asyncio_helper.proxy = None",
  "    apihelper.proxy = None",
  "    bot_instance = AsyncTeleBot(BOT_API)",
  "    for method_name in (",
  "        \"send_message\", \"send_photo\", \"edit_message_media\",",
  "    ):",
  "        _wrap_transient_retry(bot_instance, method_name)",
  "    _wrap_answer_callback_query(bot_instance)",
  "    bot_instance.setup_middleware(ContextMiddleware())",
  "    bot_instance.setup_middleware(",
  "        MaintenanceModeMiddleware(bot_instance),",
  "    )",
  "    return bot_instance",
];

// ── Листинг Ж.1: submit_request ──────────────────────────────────────────
const LISTING_J1 = [
  "async def submit_request(",
  "    self,",
  "    call: CallbackQuery,",
  "    *,",
  "    request_kind: str = \"new_access\",",
  "    template_code: str | None = None,",
  ") -> None:",
  "    tg_id = int(call.message.chat.id)",
  "    try:",
  "        snapshot, created = (",
  "            await self.service.create_or_get_pending_request(",
  "                tg_id=tg_id,",
  "                request_kind=request_kind,",
  "                template_code=template_code,",
  "            )",
  "        )",
  "    except HTTPException as exc:",
  "        await bot.answer_callback_query(",
  "            call.id, str(exc.detail), show_alert=True,",
  "        )",
  "        return",
  "    if created and self._is_auto_approved(snapshot):",
  "        await bot.answer_callback_query(",
  "            call.id, \"Доступ активирован\",",
  "        )",
  "        await self.show_status(",
  "            call,",
  "            notice=messages.get_random_message(",
  "                \"subscription_access_request_auto_approved\",",
  "            ),",
  "        )",
  "        return",
  "    if created:",
  "        await bot.answer_callback_query(",
  "            call.id, \"Заявка отправлена\",",
  "        )",
  "        await self.show_status(",
  "            call,",
  "            notice=messages.get_random_message(",
  "                \"subscription_access_request_created\",",
  "            ),",
  "        )",
  "        return",
  "    await bot.answer_callback_query(",
  "        call.id, \"У вас уже есть активная заявка\",",
  "    )",
  "    await self.show_status(",
  "        call,",
  "        notice=messages.get_random_message(",
  "            \"subscription_access_request_pending_exists\",",
  "        ),",
  "    )",
];

// ── Листинг З.1: adminApi и функции клиента ──────────────────────────────
const LISTING_Z1 = [
  "const adminApi = createHttpClient(`${API_BASE_URL}/admin`)",
  "",
  "export async function loginAdmin(",
  "  token: string,",
  "  actor?: string,",
  ") {",
  "  return postData(adminApi, '/session/login', {",
  "    token,",
  "    actor: actor || 'web-admin',",
  "  })",
  "}",
  "",
  "export async function fetchAdminOverview() {",
  "  return getData<AdminOverview>(adminApi, '/overview')",
  "}",
  "",
  "export async function runAdminAction(",
  "  payload: AdminActionPayload,",
  ") {",
  "  return postData(adminApi, '/actions', payload)",
  "}",
  "",
  "export async function reviewAdminAccessRequest(",
  "  requestId: number,",
  "  payload: {",
  "    decision: 'approve' | 'reject'",
  "    review_note?: string | null",
  "    template_code?: string | null",
  "  },",
  ") {",
  "  return postData<AdminAccessRequestItem, typeof payload>(",
  "    adminApi,",
  "    `/access-requests/${requestId}/review`,",
  "    payload,",
  "  )",
  "}",
  "",
  "export async function fetchAdminAccessRegistry(limit = 200) {",
  "  return getItems<AdminAccessRegistryItem>(",
  "    adminApi,",
  "    '/access-registry',",
  "    { params: { limit } },",
  "  )",
  "}",
];

function appendixHeader(letter, title) {
  return [
    new Paragraph({
      children: [r(`Приложение ${letter}`)],
      spacing: SP,
      indent: { firstLine: 0 },
      alignment: AlignmentType.CENTER,
      pageBreakBefore: true,
    }),
    new Paragraph({
      children: [r(title, { bold: true })],
      spacing: SP,
      indent: { firstLine: 0 },
      alignment: AlignmentType.CENTER,
    }),
    p(" ", { noIndent: true }),
  ];
}

const content = [
  h2("3.4 Реализация прикладных каналов"),

  p("Прикладные каналы реализованы как отдельные точки входа в общий сервисный и доменный слой. Серверный API объединяет маршруты веб-интерфейса и внешних уведомлений в одном FastAPI-приложении; Telegram-бот построен как событийный канал самообслуживания и фоновых задач; пользовательский веб-интерфейс реализован как одностраничное приложение с защищённой зоной; административный веб-интерфейс вынесен в отдельный скрытый маршрут. Границы между каналами поддерживаются в коде разной защитой сессии, разными точками входа и различным форматом взаимодействия, при этом доменная логика сосредоточена в общих сервисах и не дублируется в каналах."),

  h3("3.4.1 Реализация серверного API"),

  p("Серверный API реализован как FastAPI-приложение, собираемое в функции create_app модуля backend/main.py. Настройка приложения включает CORS с allow_credentials=True и списком разрешённых origin из конфигурации, lifespan-обвязку для инициализации httpx-клиента и опциональной асинхронной Redis-клиентской обёртки, а также служебный маршрут /health. После общей обвязки выполняется подключение семи роутеров под общим backend_prefix: пользовательского публичного маршрута, аутентификации, защищённого контура /me, публичных ссылок, подписочной сборки, маршрута приёма платёжных уведомлений и административного контура. Выделение каждого контура в отдельный роутер фиксирует разделение ответственности между прикладными каналами на уровне композиции приложения."),

  p("Фрагмент композиции приложения, подтверждающий подключение прикладных контуров через include_router, приведён в листинге 4."),

  caption("Листинг 4 – Композиция FastAPI-приложения и подключение роутеров"),
  ...LISTING4.map(listingLine),

  p("Вторая сторона реализации серверного API сосредоточена в backend/bootstrap.py. Здесь собираются зависимости: репозитории пользователя, платежей, рефералов и промокодов; служебные компоненты JWTEncoder, PasswordHasher, WebSessionService, WebAuthChallengeService, транзакционный email-сервис; прикладные сервисы AuthService, AccountService, LinkingService, WebCheckoutService, SubscriptionManagerService, AccessRequestService, AccessRegistryService, AdminService. Dataclass BackendDeps и набор provider-функций get_* передают готовые сервисы в обработчики маршрутов через Depends, что подтверждает, что endpoint-слой не создаёт сервисы самостоятельно, а получает их через механизм зависимостей FastAPI."),

  p("Защита пользовательского контура реализована функцией require_web_user из auth/web_auth.py. Используется HTTP-only cookie, область действия которой ограничена пользовательским контуром; идентификатор сессии извлекается из этой cookie, а текущий пользователь восстанавливается через AuthService. Административный контур использует отдельную cookie с собственным сроком жизни и проверкой роли superadmin через require_superadmin. При создании административной сессии токен сверяется через secrets.compare_digest; при превышении допустимого числа неудачных попыток входа для клиента временно вводится блокировка. Полный фрагмент require_web_user приведён в приложении Д (листинг Д.1); фрагменты require_superadmin и create_admin_session — в приложении Д (листинг Д.2)."),

  p("Платёжный webhook подключён как отдельный роутер, но рассматривается как внешний технический вход, а не как пользовательский интерфейс. Маршрут /payments/webhook/external/{method}/{token} проверяет включённость коммерческого контура, наличие настроенного webhook-токена и совпадение токена из пути с ожидаемым через hmac.compare_digest. Метод оплаты валидируется по множеству поддерживаемых провайдеров; при несоответствии возвращается 404, при отсутствии настроенного токена — 503, при несовпадении — 403. Принятое событие передаётся в PaymentWebhookService, который помещает уведомление в очередь Redis с защитой от повторов по идентификатору платежа."),

  p("Распределение контуров серверного API, их защиты и связанных сервисов приведено в таблице 14."),

  caption("Таблица 14 – Контуры серверного API"),
  makeTable(T14_ROWS, T14_WIDTHS),

  p("Разделение контуров на уровне API не означает полной независимости исполняемых компонентов: часть интеграционных сервисов физически размещена в пакете Telegram-бота и используется сервисным уровнем шире, чем пользовательский канал бота."),

  h3("3.4.2 Реализация Telegram-бота"),

  p("Инфраструктура канала собрана в telegram_bot/bot.py. Функция build_bot настраивает таймауты соединения и чтения, создаёт экземпляр AsyncTeleBot и оборачивает основные методы отправки и редактирования сообщений в механизм повторных попыток при временных ошибках Telegram API. Отдельно обрабатываются ситуации с устаревшими callback-запросами, что уменьшает количество ложных ошибок в журнале при естественной задержке ответа пользователя. К экземпляру подключаются две промежуточные компоненты: ContextMiddleware сохраняет идентификаторы чата, пользователя и его имени в асинхронном контексте для последующего использования обработчиками, MaintenanceModeMiddleware при активном режиме обслуживания отклоняет обновления пользователей, не входящих в список администраторов. Полный фрагмент build_bot приведён в приложении Е (листинг Е.1)."),

  p("Регистрация обработчиков выполняется в telegram_bot/main.py при запуске процесса. При включённых функциональных флагах вызываются register_start_routes, register_subscription_routes (с передачей флагов commerce_enabled, standard_config_enabled, traffic_limited_config_enabled и access_requests_enabled), register_promo_routes, register_referrals_routes, register_admin_routes и register_payments_routes. В том же процессе стартуют фоновые задачи: напоминания о сроке действия доступа, жизненный цикл доступа, синхронизация трафикового состояния, проверка статуса платежей и обработчик платёжной очереди. Такое сочетание показывает, что процесс Telegram-бота обслуживает не только короткие пользовательские сценарии, но и ряд фоновых задач сервисного уровня."),

  p("Сборка обработчиков и их связывание с сервисами выполнены в telegram_bot/bootstrap.py. Dataclass TelegramBotApp собирает StartHandler, ProfileHandler, HelpHandler, SupportHandler, SubscriptionMenuHandler, SubscriptionAccessRequestHandler, PaymentCommandHandler, ReferralMenuHandler, SubscriptionPromoHandler, SubscriptionTrialHandler и AdminCommandHandler. Все они получают готовые сервисы через параметры конструктора, что подтверждает сохранение доменной логики на уровне сервисов. Например, SubscriptionAccessRequestHandler делегирует решения AccessRequestService и AccessIssuanceService, а PaymentCommandHandler обращается к PaymentQueueService и PaymentProcessingService."),

  p("Событийная природа канала подтверждается регистрацией callback-обработчиков в presentation-слое. В subscription_router.py обработчик callback-запросов сопоставляет значение call.data с веткой сценария: profile_subscriptions открывает меню подписок; sub_trial запускает пробный сценарий стандартного доступа при активном соответствующем флаге; sub_access_request_* передают управление обработчику заявки; идентификаторы из множества PAID_PRODUCTS инициируют оплату при включённом коммерческом контуре. Каждая ветка проверяет свой функциональный флаг и при отключённом модуле возвращает пользователю короткое сообщение, не вызывая сервис. Фрагмент этой диспетчеризации приведён в листинге 5."),

  caption("Листинг 5 – Регистрация callback-сценариев подписочного контура"),
  ...LISTING5.map(listingLine),

  p("Связь presentation-слоя с сервисами подтверждается и в пользовательском сценарии подачи заявки. SubscriptionAccessRequestHandler предлагает выбор типа доступа и шаблона, вызывает AccessRequestService.create_request, а при наличии совпадения по реестру разрешённых субъектов фиксирует автоматическое одобрение и отображает итоговый статус. Фрагмент метода submit_request вынесен в приложение Ж (листинг Ж.1)."),

  p("Административный контур в Telegram-боте реализован более ограниченно, чем веб-панель. AdminCommandHandler обрабатывает команды быстрого доступа — поиск пользователя, просмотр карточки, выдачу временного продления, рассылку, повторную обработку платёжной очереди — и команду /admin_panel, которая выдаёт короткоживущую ссылку в административный веб-интерфейс. Ссылка формируется через JWTEncoder как одноразовый grant и указывает на backend-маршрут /admin/session/bootstrap, который при успешной проверке токена и принадлежности вызывающего к BOT_ADMIN_IDS перенаправляет пользователя на frontend-путь административной панели. Такой подход подтверждает проектное разделение: бот обеспечивает точку перехода и отдельные служебные действия, а полноценные операции управления выполняются в веб-интерфейсе."),

  p("Распределение обработчиков Telegram-бота по группам сценариев приведено в таблице 15."),

  caption("Таблица 15 – Группы обработчиков Telegram-бота"),
  makeTable(T15_ROWS, T15_WIDTHS),

  p("Состав интерфейса пользовательского канала подтверждается снимками экранов бота, приведёнными на рисунках 9–11."),

  figureImage("start.png"),
  figureCaption("Рисунок 9 – Стартовый экран Telegram-бота"),

  figureImage("menu_sub.png"),
  figureCaption("Рисунок 10 – Меню подписочного контура Telegram-бота"),

  figureImage("claim.png"),
  figureCaption("Рисунок 11 – Уведомление о статусе заявки на доступ"),

  p("Telegram-бот реализует основной событийный канал коротких пользовательских сценариев и уведомлений, но не выступает единственным интерфейсом системы: операции, требующие обзорности и работы с историей, выполняются в веб-кабинете, а полноценные управленческие действия — в административной веб-панели."),

  h3("3.4.3 Реализация веб-интерфейса пользователя"),

  p("Пользовательский веб-интерфейс реализован как Vue-приложение, собираемое через Vite. Точка входа frontend/src/main.ts создаёт экземпляр приложения, подключает маршрутизатор, Pinia и корневой компонент App.vue, а затем монтирует приложение в DOM. Корневой компонент реализует сквозное оформление и best-effort-мост с Telegram WebApp: при наличии объекта window.Telegram.WebApp вызываются методы ready, expand и копируются theme-параметры в CSS-переменные интерфейса; исключения при этом подавляются, что подчёркивает вспомогательный характер этой интеграции и её независимость от основной схемы аутентификации."),

  p("Маршрутизация реализована в frontend/src/router/index.ts. Маршруты разделены по метаданным на три группы: публичные (/, /subscription/:token, /subscription/traffic-limited/:token, /demo-payment), гостевые (/auth/login, /auth/register, /auth/password с meta.guestOnly) и защищённая зона /app с дочерними маршрутами обзора, подписок, покупки, помощи, истории платежей и профиля (meta.requiresAuth). Административный маршрут регистрируется условно и рассматривается отдельно в 3.4.4. Защита зоны /app выполнена через router.beforeEach: перед каждой навигацией вызывается ensureSession, неавторизованный пользователь перенаправляется на /auth/login с сохранением исходного пути в параметре next, а авторизованный пользователь, случайно попавший на гостевой маршрут, переводится на /app. Фрагмент guard-функции приведён в листинге 6."),

  caption("Листинг 6 – Guard защищённой зоны веб-кабинета"),
  ...LISTING6.map(listingLine),

  p("Клиентское состояние сессии реализовано в frontend/src/stores/session.ts. Функция ensureSession применяет шаблон single-flight: параллельные вызовы используют общий промис inflightRequest и не порождают дублирующих запросов к /me. При ответе 401 состояние me сбрасывается в null, флаг initialized устанавливается в true, и маршрутизатор при следующей навигации отправляет пользователя на страницу входа. Ошибки иных типов пробрасываются. Сессия реализована cookie-based: cookie устанавливает backend после успешного входа, frontend выполняет запросы с withCredentials=true через общий axios-клиент, создаваемый в api/http.ts функцией createHttpClient. Служебные хелперы getData, getItems, postData и postItems применяются в прикладных api-модулях auth, account, linking, user и publicConfig, что исключает ручное формирование HTTP-запросов в компонентах."),

  p("Страницы пользовательского кабинета опираются на эти api-модули и реализуют поддерживаемые сценарии. AppOverviewPage агрегирует сведения об аккаунте, привязках и недавних выданных правах; AppSubscriptionsPage показывает состояние стандартного и трафикового доступа, построение import-ссылки подписочного профиля и копирование параметров подключения; AppPurchasePage реализует выбор плана, оформление платежа или подачу заявки на доступ, а также повтор заявки; AppPaymentsPage работает с историей платежей и обновляет статус незавершённых операций; AppProfilePage обслуживает профиль, изменение данных, привязку Telegram через beginTelegramLink и применение промокода; AppHelpPage выводит инструкции по подключению и ссылки на поддержку. Компонент UserInfo и публичные страницы /subscription/* реализуют просмотр подписочного токена и не относятся к защищённой зоне."),

  p("Соответствие страниц веб-кабинета api-модулям frontend и backend-маршрутам приведено в таблице 16."),

  caption("Таблица 16 – Страницы веб-кабинета и API-операции"),
  makeTable(T16_ROWS, T16_WIDTHS),

  p("Состав экранов веб-кабинета подтверждается снимками, приведёнными на рисунках 12–13."),

  figureImage("overview_apge.png"),
  figureCaption("Рисунок 12 – Экран обзора аккаунта в веб-кабинете"),

  figureImage("sub_page.png"),
  figureCaption("Рисунок 13 – Экран подписок веб-кабинета"),

  p("Веб-кабинет реализует тип взаимодействия, отличный от Telegram-бота: агрегированный обзор состояний, историю операций, управление профилем и связанными каналами. Операции самообслуживания доступны в обоих пользовательских каналах, но распределение их по глубине и форме отличается, и веб-кабинет не сводится к дублированию функций бота."),

  h3("3.4.4 Реализация административного веб-интерфейса"),

  p("Административный веб-интерфейс реализован как отдельный прикладной контур frontend, подключаемый условно. В router/index.ts значение переменной окружения VITE_ADMIN_PATH прочитывается во время сборки, нормализуется и при непустом значении добавляет маршрут компонента AdminPanel.vue по пути /{adminPathSegment}. При отсутствии значения маршрут не регистрируется вовсе, что снижает публичную видимость административного контура. Это проектное снижение видимости не рассматривается как механизм защиты — фактическую защиту обеспечивают административная cookie, TTL-сессия и проверка роли на уровне backend."),

  p("Клиентские функции административного контура собраны в frontend/src/api/admin.ts. Отдельный экземпляр axios-клиента создаётся через createHttpClient с базовым URL ${API_BASE_URL}/admin и тем же параметром withCredentials, что отделяет административные запросы от пользовательского /me и связывает их с admin-cookie. В модуле реализованы функции loginAdmin, logoutAdmin, fetchAdminOverview, searchAdminUsers, fetchAdminUser, fetchAdminAudit, runAdminAction, fetchAdminAccessRequests, reviewAdminAccessRequest, а также семейство функций работы с реестром разрешённых субъектов и промокодами. Компонент AdminPanel.vue использует эти функции через соответствующие вкладки: обзор состояния, поиск пользователя и карточку пользователя с вкладками доступа, диагностики, платежей, роста и журнала. Выполнение действий реализовано через runAdminAction с типизированным набором значений AdminActionType, включающим продление доступа, выдачу пробного и компенсационного периода, пересборку подписочной ссылки, пересоздание клиентской записи, ручную выдачу и отзыв доступа, повторную обработку очереди платежей, блокировку и разблокировку пользователя, удаление учётной записи. Полный фрагмент adminApi и функций клиента приведён в приложении З (листинг З.1)."),

  p("Защита административного контура на backend реализована в backend/src/backend/admin/auth.py. Функция create_admin_session валидирует токен через secrets.compare_digest и обращается к вспомогательным функциям _assert_login_not_locked и _record_failed_login для ограничения числа попыток входа в заданном окне времени. Идентификатор попытки строится как отпечаток от пары IP и user-agent, что позволяет сузить блокировку до конкретного клиента, не затрагивая остальных."),

  p("Идентификатор сессии генерируется криптографически и сохраняется в Redis с TTL; при его недоступности используется in-memory-хранилище как резервный режим на один процесс. Проверка роли выполняется функцией require_superadmin: при отсутствии или неверной сессии возвращается 404, при недостаточной роли — 403. Набор ролей ROLE_ORDER в коде предусмотрен (support, admin, tech, superadmin), однако маршруты административного контура в текущей реализации закрываются именно проверкой require_superadmin, что определяет фактически используемую модель доступа без расширенного RBAC. Полный фрагмент require_superadmin и связанных проверок приведён в приложении Д (листинг Д.2)."),

  p("Связка Telegram-бота и административного веб-интерфейса реализована через bootstrap-маршрут /admin/session/bootstrap. Поток устроен так: AdminCommandHandler.show_admin_panel по команде /admin_panel проверяет принадлежность вызывающего к BOT_ADMIN_IDS, через JWTEncoder формирует короткоживущий grant и отправляет пользователю inline-кнопку с URL на bootstrap-маршрут; при обращении по ссылке backend проверяет токен, убеждается, что tg_id входит в список администраторов, и выполняет переадресацию 307 на frontend-путь административной панели с уже установленной cookie-сессией. Это связка каналов, а не перенос административной логики в бот: обработчик /admin_panel не подменяет веб-интерфейс и не реализует полноценные операции управления."),

  p("Основные операции административной панели и их связь с backend-маршрутами и сервисами приведены в таблице 17."),

  caption("Таблица 17 – Основные операции административного веб-интерфейса"),
  makeTable(T17_ROWS, T17_WIDTHS),

  p("Характер административной работы подтверждается снимками экранов, приведёнными на рисунках 14–15."),

  figureImage("main_and_access_request.png"),
  figureCaption("Рисунок 14 – Список заявок на доступ в административной панели"),

  figureImage("basic_admin_fun.png"),
  figureCaption("Рисунок 15 – Карточка пользователя в административной панели"),

  p("Дополнительные экраны административного веб-интерфейса, показывающие карточку пользователя с историей доступа и реестр предварительно разрешённых субъектов, вынесены в приложение И (рисунки И.1–И.2)."),

  p("Административный веб-интерфейс сосредоточивает операции, требующие контекста, фильтрации и журналирования, и подключается к тем же сервисам сервисного уровня, что и пользовательские каналы. Он не совпадает с внешней node-level панелью 3x-ui и не выступает её заменой: управление сервисным состоянием и правами доступа выполняется на стороне описываемой системы, а технические операции на узле достигаются вызовами интеграционного слоя из сервисов, вызываемых административными маршрутами."),

  // ── Приложение Д ────────────────────────────────────────────────────────
  ...appendixHeader("Д", "Защита прикладных контуров серверного API"),
  caption("Листинг Д.1 – Функция require_web_user"),
  ...LISTING_D1.map(listingLine),
  p(" ", { noIndent: true }),
  caption("Листинг Д.2 – Проверка административной сессии и ограничение попыток входа"),
  ...LISTING_D2.map(listingLine),

  // ── Приложение Е ────────────────────────────────────────────────────────
  ...appendixHeader("Е", "Сборка экземпляра Telegram-бота"),
  caption("Листинг Е.1 – Функция build_bot"),
  ...LISTING_E1.map(listingLine),

  // ── Приложение Ж ────────────────────────────────────────────────────────
  ...appendixHeader("Ж", "Подача заявки на доступ в Telegram-боте"),
  caption("Листинг Ж.1 – Метод submit_request класса SubscriptionAccessRequestHandler"),
  ...LISTING_J1.map(listingLine),

  // ── Приложение З ────────────────────────────────────────────────────────
  ...appendixHeader("З", "Клиент административного API"),
  caption("Листинг З.1 – Экземпляр adminApi и функции административного клиента"),
  ...LISTING_Z1.map(listingLine),

  // ── Приложение И ────────────────────────────────────────────────────────
  ...appendixHeader("И", "Дополнительные экраны административного веб-интерфейса"),
  figureImage("user_overview.png"),
  figureCaption("Рисунок И.1 – Карточка пользователя с историей доступа"),
  p(" ", { noIndent: true }),
  figureImage("registry.png"),
  figureCaption("Рисунок И.2 – Реестр предварительно разрешённых субъектов"),
];

const pageFooter = new Footer({
  children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: BODY_SIZE })],
    spacing: SP,
    indent: { firstLine: 0 },
  })],
});

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: BODY_SIZE } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: BODY_SIZE, bold: true, font: FONT },
        paragraph: { spacing: SP, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: BODY_SIZE, bold: true, font: FONT },
        paragraph: { spacing: SP, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: BODY_SIZE, bold: true, font: FONT },
        paragraph: { spacing: SP, outlineLevel: 2 },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
        margin: { top: TOP, right: RIGHT, bottom: BOTTOM, left: LEFT },
      },
    },
    footers: { default: pageFooter },
    children: content,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("chapter_3_4.docx", buf);
  console.log("chapter_3_4.docx written");
});
