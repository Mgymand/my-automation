const {
  Document, Packer, Paragraph, TextRun, AlignmentType, HeadingLevel,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, VerticalAlign,
} = require('docx');
const fs = require('fs');

const FONT = '游明朝';
const SIZE = 21; // 10.5pt -> half-points

const t = (text, opts = {}) => new TextRun({ text, font: FONT, size: opts.size || SIZE, bold: !!opts.bold, underline: opts.underline ? {} : undefined });

const p = (text, opts = {}) => new Paragraph({
  alignment: opts.align || AlignmentType.LEFT,
  spacing: { after: opts.after === undefined ? 80 : opts.after, line: 300 },
  indent: opts.indent,
  children: Array.isArray(text) ? text : [t(text, opts)],
});

const NOBORDER = {
  top: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
  bottom: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
  left: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
  right: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
  insideHorizontal: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
  insideVertical: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
};

// --- table helpers -----------------------------------------------------
const cell = (children, width, opts = {}) => new TableCell({
  width: { size: width, type: WidthType.DXA },
  columnSpan: opts.span,
  verticalAlign: VerticalAlign.CENTER,
  shading: opts.shade ? { type: ShadingType.CLEAR, fill: 'F2F2F2', color: 'auto' } : undefined,
  margins: { top: 80, bottom: 80, left: 120, right: 120 },
  children,
});

const TW = 9400; // table width (A4 with 25mm margins ~ 9639 dxa)

