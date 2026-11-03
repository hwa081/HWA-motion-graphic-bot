"""mgl.planner - the "creative director" step: think first, then build.

Before the spec is written, one AI request produces a short DIRECTOR'S PLAN: the concept, the mood, one signature idea,
a scene-by-scene outline (purpose, layout archetype, motion, transition) and the effects the library cannot do yet (the wishlist).
The spec writer must follow the plan, which gives the bot a story and consistent taste instead of "layers in a row".
"""
import json
from . import gemini, engine as E, spec as S

PLAN_SYSTEM = 'You are a world-class creative director for motion graphics. You plan before anyone builds. Answer with JSON only.'
ARCHETYPES = ['typographic hero', 'card fan', 'chip cluster', 'device mockup', 'chart reveal', 'big number', 'split screen', 'logo reveal', 'ui prompt bar',
              'quote', 'list stagger', 'image feature', 'grid gallery', 'timeline steps', 'map pings', 'orbit diagram', 'process flow', 'kinetic statement']


def plan_prompt(brief, duration, size_key, context='', recipe_text='', reference_note=''):
    return (
        'Plan a %ss motion-graphics video (canvas %s) for this brief:\n"%s"\n\n'
        'You can build with these ingredients: background styles %s; entrance animations %s; transitions %s; layer types text, card, chip, chart, device, image (photo/icon search), progress, blob, particles, grid, line, rrect, circle, emoji; camera moves.\n'
        '%s%s%s\n'
        'THINK like a director, then return ONE JSON object:\n'
        '{"concept": "one sentence: the story / idea of the video",\n'
        ' "audience_mood": "who watches and the feeling to create",\n'
        ' "signature": "ONE memorable visual idea that makes this video different from a template",\n'
        ' "palette": ["#rrggbb", ... up to 4],\n'
        ' "rejected": ["2 obvious ideas you rejected and why (too generic / overused)"],\n'
        ' "scenes": [{"t0": seconds, "t1": seconds, "purpose": "what the viewer learns/feels", "archetype": one of %s, "visual": "what is on screen", '
        '"motion": "how it enters/moves", "background": style, "transition_out": style or "none"}] (scenes cover 0..%s without gaps; the last one stays visible to the end),\n'
        ' "risks": ["what could go wrong (text length, clutter, contrast ...) and the guard"],\n'
        ' "wishes": ["effects you would love to use but the ingredients above cannot do (max 2, empty list if none)"]}\n'
        'Rules: every scene needs a different archetype than its neighbours; match the pace to the brief; keep text short; respect the brand kit and the lessons.'
        % (duration, size_key, brief.strip()[:600], ', '.join(sorted(E.BG_STYLES)), ', '.join(a for a in S.ANIMS if a != 'none'), ', '.join(S.TRANSITIONS),
           ', '.join(ARCHETYPES), duration,
           ('\n' + context[:3500] + '\n') if context else '', ('\n' + recipe_text[:1800]) if recipe_text else '', ('\n' + reference_note[:1200]) if reference_note else ''))


def _s(v, n=160): return str(v).strip()[:n] if v is not None else ''


def clean_plan(data, duration):
    if not isinstance(data, dict): raise ValueError('plan was not a JSON object')
    scenes = []
    for sc in (data.get('scenes') or [])[:12]:
        if not isinstance(sc, dict): continue
        try: t0 = float(sc.get('t0', 0)); t1 = float(sc.get('t1', duration))
        except Exception: continue
        if t1 <= t0: continue
        bg = _s(sc.get('background'), 30); tr = _s(sc.get('transition_out'), 20)
        scenes.append({'t0': max(0.0, min(t0, duration)), 't1': min(float(duration), t1), 'purpose': _s(sc.get('purpose')), 'archetype': _s(sc.get('archetype'), 40),
                       'visual': _s(sc.get('visual'), 220), 'motion': _s(sc.get('motion'), 160),
                       'background': bg if bg in E.BG_STYLES else '', 'transition_out': tr if tr in S.TRANSITIONS else 'none'})
    if not scenes: raise ValueError('plan has no usable scenes')
    pal = [p for p in (data.get('palette') or []) if isinstance(p, str) and S.parse_color(p)][:4]
    return {'concept': _s(data.get('concept'), 240), 'mood': _s(data.get('audience_mood'), 200), 'signature': _s(data.get('signature'), 240), 'palette': pal,
            'rejected': [_s(x, 200) for x in (data.get('rejected') or [])[:3]], 'scenes': scenes,
            'risks': [_s(x, 200) for x in (data.get('risks') or [])[:4]], 'wishes': [_s(x, 200) for x in (data.get('wishes') or [])[:2] if _s(x, 200)]}


def plan_text(p):
    lines = ["=== DIRECTOR'S PLAN (you already thought about this video; build exactly this story, scene by scene) ===",
             'CONCEPT: %s' % p['concept'], 'MOOD: %s' % p['mood'], 'SIGNATURE IDEA (must be clearly visible): %s' % p['signature']]
    if p['palette']: lines.append('PALETTE: ' + ', '.join(p['palette']))
    lines.append('SCENES:')
    for i, sc in enumerate(p['scenes'], 1):
        lines.append('%d. %.1f-%.1fs [%s] %s | visual: %s | motion: %s%s%s' % (
            i, sc['t0'], sc['t1'], sc['archetype'] or 'scene', sc['purpose'], sc['visual'], sc['motion'],
            (' | background: ' + sc['background']) if sc['background'] else '', (' | transition out: ' + sc['transition_out']) if sc['transition_out'] != 'none' else ''))
    if p['risks']: lines.append('WATCH OUT: ' + '; '.join(p['risks']))
    return '\n'.join(lines) + '\n'


def make_plan(ask, brief, duration, size_key, context='', recipe_text='', reference_note='', mem=None, log=print):
    """-> (plan dict, text). Raises on failure (the caller falls back to building without a plan). Wishes are written to the notebook."""
    txt = ask(PLAN_SYSTEM, [{'role': 'user', 'parts': [gemini.text_part(plan_prompt(brief, duration, size_key, context, recipe_text, reference_note))]}])
    plan = clean_plan(gemini.extract_json(txt), duration)
    if mem is not None:
        for w in plan['wishes']: mem.add_wish(w, source='planner')
    return plan, plan_text(plan)
