const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
        TableOfContents, PageNumber, SectionType } = require('docx');
const fs = require('fs');

const mm = (v) => Math.round(v / 25.4 * 1440);
const LEFT  = mm(30);
const RIGHT = mm(15);
const TOP   = mm(20);
const BOT   = mm(20);
const INDENT = mm(12.5);

const FONT = "Times New Roman";
const SZ   = 28;
const SP   = { line: 360, lineRule: "auto", before: 0, after: 0 };

const pageMargin = { top: TOP, right: RIGHT, bottom: BOT, left: LEFT };
const pageSize   = { width: 11906, height: 16838 };

function run(text, opts = {}) {
  return new TextRun({ text, font: FONT, size: SZ, ...opts });
}

function para(children, paraOpts = {}) {
  return new Paragraph({
    children: Array.isArray(children) ? children : [run(children)],
    spacing: SP,
    indent: { firstLine: INDENT },
    ...paraOpts,
  });
}

function structHead(text) {
  return new Paragraph({
    children: [run(text, { bold: true, allCaps: true })],
    alignment: AlignmentType.CENTER,
    spacing: SP,
    indent: { firstLine: 0 },
    pageBreakBefore: true,
  });
}

function h1(numText) {
  return new Paragraph({
    children: [run(numText, { bold: true, allCaps: true })],
    spacing: SP,
    indent: { firstLine: INDENT },
    pageBreakBefore: true,
    heading: HeadingLevel.HEADING_1,
  });
}

function h2(numText) {
  return new Paragraph({
    children: [run(numText, { bold: true })],
    spacing: SP,
    indent: { firstLine: INDENT },
    heading: HeadingLevel.HEADING_2,
  });
}

function placeholder(text) {
  return para(text);
}

function twoColTable(header1, header2) {
  const brd = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
  const brdAll = { top: brd, bottom: brd, left: brd, right: brd };
  const cw = 11906 - LEFT - RIGHT;
  const c1 = Math.round(cw * 0.35);
  const c2 = cw - c1;
  const cell = (text, bold = false, width) => new TableCell({
    borders: brdAll,
    width: { size: width, type: WidthType.DXA },
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    children: [new Paragraph({
      children: [run(text, { bold })],
      spacing: SP,
      indent: { firstLine: 0 },
    })],
  });
  return new Table({
    width: { size: cw, type: WidthType.DXA },
    columnWidths: [c1, c2],
    rows: [
      new TableRow({ children: [cell(header1, true, c1), cell(header2, true, c2)] }),
      new TableRow({ children: [cell("", false, c1), cell("", false, c2)] }),
      new TableRow({ children: [cell("", false, c1), cell("", false, c2)] }),
    ],
  });
}

const pageFooter = new Footer({
  children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SZ })],
    spacing: SP,
    indent: { firstLine: 0 },
  })],
});

const emptyFooter = new Footer({ children: [new Paragraph({ children: [] })] });

function pb(children, opts = {}) {
  const ch = typeof children === 'string' ? [run(children)] : children;
  return new Paragraph({
    children: ch,
    spacing: SP,
    indent: { firstLine: INDENT },
    alignment: AlignmentType.JUSTIFIED,
    ...opts,
  });
}

function task(num, text) {
  return new Paragraph({
    children: [run(`${num}) ${text}`)],
    spacing: SP,
    indent: { firstLine: INDENT },
    alignment: AlignmentType.JUSTIFIED,
  });
}

function ref(num, text) {
  return new Paragraph({
    children: [run(`${num}. ${text}`)],
    spacing: SP,
    indent: { firstLine: INDENT },
    alignment: AlignmentType.JUSTIFIED,
  });
}

