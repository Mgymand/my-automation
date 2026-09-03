# -*- coding: utf-8 -*-
import sys, subprocess, os
from gen_common import *
import gen_p1, gen_p2, gen_p3, gen_research as GR
from gen_editor import editor_parts

def body_html():
    parts = [
        gen_p1.cover(), gen_p1.summary(), gen_p1.howto(),
        gen_p1.p1_1(), gen_p1.p1_2(), gen_p1.p1_3(), gen_p1.p1_4(),
        GR.p1_5(), GR.p1_6(), GR.p1_7(), gen_p1.p1_8(), gen_p1.p1_9(), GR.p1_10(),
        gen_p2.p2_1(), GR.p2_2(), GR.p2_3(), gen_p2.p2_4(), gen_p2.p2_5(), gen_p2.p2_6(), gen_p2.p2_7(), gen_p2.p2_8(), GR.p2_9(), gen_p2.p2_10(),
        gen_p3.p3(), GR.appx_a(), GR.appx_b(), gen_p3.appx_c(), gen_p3.appx_d(), gen_p3.appx_e(), gen_p3.appx_f(),
    ]
    return ''.join(parts)

def build(out_html='ringi.html', out_pdf='ringi.pdf'):
    body = body_html()
    doc = ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>春日部東中野 稟議書</title>' + CSS + '</head><body><div class="sheet">' + body + '</div></body></html>')
    open(out_html, 'w', encoding='utf-8').write(doc)
    chrome = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
    subprocess.run([chrome, '--headless=new', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer', f'--print-to-pdf={out_pdf}', os.path.abspath(out_html)], capture_output=True)
    print('html', len(doc), 'bytes;', out_pdf, os.path.getsize(out_pdf))




def build_editable(out_html='editable.html', out_artifact='artifact_editable.html'):
    """編集版：同じ本文＋ツールバー＋編集スクリプト。out_html は単体で開ける完全なHTML、out_artifact はArtifact公開用（骨格なし）。"""
    body = body_html()
    css, bar, js = editor_parts()
    inner = ('<title>春日部東中野 稟議書（編集版）</title>' + CSS + css + bar + '<div class="sheet" id="doc">' + body + '</div>'
             '<script id="editor-script">' + js + '</script>')
    doc = ('<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n'
           '<title>春日部東中野 稟議書（編集版）</title>\n' + CSS + css + '</head>\n<body>\n' + bar + '\n<div class="sheet" id="doc">' + body + '</div>\n'
           '<script id="editor-script">' + js + '</script>\n</body>\n</html>\n')
    open(out_html, 'w', encoding='utf-8').write(doc)
    open(out_artifact, 'w', encoding='utf-8').write(inner)
    print('editable', out_html, len(doc), 'bytes;', out_artifact, len(inner), 'bytes')

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'editable':
        build_editable(*sys.argv[2:])
    else:
        build(*sys.argv[1:])
