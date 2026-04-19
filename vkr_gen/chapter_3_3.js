const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
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

// ── Таблица 10: источники основания выдачи ────────────────────────────────
const T10_WIDTHS = [3000, 3000, CONTENT_WIDTH - 3000 - 3000];
const T10_ROWS = [
  [
    "Основание выдачи",
    "Реализационный вход",
    "Где фиксируется решение",
  ],
  [
    "Заявка пользователя",
    "AccessRequestService.create_request",
    "AccessRequestRepository.mark_reviewed",
  ],
  [
    "Реестр предварительно разрешённых субъектов",
    "AccessRequestService._maybe_auto_approve",
    "AccessRegistryService.find_auto_approve_match",
  ],
  [
    "Оплаченный платёж",
    "PaymentWebhookService, Redis-очередь",
    "PaymentFulfillmentService, PaymentProcessingService",
  ],
];

// ── Таблица 11: типы доступа и связанные сервисы ─────────────────────────
const T11_WIDTHS = [1800, 2500, 2200, 1500, CONTENT_WIDTH - 1800 - 2500 - 2200 - 1500];
const T11_ROWS = [
  [
    "Тип доступа",
    "Основной сервис",
    "Доменное состояние",
    "Техническая запись",
    "Характер операции",
  ],
  [
    "Ограничение по сроку",
    "StandardUserSubscriptionService",
    "SubscriptionState, AccessGrant",
    "VpnClient",
    "Продление выражается в пересчёте срока действия",
  ],
  [
    "Ограничение по трафику",
    "TrafficLimitedService",
    "TrafficState, TrafficGrant, AccessGrant",
    "VpnClient",
    "Лимит связан с конкретной клиентской записью",
  ],
  [
    "Ручной отзыв",
    "AdminService совместно с профильным сервисом доступа",
    "AccessGrant, SubscriptionState или TrafficState",
    "изменение через интеграционный слой",
    "Отзыв права и изменение состояния клиента не отождествляются",
  ],
];

// ── Таблица 12: автоматические контуры ───────────────────────────────────
const T12_WIDTHS = [3000, 3000, CONTENT_WIDTH - 3000 - 3000];
const T12_ROWS = [
  [
    "Автоматический контур",
    "Что инициирует",
    "Что изменяет",
  ],
  [
    "Истечение ожидающих заявок",
    "возраст pending-заявки",
    "статус AccessRequest",
  ],
  [
    "Истечение выданных прав",
    "срок действия AccessGrant",
    "статус AccessGrant",
  ],
  [
    "Напоминания",
    "приближение срока",
    "очередь уведомлений",
  ],
  [
    "Сверка трафика",
    "данные внешней панели о расходе",
    "TrafficState",
  ],
  [
    "Платёжная очередь",
    "оплаченный платёж",
    "основание для AccessIssuanceService",
  ],
];

// ── Таблица 13: сводное соответствие переходов жизненного цикла ──────────
const T13_WIDTHS = [2400, 1000, 2400, 2200, CONTENT_WIDTH - 2400 - 1000 - 2400 - 2200];
const T13_ROWS = [
  [
    "Переход жизненного цикла",
    "Подпункт",
    "Реализующий сервис",
    "Репозиторий или внешний вызов",
    "Комментарий",
  ],
  [
    "Создание заявки",
    "3.3.1",
    "AccessRequestService.create_request",
    "AccessRequestRepository.create_request",
    "Фиксация pending-заявки, проверка дубликатов",
  ],
  [
    "Автоматическое одобрение по реестру",
    "3.3.1",
    "AccessRequestService._maybe_auto_approve",
    "AccessRegistryService.find_auto_approve_match",
    "Решение по активной записи реестра",
  ],
  [
    "Одобрение или отклонение заявки",
    "3.3.1",
    "AccessRequestService.review_request",
    "AccessRequestRepository.mark_reviewed",
    "Решение отделено от технической выдачи",
  ],
  [
    "Фиксация выданного права",
    "3.3.2",
    "AccessIssuanceService.activate_from_payload",
    "AccessGrantRepository.record_grant",
    "Право фиксируется по источнику выдачи",
  ],
  [
    "Продление доступа по сроку",
    "3.3.2",
    "StandardUserSubscriptionService",
    "SubscriptionState, VpnClient, ClientManager.update_scoped_client",
    "Обновление доменного состояния и клиента на узле",
  ],
  [
    "Выдача трафикового лимита",
    "3.3.2",
    "TrafficLimitedService",
    "TrafficGrant, TrafficState, ClientManager.update_scoped_client",
    "Лимит связан с технической клиентской записью",
  ],
  [
    "Истечение заявок и прав",
    "3.3.3",
    "репозиторные и фоновые контуры",
    "expire_stale_pending, reconcile_expired_grants",
    "Автоматический переход в сервисном состоянии",
  ],
  [
    "Синхронизация трафика",
    "3.3.3, 3.3.4",
    "TrafficLimitedSyncService",
    "TrafficState, ClientManager.get_scoped_client_usage_bytes",
    "Сервисное состояние уточняется по данным внешней панели",
  ],
  [
    "Обработка оплаченного платежа",
    "3.3.1, 3.3.3",
    "PaymentFulfillmentService, PaymentProcessingService",
    "Redis-очередь, AccessIssuanceService",
    "Платёж является основанием, но не заменяет право",
  ],
];

