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

// ── Таблица 8: группы доменных моделей ────────────────────────────────────
const T8_WIDTHS = [2300, 3700, CONTENT_WIDTH - 2300 - 3700];
const T8_ROWS = [
  [
    "Доменный контур",
    "Модели в shared/src/shared/models/",
    "Реализационное назначение",
  ],
  [
    "Пользователь и идентификация",
    "AppUser, TelegramAccount, WebAccount, IdentityLinkToken, WebSession, WebAuthChallenge, UserProfile",
    "Отделение субъекта доступа от каналов входа и процедур связывания учётных записей",
  ],
  [
    "Заявки и права доступа",
    "AccessRequest, AccessRegistryEntry, AccessGrant",
    "Фиксация обращения пользователя, заранее разрешённого основания и выданного права доступа",
  ],
  [
    "Подписка и трафик",
    "SubscriptionState, SubscriptionGrant, TrafficState, TrafficGrant",
    "Разделение текущего временного состояния пользователя и технических трафиковых ограничений клиента",
  ],
  [
    "Технический контур доступа",
    "VpnLocation, VpnControlPlane, VpnAccessPoint, VpnClient, VpnClientDeployment",
    "Связывание доменного решения с внешним node-level control-plane и конкретными точками доступа",
  ],
  [
    "Платежи и вспомогательные основания",
    "Plan, PaymentOrder, PaymentAttempt, PaymentWebhookEvent, PromoCode, PromoRedemption, ReferralEdge, ReferralReward, ReferralRewardRule",
    "Описание оплачиваемых и поощрительных оснований предоставления временных прав",
  ],
  [
    "Аудит",
    "AdminAuditLog",
    "Фиксация административных действий и связанных с ними контекстов",
  ],
];

// ── Таблица 9: разделение хранилищ и миграционного контура ───────────────
const T9_WIDTHS = [1600, 2800, 2000, CONTENT_WIDTH - 1600 - 2800 - 2000];
const T9_ROWS = [
  [
    "Контур",
    "Артефакты проекта",
    "Тип состояния",
    "Роль в реализации",
  ],
  [
    "PostgreSQL",
    "shared/src/shared/config/database/engine.py, session.py; сервис postgres в compose",
    "долговременное доменное состояние",
    "Хранение пользователей, заявок, прав доступа, подписочных и трафиковых записей, платежей, топологии и аудита",
  ],
  [
    "Redis",
    "shared/src/shared/utils/async_redis_client.py; reminder_queue_service.py; payment_queue_service.py; сервис redis в compose",
    "временное служебное состояние",
    "Очереди напоминаний и платёжных событий, TTL-ключи, дедупликация, служебные блокировки, отдельные кэшируемые ответы",
  ],
  [
    "Alembic",
    "shared/alembic/env.py; shared/alembic/versions/*.py; сервис alembic в compose",
    "управляемая эволюция схемы",
    "Согласованное изменение структуры таблиц до запуска серверного API и чат-бота",
  ],
];

// ── Листинг 2: SQLModel-модель AccessGrant (фрагмент) ─────────────────────
const LISTING2 = [
  "class AccessGrant(SQLModel, table=True):",
  "    __tablename__ = \"access_grants\"",
  "    __table_args__ = (",
  "        UniqueConstraint(\"source_type\", \"source_ref\",",
  "                         name=\"uq_access_grants_source\"),",
  "    )",
  "",
  "    user_id: int = Field(sa_column=Column(",
  "        BigInteger, ForeignKey(\"users.id\", ondelete=\"CASCADE\"),",
  "        nullable=False))",
  "    entitlement_kind: str = Field(sa_column=Column(Text, nullable=False))",
  "    source_type: str = Field(sa_column=Column(Text, nullable=False))",
  "    source_ref: str | None = Field(default=None,",
  "        sa_column=Column(Text, nullable=True))",
  "    status: str = Field(sa_column=Column(Text, nullable=False))",
  "    expires_at: datetime | None = Field(default=None,",
  "        sa_column=Column(DateTime(timezone=True), nullable=True))",
  "    quota_bytes: int | None = Field(default=None,",
  "        sa_column=Column(BigInteger, nullable=True))",
];

