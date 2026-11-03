"""mgl.reference - learn from reference videos.

video  ->  contact sheets (frames with time stamps)  ->  Gemini analyses the design  ->  style card saved in memory
many videos  ->  style cards  ->  Gemini writes one style guide (patterns, rules, named recipes) used in every later prompt
"""
import hashlib, os, re
import cv2, numpy as np
from . import gemini

VIDEO_EXT = ('.mp4', '.mov', '.webm', '.mkv', '.m4v', '.avi', '.gif')
ARCHETYPES = ['typographic_hero', 'card_fan', 'chip_cluster', 'device_mockup', 'chart_reveal', 'big_number', 'split_screen', 'logo_reveal',
              'ui_prompt_bar', 'quote', 'list_stagger', 'image_feature', 'grid_gallery', 'timeline_steps']


def video_sha(path):
    h = hashlib.sha1(); size = os.path.getsize(path)
    with open(path, 'rb') as f:
        h.update(f.read(1 << 20)); f.seek(max(0, size - (1 << 20))); h.update(f.read(1 << 20))
    h.update(str(size).encode())
    return h.hexdigest()[:16]


def video_info(path):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if total <= 0 or w <= 0: raise ValueError('cannot read video %s' % path)
    return dict(frames=total, fps=fps, duration=total / fps, width=w, height=h,
                aspect='16:9' if w > h * 1.3 else ('9:16' if h > w * 1.3 else '1:1'))


