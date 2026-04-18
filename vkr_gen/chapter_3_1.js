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
const BODY_SIZE = 28;      // 14pt
const TABLE_SIZE = 24;     // 12pt в таблицах
const LISTING_SIZE = 24;   // 12pt в листингах
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

function h1(text, opts = {}) {
  return p([r(text, { bold: true, allCaps: true })], {
    heading: HeadingLevel.HEADING_1,
    pageBreakBefore: opts.pageBreakBefore ?? false,
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

// ── Таблица 7: состав программной реализации ──────────────────────────────
const T7_WIDTHS = [1500, 1500, 2000, 1800, CONTENT_WIDTH - 1500 - 1500 - 2000 - 1800];
const T7_ROWS = [
  [
    "Компонент / артефакт реализации",
    "Размещение",
    "Точка входа или сборки",
    "Способ запуска",
    "Реализационная роль",
  ],
  [
    "Серверный API-сервис",
    "backend/",
    "backend/src/backend/main.py",
    "uvicorn backend.main:app, контейнер backend",
    "HTTP API веб-кабинета, административного контура, публичных и платёжных маршрутов",
  ],
  [
    "Чат-бот",
    "telegram_bot/",
    "telegram_bot/src/telegram_bot/main.py",
    "python -m telegram_bot.main, контейнер telegram_bot",
    "Событийный пользовательский канал и фоновые процессы сопровождения",
  ],
  [
    "Общий доменный слой",
    "shared/",
    "не имеет сетевой точки входа",
    "подключается как локальный Poetry-пакет",
    "Модели, репозитории, конфигурация, миграции, служебные утилиты",
  ],
  [
    "Миграционный компонент",
    "shared/alembic/",
    "alembic upgrade head",
    "одноразовый контейнер alembic",
    "Управляемое изменение схемы базы данных до запуска долгоживущих сервисов",
  ],
  [
    "Веб-интерфейс",
    "frontend/",
    "npm run build, frontend/Dockerfile",
    "сборка SPA, выдача статических ресурсов",
    "Пользовательский кабинет, административная панель, публичные страницы",
  ],
  [
    "Хранилище доменного состояния",
    "PostgreSQL",
    "сервис postgres в compose",
    "контейнер postgres",
    "Долговременное доменное состояние системы",
  ],
  [
    "Служебное хранилище",
    "Redis",
    "сервис redis в compose",
    "контейнер redis",
    "Очереди, TTL-ключи, промежуточные служебные состояния",
  ],
  [
    "Инфраструктурный контур",
    "ansible/",
    "роли и плейбуки",
    "выполняется вне прикладного контура",
    "Подготовка узлов доступа и хоста приложения",
  ],
];

// ── Листинг 1 ─────────────────────────────────────────────────────────────
const LISTING1 = [
  "[tool.poetry.dependencies]",
  "python = \"^3.11\"",
  "fastapi = \"^0.135.3\"",
  "...",
  "# Local shared dependency",
  "shared = { path = \"../shared\", develop = true }",
  "telegram-bot = { path = \"../telegram_bot\", develop = true }",
];

const content = [
  h1("3 РЕАЛИЗАЦИЯ СИСТЕМЫ"),

  p("Глава 2 завершилась обоснованием архитектурных и технологических решений проектируемой системы. На уровне программной реализации эти решения получают воплощение в виде набора исполняемых компонентов, общего доменного пакета, миграционного контура и средств воспроизводимого запуска. На этом уровне система рассматривается как единый программный комплекс, включающий исполняемые процессы, разделяемый кодовый слой и инфраструктурные элементы, необходимые для её функционирования и запуска."),

  h2("3.1 Состав программной реализации"),

  p("Программная реализация организована в виде единого репозитория с несколькими независимо запускаемыми компонентами и общим доменным пакетом. Такое устройство согласуется с требованием НФТ-8 о раздельном запуске компонентов при согласованном выпуске общих моделей и сервисов: раздельность проявляется на уровне процессов и контейнеров, а согласованность — на уровне совместного кодового слоя. Состав программной реализации сведён в таблице 7."),

  caption("Таблица 7 – Состав программной реализации"),
  makeTable(T7_ROWS, T7_WIDTHS),

  p("Представленные в таблице 7 элементы образуют три разнородные группы, которые в дальнейшем изложении принципиально различаются. Первая группа — исполняемые процессы прикладного контура: серверный API-сервис и чат-бот. Они запускаются как долгоживущие контейнеры, обслуживают разные каналы взаимодействия и образуют два основных исполняемых компонента, в которых сосредоточена прикладная логика сервисного уровня. Вторая группа — общий кодовый слой shared и миграционный компонент. Пакет shared не выступает самостоятельным исполняемым компонентом: он предоставляет единое описание доменных сущностей, репозиторный слой над ними, общие настройки и вспомогательные утилиты, разделяемые между серверным API и чат-ботом. Миграционный компонент собирается на основе того же пакета и запускается как одноразовая операция, предшествующая старту прикладных сервисов; это отделяет изменения схемы данных от их использования во время работы приложения. Третья группа — внешние для прикладного кода артефакты: PostgreSQL и Redis как инфраструктурные зависимости, веб-интерфейс как контур сборки и публикации статических ресурсов одностраничного приложения, а также инфраструктурный контур на базе Ansible, обеспечивающий подготовку окружения и воспроизводимую поставку."),

  p("Реализационная связность компонентов не исчерпывается сетевым взаимодействием. Серверный API-сервис и чат-бот используют общий пакет shared, а также разделяют часть прикладного кода, связанного с техническим применением доступа и интеграцией с внешним node-level control-plane. Эта связь оформляется через локальные зависимости Poetry и показывает, что границы между компонентами проходят на уровне исполняемых процессов, при этом полное кодовое дублирование между ними не требуется; подтверждающий фрагмент манифеста backend/pyproject.toml приведён в листинге 1."),

  caption("Листинг 1 – Локальные Poetry-зависимости пакета backend"),
  ...LISTING1.map(listingLine),

  p("Первое из двух локальных включений фиксирует общий доменный слой как разделяемую библиотеку без дублирования кода между компонентами; второе показывает, что часть прикладной логики повторно используется между исполняемыми компонентами без вынесения её в самостоятельный сетевой сервис. Такая кодовая связность не превращает систему в микросервисную схему в строгом смысле. Компоненты остаются разделёнными на уровне исполняемых процессов и контейнеров, однако используют общий кодовый слой и отдельные повторно применяемые сервисы. Поэтому изменение общих участков требует согласованного выпуска связанных компонентов и не предполагает их полностью независимого развёртывания."),

  p("Воспроизводимый запуск прикладной части системы описан средствами Docker Compose. Локальная схема (docker-compose.yml) собирает образы из локальных Dockerfile и предполагает режим разработки; производственная схема (docker-compose.prod.yml) использует заранее собранные образы, внешний файл .env.production и ограничение публикации серверного API на локальный интерфейс хоста. В обеих схемах сохраняется один и тот же перечень сервисов: backend, telegram_bot, alembic, postgres, redis и сборочный сервис веб-интерфейса. Состав программной реализации подтверждается как организацией исходного кода, так и воспроизводимой конфигурацией запуска."),

  p("Рассмотренный состав программной реализации задаёт общую рамку дальнейшего изложения. Далее последовательно раскрываются общий доменный слой, механизмы жизненного цикла доступа, прикладные каналы, инфраструктурный контур и функциональная проверка реализации."),
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
  fs.writeFileSync("chapter_3.1.docx", buf);
  console.log("chapter_3.1.docx written");
});
