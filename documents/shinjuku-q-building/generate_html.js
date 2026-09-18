// content.js から印刷用 HTML を生成する。PDF 化は Chromium の --print-to-pdf で行う。
const fs = require('fs');
const c = require('./content');

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const nl = (s) => esc(s).replace(/\n/g, '<br>');

const sigRows = c.signatureRows.map(([label, line, seal]) =>
  `<tr><th>${esc(label)}</th><td class="${line ? 'ruled' : ''}"></td><td class="seal">${seal ? '㊞' : ''}</td></tr>`).join('');

const s2Rows = c.s2.rows.map(([label, vals]) =>
  `<tr><th>${nl(label)}</th><td>${vals.map((v) => `<div>${esc(v)}</div>`).join('')}</td></tr>`).join('');

const s4Rows = c.s4.rows.map(([label, val]) =>
  `<tr><th>${esc(label)}</th><td>${esc(val)}</td></tr>`).join('');

const html = `<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><title>${esc(c.title)}</title>
<style>
  @page { size: A4; margin: 18mm 20mm; }
  body { font-family: "Yu Mincho", "YuMincho", "Hiragino Mincho ProN", "MS Mincho", "IPAMincho", "IPAGothic", serif;
         font-size: 10pt; line-height: 1.65; color: #000; margin: 0; }
  p { margin: 0 0 0.45em; text-align: justify; }
  .right { text-align: right; }
  .center { text-align: center; }
  h1 { font-size: 14pt; text-align: center; letter-spacing: .2em; margin: .9em 0 1em; font-weight: 700; }
  h2 { font-size: 10pt; font-weight: 700; margin: .95em 0 .35em; break-after: avoid; }
  table.grid, .sig { break-inside: avoid; }
  p { orphans: 2; widows: 2; }
  .sig { width: 62mm; margin-left: auto; border-collapse: collapse; margin-bottom: .3em; }
  .sig th { text-align: left; font-weight: 400; white-space: nowrap; padding: .25em .6em .25em 0; }
  .sig td { width: 100%; padding: .25em 0; }
  .sig td.ruled { border-bottom: 1px solid #000; }
  .sig td.seal { width: 8mm; text-align: center; border: none; padding-left: .4em; }
  .note { font-size: 9pt; margin: .2em 0; }
  table.grid { width: 100%; border-collapse: collapse; margin: .4em 0 .2em; }
  table.grid th, table.grid td { border: 1px solid #000; padding: .35em .6em; vertical-align: middle; text-align: left; }
  table.grid th { background: #f2f2f2; font-weight: 400; width: 32mm; white-space: nowrap; }
  table.grid td.opt { width: auto; }
  table.grid td.date { width: 46mm; white-space: nowrap; }
  .sub { font-size: 9pt; }
  .cond { margin: 0 0 .2em 1em; }
  .end { text-align: right; margin-top: .8em; break-before: avoid; }
</style></head>
<body>
  <p class="right">${esc(c.BLANK_DATE)}</p>
  <p><strong>${esc(c.addressee)}</strong></p>
  <table class="sig">${sigRows}</table>
  <p class="right note">${esc(c.signatureNote)}</p>

  <h1>${esc(c.title)}</h1>
  ${c.opening.map((t) => `<p>${esc(t)}</p>`).join('\n  ')}
  <p class="right">${esc(c.closing)}</p>
  <p class="center">記</p>

  <h2>${esc(c.s1.heading)}</h2>
  <table class="grid">
    <tr><th>${esc(c.s1.labelApply)}</th><td colspan="2">${esc(c.BLANK_DATE)}</td></tr>
    <tr><th rowspan="2">${esc(c.s1.labelEnd)}</th>
        <td class="opt">${esc(c.s1.optionA)}<div class="sub">${esc(c.s1.optionANote)}</div></td>
        <td class="date">${esc(c.s1.endDate)}</td></tr>
    <tr><td class="opt">${esc(c.s1.optionB)}<div class="sub">${esc(c.s1.optionBNote)}</div></td>
        <td class="date">${esc(c.s1.endDate)}</td></tr>
  </table>
  ${c.s1.notes.map((t) => `<p class="note">${esc(t)}</p>`).join('\n  ')}

  <h2>${esc(c.s2.heading)}</h2>
  <table class="grid">${s2Rows}</table>
  <p class="note">${esc(c.s2.note)}</p>

  <h2>${esc(c.s3.heading)}</h2>
  ${c.s3.paragraphs.map((t) => `<p>${esc(t)}</p>`).join('\n  ')}
  ${c.s3.conditions.map((t) => `<p class="cond">${esc(t)}</p>`).join('\n  ')}
  <p>${esc(c.s3.tail)}</p>

  <h2>${esc(c.s4.heading)}</h2>
  <table class="grid">${s4Rows}</table>

  <p class="end">${esc(c.end)}</p>
</body></html>`;

fs.writeFileSync(process.argv[2] || 'kaiyaku.html', html);
console.log('written', process.argv[2]);