def frame_sheets(path, per_sheet=12, sheets=2, cols=4, tile_w=480):
    """list of PNG bytes; sheet k covers the k-th part of the video, tiles labelled with their time"""
    info = video_info(path)
    cap = cv2.VideoCapture(path)
    out = []
    total, fps = info['frames'], info['fps']
    n_total = per_sheet * sheets
    idxs = [int((total - 1) * (0.01 + 0.97 * i / max(1, n_total - 1))) for i in range(n_total)]
    for k in range(sheets):
        tiles = []
        for idx in idxs[k * per_sheet:(k + 1) * per_sheet]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if not ok: continue
            h = int(tile_w * fr.shape[0] / fr.shape[1])
            fr = cv2.resize(fr, (tile_w, h), interpolation=cv2.INTER_AREA)
            lab = '%.1fs' % (idx / fps)
            cv2.putText(fr, lab, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(fr, lab, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            tiles.append(fr)
        if not tiles: continue
        while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
        sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
        ok, buf = cv2.imencode('.png', sheet)
        if ok: out.append(buf.tobytes())
        if info['duration'] < 8 and k == 0 and sheets > 1: break      # very short clip: one sheet is enough
    cap.release()
    if not out: raise ValueError('no frames could be read from %s' % path)
    return out, info


ANALYZE_SYSTEM = 'You are a senior motion designer who reverse-engineers videos into reusable design knowledge. Answer with JSON only.'


def analysis_prompt(info, name):
    return (
        'These pictures are contact sheets of frames (time stamps in yellow) from the reference video "%s" '
        '(%.1f s, aspect %s). Study the design carefully and describe it so another designer can recreate its STRUCTURE and FEEL with new content.\n\n'
        'Return one JSON object with exactly these keys:\n'
        '{"title": short name for this style,\n'
        ' "tags": up to 8 lowercase keywords (genre, mood, product type),\n'
        ' "palette": up to 6 hex colours that dominate (backgrounds, accents, text),\n'
        ' "backgrounds": how the backgrounds look and change (e.g. "dark aurora gradient -> pastel gradient"),\n'
        ' "typography": {"headline": "weight, italic?, case, approx size class", "body": "...", "text_effects": "how text appears (typing, blur-in, letters, marquee ...)"},\n'
        ' "scenes": [{"t0": seconds, "t1": seconds, "archetype": one of %s, "description": what is on screen, "text": visible text, "motion": how things enter/move/leave, "camera": "none|push-in|pull-out|pan"}] (max 12),\n'
        ' "transitions": list of transition styles between scenes (wipe, iris, stripes, flash, glitch, crossfade, camera move ...),\n'
        ' "pacing": {"scene_seconds": average scene length, "rhythm": "slow|medium|fast", "notes": "..."},\n'
        ' "motion_language": "easing, speed, overshoot, blur use ...",\n'
        ' "layout_rules": ["concrete rules about spacing, alignment, hierarchy, safe areas"],\n'
        ' "professional_because": ["why it looks professional"],\n'
        ' "weaknesses": ["what could be better"],\n'
        ' "techniques": [{"name": "short name of a reusable trick this video uses", "when": "when to use it", "how": "how to build it with text/card/chip/chart/device/image layers, animations and timing"}] (max 3, only genuinely reusable tricks),\n'
        ' "notes": "anything else useful"}\n'
        'Be specific and concrete. Do not invent text you cannot see.' % (name, info['duration'], info['aspect'], ', '.join(ARCHETYPES)))


def _clean_card(data, name, sha, info):
    def s(v, n=220): return str(v)[:n] if v is not None else ''
    def lst(v, n=8, ln=160): return [s(x, ln) for x in v[:n]] if isinstance(v, list) else []
    pal = [p for p in lst(data.get('palette'), 6, 9) if re.fullmatch(r'#?[0-9a-fA-F]{6}', p.strip())]
    scenes = []
    for sc in (data.get('scenes') or [])[:12]:
        if isinstance(sc, dict):
            scenes.append({k: (sc.get(k) if k in ('t0', 't1') and isinstance(sc.get(k), (int, float)) else s(sc.get(k), 160)) for k in ('t0', 't1', 'archetype', 'description', 'text', 'motion', 'camera') if k in sc})
    typo = data.get('typography') if isinstance(data.get('typography'), dict) else {}
    pac = data.get('pacing') if isinstance(data.get('pacing'), dict) else {}
    return {
        'sha': sha, 'source': os.path.basename(name), 'title': s(data.get('title') or os.path.splitext(os.path.basename(name))[0], 80),
        'tags': [t.lower() for t in lst(data.get('tags'), 8, 24)], 'palette': ['#' + p.strip().lstrip('#') for p in pal],
        'backgrounds': s(data.get('backgrounds')), 'typography': {k: s(v) for k, v in typo.items()}, 'scenes': scenes,
        'transitions': lst(data.get('transitions'), 8, 60), 'pacing': {k: s(v) for k, v in pac.items()}, 'motion': s(data.get('motion_language'), 300),
        'layout_rules': lst(data.get('layout_rules'), 6), 'professional_because': lst(data.get('professional_because'), 6),
        'weaknesses': lst(data.get('weaknesses'), 4), 'notes': s(data.get('notes'), 300),
        'techniques': [{'name': s(t.get('name'), 60), 'when': s(t.get('when'), 160), 'how': s(t.get('how'), 300)} for t in (data.get('techniques') or [])[:3] if isinstance(t, dict) and t.get('name') and t.get('how')],
        'aspect': info['aspect'], 'duration': round(info['duration'], 1)}


def analyze_video(ask, path, log=print):
    """returns a style card (dict) for one reference video"""
    sha = video_sha(path)
    sheets, info = frame_sheets(path)
    parts = [{'text': analysis_prompt(info, os.path.basename(path))}] + [gemini.image_part(png) for png in sheets]
    txt = ask(ANALYZE_SYSTEM, [{'role': 'user', 'parts': parts}])
    data = gemini.extract_json(txt)
    if not isinstance(data, dict): raise ValueError('analysis was not a JSON object')
    return _clean_card(data, path, sha, info)


def learn_folder(mem, ask, folder, limit=5, log=print):
    """analyse reference videos in `folder` that are not in memory yet (max `limit` per run). returns (new_cards, skipped, failed)"""
    if not os.path.isdir(folder):
        raise FileNotFoundError('reference folder not found: %s' % folder)
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(VIDEO_EXT))
    new, skipped, failed = [], [], []
    for fn in files:
        p = os.path.join(folder, fn)
        try:
            sha = video_sha(p)
        except Exception as ex:
            failed.append((fn, str(ex))); continue
        if mem.has_source(sha):
            skipped.append(fn); continue
        if len(new) >= limit:
            log('   limit of %d new videos per run reached - run learn again for the rest' % limit)
            break
        log('   analysing %s ...' % fn)
        try:
            card = analyze_video(ask, p, log)
            mem.add_style(card)
            new.append(card)
        except Exception as ex:
            log('   failed: %s' % ex)
            failed.append((fn, str(ex)[:200]))
    return new, skipped, failed


GUIDE_SYSTEM = 'You are a design director. You write concise, concrete guidance for a motion-graphics bot. Plain markdown, no preamble.'


def synthesize_style_guide(mem, ask, max_cards=14, log=print):
    cards = mem.styles[-max_cards:]
    if len(cards) < 2:
        return None
    compact = []
    for c in cards:
        compact.append({k: c.get(k) for k in ('title', 'tags', 'palette', 'backgrounds', 'typography', 'transitions', 'pacing', 'motion', 'layout_rules', 'professional_because', 'weaknesses')}
                       | {'scenes': [(s.get('archetype'), s.get('motion')) for s in c.get('scenes', [])][:8]})
    import json
    prompt = ('Below are style cards of %d reference videos the user collected. Compare them and write a STYLE GUIDE (max 2200 characters, markdown) that a bot will read before designing new videos:\n'
              '1. COMMON PATTERNS across the videos (what they all do).\n2. DIFFERENCES worth keeping as separate looks - name 3-5 distinct DESIGN RECIPES (e.g. "Neon dashboard", "Soft pastel product tour") each with palette, background style, typography, motion, transitions.\n'
              '3. RULES that make them look professional (spacing, hierarchy, easing, timing, transitions) with concrete numbers.\n4. MISTAKES to avoid (from the weaknesses).\n'
              'Use the library vocabulary where possible: background styles (dark_aurora, light_pastel, neon_night, ocean, sunset, mono_dark, mono_light), entrance animations (blur, pop, slide_up, rise, bounce, spin, tilt, wipe_right, zoom), '
              'transitions (wipe, iris, stripes, flash, glitch), layer types (text, card, chip, chart, device, image, progress, blob, particles, grid).\n\nSTYLE CARDS:\n%s' % (len(compact), json.dumps(compact, ensure_ascii=False)[:14000]))
    txt = ask(GUIDE_SYSTEM, [{'role': 'user', 'parts': [{'text': prompt}]}], json_mode=False)
    txt = re.sub(r'^```(?:markdown|md)?\s*|\s*```$', '', txt.strip())
    if len(txt) < 200: raise ValueError('style guide too short')
    mem.write_style_guide('# Style guide (from %d reference videos, updated %s)\n\n%s' % (len(cards), __import__('datetime').date.today().isoformat(), txt[:3000]))
    return txt