function introContent() {
  return [
    pb('Переход к дистанционным форматам занятости, ускорившийся в 2020–2021 годах, изменил не только организацию труда, но и требования к сетевой инфраструктуре предприятий. По данным Eurostat, доля занятых в странах Европейского союза в возрасте 20–64 лет, регулярно работающих из дома, выросла с 5,5% в 2019 году до 12,3% в 2020-м и достигла 13,5% в 2021-м — прирост более чем вдвое за два года [1]. Европейская комиссия в техническом докладе JRC120945 характеризует этот сдвиг как структурный [2], а Международная организация труда в докладе «Working from Home: From Invisibility to Decent Work» (2021) указывает на необходимость соответствующей инфраструктуры безопасного подключения [3]. По оценке Бюро статистики труда США (BLS, 2024), рост доли дистанционной занятости устойчиво сохраняется в постпандемийный период [4].'),
    pb('Следствием этого структурного перехода стал устойчивый рост требований к средствам защищённого удалённого доступа. NIST в специальном издании SP 800-207 описывает архитектурную парадигму нулевого доверия (Zero Trust Architecture, ZTA), при которой доступ к ресурсам предоставляется по результату явных функций аутентификации и авторизации вне зависимости от сетевого местоположения субъекта [5]. Наряду с требованиями к защищённости канала возрастает потребность в управлении доступом на организационном уровне: необходимо фиксировать основания выдачи, контролировать сроки и ограничения, обеспечивать отзыв доступа и сохранять историю операций.'),
    pb('Существующие решения, как правило, закрывают лишь часть этой задачи. Одни из них ориентированы прежде всего на организацию защищённого канала, другие — на техническое управление клиентскими записями и параметрами доступа на конкретном узле [6–9]. При этом жизненный цикл доступа на уровне пользователя и администратора — подача заявки, принятие решения, продление, отзыв, уведомление и аудит — нередко остаётся вне единого сервисного контура. Именно отсутствие такого контура поверх существующих протоколов и панелей образует инженерную проблему, на решение которой направлена настоящая работа.'),
    pb('В научной литературе вопросы автоматизации конфигурирования VPN-систем рассматриваются преимущественно на уровне протоколов, конфигурации сетевой инфраструктуры и схем размещения [10–12]. Применение чат-ботов в сервисных сценариях также рассматривается в отдельных обзорных работах [13]. Вместе с тем задача проектирования сервиса, объединяющего управление жизненным циклом доступа, пользовательский чат-бот-интерфейс, web-контур и воспроизводимое инфраструктурное развёртывание, освещена ограниченно. Официальная документация Telegram Bot API подтверждает наличие механизмов, достаточных для построения интерактивного канала самообслуживания [14].'),
    pb('Актуальность настоящей работы определяется устойчивым ростом потребности в управляемом защищённом удалённом доступе, фрагментарностью существующих решений и ограниченной проработанностью сервисного уровня управления жизненным циклом доступа в доступных публикациях. Для практики это означает необходимость разработки программной системы, которая не подменяет протокол или панель управления узлом доступа, а объединяет поверх них пользовательский, административный и инфраструктурный контуры.'),
    pb([run('Цель работы', { bold: true }), run(' — разработать автоматизированный сервис защищённого удалённого доступа, обеспечивающий развёртывание серверной инфраструктуры, управление пользователями и жизненный цикл доступа посредством интерфейса Telegram-бота и web-панели.')]),
    pb('Для достижения поставленной цели необходимо решить следующие задачи:'),
    task('1', 'проанализировать предметную область защищённого удалённого доступа и существующие подходы к организации и управлению средствами защищённого удалённого доступа;'),
    task('2', 'сформировать функциональные и нефункциональные требования к разрабатываемому сервису;'),
    task('3', 'спроектировать модульную архитектуру системы, включая инфраструктурный, серверный, пользовательский и административный уровни;'),
    task('4', 'разработать модуль автоматизированного развёртывания серверной инфраструктуры на базе Ansible;'),
    task('5', 'реализовать backend API и общий доменный слой для управления пользователями, заявками, подписками и точками доступа;'),
    task('6', 'реализовать Telegram-бота как основной пользовательский интерфейс выдачи и сопровождения доступа;'),
    task('7', 'реализовать web-кабинет пользователя и административную панель;'),
    task('8', 'провести проверку работоспособности системы на типовых сценариях использования.'),
    pb([run('Объект исследования', { bold: true }), run(' — процессы организации защищённого удалённого доступа к сетевым ресурсам и управления жизненным циклом доступа.')]),
    pb([run('Предмет исследования', { bold: true }), run(' — методы и программные средства автоматизации развёртывания, выдачи и управления доступом с использованием чат-бот-интерфейса и web-панели.')]),
    pb([run('В работе применялись следующие методы', { bold: true }), run(': системный анализ предметной области и существующих программных решений; объектно-ориентированное проектирование при разработке модульной архитектуры; метод прецедентов при формировании требований к системе; экспериментальная проверка работоспособности на типовых сценариях использования.')]),
    pb([run('Практическая значимость', { bold: true }), run(' работы состоит в разработке программной системы, которая может использоваться как основа для самостоятельного развёртывания и адаптации сервиса защищённого удалённого доступа с управлением через Telegram-бот и web-интерфейс. Полученный результат ориентирован на снижение доли ручных операций при выдаче и сопровождении доступа, а также на воспроизводимое развёртывание инфраструктурного контура.')]),
    pb([run('Структура работы.', { bold: true }), run(' Выпускная квалификационная работа состоит из введения, трёх глав, заключения, списка использованных источников и приложений. В первой главе проведён анализ предметной области и существующих решений, сформированы требования к системе. Вторая глава посвящена проектированию архитектуры сервиса, выбору технологий и проектированию ключевых подсистем. В третьей главе описана реализация компонентов системы и результаты проверки работоспособности на типовых сценариях.')]),
  ];
}

