// content.js から Word 版（.docx）を生成する。
//   npm i docx && node generate_docx.js 出力先.docx
const {
  Document, Packer, Paragraph, TextRun, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, VerticalAlign,
} = require('docx');
const fs = require('fs');
const c = require('./content');

const FONT = '游明朝';
const SIZE = 20;      // 10pt
const SMALL = 18;     // 9pt

const t = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || SIZE, bold: !!o.bold });
const p = (text, o = {}) => new Paragraph({
  alignment: o.align || AlignmentType.LEFT,
  spacing: { after: o.after === undefined ? 80 : o.after, line: 290 },
  indent: o.indent,
  children: Array.isArray(text) ? text : [t(text, o)],
});

const NOBORDER = ['top', 'bottom', 'left', 'right', 'insideHorizontal', 'insideVertical']
  .reduce((a, k) => ({ ...a, [k]: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' } }), {});

const TW = 9400;
const cell = (children, width, o = {}) => new TableCell({
  width: { size: width, type: WidthType.DXA },
  columnSpan: o.span,
  rowSpan: o.rowSpan,
  verticalAlign: VerticalAlign.CENTER,
  shading: o.shade ? { type: ShadingType.CLEAR, fill: 'F2F2F2', color: 'auto' } : undefined,
  margins: { top: 70, bottom: 70, left: 120, right: 120 },
  children,
});

// cells: [{ body: string | Paragraph[], shade?, span?, rowSpan? }]
const grid = (rows, widths) => new Table({
  width: { size: TW, type: WidthType.DXA },
  columnWidths: widths,
  rows: rows.map((cells) => new TableRow({
    children: cells.map((cl, i) => cell(
      Array.isArray(cl.body) ? cl.body : [p(cl.body, { after: 0 })],
      cl.span ? widths.slice(i, i + cl.span).reduce((a, b) => a + b, 0) : widths[i],
      cl,
    )),
  })),
});

const lines = (arr, o = {}) => arr.map((s, i) => p(s, { after: i === arr.length - 1 ? 0 : 40, ...o }));

const W = [1900, 4400, 3100];

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: SIZE } } } },
  sections: [{
    properties: { page: { margin: { top: 1020, bottom: 1020, left: 1134, right: 1134 } } },
    children: [
      p(c.BLANK_DATE, { align: AlignmentType.RIGHT, after: 240 }),
      p([t(c.addressee, { bold: true })], { after: 200 }),

      // 署名・捺印欄
      new Table({
        width: { size: 5200, type: WidthType.DXA },
        columnWidths: [1400, 2800, 1000],
        indent: { size: 4200, type: WidthType.DXA },
        borders: NOBORDER,
        rows: c.signatureRows.map(([label, ruled, seal]) => new TableRow({
          children: [
            cell([p(label, { after: 0 })], 1400),
            cell([new Paragraph({
              spacing: { after: 0, line: 290 },
              border: ruled ? { bottom: { style: BorderStyle.SINGLE, size: 6, color: '000000' } } : undefined,
              children: [t('')],
            })], 2800),
            cell([p(seal ? '㊞' : '', { after: 0, align: AlignmentType.CENTER })], 1000),
          ],
        })),
      }),
      p(c.signatureNote, { align: AlignmentType.RIGHT, size: SMALL, after: 300 }),

      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 300, line: 290 },
        children: [new TextRun({ text: c.title, font: FONT, size: 28, bold: true })],
      }),

      ...c.opening.map((s) => p(s)),
      p(c.closing, { align: AlignmentType.RIGHT, after: 180 }),
      p('記', { align: AlignmentType.CENTER, after: 180 }),

      p([t(c.s1.heading, { bold: true })], { after: 120 }),
      grid([
        [{ body: c.s1.labelApply, shade: true }, { body: c.BLANK_DATE, span: 2 }],
        [{ body: c.s1.labelEnd, shade: true, rowSpan: 2 },
         { body: [p(c.s1.optionA, { after: 0 }), p(c.s1.optionANote, { after: 0, size: SMALL })] },
         { body: c.s1.endDate }],
        [{ body: [p(c.s1.optionB, { after: 0 }), p(c.s1.optionBNote, { after: 0, size: SMALL })] },
         { body: c.s1.endDate }],
      ], W),
      ...c.s1.notes.map((s, i) => p(s, { size: SMALL, after: i === c.s1.notes.length - 1 ? 240 : 0 })),

      p([t(c.s2.heading, { bold: true })], { after: 120 }),
      grid(c.s2.rows.map(([label, vals]) => [
        { body: lines(label.split('\n')), shade: true },
        { body: lines(vals), span: 2 },
      ]), W),
      p(c.s2.note, { size: SMALL, after: 240 }),

      p([t(c.s3.heading, { bold: true })], { after: 120 }),
      ...c.s3.paragraphs.map((s) => p(s)),
      ...c.s3.conditions.map((s) => p(s, { indent: { left: 240 }, after: 40 })),
      p(c.s3.tail, { after: 240 }),

      p([t(c.s4.heading, { bold: true })], { after: 120 }),
      grid(c.s4.rows.map(([label, val]) => [{ body: label, shade: true }, { body: val, span: 2 }]), W),

      p(c.end, { align: AlignmentType.RIGHT, after: 0 }),
    ],
  }],
});

Packer.toBuffer(doc).then((b) => {
  fs.writeFileSync(process.argv[2], b);
  console.log('written', process.argv[2]);
});
