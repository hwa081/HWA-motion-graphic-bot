"""Storyboard PDF of the design library (HTML -> PDF with Chromium/Playwright)."""
import os, json, html, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSS = """
@page { size: A4; margin: 10mm 10mm 12mm 10mm; }
*{box-sizing:border-box} body{font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#151a30;font-size:9.2pt;line-height:1.35;margin:0}
h1{font-size:30pt;margin:0 0 4mm;background:linear-gradient(90deg,#6a4bff,#ff4fa3);-webkit-background-clip:text;color:transparent}
h2{font-size:15pt;margin:6mm 0 2mm;color:#3b2fb8} h3{font-size:11pt;margin:3mm 0 1mm}
.cover{height:270mm;display:flex;flex-direction:column;justify-content:center;page-break-after:always}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;background:#eceaff;color:#3b2fb8;font-size:7.5pt;margin-right:3px}
.pill.ui{background:#ffe8f3;color:#b0206a}
.card{height:134mm;border:1px solid #d9dcec;border-radius:3mm;padding:3mm 4mm;margin-bottom:4mm;page-break-inside:avoid;overflow:hidden}
.hd{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid #eceef8;padding-bottom:1.5mm;margin-bottom:2mm}
.hd b{font-size:12pt}.hd span{color:#6b7090;font-size:8pt}
.strip{display:grid;grid-template-columns:repeat(4,1fr);gap:1.5mm;margin-bottom:2mm}
.strip div{position:relative}.strip img{width:100%;border-radius:1.2mm;display:block}.strip i{position:absolute;left:1mm;bottom:1mm;background:#000a;color:#fff;font-size:6.5pt;padding:0 3px;border-radius:2px;font-style:normal}
.cols{display:grid;grid-template-columns:1.1fr 1fr;gap:4mm}
.say{margin:0;padding:0;list-style:none}.say li{margin-bottom:1mm}.say b{color:#6a4bff;font-family:monospace;margin-right:2mm}
.sb div{margin-bottom:1mm;font-size:8pt}.sb b{color:#d02a82;font-family:monospace;margin-right:2mm}
.meta{font-size:8pt;color:#454a70;margin:1mm 0}
table{border-collapse:collapse;width:100%;font-size:8pt}td,th{border-bottom:1px solid #e3e5f2;padding:1px 4px;text-align:left}
.pb{page-break-before:always}
"""

def esc(s): return html.escape(str(s))

def card(d):
    pre = ''.join('<div><img src="previews/%s_%d.jpg"><i>%.1fs</i></div>' % (d['id'], k, d['duration'] * f) for k, f in enumerate((0.14, 0.38, 0.64, 0.92)))
    say = ''.join('<li><b>%.1fs</b>%s</li>' % (x['t'], esc(x['text'])) for x in d['script'])
    sb = ''.join('<div><b>%.1fs</b>%s</div>' % (s['t'], esc('  +  '.join('%s (%s)' % (i['what'], i['anim']) for i in s['items']))) for s in d['storyboard'][:9])
    return ('<div class="card"><div class="hd"><b>%s</b><span>%s &middot; %.1fs &middot; sound: %s</span></div>'
            '<div><span class="pill %s">%s</span><span class="pill">%s</span>%s</div>'
            '<div class="strip">%s</div><div class="meta"><b>Idea:</b> %s. <b>Use when:</b> %s.</div>'
            '<div class="cols"><div><h3>Narration (voice, timed to the visuals)</h3><ul class="say">%s</ul></div><div><h3>Storyboard (what appears)</h3><div class="sb">%s</div></div></div></div>') % (
        esc(d['title']), esc(d['id']), d['duration'], d['sound'], 'ui' if d['category'] == 'saas' else '', 'SaaS / UI' if d['category'] == 'saas' else 'Documentary',
        esc(d['topic']), ''.join('<span class="pill">%s</span>' % esc(t) for t in d['tags'][:4]), pre, esc(d['idea']), esc(d['when']), say, sb)

def build(out_pdf, root=ROOT):
    ds = json.load(open(os.path.join(root, 'library', 'designs.json'), encoding='utf-8'))['designs']
    arch = {}
    for d in ds: arch.setdefault(d['archetype'], []).append(d)
    rows = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%d</td></tr>' % (esc(a), esc(v[0]['idea']), esc(v[0]['when']), len(v)) for a, v in arch.items())
    n_doc = sum(1 for d in ds if d['category'] == 'documentary')
    cover = ('<div class="cover"><h1>Motion Design Library</h1><p style="font-size:14pt">%d ready designs &middot; %d documentary scenes &middot; %d SaaS / UI animations</p>'
             '<p>Every design has: a <b>narration script timed to the visuals</b>, a <b>storyboard</b> (what appears at which second), <b>4 real rendered frames</b> and a <b>renderable spec</b> (JSON) the bot can learn from, re-render or remix into brand-new designs.</p>'
             '<h2>How the bot uses it</h2><ul><li>Reads the most similar designs (script + storyboard + spec) before it designs your video.</li><li>Learns the pattern: what the voice says &rarr; what appears on that second.</li>'
             '<li>Invents NEW designs by combining patterns, changing layout, colours, animation family, camera and transitions &mdash; never copying.</li><li>Topics: space, history, ocean, nature, science, technology, economy &mdash; and SaaS / UI motion graphics.</li></ul>'
             '<h2>How to read a page</h2><p>Top: title, id, duration, suggested sound style. Strip: 4 frames of the real render. Left: narration with timestamps. Right: storyboard shots.</p></div>') % (len(ds), n_doc, len(ds) - n_doc)
    idx = '<div class="pb"><h2>The %d design patterns (each has 4 variations)</h2><table><tr><th>Pattern</th><th>What it is</th><th>Use when</th><th>#</th></tr>%s</table>' % (len(arch), rows)
    idx += '<h2>Make a NEW design (recipe the bot follows)</h2><ol><li>Pick the scene idea (one idea per scene, 5&ndash;9 seconds).</li><li>Write the narration first, one sentence per beat.</li><li>Choose a pattern and put each key word on its own second.</li><li>Change at least 3 things from the library design: layout, theme, animation family, camera, transition, content.</li><li>Alternate dense and calm scenes; use transitions only between scenes.</li><li>Keep text short and big, inside the safe margins.</li></ol></div>'
    pages = []
    for i in range(0, len(ds), 2):
        pages.append('<div class="pb">' + card(ds[i]) + (card(ds[i + 1]) if i + 1 < len(ds) else '') + '</div>')
    doc = '<!doctype html><meta charset="utf-8"><style>%s</style>%s%s%s' % (CSS, cover, idx, ''.join(pages))
    hp = os.path.join(root, 'library', 'design_library.html'); open(hp, 'w', encoding='utf-8').write(doc)
    from playwright.sync_api import sync_playwright
    os.makedirs(os.path.dirname(os.path.abspath(out_pdf)), exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(); pg.goto('file://' + hp); pg.wait_for_timeout(800)
        pg.pdf(path=out_pdf, format='A4', print_background=True, margin={'top': '10mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm'},
               display_header_footer=True, header_template='<span></span>', footer_template='<div style="font-size:7px;width:100%;text-align:center;color:#888">Motion Design Library &middot; page <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        b.close()
    print('wrote', out_pdf, os.path.getsize(out_pdf) // 1024, 'KB'); return 0

if __name__ == '__main__':
    sys.exit(build(sys.argv[1] if len(sys.argv) > 1 else 'out/design_library.pdf'))
