const { Document, Packer, Paragraph, TextRun, Footer,
        AlignmentType, PageNumber, PageBreak } = require('docx');
const fs = require('fs');

const mm  = (v) => Math.round(v / 25.4 * 1440);
const LEFT   = mm(30);
const RIGHT  = mm(15);
const TOP    = mm(20);
const BOT    = mm(20);
const INDENT = mm(12.5);
const FONT = "Times New Roman";
const SZ   = 28;
const SP   = { line: 360, lineRule: "auto", before: 0, after: 0 };

function r(text, opts = {}) {
  return new TextRun({ text, font: FONT, size: SZ, ...opts });
}

function p(runs, opts = {}) {
  const children = typeof runs === 'string' ? [r(runs)] : runs;
  return new Paragraph({
    children,
    spacing: SP,
    indent: { firstLine: INDENT },
    alignment: AlignmentType.BOTH,
    ...opts,
  });
}

function task(num, text) {
  return new Paragraph({
    children: [r(`${num}) ${text}`)],
    spacing: SP,
    indent: { firstLine: INDENT },
    alignment: AlignmentType.BOTH,
  });
}

function structHead(text) {
  return new Paragraph({
    children: [r(text, { bold: true, allCaps: true })],
    alignment: AlignmentType.CENTER,
    spacing: SP,
    indent: { firstLine: 0 },
    pageBreakBefore: true,
  });
}

