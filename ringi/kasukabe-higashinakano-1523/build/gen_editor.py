# -*- coding: utf-8 -*-
"""編集版（ブラウザ上で直接編集・保存・印刷できる版）のシェル"""
import json

EDITOR_CSS = r"""
<style id="editor-style" data-doc="1">
#editor-bar{position:fixed;top:0;left:0;right:0;z-index:50;background:#1f2d4d;color:#fff;font-family:'Noto Sans JP',sans-serif;font-size:12.5px;box-shadow:0 2px 8px rgba(0,0,0,.25)}
#editor-bar .row{display:flex;align-items:center;gap:6px;padding:6px 12px;flex-wrap:wrap}
#editor-bar .ttl{font-weight:700;letter-spacing:.06em;margin-right:8px}
#editor-bar button{font:inherit;font-size:12.5px;padding:4px 10px;border:1px solid rgba(255,255,255,.55);background:transparent;color:#fff;border-radius:3px;cursor:pointer;line-height:1.4}
#editor-bar button:hover{background:rgba(255,255,255,.14)}
#editor-bar button[disabled]{opacity:.4;cursor:default}
#editor-bar button.primary{background:#a63a2e;border-color:#a63a2e;font-weight:700}
#editor-bar button.on{background:#fff;color:#1f2d4d;font-weight:700}
#editor-bar .sep{width:1px;height:20px;background:rgba(255,255,255,.3);margin:0 4px}
#editor-bar .status{margin-left:auto;font-size:12px;color:#e6e8ec;max-width:46%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#editor-bar .status.warn{color:#ffd9a8}
#editor-bar .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#7fc98f;margin-right:6px;vertical-align:middle}
#editor-bar .dot.dirty{background:#ffb347}
#editor-help{display:none;background:#eef1f7;color:#1b1b1f;padding:8px 14px;font-size:12px;line-height:1.7;border-top:1px solid #c9ccd4}
#editor-help.show{display:block}
#editor-help b{color:#1f2d4d}
#draft-banner{display:none;background:#fbf6ea;color:#1b1b1f;padding:6px 14px;font-size:12.5px;border-top:1px solid #d9c9a0}
#draft-banner.show{display:flex;gap:10px;align-items:center}
#draft-banner button{color:#1f2d4d;border-color:#1f2d4d}
body.has-bar{padding-top:48px}
body.editing .sheet{outline:2px dashed #a63a2e;outline-offset:6px}
body.editing .sheet [contenteditable="false"]{opacity:.85;cursor:not-allowed}
body.editing .sheet :is(p,li,td,th,h2,h3,h4,dd,dt,figcaption,.tile .v,.tile .l,.tile .s,.intent,.note,.warn):hover{box-shadow:inset 0 0 0 1px rgba(166,58,46,.35)}
@media print{#editor-bar,#editor-help,#draft-banner{display:none!important} body.has-bar{padding-top:0} body.editing .sheet{outline:none}}
</style>
"""

TOOLBAR = """<div id="editor-bar">
<div class="row">
<span class="ttl">稟議書 編集版</span>
<button id="btn-edit" title="文章を直接編集できる状態に切り替えます">編集モード</button>
<button id="btn-undo" title="Ctrl+Z">元に戻す</button>
<button id="btn-redo" title="Ctrl+Y">やり直す</button>
<span class="sep"></span>
<button id="btn-row-add" title="カーソルのある表の行を下に複製します">表：行を追加</button>
<button id="btn-row-del" title="カーソルのある表の行を削除します">表：行を削除</button>
<span class="sep"></span>
<button id="btn-save" class="primary" hidden title="編集内容を新しい版として保存し、このページを見る全員に反映します（Ctrl+S）">保存（新版を公開）</button>
<button id="btn-download" hidden title="編集済みのHTMLファイルを手元に保存します">HTMLをダウンロード</button>
<button id="btn-print" title="ブラウザの印刷ダイアログを開きます。送信先を「PDFに保存」にしてください">印刷／PDF保存</button>
<button id="btn-discard" title="未保存の編集を捨てて、保存済みの内容に戻します">変更を破棄</button>
<button id="btn-help">使い方</button>
<span class="status" id="editor-status"><span class="dot" id="editor-dot"></span>読み込み中…</span>
</div>
<div id="draft-banner"><span>前回の未保存の下書きがあります。</span><button id="btn-draft-restore">下書きを復元</button><button id="btn-draft-drop">下書きを破棄</button></div>
<div id="editor-help">
<b>編集の手順</b>：「編集モード」を押す → 直したい文章をクリックして入力 → 「保存（新版を公開）」。保存すると版が増え、このリンクを開く全員に反映されます（履歴から前の版に戻せます）。<br>
<b>PDFにする</b>：「印刷／PDF保存」→ 送信先「PDFに保存」→ 余白「既定」、「背景のグラフィック」をオンにすると、配布用PDFと同じ体裁（藍色の見出し帯・頁番号・社外秘表示）で出力されます。<br>
<b>体裁を保つコツ</b>：Enterで新しい段落、Shift+Enterで行内改行。表の中でもセルをクリックして直接編集できます（行の追加・削除はツールバー）。図・グラフは編集対象外です。見出し帯や「記載意図」欄の枠は自動で保たれます。<br>
<b>数値の注意</b>：表の数値は収支モデル（build/model.py）から自動計算されたものです。前提（価格・室数・単価など）を変えて全体を再計算したい場合は、リポジトリの build/gen.py で再生成してください。手で数値を直す場合は関連する箇所（要旨・Ⅰ-8・Ⅱ-6・Ⅱ-7・Ⅲ）の整合にご注意ください。<br>
<b>保存ができない場合</b>：閲覧のみの権限か、このページをファイルとして開いている状態です。「HTMLをダウンロード」で手元に保存し、Chromeで開けば同じように編集・印刷できます。
</div>
</div>"""