function sourcesContent() {
  return [
    ref(1,  'Rise in EU population working from home [Электронный ресурс] // Eurostat. — 2022. — URL: https://ec.europa.eu/eurostat/web/products-eurostat-news/-/ddn-20221108-1 (дата обращения: 13.04.2026).'),
    ref(2,  'Milasi S., González-Vázquez I., Fernandez-Macias E. Telework in the EU before and after the COVID-19: where we were, where we head to [Электронный ресурс] : JRC120945 / European Commission Joint Research Centre. — 2021. — URL: https://joint-research-centre.ec.europa.eu/system/files/2021-06/jrc120945_policy_brief_-_covid_and_telework_final.pdf (дата обращения: 13.04.2026).'),
    ref(3,  'Working from Home: From Invisibility to Decent Work [Электронный ресурс] / International Labour Organization. — Geneva : ILO, 2021. — URL: https://www.ilo.org/publications/major-publications/working-home-invisibility-decent-work (дата обращения: 13.04.2026).'),
    ref(4,  'The rise in remote work since the pandemic and its impact on productivity [Электронный ресурс] // U.S. Bureau of Labor Statistics. Beyond the Numbers. — 2024. — Vol. 13. — URL: https://www.bls.gov/opub/btn/volume-13/remote-work-productivity.htm (дата обращения: 13.04.2026).'),
    ref(5,  'Rose S., Borchert O., Mitchell S., Connelly S. Zero Trust Architecture : NIST Special Publication 800-207 [Электронный ресурс] / National Institute of Standards and Technology. — Gaithersburg, MD : NIST, 2020. — DOI: 10.6028/NIST.SP.800-207. — URL: https://doi.org/10.6028/NIST.SP.800-207 (дата обращения: 13.04.2026).'),
    ref(6,  'Donenfeld J. A. WireGuard: Next Generation Kernel Network Tunnel // Proceedings of the Network and Distributed System Security Symposium (NDSS). — San Diego, 2017. — URL: https://www.wireguard.com/papers/wireguard.pdf (дата обращения: 13.04.2026).'),
    ref(7,  'OpenVPN Access Server: REST API Documentation [Электронный ресурс] // OpenVPN, Inc. — URL: https://openvpn.net/as-docs/rest-api/ (дата обращения: 13.04.2026).'),
    ref(8,  '3x-ui: Xray panel supporting multi-protocol multi-user management [Электронный ресурс] / MHSanaei. — GitHub, 2023–2025. — URL: https://github.com/MHSanaei/3x-ui (дата обращения: 13.04.2026).'),
    ref(9,  'Outline — Developer Documentation [Электронный ресурс] / Jigsaw, Google. — URL: https://developers.google.com/outline (дата обращения: 13.04.2026).'),
    ref(10, 'Bringhenti D., Marchetto G., Sisto R., Valenza F. Automation for Network Security Configuration: State of the Art and Research Trends // ACM Computing Surveys. — 2023. — Vol. 56, No. 3. — Art. 57. — P. 1–37. — DOI: 10.1145/3616401.'),
    ref(11, 'Bringhenti D., Sisto R., Valenza F. Automating VPN Configuration in Computer Networks // IEEE Transactions on Dependable and Secure Computing. — 2024. — DOI: 10.1109/TDSC.2024.3401547. — URL: https://ieeexplore.ieee.org/document/10547475 (дата обращения: 13.04.2026).'),
    ref(12, 'Firdaouss L., Bahnasse A., Belkadi M., Yazidi I. Automated VPN configuration using DevOps // Procedia Computer Science. — 2022. — Vol. 198. — P. 632–637. — DOI: 10.1016/j.procs.2021.12.298.'),
    ref(13, 'Caldarini G., Jaf S., McGarry K. A Literature Survey of Recent Advances in Chatbots // Information. — 2022. — Vol. 13, No. 1. — Art. 41. — DOI: 10.3390/info13010041.'),
    ref(14, 'Telegram Bot API [Электронный ресурс] // Telegram Messenger Inc. — URL: https://core.telegram.org/bots/api (дата обращения: 13.04.2026).'),
  ];
}

