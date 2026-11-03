"""Build the design library: specs + storyboard + previews + index.  python -m libgen.build [--only id,..] [--no-render]"""
import os, sys, json, re
sys.path.insert(0, '.')
from libgen.var_doc1 import V
import libgen.var_doc2, libgen.var_saas
from libgen.arch_doc import DOC
from libgen.arch_saas import SAAS
import mgl.spec as S, mgl.qa as Q

ARCH = {**DOC, **SAAS}
ARCH_INFO = {  # archetype -> (category, what it is, when to use, sound)
 'title_hero': ('documentary','Full-bleed photo with kicker, two-line title and subtitle','Opening of any documentary / episode','kinetic'),
 'archival_photo': ('documentary','Ken Burns photo with lower-third caption, year counter and fact pills','Introducing a person, place or event','kinetic'),
 'timeline': ('documentary','Horizontal line with 4 dated events appearing in order','History, progress, before/after sequences','kinetic'),
 'big_stat': ('documentary','Giant counting number inside a growing ring','One striking number that carries the point','kinetic'),
 'ping_map': ('documentary','Grid map with pulsing location pings joined by a route','Journeys, trade routes, data paths','kinetic'),
 'quote_card': ('documentary','Huge quote mark and 3-line quote revealed line by line','A quote or statement the audience should feel','kinetic'),
 'split_compare': ('documentary','Two glass cards with counting numbers and a VS badge','Comparisons: then/now, A/B','kinetic'),
 'steps_list': ('documentary','Numbered rows sliding in with emoji','Processes and how-it-works lists','kinetic'),
 'chart_reveal': ('documentary','Chart that grows, plus a key-number side panel','Showing data and one takeaway','kinetic'),
 'process_flow': ('documentary','4 connected nodes with emoji and step numbers','Cycles and pipelines','kinetic'),
 'orbit_diagram': ('documentary','Central body with orbit rings and moving bodies, legend chips','Solar system, atoms, any orbiting model','kinetic'),
 'chapter_opener': ('documentary','Giant chapter number, title and photo panel','Splitting a long video into chapters','kinetic'),
 'fact_fan': ('documentary','3 tilted cards with counting numbers','Quick fact sets','kinetic'),
 'year_ticker': ('documentary','Huge year counter running between two dates with progress bar','Jumping across time','kinetic'),
 'icon_grid': ('documentary','2x3 glass tiles with emoji labels','Categories, types, overviews','kinetic'),
 'glitch_transition': ('documentary','Scene A, glitch transition, scene B with a counting stat','Before/after or past/present jumps','kinetic'),
 'outro_logo': ('documentary','Logo with ripples, name, tagline and CTA chip','Ending / sign-off','kinetic'),
 'kinetic_statement': ('documentary','3 big words slam in, last one highlighted, shapes float','Punchy statements between scenes','kinetic'),
 'device_showcase': ('saas','Laptop / phone / browser mockup with floating feature chips','Product hero, app reveal','ui'),
 'settings_toggles': ('saas','Glass panel with rows whose toggles switch on one by one','Settings, privacy, feature switches','ui'),
 'toast_notifications': ('saas','Notification toasts sliding in and stacking','Alerts, activity feeds','ui'),
 'kpi_dashboard': ('saas','3 KPI cards with counting numbers, line chart and ring','Dashboards, reports','ui'),
 'ai_prompt_bar': ('saas','Prompt bar with typed text, send pulse, result tiles','AI assistants, search','ui'),
 'pricing_cards': ('saas','3 plan cards with counting prices and a popular badge','Pricing sections','ui'),
 'loading_success': ('saas','Progress ring that turns into a green check with ripples','Upload / payment / setup success','ui'),
 'onboarding_steps': ('saas','Stepper with progress bar and swapping content card','Onboarding, tutorials','ui'),
 'command_palette': ('saas','Command palette with typed query and shortcut rows','Power-user search / shortcuts','ui'),
 'chat_bubbles': ('saas','Alternating chat bubbles sliding in','Support, messaging, tutoring','ui'),
 'feature_trio': ('saas','3 glass feature cards with coloured icons and bars','Feature highlights','ui'),
}
BG_MAP = {'neon':'neon_night','aurora':'dark_aurora','ocean':'ocean','sunset':'sunset','mono':'mono_dark','pastel':'light_pastel','clean':'mono_light'}

