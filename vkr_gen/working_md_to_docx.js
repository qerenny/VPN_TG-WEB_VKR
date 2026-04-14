const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  Packer,
  PageNumber,
  Paragraph,
  SectionType,
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
const INPUT = path.join(ROOT, "docs", "vkr_working.md");
const OUTPUT = path.join(ROOT, "docs", "vkr_working.docx");

const mm = (value) => Math.round((value / 25.4) * 1440);
const LEFT = mm(30);
const RIGHT = mm(15);
const TOP = mm(20);
const BOTTOM = mm(20);
const INDENT = mm(12.5);
const PAGE_WIDTH = 11906;
const PAGE_HEIGHT = 16838;
const CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT;
const FONT = "Times New Roman";
const BODY_SIZE = 28;
const TABLE_SIZE = 22;
const SPACING = { line: 360, lineRule: "auto", before: 0, after: 0 };

function textRun(text, options = {}) {
  return new TextRun({
    text,
    font: FONT,
    size: options.size ?? BODY_SIZE,
    bold: options.bold,
    allCaps: options.allCaps,
  });
}

function paragraph(text, options = {}) {
  return new Paragraph({
    children: [textRun(text, options.run ?? {})],
    spacing: SPACING,
    indent: { firstLine: options.noIndent ? 0 : INDENT },
    alignment: options.alignment ?? AlignmentType.JUSTIFIED,
    heading: options.heading,
    pageBreakBefore: options.pageBreakBefore,
  });
}

function h1(text, isFirst) {
  return paragraph(text, {
    run: { bold: true, allCaps: true },
    heading: HeadingLevel.HEADING_1,
    pageBreakBefore: !isFirst,
  });
}

function h2(text) {
  return paragraph(text, {
    run: { bold: true },
    heading: HeadingLevel.HEADING_2,
  });
}

function h3(text) {
  return paragraph(text);
}

function structHead(text, isFirst) {
  return paragraph(text, {
    noIndent: true,
    alignment: AlignmentType.CENTER,
    run: { bold: true, allCaps: true },
    pageBreakBefore: !isFirst,
  });
}

function tableCaption(text) {
  return paragraph(text, {
    noIndent: true,
    alignment: AlignmentType.LEFT,
  });
}

function cellParagraph(text, isHeader) {
  return new Paragraph({
    children: [
      textRun(text, {
        bold: isHeader,
        size: TABLE_SIZE,
      }),
    ],
    spacing: SPACING,
    indent: { firstLine: 0 },
    alignment: isHeader ? AlignmentType.CENTER : AlignmentType.LEFT,
  });
}

function tableCell(text, isHeader, width) {
  const border = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
  return new TableCell({
    borders: { top: border, bottom: border, left: border, right: border },
    verticalAlign: isHeader ? VerticalAlign.CENTER : VerticalAlign.TOP,
    width: { size: width, type: WidthType.DXA },
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [cellParagraph(text, isHeader)],
  });
}

function columnWidths(headers) {
  const joined = headers.join("|");
  if (joined.includes("Идентификатор|Контур|Требование|Проектное обоснование")) {
    return [1200, 1650, 3300, CONTENT_WIDTH - 1200 - 1650 - 3300];
  }
  if (joined.includes("Идентификатор|Требование|Обоснование")) {
    return [1300, 4550, CONTENT_WIDTH - 1300 - 4550];
  }
  if (joined.includes("Область|Ограничение или допущение|Обоснование")) {
    return [1800, 4050, CONTENT_WIDTH - 1800 - 4050];
  }
  const base = Math.floor(CONTENT_WIDTH / headers.length);
  return headers.map((_, index) =>
    index === headers.length - 1 ? CONTENT_WIDTH - base * (headers.length - 1) : base,
  );
}

function markdownTable(rows) {
  const headers = rows[0];
  const widths = columnWidths(headers);
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((row, rowIndex) => new TableRow({
      children: row.map((value, colIndex) => tableCell(value, rowIndex === 0, widths[colIndex])),
    })),
  });
}

function parseTable(lines, startIndex) {
  const rows = [];
  let index = startIndex;

  while (index < lines.length && lines[index].trim().startsWith("|")) {
    const line = lines[index].trim();
    const cells = line
      .slice(1, line.endsWith("|") ? -1 : undefined)
      .split("|")
      .map((cell) => cell.trim());
    const isSeparator = cells.every((cell) => /^:?-{3,}:?$/.test(cell));
    if (!isSeparator) {
      rows.push(cells);
    }
    index += 1;
  }

  return { table: markdownTable(rows), nextIndex: index };
}

function parseMarkdown(markdown) {
  const children = [];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  let isFirstBlock = true;

  while (index < lines.length) {
    const raw = lines[index];
    const line = raw.trim();

    if (!line) {
      index += 1;
      continue;
    }

    if (line.startsWith("|")) {
      const parsed = parseTable(lines, index);
      children.push(parsed.table);
      index = parsed.nextIndex;
      isFirstBlock = false;
      continue;
    }

    if (/^Таблица\s+\d+/.test(line)) {
      children.push(tableCaption(line));
      index += 1;
      isFirstBlock = false;
      continue;
    }

    if (line.startsWith("# ")) {
      const title = line.slice(2).trim();
      const isSources = title.toUpperCase() === "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ";
      children.push(isSources ? structHead(title, isFirstBlock) : h1(title, isFirstBlock));
      index += 1;
      isFirstBlock = false;
      continue;
    }

    if (line.startsWith("## ")) {
      children.push(h2(line.slice(3).trim()));
      index += 1;
      isFirstBlock = false;
      continue;
    }

    if (line.startsWith("### ")) {
      children.push(h3(line.slice(4).trim()));
      index += 1;
      isFirstBlock = false;
      continue;
    }

    children.push(paragraph(line));
    index += 1;
    isFirstBlock = false;
  }

  return children;
}

const pageFooter = new Footer({
  children: [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({
          children: [PageNumber.CURRENT],
          font: FONT,
          size: BODY_SIZE,
        }),
      ],
      spacing: SPACING,
      indent: { firstLine: 0 },
    }),
  ],
});

async function main() {
  const content = fs.readFileSync(INPUT, "utf8");
  const doc = new Document({
    styles: {
      default: {
        document: {
          run: { font: FONT, size: BODY_SIZE },
          paragraph: { spacing: SPACING },
        },
      },
      paragraphStyles: [
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: BODY_SIZE, bold: true, font: FONT, allCaps: true },
          paragraph: { spacing: SPACING, indent: { firstLine: INDENT }, outlineLevel: 0 },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: { size: BODY_SIZE, bold: true, font: FONT },
          paragraph: { spacing: SPACING, indent: { firstLine: INDENT }, outlineLevel: 1 },
        },
      ],
    },
    sections: [
      {
        properties: {
          type: SectionType.NEXT_PAGE,
          page: {
            size: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
            margin: { top: TOP, right: RIGHT, bottom: BOTTOM, left: LEFT },
          },
        },
        footers: { default: pageFooter },
        children: parseMarkdown(content),
      },
    ],
  });

  fs.writeFileSync(OUTPUT, await Packer.toBuffer(doc));
  console.log(`Created ${OUTPUT}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