function infoTable(rows, widths) {
  return new Table({
    width: { size: TW, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((cells) => new TableRow({
      children: cells.map((c, i) => cell(
        (Array.isArray(c.body) ? c.body : [p(c.body, { after: 0 })]),
        c.span ? widths.slice(i, i + c.span).reduce((a, b) => a + b, 0) : widths[i],
        { span: c.span, shade: c.shade },
      )),
    })),
  });
}

const BLANK = '　　　　年　　　月　　　日';

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: SIZE } } } },
  sections: [{
    properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    children: [
      p(BLANK, { align: AlignmentType.RIGHT, after: 240 }),
      p([t('賃貸人　株式会社邱永漢事務所　御中', { bold: true })], { after: 200 }),

      // 差出人（署名・捺印欄）
      new Table({
        width: { size: 5200, type: WidthType.DXA },
        columnWidths: [1400, 2800, 1000],
        indent: { size: 4200, type: WidthType.DXA },
        borders: NOBORDER,
        rows: [
          ['賃借人', '', ''],
          ['所 在 地', '', ''],
          ['法 人 名', '', ''],
          ['代 表 者', '', '印'],
        ].map(([label, val, seal], idx) => new TableRow({
          children: [
            cell([p(label, { after: 0 })], 1400),
            cell([new Paragraph({
              spacing: { after: 0, line: 300 },
              border: idx === 0 ? undefined : { bottom: { style: BorderStyle.SINGLE, size: 6, color: '000000' } },
              children: [t(val)],
            })], 2800),
            cell([p(seal ? '㊞' : '', { after: 0, align: AlignmentType.CENTER })], 1000),
          ],
        })),
      }),
      p('※ 個人名義でご契約の場合は、住所・氏名をご記入のうえご捺印ください。', { align: AlignmentType.RIGHT, size: 18, after: 320 }),

      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 320, line: 300 },
        children: [new TextRun({ text: '解　約　通　知　書', font: FONT, size: 30, bold: true })],
      }),

      p('　拝啓　時下ますますご清栄のこととお慶び申し上げます。平素は格別のご高配を賜り、厚く御礼申し上げます。'),
      p('　さて、新宿Ｑビル３階（以下「本物件」といいます。）につきまして、貴社との間で締結いたしました２０２６年６月２９日付定期建物賃貸借契約（以下「本契約」といいます。）について、下記のとおり解約を申し入れます。なお、契約終了の手続きに際しましては、本契約の各条項を遵守することをお約束いたします。'),
      p('　また、本物件につきましては、当方の加盟店本部である株式会社Ｌｉｍｅ（以下「Ｌｉｍｅ社」といいます。）が、解約日の翌日を始期として貴社と新たに賃貸借契約を締結し、本物件を継続してご利用させていただきたく協議を進めております。つきましては、本契約第１８条第２項に定める違約金のお取扱いにつきまして、下記３．のとおりご相談させていただきたく、何卒ご高配賜りますようお願い申し上げます。'),
      p('　このたびは、２０２６年９月分賃料のお支払いが遅延し、また当方からのご連絡が行き届かず、多大なご迷惑とご心配をおかけいたしましたことを、深くお詫び申し上げます。'),
      p('敬具', { align: AlignmentType.RIGHT, after: 200 }),
      p('記', { align: AlignmentType.CENTER, after: 200 }),

      p([t('１．解約の申し入れについて', { bold: true })], { after: 120 }),
      infoTable([
        [{ body: '解約申し入れ日', shade: true }, { body: BLANK, span: 2 }],
        [{ body: '契約終了日\n（解約日）', shade: true, body: [p('契約終了日（解約日）', { after: 0 })] },
         { body: [p('□　予約解約をする', { after: 0 }), p('　　（本契約第１８条に基づき、６か月前の予告をもって解約する）', { after: 0, size: 18 })] },
         { body: [p('【契約終了日】　' + BLANK, { after: 0 })] }],
        [{ body: '', shade: true },
         { body: [p('□　即時解約をする', { after: 0 }), p('　　（本契約第１８条に定める予告期間（６か月）に代えて、６か月分の賃料相当額を支払うことにより即時解約する）', { after: 0, size: 18 })] },
         { body: [p('【契約終了日】　' + BLANK, { after: 0 })] }],
      ], [1900, 4500, 3000]),
      p('※　上記のうち任意の解約手続きを選択し、該当箇所にチェックをお願いいたします。', { size: 18, after: 0 }),
      p('※　違約金のお取扱いについては、下記３．のとおりご相談させていただきたく存じます。', { size: 18, after: 240 }),

      p([t('２．原状回復・明渡しの立会い、精算等について', { bold: true })], { after: 120 }),
      infoTable([
        [{ body: '退室立会希望日時', shade: true }, { body: '　　　年　　月　　日　　　時　　分（平日１０〜１７時／未定の場合は空欄）', span: 2 }],
        [{ body: '精算金返還先\n指定銀行口座', shade: true, body: [p('精算金返還先', { after: 0 }), p('指定銀行口座', { after: 0 })] },
         { body: '　　　　　　　　　　銀行　　　　　　　　　　支店', span: 2 }],
        [{ body: '', shade: true }, { body: '普通／当座　番号　　　　　　　　　　名義', span: 2 }],
        [{ body: '明渡し後の連絡先', shade: true }, { body: '氏名　　　　　　　　　　　　　　　　　　', span: 2 }],
        [{ body: '', shade: true }, { body: '住所　　　　　　　　　　　　　　　　　　', span: 2 }],
        [{ body: '', shade: true }, { body: '電話　　　　　　　　　　Ｅ-ｍａｉｌ　　　　　　　　', span: 2 }],
      ], [1900, 4500, 3000]),
      p('※　Ｌｉｍｅ社が本物件を現状のまま引き継ぐ場合には、原状回復の要否・範囲につきましても、併せてご協議いただけますと幸いです。', { size: 18, after: 240 }),

      p([t('３．違約金のお取扱いに関するお願い（ご相談）', { bold: true })], { after: 120 }),
      p('　本契約第１８条第２項により、契約開始日から満２年を経過する前に解約する場合には、解約日から契約期間満了日（２０２９年６月３０日）までの残存期間分の賃料等相当額を違約金としてお支払いする旨が定められていることは、承知いたしております。'),
      p('　もっとも、本件は、本物件における営業を終了して空室とするものではなく、解約日の翌日付でＬｉｍｅ社が貴社と新たな賃貸借契約を締結し、賃料等のお支払いを引き継ぐことを前提としたものです。この場合、貴社におかれましては、空室期間の発生や再募集に要する費用等のご負担が生じないものと存じます。'),
      p('　つきましては、下記の各条件が満たされることを条件として、本契約に基づく違約金につき、その全部の免除又は相当額への減額をご検討賜りたく、伏してお願い申し上げます。'),
      p('（１）解約日の翌日を始期として、貴社とＬｉｍｅ社との間で本物件の賃貸借契約が締結されること', { indent: { left: 240 }, after: 40 }),
      p('（２）前号の新契約における賃料等の条件が、本契約と同等以上であること', { indent: { left: 240 }, after: 40 }),
      p('（３）本契約に基づく解約日までの賃料等（２０２６年９月分を含みます。）その他の債務を、当方又はＬｉｍｅ社において清算すること', { indent: { left: 240 }, after: 40 }),
      p('（４）その他、貴社がご指定される引継ぎ上必要な事項に応じること', { indent: { left: 240 }, after: 120 }),
      p('　なお、上記の取扱いにつきましては、貴社、Ｌｉｍｅ社及び当方の三者による合意解約（合意書の締結）の形式によることも含め、柔軟に対応させていただく所存です。ご検討のうえ、ご連絡を賜りますようお願い申し上げます。', { after: 240 }),

      p([t('４．本件に関するご連絡先', { bold: true })], { after: 120 }),
      infoTable([
        [{ body: '氏名', shade: true }, { body: '　　　　　　　　　　　　　　　　　　', span: 2 }],
        [{ body: '電話', shade: true }, { body: '　　　　　　　　　　Ｅ-ｍａｉｌ　　　　　　　　', span: 2 }],
      ], [1900, 4500, 3000]),

      p('以上', { align: AlignmentType.RIGHT, after: 0 }),
    ],
  }],
});

Packer.toBuffer(doc).then((b) => {
  fs.writeFileSync(process.argv[2], b);
  console.log('written', process.argv[2]);
});