EDITOR_JS = r"""
(function(){
  var doc = document.getElementById('doc');
  var $ = function(id){ return document.getElementById(id); };
  var KEY = 'ringi-editor-draft:' + location.pathname;
  var state = { editing:false, dirty:false, artifact:null, downloads:null, platform: !!(window.claude && typeof window.claude.use === 'function') };
  var BAR = __BAR__;
  var FILENAME = __FILENAME__;
  document.body.classList.add('has-bar');

  function setStatus(msg, warn){ var s = $('editor-status'); s.innerHTML = '<span class="dot' + (state.dirty ? ' dirty' : '') + '" id="editor-dot"></span>' + esc(msg); s.className = 'status' + (warn ? ' warn' : ''); }
  function esc(t){ return String(t).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function lockNonText(){ doc.querySelectorAll('svg, figure img').forEach(function(el){ el.setAttribute('contenteditable','false'); }); }
  function setEditing(on){
    state.editing = on;
    doc.setAttribute('contenteditable', on ? 'true' : 'false');
    document.body.classList.toggle('editing', on);
    $('btn-edit').classList.toggle('on', on);
    $('btn-edit').textContent = on ? '編集モード：ON' : '編集モード';
    if (on) { lockNonText(); setStatus('編集モードです。文章をクリックして直接入力できます'); doc.focus(); }
    else { setStatus(state.dirty ? '未保存の変更があります' : '閲覧モード', state.dirty); }
  }
  function cleanContent(){
    var clone = doc.cloneNode(true);
    clone.querySelectorAll('[contenteditable]').forEach(function(el){ el.removeAttribute('contenteditable'); });
    return clone.innerHTML;
  }
  function buildDocument(){
    var styles = Array.prototype.map.call(document.querySelectorAll('head link[data-doc], head style[data-doc]'), function(e){ return e.outerHTML; }).join('\n');
    var script = document.getElementById('editor-script').textContent;
    return '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>' + esc(document.title) + '</title>\n' + styles + '\n</head>\n<body>\n' + BAR + '\n<div class="sheet" id="doc">' + cleanContent() + '</div>\n<script id="editor-script">' + script + '<\/script>\n</body>\n</html>\n';
  }
  var draftTimer = null;
  function scheduleDraft(){ clearTimeout(draftTimer); draftTimer = setTimeout(saveDraft, 1500); }
  function saveDraft(){ try { localStorage.setItem(KEY, JSON.stringify({ html: cleanContent(), at: Date.now() })); } catch(e){} }
  function loadDraft(){ try { var d = JSON.parse(localStorage.getItem(KEY) || 'null'); return d && d.html ? d : null; } catch(e){ return null; } }
  function dropDraft(){ try { localStorage.removeItem(KEY); } catch(e){} }

  doc.addEventListener('input', function(){ state.dirty = true; setStatus('未保存の変更があります', true); scheduleDraft(); });
  window.addEventListener('beforeunload', function(e){ if (state.dirty) { e.preventDefault(); e.returnValue = ''; } });

  $('btn-edit').onclick = function(){ setEditing(!state.editing); };
  $('btn-undo').onclick = function(){ doc.focus(); document.execCommand('undo'); };
  $('btn-redo').onclick = function(){ doc.focus(); document.execCommand('redo'); };
  $('btn-print').onclick = function(){ window.print(); };
  $('btn-help').onclick = function(){ $('editor-help').classList.toggle('show'); };
  $('btn-discard').onclick = function(){ if (!state.dirty || confirm('未保存の変更を破棄して、保存済みの内容に戻しますか？')) { dropDraft(); state.dirty = false; location.reload(); } };

  function currentRow(){ var sel = window.getSelection(); if (!sel || !sel.anchorNode) return null; var n = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement; var tr = n && n.closest ? n.closest('#doc tr') : null; return tr; }
  $('btn-row-add').onclick = function(){ var tr = currentRow(); if (!tr) { setStatus('表のセルにカーソルを置いてから押してください', true); return; } var c = tr.cloneNode(true); c.querySelectorAll('td').forEach(function(td){ td.innerHTML = '&nbsp;'; }); tr.parentNode.insertBefore(c, tr.nextSibling); state.dirty = true; setStatus('行を追加しました', true); scheduleDraft(); };
  $('btn-row-del').onclick = function(){ var tr = currentRow(); if (!tr) { setStatus('表のセルにカーソルを置いてから押してください', true); return; } if (confirm('この行を削除しますか？')) { tr.remove(); state.dirty = true; setStatus('行を削除しました', true); scheduleDraft(); } };

  async function publish(){
    if (!state.artifact) return;
    var html = buildDocument();
    $('btn-save').disabled = true; setStatus('保存中…');
    try {
      await state.artifact.publish(html);
      dropDraft(); state.dirty = false; setStatus('保存しました。最新版を読み込みます');
    } catch (e) {
      var code = e && e.code;
      saveDraft();
      if (code === 'conflict') setStatus('他の人が先に保存したため反映できませんでした。編集内容は下書きに保持しています。再読み込み後に「下書きを復元」で続けられます', true);
      else if (code === 'not_writer' || code === 'not_granted') { setStatus('このページを保存する権限がありません（閲覧のみ）。「HTMLをダウンロード」で手元に保存してください', true); $('btn-save').hidden = true; }
      else if (code === 'rate_limited') setStatus('保存が集中しています。少し待ってからもう一度お試しください', true);
      else setStatus('保存に失敗しました：' + (e && (e.message || e.code) || '不明なエラー') + '。下書きは保持しています', true);
    } finally { $('btn-save').disabled = false; }
  }
  $('btn-save').onclick = publish;

  async function download(){
    var html = buildDocument();
    if (state.downloads) {
      try { await state.downloads.save({ filename: FILENAME, data: html }); setStatus('ダウンロードしました'); }
      catch (e) { if (!e || e.code !== 'declined') setStatus('ダウンロードできませんでした' + (e && e.code ? '（' + e.code + '）' : ''), true); }
    } else {
      var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' })); a.download = FILENAME; document.body.appendChild(a); a.click(); a.remove();
      setStatus('ダウンロードしました');
    }
  }
  $('btn-download').onclick = download;
  document.addEventListener('keydown', function(e){ if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); if (state.artifact && !$('btn-save').hidden) publish(); else download(); } });

  // 下書きの復元
  var draft = loadDraft();
  if (draft && draft.html !== doc.innerHTML) {
    $('draft-banner').classList.add('show');
    $('btn-draft-restore').onclick = function(){ doc.innerHTML = draft.html; state.dirty = true; $('draft-banner').classList.remove('show'); setEditing(true); setStatus('下書きを復元しました（未保存）', true); };
    $('btn-draft-drop').onclick = function(){ dropDraft(); $('draft-banner').classList.remove('show'); };
  } else if (draft) { dropDraft(); }

  // 機能の有効化（プラットフォーム上でのみ保存が使える）
  if (state.platform) {
    setStatus('閲覧モード（保存機能を確認中…）');
    window.claude.use('artifact').then(function(ns){ state.artifact = ns; if (ns) { $('btn-save').hidden = false; setStatus('閲覧モード。「編集モード」を押すと文章を直接修正できます'); } else { setStatus('閲覧モード。このビューでは保存できません（ダウンロードして編集してください）', true); } });
    window.claude.use('downloads').then(function(ns){ state.downloads = ns; $('btn-download').hidden = !ns; });
  } else {
    $('btn-download').hidden = false;
    setStatus('ファイル版：編集後は「HTMLをダウンロード」で保存し、「印刷／PDF保存」でPDF化できます');
  }
  setEditing(false);
})();
"""

FILENAME = '稟議書_春日部市東中野1523-13_編集版.html'

def editor_parts():
    js = EDITOR_JS.replace('__BAR__', json.dumps(TOOLBAR, ensure_ascii=False)).replace('__FILENAME__', json.dumps(FILENAME, ensure_ascii=False))
    return EDITOR_CSS, TOOLBAR, js