function ref(num, text) {
  return new Paragraph({
    children: [r(`${num}. ${text}`)],
    spacing: SP,
    indent: { firstLine: INDENT },
    alignment: AlignmentType.BOTH,
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

// ─── ВВЕДЕНИЕ ────────────────────────────────────────────────────────────────

const intro = [
  new Paragraph({
    children: [r('ВВЕДЕНИЕ', { bold: true, allCaps: true })],
    alignment: AlignmentType.CENTER,
    spacing: SP,
    indent: { firstLine: 0 },
  }),

  // Абзац 1 — рост удалённой работы
  p('Переход к дистанционным форматам занятости, ускорившийся в 2020–2021 годах, изменил не только организацию труда, но и требования к сетевой инфраструктуре предприятий. По данным Eurostat, доля занятых в странах Европейского союза в возрасте 20–64 лет, регулярно работающих из дома, выросла с 5,5% в 2019 году до 12,3% в 2020-м и достигла 13,5% в 2021-м — прирост более чем вдвое за два года [1]. Европейская комиссия в техническом докладе JRC120945 характеризует этот сдвиг как структурный [2], а Международная организация труда в докладе «Working from Home: From Invisibility to Decent Work» (2021) указывает на необходимость соответствующей инфраструктуры безопасного подключения [3]. По оценке Бюро статистики труда США (BLS, 2024), рост доли дистанционной занятости устойчиво сохраняется в постпандемийный период [4].'),

  // Абзац 2 — рост спроса на защищённый доступ, без NIST
  p('Следствием этого структурного перехода стал устойчивый рост спроса на средства защищённого удалённого доступа. По оценке Gartner (октябрь 2022), к 2025 году не менее 70% новых развёртываний удалённого доступа будут построены по модели нулевого доверия (ZTNA) — против менее 10% в 2021 году, — а совокупные расходы на сетевую безопасность увеличиваются на 11,3% ежегодно [5]. Параллельно возрастают и организационные требования к управляемости доступа: необходимость централизованного контроля над выданными конфигурациями, сроками их действия и историей операций становится стандартным ожиданием как со стороны администраторов, так и со стороны конечных пользователей.'),

  // Абзац 3 — обзор существующих решений
  p([
    r('Инструментальная база, сложившаяся к настоящему времени, покрывает лишь часть этой задачи. Протокол WireGuard обеспечивает криптографически стойкий туннель менее чем в 4 000 строках кода ядра, однако не содержит ни панели управления пользователями, ни механизмов жизненного цикла доступа [6]. Коммерческий OpenVPN Access Server предоставляет REST API для автоматизации операций над учётными записями и профилями подключения [7], но требует лицензионных расходов и не предполагает встроенного канала самообслуживания конечного пользователя. Открытая web-панель 3x-ui поддерживает широкий набор транспортных протоколов — Vless, Vmess, Trojan, Shadowsocks, WireGuard — и позволяет задавать индивидуальные лимиты трафика и сроки действия, однако не располагает документированным программным интерфейсом для интеграции с внешними системами управления и не предоставляет пользовательского канала получения доступа [8]. Решение Outline (Jigsaw, Google) реализует REST Management API для управления ключами доступа, однако не предусматривает платёжного контура, управления заявками и развёрнутой модели жизненного цикла пользователей [9].'),
  ]),

  // Абзац 4 — системный разрыв + степень разработанности (без явного именования журналов)
  p('Разрыв между уровнем серверной панели и уровнем конечного пользователя носит системный характер: ни одно из рассмотренных решений не объединяет в едином программном продукте автоматизированное развёртывание инфраструктуры, управление полным жизненным циклом доступа и интерфейс пользовательского самообслуживания. В научной литературе вопросы автоматизации конфигурирования VPN-систем рассматривались преимущественно на уровне протоколов и схем размещения [10, 11, 12]; задача интеграции управления жизненным циклом подписки с пользовательским интерфейсом в опубликованных работах не ставилась. Применение чат-ботов как канала управления сервисными процессами обозначено в ряде обзоров [13], однако использование Telegram-бота именно как интерфейса управления инфраструктурой удалённого доступа — с провижнингом клиентов на серверной панели, контролем сроков и платёжным контуром — остаётся недостаточно исследованной областью. Официальная документация Telegram Bot API [14] подтверждает наличие технических механизмов — long polling, webhook, inline-клавиатуры, callback-запросы, — достаточных для реализации полного сценария самообслуживания без установки дополнительного приложения пользователем.'),

  // Абзац 5 — итоговая актуальность
  p('Актуальность настоящей работы определяется тремя взаимосвязанными факторами: устойчивым структурным ростом потребности в управляемом защищённом удалённом доступе; отсутствием готового open-source решения, интегрирующего автоматизированное развёртывание, управление жизненным циклом доступа и доступный пользовательский интерфейс в едином сервисе; недостаточной разработанностью соответствующего подхода в научной литературе применительно к сценариям без привязки к закрытым коммерческим платформам.'),

  // Цель
  p([r('Цель работы', { bold: true }), r(' — разработать автоматизированный сервис защищённого удалённого доступа, обеспечивающий развёртывание серверной инфраструктуры, управление пользователями и полный жизненный цикл выдачи доступа посредством интерфейса Telegram-бота и web-панели.')]),

  // Задачи
  p('Для достижения поставленной цели необходимо решить следующие задачи:'),
  task('1', 'проанализировать предметную область защищённого удалённого доступа и существующие подходы к управлению VPN/прокси-сервисами;'),
  task('2', 'сформировать функциональные и нефункциональные требования к разрабатываемому сервису;'),
  task('3', 'спроектировать модульную архитектуру системы, включая инфраструктурный, серверный, пользовательский и административный уровни;'),
  task('4', 'разработать модуль автоматизированного развёртывания серверной инфраструктуры на базе Ansible;'),
  task('5', 'реализовать backend API и общий доменный слой для управления пользователями, заявками, подписками и точками доступа;'),
  task('6', 'реализовать Telegram-бота как основной пользовательский интерфейс выдачи и сопровождения доступа;'),
  task('7', 'реализовать web-кабинет пользователя и административную панель;'),
  task('8', 'провести проверку работоспособности системы на типовых сценариях использования.'),

  // Объект и предмет
  p([r('Объект исследования', { bold: true }), r(' — процессы организации защищённого удалённого доступа к сетевым ресурсам и управления жизненным циклом доступа.')]),
  p([r('Предмет исследования', { bold: true }), r(' — методы и программные средства автоматизации развёртывания, выдачи и управления доступом с использованием чат-бот-интерфейса и web-панели.')]),

  // Методы
  p([
    r('В работе применялись следующие '),
    r('методы', { bold: true }),
    r(': системный анализ предметной области и существующих программных решений; объектно-ориентированное проектирование при разработке модульной архитектуры; метод прецедентов при формировании требований к системе; экспериментальная проверка работоспособности на типовых сценариях использования.'),
  ]),

  // Практическая значимость
  p([
    r('Практическая значимость', { bold: true }),
    r(' работы состоит в том, что разработанный сервис представляет собой готовое open-source решение, пригодное для самостоятельного развёртывания и адаптации. Архитектурная организация — пять слабосвязанных компонентов (backend, telegram_bot, shared, frontend, ansible), каждый из которых запускается как самостоятельная единица развёртывания и взаимодействует с остальными через явно определённые интерфейсы: REST API и общий доменный слой, — допускает замену или расширение отдельных подсистем без переработки остальных. Управление конфигурацией через переменные окружения и feature flags позволяет активировать или отключать функциональные блоки в зависимости от потребностей конкретного развёртывания: внутреннего корпоративного сервиса доступа или B2C-платформы с платёжным контуром.'),
  ]),

  // Структура
  p([
    r('Структура работы.', { bold: true }),
    r(' Выпускная квалификационная работа состоит из введения, трёх глав, заключения, списка использованных источников и приложений. В первой главе проведён анализ предметной области и существующих решений, сформированы требования к системе. Вторая глава посвящена проектированию архитектуры сервиса, выбору технологий и проектированию ключевых подсистем. В третьей главе описана реализация компонентов системы и результаты проверки работоспособности на типовых сценариях.'),
  ]),
];

// ─── СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ ────────────────────────────────────────

const sources = [
  structHead('СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ'),

  ref(1,  'Rise in EU population working from home [Электронный ресурс] // Eurostat. — 2022. — URL: https://ec.europa.eu/eurostat/web/products-eurostat-news/-/ddn-20221108-1 (дата обращения: 13.04.2026).'),
  ref(2,  'Milasi S., González-Vázquez I., Fernandez-Macias E. Telework in the EU before and after the COVID-19: where we were, where we head to [Электронный ресурс] : JRC120945 / European Commission Joint Research Centre. — 2021. — URL: https://joint-research-centre.ec.europa.eu/system/files/2021-06/jrc120945_policy_brief_-_covid_and_telework_final.pdf (дата обращения: 13.04.2026).'),
  ref(3,  'Working from Home: From Invisibility to Decent Work [Электронный ресурс] / International Labour Organization. — Geneva : ILO, 2021. — URL: https://www.ilo.org/publications/major-publications/working-home-invisibility-decent-work (дата обращения: 13.04.2026).'),
  ref(4,  'The rise in remote work since the pandemic and its impact on productivity [Электронный ресурс] // U.S. Bureau of Labor Statistics. Beyond the Numbers. — 2024. — Vol. 13. — URL: https://www.bls.gov/opub/btn/volume-13/remote-work-productivity.htm (дата обращения: 13.04.2026).'),
  ref(5,  'Gartner Identifies Three Factors Influencing Growth in Security Spending [Электронный ресурс] // Gartner, Inc. — 2022. — URL: https://www.gartner.com/en/newsroom/press-releases/2022-10-13-gartner-identifies-three-factors-influencing-growth-i (дата обращения: 13.04.2026).'),
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

// ─── ДОКУМЕНТ ────────────────────────────────────────────────────────────────

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: FONT, size: SZ },
        paragraph: { spacing: SP },
      },
    },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: TOP, right: RIGHT, bottom: BOT, left: LEFT },
        pageNumberStart: 1,
      },
    },
    footers: { default: pageFooter },
    children: [...intro, ...sources],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(
    '/Users/qerenny/Documents/VPN_TG-WEB_system/docs/vkr_working.docx', buf
  );
  console.log('vkr_working.docx обновлён.');
}).catch(e => { console.error(e); process.exit(1); });