def shots(spec):
    """storyboard: group layers by start time into shots (what appears when)"""
    ev = []
    for L in spec['layers']:
        ty = L['type']
        if ty in ('grid', 'blob', 'particles') or (ty == 'rrect' and L.get('w', 0) >= 1900): continue
        if ty == 'text': d = 'text "%s"' % re.sub(r'\{n\}', '#', L['text'])[:40]
        elif ty == 'image': d = 'photo (%s)' % os.path.basename(L['path']).split('.')[0]
        elif ty == 'chip': d = 'chip "%s"' % L['label']
        elif ty == 'card': d = 'card "%s"' % L.get('title', '')
        elif ty == 'chart': d = '%s chart' % L['kind']
        elif ty == 'device': d = '%s mockup' % L['kind']
        elif ty == 'progress': d = '%s progress' % L.get('kind', 'bar')
        elif ty == 'transition': d = '%s transition' % L['style']
        elif ty == 'emoji': d = 'emoji %s' % L['char']
        elif ty == 'icon': d = 'icon %s' % L['name']
        elif ty == 'rrect': d = 'panel'
        elif ty == 'circle': d = 'dot/ring'
        elif ty == 'line': d = 'line draw'
        else: d = ty
        an = (L.get('in') or {}).get('anim', 'fade') if isinstance(L.get('in'), dict) else 'fade'
        ev.append((round(L.get('start', 0), 1), d, an))
    out, cur = [], None
    for t, d, an in sorted(ev, key=lambda e: e[0]):
        if cur is None or t - cur['t'] > 0.9:
            cur = {'t': t, 'items': []}; out.append(cur)
        if len(cur['items']) < 6 and d not in [i['what'] for i in cur['items']] and d != 'dot/ring': cur['items'].append({'what': d, 'anim': an})
    return [o for o in out if o['items']]

def build_all(only=None):
    res = []
    for i, (a, title, topic, tags, d) in enumerate(V):
        cat = ARCH_INFO[a][0]
        did = '%s-%02d-%s' % ('doc' if cat == 'documentary' else 'ui', i + 1, a.replace('_', '-'))
        if only and did not in only: continue
        sc = ARCH[a](d)
        spec = sc.spec(title)
        spec['background'] = BG_MAP[d['th']]
        sc.script.sort(key=lambda x: x[0])
        res.append(dict(id=did, title=title, category=cat, archetype=a, topic=topic, tags=tags, theme=d['th'], duration=sc.dur,
                        idea=ARCH_INFO[a][1], when=ARCH_INFO[a][2], sound=ARCH_INFO[a][3],
                        script=[{'t': t, 'text': x} for t, x in sc.script], storyboard=shots(spec), spec=spec))
    return res

def check(it):
    errs, warns = S.validate(it['spec'], '.')
    qa = Q.analyze(it['spec'], '.', samples=10)
    return errs + qa['errors'], warns

FR = (0.14, 0.38, 0.64, 0.92)

def render_previews(it):
    import cv2
    spec = it['spec']; S.setup(spec); ctx = S.Context('.'); paths = []
    for k, f in enumerate(FR):
        fr = S.render_frame(spec, spec['duration'] * f, ctx)
        fr = cv2.resize(fr, (800, 450), interpolation=cv2.INTER_AREA)
        p = 'library/previews/%s_%d.jpg' % (it['id'], k)
        cv2.imwrite(p, cv2.cvtColor(fr, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80]); paths.append(p)
    return paths

def write_library(items):
    os.makedirs('library/specs', exist_ok=True); os.makedirs('library/previews', exist_ok=True)
    idx = []
    for it in items:
        json.dump(it['spec'], open('library/specs/%s.json' % it['id'], 'w'), ensure_ascii=False, separators=(',', ':'))
        meta = {k: v for k, v in it.items() if k != 'spec'}
        meta['previews'] = ['previews/%s_%d.jpg' % (it['id'], k) for k in range(4)]
        meta['spec_file'] = 'specs/%s.json' % it['id']
        idx.append(meta)
    json.dump({'version': 1, 'count': len(idx), 'designs': idx}, open('library/designs.json', 'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    only = None
    for a in sys.argv[1:]:
        if a.startswith('--only='): only = a[7:].split(',')
    items = build_all(only); bad = 0
    from multiprocessing import Pool
    with Pool(max(1, os.cpu_count() or 1)) as pool:
        for it, (pr, warns) in zip(items, [] if '--noqa' in sys.argv else pool.imap(check, items)):
            if pr or warns:
                bad += bool(pr)
                print(it['id'], 'ERR' if pr else 'warn', (pr + warns)[:4], flush=True)
    print(len(items), 'designs,', bad, 'with errors', flush=True)
    if '--render' in sys.argv and not bad:
        write_library(items)
        with Pool(max(1, os.cpu_count() or 1)) as pool:
            for n, _ in enumerate(pool.imap(render_previews, items)):
                if n % 10 == 0: print('rendered', n, flush=True)
        print('library written', flush=True)