// ── Листинг А.1: метод record_grant специализированного репозитория ──────
const LISTING3 = [
  "class AccessGrantRepository:",
  "    async def record_grant(",
  "        self, *,",
  "        user_id: int,",
  "        template_code: str,",
  "        scope: str,",
  "        entitlement_kind: str,",
  "        source_type: str,",
  "        source_ref: str | None,",
  "        expires_at: datetime | None,",
  "        quota_bytes: int | None,",
  "        granted_by_user_id: int | None = None,",
  "        status: str = \"active\",",
  "        metadata: dict | None = None,",
  "    ) -> AccessGrant:",
  "        async with get_db_session() as session:",
  "            if source_ref:",
  "                existing = (await session.execute(",
  "                    select(AccessGrant).where(",
  "                        AccessGrant.source_type == str(source_type),",
  "                        AccessGrant.source_ref == str(source_ref),",
  "                    )",
  "                )).scalar_one_or_none()",
  "                if existing is not None:",
  "                    return existing",
  "",
  "            plan = (await session.execute(",
  "                select(Plan).where(",
  "                    Plan.code == str(template_code).strip().lower())",
  "            )).scalar_one_or_none()",
  "",
  "            now = datetime.now(timezone.utc)",
  "            grant = AccessGrant(",
  "                user_id=int(user_id),",
  "                granted_by_user_id=(",
  "                    int(granted_by_user_id)",
  "                    if granted_by_user_id is not None else None),",
  "                plan_id=int(plan.id) if plan is not None else None,",
  "                template_code=str(template_code).strip().lower(),",
  "                scope=str(scope).strip().lower(),",
  "                entitlement_kind=str(entitlement_kind).strip().lower(),",
  "                source_type=str(source_type).strip().lower(),",
  "                source_ref=str(source_ref).strip() if source_ref else None,",
  "                status=str(status).strip().lower(),",
  "                expires_at=expires_at,",
  "                quota_bytes=quota_bytes,",
  "                created_at=now,",
  "                activated_at=now,",
  "                revoked_at=None,",
  "                metadata_json=dict(metadata or {}),",
  "            )",
  "            session.add(grant)",
  "            await session.commit()",
  "            await session.refresh(grant)",
  "            return grant",
];

// ── Листинг Б.1: Alembic-миграция access_grants (полностью) ───────────────
const LISTING4 = [
  "\"\"\"add access grants",
  "",
  "Revision ID: c74d9b2e1a6f",
  "Revises: b806a150f35d",
  "Create Date: 2026-04-09 19:25:00.000000",
  "\"\"\"",
  "from typing import Sequence, Union",
  "",
  "from alembic import op",
  "import sqlalchemy as sa",
  "",
  "",
  "revision: str = \"c74d9b2e1a6f\"",
  "down_revision: Union[str, None] = \"b806a150f35d\"",
  "branch_labels: Union[str, Sequence[str], None] = None",
  "depends_on: Union[str, Sequence[str], None] = None",
  "",
  "",
  "def upgrade() -> None:",
  "    op.create_table(",
  "        \"access_grants\",",
  "        sa.Column(\"id\", sa.Integer(), nullable=False),",
  "        sa.Column(\"user_id\", sa.BigInteger(), nullable=False),",
  "        sa.Column(\"granted_by_user_id\", sa.BigInteger(), nullable=True),",
  "        sa.Column(\"plan_id\", sa.BigInteger(), nullable=True),",
  "        sa.Column(\"template_code\", sa.Text(), nullable=False),",
  "        sa.Column(\"scope\", sa.Text(), nullable=False),",
  "        sa.Column(\"entitlement_kind\", sa.Text(), nullable=False),",
  "        sa.Column(\"source_type\", sa.Text(), nullable=False),",
  "        sa.Column(\"source_ref\", sa.Text(), nullable=True),",
  "        sa.Column(\"status\", sa.Text(), nullable=False),",
  "        sa.Column(\"expires_at\", sa.DateTime(timezone=True), nullable=True),",
  "        sa.Column(\"quota_bytes\", sa.BigInteger(), nullable=True),",
  "        sa.Column(\"created_at\", sa.DateTime(timezone=True), nullable=False),",
  "        sa.Column(\"activated_at\", sa.DateTime(timezone=True), nullable=True),",
  "        sa.Column(\"metadata\", sa.JSON(), nullable=False),",
  "        sa.ForeignKeyConstraint([\"granted_by_user_id\"], [\"users.id\"],",
  "                                ondelete=\"SET NULL\"),",
  "        sa.ForeignKeyConstraint([\"plan_id\"], [\"plans.id\"],",
  "                                ondelete=\"SET NULL\"),",
  "        sa.ForeignKeyConstraint([\"user_id\"], [\"users.id\"],",
  "                                ondelete=\"CASCADE\"),",
  "        sa.PrimaryKeyConstraint(\"id\"),",
  "        sa.UniqueConstraint(\"source_type\", \"source_ref\",",
  "                            name=\"uq_access_grants_source\"),",
  "    )",
  "    op.create_index(op.f(\"ix_access_grants_user_id\"),",
  "                    \"access_grants\", [\"user_id\"], unique=False)",
  "    op.create_index(op.f(\"ix_access_grants_status\"),",
  "                    \"access_grants\", [\"status\"], unique=False)",
  "    op.create_index(op.f(\"ix_access_grants_source_type\"),",
  "                    \"access_grants\", [\"source_type\"], unique=False)",
  "",
  "",
  "def downgrade() -> None:",
  "    op.drop_index(op.f(\"ix_access_grants_source_type\"),",
  "                  table_name=\"access_grants\")",
  "    op.drop_index(op.f(\"ix_access_grants_status\"),",
  "                  table_name=\"access_grants\")",
  "    op.drop_index(op.f(\"ix_access_grants_user_id\"),",
  "                  table_name=\"access_grants\")",
  "    op.drop_table(\"access_grants\")",
];