// ── Листинг 5: фрагмент AccessRequestService._approve_request ────────────
const LISTING5 = [
  "async def _approve_request(",
  "    self, *,",
  "    row: AccessRequest,",
  "    template_code: str,",
  "    source_type: str,",
  "    reviewed_by_actor: str,",
  "    review_note: str | None,",
  "    extra_metadata: dict[str, Any],",
  "    review_metadata: dict[str, Any],",
  ") -> AccessRequest:",
  "    plan = await self._load_plan_or_404(template_code)",
  "    self._ensure_plan_scope_enabled(str(plan.scope))",
  "",
  "    source_ref = f\"access_request:{int(row.id)}\"",
  "    await self.access_issuance_service.activate_from_payload(",
  "        payload=str(plan.payload),",
  "        source_type=source_type,",
  "        source_ref=source_ref,",
  "        user_id=int(row.user_id),",
  "        extra_metadata=extra_metadata,",
  "    )",
  "    grant = await self.access_grant_repository.get_by_source(",
  "        source_type=source_type,",
  "        source_ref=source_ref,",
  "    )",
  "    return await self.access_request_repository.mark_reviewed(",
  "        request_id=int(row.id),",
  "        status_name=\"approved\",",
  "        reviewed_by_actor=reviewed_by_actor,",
  "        review_note=review_note,",
  "        access_grant_id=(",
  "            int(grant.id) if grant is not None and grant.id is not None else None",
  "        ),",
  "        metadata=review_metadata,",
  "    )",
];

// ── Листинг В.1: расширенный activate_from_payload ───────────────────────
const LISTING_V1 = [
  "class AccessIssuanceService:",
  "    async def activate_from_payload(",
  "        self, *,",
  "        payload: str,",
  "        source_type: str,",
  "        source_ref: str | None = None,",
  "        tg_id: int | None = None,",
  "        user_id: int | None = None,",
  "        channel_override: str | None = None,",
  "        extra_metadata: dict | None = None,",
  "        duration_days_override: int | None = None,",
  "        quota_bytes_override: int | None = None,",
  "        replace_existing: bool = False,",
  "    ) -> AccessIssuanceResult:",
  "        seed = get_plan_seed_by_payload(payload)",
  "        if seed is None:",
  "            raise ValueError(f\"Unsupported access payload: {payload!r}\")",
  "",
  "        normalized_source_type = str(source_type)",
  "        normalized_source_ref = (",
  "            str(source_ref).strip() if source_ref is not None else None",
  "        )",
  "        if normalized_source_ref:",
  "            existing_grant = await self.access_grant_repository.get_by_source(",
  "                source_type=normalized_source_type,",
  "                source_ref=normalized_source_ref,",
  "            )",
  "            if existing_grant is not None:",
  "                return self._build_existing_grant_result(seed=seed)",
  "",
  "        if (seed.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED",
  "                and seed.entitlement_kind == ENTITLEMENT_KIND_TRAFFIC):",
  "            return await self._activate_traffic_limited(",
  "                seed=seed, payload=str(payload),",
  "                source_type=normalized_source_type,",
  "                source_ref=normalized_source_ref or str(payload),",
  "                tg_id=tg_id, user_id=user_id,",
  "                channel_override=channel_override,",
  "                extra_metadata=extra_metadata,",
  "                duration_days_override=duration_days_override,",
  "                quota_bytes_override=quota_bytes_override,",
  "            )",
  "",
  "        if (seed.scope == PRODUCT_SCOPE_STANDARD",
  "                and seed.entitlement_kind == ENTITLEMENT_KIND_TIME):",
  "            return await self._activate_standard(",
  "                seed=seed, payload=str(payload),",
  "                duration_days=int(seed.duration_days),",
  "                source_type=normalized_source_type,",
  "                source_ref=normalized_source_ref,",
  "                tg_id=tg_id, user_id=user_id,",
  "                channel_override=channel_override,",
  "                extra_metadata=extra_metadata,",
  "                duration_days_override=duration_days_override,",
  "                replace_existing=replace_existing,",
  "            )",
  "",
  "        raise ValueError(",
  "            f\"Unsupported access template: scope={seed.scope!r}, \"",
  "            f\"entitlement_kind={seed.entitlement_kind!r}, payload={payload!r}\"",
  "        )",
];