function buildDoc() {
  const todo = "[Текст раздела]";

  const sec1 = {
    properties: {
      page: { size: pageSize, margin: pageMargin },
      type: SectionType.NEXT_PAGE,
    },
    footers: { default: emptyFooter },
    children: [
      new Paragraph({
        children: [run("ТИТУЛЬНЫЙ ЛИСТ", { bold: true, allCaps: true })],
        alignment: AlignmentType.CENTER,
        spacing: SP,
        indent: { firstLine: 0 },
      }),
      para("(загружается из ИСУ)"),
      new Paragraph({
        children: [run("ЗАДАНИЕ", { bold: true, allCaps: true })],
        alignment: AlignmentType.CENTER,
        spacing: SP,
        indent: { firstLine: 0 },
        pageBreakBefore: true,
      }),
      para("(загружается из ИСУ)"),
      new Paragraph({
        children: [run("АННОТАЦИЯ", { bold: true, allCaps: true })],
        alignment: AlignmentType.CENTER,
        spacing: SP,
        indent: { firstLine: 0 },
        pageBreakBefore: true,
      }),
      para("(загружается из ИСУ)"),
    ],
  };

  const sec2 = {
    properties: {
      page: { size: pageSize, margin: pageMargin },
      pageNumberStart: 4,
      type: SectionType.NEXT_PAGE,
    },
    footers: { default: pageFooter },
    children: [
      new Paragraph({
        children: [run("СОДЕРЖАНИЕ", { bold: true, allCaps: true })],
        alignment: AlignmentType.CENTER,
        spacing: SP,
        indent: { firstLine: 0 },
      }),
      new TableOfContents("", { hyperlink: true, headingStyleRange: "1-2" }),

      structHead("СПИСОК СОКРАЩЕНИЙ И УСЛОВНЫХ ОБОЗНАЧЕНИЙ"),
      new Paragraph({ children: [], spacing: SP }),
      twoColTable("Сокращение", "Расшифровка"),

      structHead("ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ"),
      new Paragraph({ children: [], spacing: SP }),
      twoColTable("Термин", "Определение"),

      structHead("ВВЕДЕНИЕ"),
      ...introContent(),

      h1("1 ОБОСНОВАНИЕ ТЕМЫ И АНАЛИЗ ПРЕДМЕТНОЙ ОБЛАСТИ"),
      placeholder(todo),
      h2("1.1 [Заголовок подраздела]"),
      placeholder(todo),

      h1("2 ПРОЕКТИРОВАНИЕ СИСТЕМЫ"),
      placeholder(todo),
      h2("2.1 [Заголовок подраздела]"),
      placeholder(todo),

      h1("3 РЕАЛИЗАЦИЯ И ПРОВЕРКА РАБОТОСПОСОБНОСТИ"),
      placeholder(todo),
      h2("3.1 [Заголовок подраздела]"),
      placeholder(todo),

      structHead("ЗАКЛЮЧЕНИЕ"),
      placeholder(todo),

      structHead("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"),
      ...sourcesContent(),

      new Paragraph({
        children: [run("ПРИЛОЖЕНИЕ А", { bold: true, allCaps: true })],
        alignment: AlignmentType.CENTER,
        spacing: SP,
        indent: { firstLine: 0 },
        pageBreakBefore: true,
      }),
      new Paragraph({
        children: [run("[Заголовок приложения]", { bold: true })],
        alignment: AlignmentType.CENTER,
        spacing: SP,
        indent: { firstLine: 0 },
      }),
      placeholder(todo),
    ],
  };

  return new Document({
    styles: {
      default: {
        document: {
          run: { font: FONT, size: SZ },
          paragraph: { spacing: SP },
        },
      },
      paragraphStyles: [
        {
          id: "Heading1", name: "Heading 1",
          basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: SZ, bold: true, font: FONT, allCaps: true },
          paragraph: { spacing: SP, indent: { firstLine: INDENT }, outlineLevel: 0 },
        },
        {
          id: "Heading2", name: "Heading 2",
          basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: SZ, bold: true, font: FONT },
          paragraph: { spacing: SP, indent: { firstLine: INDENT }, outlineLevel: 1 },
        },
      ],
    },
    sections: [sec1, sec2],
  });
}

async function main() {
  const buf = await Packer.toBuffer(buildDoc());
  fs.writeFileSync("/Users/qerenny/Documents/VPN_TG-WEB_system/docs/revise_version/vkr_revised.docx", buf);
  console.log("vkr_revised.docx создан.");
}

main().catch(e => { console.error(e); process.exit(1); });