const content = [
  h2("3.2 Реализация доменного слоя и хранилища данных"),

  p("Общая предметная модель серверного API, чат-бота и миграционного контура реализована в виде общего Poetry-пакета shared, подключаемого локальной зависимостью к прикладным компонентам. В этом пакете сосредоточены доменные сущности, репозиторный слой, конфигурация и миграционный контур, что позволяет использовать единую схему данных и единый понятийный аппарат при раздельном запуске компонентов."),

  p("Структура пакета shared отражает разделение ответственности: каталог models/ содержит SQLModel-описания предметных сущностей, infrastructure/ — репозитории и инфраструктурные сервисы доступа к данным, config/ — загрузку параметров и настройки подключения к базе и Redis, utils/ — общие утилиты (Redis-клиент, JWT, временные преобразования, токены связывания, контекст логирования), constants/ и product_constants.py — значения доменных статусов, типов доступа и платёжных сценариев, alembic/ — миграционный контур. Такое разделение обеспечивает доменную целостность при раздельном запуске компонентов: серверный API и чат-бот работают с одной схемой данных и одними предметными объектами и различаются каналами взаимодействия."),

  p("Доменные сущности сгруппированы по предметным контурам, каждая группа реализована самостоятельным модулем в shared/src/shared/models/. Распределение моделей по группам приведено в таблице 8."),

  caption("Таблица 8 – Группы доменных моделей в пакете shared"),
  makeTable(T8_ROWS, T8_WIDTHS),

  p("Доменный слой реализован на базе типизированных SQLModel-классов, совмещающих описание сущности, её полей и отображения на таблицу базы данных. Такой подход позволяет использовать единый класс одновременно как носитель предметной структуры и как основу ORM-отображения, не дублируя описание между слоем данных и прикладным кодом. В ключевых сущностях жизненного цикла доступа фиксируются связи между пользователем, основанием выдачи, видом ограничения, сроком действия и служебными метаданными."),

  p("Центральная для жизненного цикла доступа сущность AccessGrant демонстрирует форму такого описания: уникальное ограничение по паре (source_type, source_ref) обеспечивает идемпотентность по источнику выдачи, поля entitlement_kind и quota_bytes разделяют временное и трафиковое ограничение, expires_at и status фиксируют срок действия и текущее состояние права. Соответствующий фрагмент модели приведён в листинге 2."),

  caption("Листинг 2 – Фрагмент SQLModel-модели AccessGrant"),
  ...LISTING2.map(listingLine),

  p("Работа с предметными данными вынесена из интерфейсных обработчиков в репозиторный слой shared/src/shared/infrastructure/. Общий способ работы с асинхронной сессией задан базовым классом, а значимые доменные операции размещены в специализированных репозиториях: AccessGrantRepository, AccessRequestRepository, AccessRegistryRepository, PaymentRepository, TelegramUserRepository, ReferralRepository, PromoCodeRepository, а также сервис VpnTopologyService. Каждый такой класс инкапсулирует операции своего предметного контура и обращается к базе данных через единый сессионный контекст. Типичная форма предметной операции включает проверку идемпотентности по источнику, формирование SQLModel-объекта и его фиксацию в базе в пределах одной транзакции; полный листинг метода record_grant репозитория AccessGrantRepository приведён в приложении А (листинг А.1)."),

  p("Конфигурационный слой общего пакета решает две задачи. Во-первых, он обеспечивает загрузку параметров окружения и их типизированное представление для прикладных контуров: пользовательского, административного, платёжного, почтового и фонового. Во-вторых, он задаёт единый способ подключения к PostgreSQL и Redis, благодаря чему серверный API и чат-бот используют одну и ту же конфигурацию хранилищ и единый сессионный контекст. Соответствующие модули сосредоточены в shared/src/shared/config/ (загрузка и настройки, подключение к базе, сессия) и shared/src/shared/utils/async_redis_client.py."),

  p("Хранение состояния в реализации разведено на три контура: долговременное доменное состояние, временное служебное состояние и управляемое изменение схемы данных. Разделение артефактов и ролей сведено в таблице 9."),

  caption("Таблица 9 – Разделение хранилищ и миграционного контура"),
  makeTable(T9_ROWS, T9_WIDTHS),

  p("PostgreSQL выступает основным хранилищем доменного состояния. В нём сосредоточены пользователи и каналы идентификации, заявки и выданные права доступа, подписочные и трафиковые записи, топология узлов и клиентские записи, платежи, промокоды, рефералы и аудит. Подключение описано асинхронным SQLAlchemy engine в shared/src/shared/config/database/engine.py, единый сессионный контекст в shared/src/shared/config/database/session.py используется всеми репозиториями, а сервис postgres в compose-файлах фиксирует хранилище на уровне воспроизводимого запуска."),

  p("Redis занимает вспомогательную позицию: очереди напоминаний и платёжных событий (reminder_queue_service.py, payment_queue_service.py), дедупликационные ключи при обработке платёжных webhook, TTL-состояния сессий и попыток входа, служебные блокировки фоновых процессов, кэширование отдельных подписочных ответов. Redis поддерживает временные процессы и снижает связность фоновых операций с синхронными запросами, тогда как каноническая история доступа сохраняется в PostgreSQL."),

  p("Эволюция схемы данных реализована через Alembic. В shared/alembic/env.py вызывается register_models(), после чего SQLModel.metadata используется как целевая метадата миграций; для выполнения операций DDL асинхронная строка подключения преобразуется в синхронную. Миграционная цепочка отражает поэтапное развитие доменной модели: от базовой схемы пользователей, подписок, платежей, VPN-топологии и аудита — к появлению сущности выданного права доступа, затем заявок на доступ, далее реестра предварительно разрешённых субъектов и, наконец, к расширению полей жизненного цикла доступа. Полный текст миграции, соответствующей созданию таблицы access_grants, приведён в приложении Б (листинг Б.1)."),

  p("Миграционный контур отделён от долгоживущих сервисов на уровне Docker Compose: сервис alembic выполняет alembic upgrade head как одноразовую операцию, а сервисы backend и telegram_bot зависят от его успешного завершения. Производственная схема сохраняет тот же принцип на базе заранее собранных образов и файла .env.production. Изменение схемы данных выполняется до запуска прикладных процессов и исключает одновременное обновление структуры таблиц и обслуживания пользовательских запросов."),

  p("Тем самым общий доменный слой в реализации выступает не вспомогательным набором моделей, а единым основанием для работы прикладных компонентов, фиксации состояний доступа и согласованного изменения схемы данных."),

  // ── Приложение А ────────────────────────────────────────────────────────
  new Paragraph({
    children: [r("Приложение А")],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
    pageBreakBefore: true,
  }),
  new Paragraph({
    children: [r("Метод record_grant репозитория AccessGrantRepository", { bold: true })],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
  }),
  p(" ", { noIndent: true }),
  caption("Листинг А.1 – Метод record_grant класса AccessGrantRepository"),
  ...LISTING3.map(listingLine),

  // ── Приложение Б ────────────────────────────────────────────────────────
  new Paragraph({
    children: [r("Приложение Б")],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
    pageBreakBefore: true,
  }),
  new Paragraph({
    children: [r("Alembic-миграция создания таблицы access_grants", { bold: true })],
    spacing: SP,
    indent: { firstLine: 0 },
    alignment: AlignmentType.CENTER,
  }),
  p(" ", { noIndent: true }),
  caption("Листинг Б.1 – Миграция c74d9b2e1a6f_add_access_grants"),
  ...LISTING4.map(listingLine),
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
  fs.writeFileSync("chapter_3.2.docx", buf);
  console.log("chapter_3.2.docx written");
});