// ── Листинг Г.1: ClientManager.add_scoped_client (фрагмент) ──────────────
const LISTING_G1 = [
  "class ClientManager:",
  "    async def add_scoped_client(",
  "        self, *,",
  "        server_pool: dict[str, dict],",
  "        cache_namespace: str,",
  "        tg_id: int,",
  "        client_uuid: str,",
  "        email: str,",
  "        sub_id: str,",
  "        expires_at: int,",
  "        total_bytes: int = 0,",
  "    ) -> None:",
  "        async def handler(session, inbound_url, server_name, inbound_ids):",
  "            try:",
  "                expected_emails = {",
  "                    self._build_inbound_email(email, inbound_id)",
  "                    for inbound_id in inbound_ids",
  "                }",
  "                for inbound_id in inbound_ids:",
  "                    current_email = self._build_inbound_email(email, inbound_id)",
  "                    client_template = build_client_template(inbound_id)",
  "                    data = self.jsonutils.update_post_client_json(",
  "                        tg_id, client_template, client_uuid,",
  "                        current_email, expires_at, sub_id,",
  "                        total_bytes=total_bytes,",
  "                    )",
  "                    url = inbound_url + \"addClient\"",
  "                    response = await session.post(",
  "                        url, headers=self.headers, json=data)",
  "                    response.raise_for_status()",
  "",
  "                    response_data = response.json()",
  "                    if not response_data.get(\"success\", True):",
  "                        if self._is_expected_duplicate_email_error(",
  "                            response_data, expected_emails,",
  "                        ):",
  "                            logger.warning(",
  "                                f\"[{server_name}] Duplicate scoped email \"",
  "                                f\"for tg_id={tg_id}; already provisioned.\"",
  "                            )",
  "                            continue",
  "                        raise Exception(",
  "                            f\"[{server_name}] API error: {response_data}\"",
  "                        )",
  "            except Exception as err:",
  "                logger.error(",
  "                    f\"[{server_name}] add_scoped_client handler: {err}\"",
  "                )",
  "                raise",
  "",
  "        await self._process_on_server_pool(",
  "            handler,",
  "            server_pool=server_pool,",
  "            cache_namespace=cache_namespace,",
  "        )",
];

const content = [
  h2("3.3 Реализация жизненного цикла доступа"),

  p("Жизненный цикл доступа в реализации представлен связкой нескольких сервисных контуров, а не одним универсальным модулем. Контур заявок и решений, контур фиксации выданных прав, временной и трафиковый контуры доступа, платёжный контур и интеграционный слой совместно обеспечивают переход от основания выдачи к техническому применению доступа на узле. Такое распределение сохраняет на уровне кода различие между заявкой как намерением, выданным правом как основанием предоставления доступа, текущим подписочным или трафиковым состоянием и клиентской записью на узле."),

  h3("3.3.1 Реализация оснований выдачи и принятия решения"),

  p("Основание доступа в реализации отделено от технического применения. Заявка, совпадение по реестру предварительно разрешённых субъектов и подтверждённый платёж выступают как различные источники запуска доменного перехода, по результатам которого фиксируется право доступа и инициируется его техническое применение."),

  p("Заявочный контур реализован в AccessRequestService. Метод create_request принимает запрос пользователя, проверяет наличие активных ограничений, устраняет устаревшие ожидающие заявки через общий метод expire_stale_pending и создаёт запись со статусом pending. Репозиторный класс AccessRequestRepository отвечает за создание заявки, поиск дубликатов и изменение статуса при рассмотрении. Рассмотрение реализовано методом review_request: допустимыми решениями являются одобрение и отклонение, при отклонении сохраняются субъект решения, статус, время и комментарий, а при одобрении управление передаётся общему сервису выдачи через AccessIssuanceService.activate_from_payload и связанный с ним репозиторий выданных прав."),

  p("Реестр предварительно разрешённых субъектов реализован в AccessRegistryService и AccessRegistryRepository. При создании заявки AccessRequestService обращается к вспомогательному методу _maybe_auto_approve, который ищет активное совпадение через find_auto_approve_match и, при наличии такого совпадения, оформляет одобрение от имени реестрового источника решения. Запись реестра используется как источник решения о выдаче доступа, после чего общий сервис выдачи формирует AccessGrant и запускает соответствующий профильный контур."),

  p("Платёжный контур описывается как асинхронный источник основания. PaymentWebhookService принимает изменение статуса платежа, обновляет запись PaymentOrder и при оплаченном статусе помещает событие в Redis-очередь. Фактическая выдача выполняется позднее: PaymentFulfillmentService извлекает событие из очереди и через PaymentProcessingService передаёт его в AccessIssuanceService.activate_from_payload с указанием source_type=\"payment\" и идентификатора платежа в качестве source_ref. Разделение веб-приёма события, очереди и обработчика позволяет повторять обработку при сбое и снимает прямую зависимость выдачи доступа от момента получения платёжного уведомления."),

  p("Сопоставление источников основания, реализационных входов и мест фиксации решения приведено в таблице 10."),

  caption("Таблица 10 – Источники основания выдачи доступа"),
  makeTable(T10_ROWS, T10_WIDTHS),

  p("Переход от административного решения к выдаче доступа реализуется в одном методе; фрагмент, подтверждающий эту границу, приведён в листинге 3. В теле метода решение о шаблоне доступа преобразуется в вызов AccessIssuanceService.activate_from_payload, результат выдачи связывается с заявкой через идентификатор выданного права, а статус заявки изменяется на approved через AccessRequestRepository.mark_reviewed."),

  caption("Листинг 3 – Метод _approve_request сервиса AccessRequestService"),
  ...LISTING5.map(listingLine),

  h3("3.3.2 Реализация технической выдачи и сопровождения доступа"),

  p("Полученное основание превращается в доменное право и техническую клиентскую запись в AccessIssuanceService. Метод activate_from_payload принимает сведения об источнике, пользователе и шаблоне доступа, разрешает шаблон через каталог плановых сидов, проверяет идемпотентность по паре (source_type, source_ref) через AccessGrantRepository.get_by_source и выбирает дальнейший контур в зависимости от scope и entitlement_kind. Расширенный фрагмент метода activate_from_payload сервиса AccessIssuanceService приведён в приложении В (листинг В.1)."),

  p("Фиксация выданного права выполняется через AccessGrantRepository.record_grant. Операция организована идемпотентно по источнику выдачи, что позволяет повторно обрабатывать административное одобрение или платёжное событие без дублирования права доступа."),

  p("Для доступа с ограничением по сроку техническое применение выполняется через StandardUserSubscriptionService и связанный с ним сервис подписочного сопровождения. При активации пересчитывается новое значение expires_at, при отсутствии активной клиентской записи создаётся VpnClient и соответствующая клиентская запись на узле через интеграционный слой, при наличии записи обновляется срок действия у существующего клиента. Подписочное состояние пользователя фиксируется в SubscriptionState."),

  p("Для доступа с ограничением по трафику применяется TrafficLimitedService. Каждая выдача оформляется отдельной записью TrafficGrant, а текущее состояние и выделенный лимит ведутся в TrafficState. Временной и трафиковый контуры различаются носителем состояния: в первом случае оно связано с пользователем, во втором — с конкретной клиентской записью."),

  p("Отзыв доступа реализован как обратный переход жизненного цикла. В административном контуре он инициируется через AdminService, который обращается к профильному сервису доступа. Для стандартного доступа StandardUserSubscriptionService.revoke_access переводит соответствующие права в состояние revoked; для трафикового доступа TrafficLimitedService.revoke_access_for_user изменяет текущее состояние лимита и фиксирует причину. Фиксация доменного состояния и техническое изменение клиента на узле остаются связанными, но не тождественными операциями."),

  p("Соответствие типов доступа основным сервисам, доменным состояниям и техническим клиентским записям приведено в таблице 11."),

  caption("Таблица 11 – Реализация временного и трафикового доступа, а также ручного отзыва"),
  makeTable(T11_ROWS, T11_WIDTHS),

  h3("3.3.3 Реализация автоматических переходов и фоновых контуров"),

  p("Часть переходов жизненного цикла выполняется без непосредственного действия пользователя или администратора. Они реализованы как операции репозиториев, вызываемые в фоновых задачах процесса Telegram-бота, и как асинхронные обработчики служебных очередей в Redis."),

  p("Для заявок автоматический переход реализован в методе expire_stale_pending: он находит pending-заявки с истёкшим сроком ожидания и переводит их в соответствующий статус, после чего уведомления о рассмотрении направляются через сервис оповещений. Для выданных прав используется AccessGrantRepository.reconcile_expired_grants: активные записи, у которых expires_at уже наступил, переводятся в состояние expired, а в метаданные вносится время перехода. Оба метода выполняются в фоновых задачах и при подготовке операций выдачи, что обеспечивает согласованность сервисного состояния без ожидания внешних подтверждений."),

  p("Фоновые контуры сопровождения организованы в процессе Telegram-бота. В telegram_bot/main.py при включённых функциональных флагах запускаются задачи напоминаний о сроке действия доступа через SubscriptionReminderService и ReminderQueueService, задачи жизненного цикла доступа, задачи платёжной обработки через PaymentFulfillmentService и PaymentStatusUpdateService, а также задача синхронизации трафикового доступа через TrafficLimitedSyncService. Запуск таких задач относится к организации фоновых процессов и не сводится к интерфейсной функции Telegram-бота."),

  p("Синхронизация трафикового состояния реализована в TrafficLimitedSyncService. Метод получения расхода обращается к ClientManager.get_scoped_client_usage_bytes, после чего вспомогательная операция обновления состояния уточняет использованный объём, пересчитывает остаток и фиксирует время последней сверки в TrafficState. Формулируется такой контур осторожно: он поддерживает актуализацию сервисного состояния на основании данных внешнего control-plane, но не выступает безусловной гарантией автоматического отзыва доступа при исчерпании квоты."),

  p("Платёжный фоновой контур оформлен как асинхронная доставка основания до общего сервиса выдачи. PaymentWebhookService помещает событие оплаты в Redis-очередь, PaymentFulfillmentService извлекает очередное событие в методе process_queue_once, валидирует его и передаёт в PaymentProcessingService, который, в свою очередь, вызывает AccessIssuanceService.activate_from_payload. Промежуточное звено в виде очереди и отдельного обработчика позволяет повторно обрабатывать событие при сбое, сохраняет идемпотентность по идентификатору платежа и исключает прямую зависимость сервиса выдачи доступа от момента поступления платёжного уведомления."),

  p("Перечень автоматических контуров, их инициаторов и изменяемых состояний приведён в таблице 12."),

  caption("Таблица 12 – Автоматические контуры жизненного цикла доступа"),
  makeTable(T12_ROWS, T12_WIDTHS),

  p("Автоматические контуры поддерживают актуальность сервисного состояния, но не во всех случаях предполагают мгновенное совпадение с состоянием внешнего узла."),

  h3("3.3.4 Интеграция с внешним node-level control-plane"),

  p("Граница между сервисным уровнем и внешней панелью управления узлами доступа реализована в интеграционном слое. Его задача состоит в том, чтобы преобразовать доменное решение в операции создания и изменения клиентской записи на узле, не выходя на уровень передачи пользовательского трафика."),

  p("Интеграционный слой размещён в кодовой базе чат-бота, но используется шире собственного пользовательского канала и участвует в реализации сервисного контура в целом. Такое размещение отражается в описании как общий используемый интеграционный слой в кодовой базе бота, а не как самостоятельный сетевой сервис и не как независимый общий пакет."),

  p("APIConnection инкапсулирует соединение с API внешней панели: формирование базового адреса, авторизацию, повторную попытку входа при ошибках и поддержание клиентской сессии. ClientManager реализует операции с клиентскими записями: создание клиента методом add_scoped_client, обновление срока действия и трафикового лимита методом update_scoped_client, проверку наличия клиента, получение статистики потребления через get_scoped_client_usage_bytes, удаление клиента в отдельных сценариях и синхронизацию сведений о размещении клиента в топологии узлов. Фрагмент метода add_scoped_client класса ClientManager приведён в приложении Г (листинг Г.1) и подтверждает границу интеграции, в том числе обход пула серверов и входящих точек, применение шаблона клиентской записи и обработку ожидаемых ответов внешнего API."),

  p("Обработка ошибок внешнего API выполняется без преувеличений относительно согласованности. Вызовы ClientManager перебирают пул серверов и входящих точек, логируют ошибки отдельных узлов и собирают их в агрегированное исключение; отдельные ожидаемые ситуации, например дублирование email или отсутствие client id при обновлении, обрабатываются специальными ветками без прерывания вышестоящего контура. Такая форма обработки снижает расхождение между сервисным и техническим состояниями, но не позволяет утверждать, что внешний API всегда доступен или что доменное и техническое состояние синхронизируются мгновенно."),

  p("Для стандартного доступа техническое применение проходит через StandardUserSubscriptionService: при отсутствии активного VpnClient создаётся новая клиентская запись, при наличии — обновляется существующая. Для трафикового доступа техническое создание клиента и установка лимита выполняются через TrafficLimitedService и связанный с ним сервис подготовки трафикового клиента. После изменения клиента на узле инициируется синхронизация размещения через sync_v2_scoped_topology и VpnTopologyService, что поддерживает согласованность записей VpnClientDeployment, VpnAccessPoint и VpnControlPlane с фактическим состоянием пула узлов; возможные ошибки синхронизации топологии логируются и не трактуются как полная гарантия обновления."),

  p("Эти операции снижают расхождение между сервисным и техническим состояниями, но не дают оснований описывать интеграцию как мгновенно согласованную во всех ситуациях. При недоступности внешнего API или ошибках отдельных узлов сервисный уровень сохраняет зафиксированное доменное решение и допускает повторное выполнение технической операции."),

  p("Итоговое соответствие переходов жизненного цикла реализующим сервисам, репозиториям и внешним вызовам сведено в таблице 13."),

  caption("Таблица 13 – Соответствие переходов жизненного цикла реализационным артефактам"),
  makeTable(T13_ROWS, T13_WIDTHS),

  p("В реализации жизненный цикл доступа воплощён как связка доменных сервисов, репозиториев, фоновых контуров и интеграционного слоя. Решение о выдаче отделено от фиксации права и от технического применения на узле; автоматические переходы опираются на операции сервисного уровня и служебное состояние; интеграционный слой ограничивает зону ответственности системы операциями над клиентскими записями."),

  // ── Приложение В ────────────────────────────────────────────────────────
  new Paragraph({
    children: [r("Приложение В")],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
    pageBreakBefore: true,
  }),
  new Paragraph({
    children: [r("Метод activate_from_payload сервиса AccessIssuanceService", { bold: true })],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
  }),
  p(" ", { noIndent: true }),
  caption("Листинг В.1 – Метод activate_from_payload сервиса AccessIssuanceService"),
  ...LISTING_V1.map(listingLine),

  // ── Приложение Г ────────────────────────────────────────────────────────
  new Paragraph({
    children: [r("Приложение Г")],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
    pageBreakBefore: true,
  }),
  new Paragraph({
    children: [r("Метод add_scoped_client интеграционного слоя ClientManager", { bold: true })],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
  }),
  p(" ", { noIndent: true }),
  caption("Листинг Г.1 – Метод add_scoped_client класса ClientManager"),
  ...LISTING_G1.map(listingLine),
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
  fs.writeFileSync("chapter_3.3.docx", buf);
  console.log("chapter_3.3.docx written");
});
