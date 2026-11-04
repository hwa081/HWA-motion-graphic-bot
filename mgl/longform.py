"""mgl.longform - videos longer than one minute (up to 10 minutes), made part by part.

  1. outline: one AI request splits the brief into parts of about 20-40 s (title + what happens), or a plain split when the AI fails
  2. every part is designed like a normal video (same brand, same palette as part 1), its design is SAVED right away (mgl.work checkpoint)
  3. when all designs exist the parts are rendered (in parallel, draft or final), sound is made per part, everything is joined into ONE mp4
If the run stops anywhere (free quota, time limit, crash) the saved parts stay; the next run with the same brief continues with the first missing part.
"""
import json, math, os, re, shutil, subprocess, time

from . import gemini
from . import work as WK

MIN_PART, MAX_PART, TARGET_PART = 12.0, 45.0, 30.0
MAX_TOTAL = 600
OUTLINE_SYSTEM = 'You are a documentary / explainer video director. You split a long video into parts. Answer with JSON only.'


def n_parts(total):
    return max(2, int(math.ceil(float(total) / TARGET_PART)))


def outline_prompt(brief, total, n, size_key):
    return ('Split this video into %d parts. Total length %s seconds, canvas %s.\nBrief: "%s"\n\n'
            'Return ONE JSON object: {"title": "short video title", "parts": [{"title": "part title", "brief": "2-3 sentences: what the viewer sees and learns in this part, '
            'the key text ideas, how it connects to the previous part", "seconds": number}]}\n'
            'Rules: exactly %d parts, a clear story arc (hook, development, ending), every part %d-%d seconds, seconds add up to %s, no part repeats another.'
            % (n, total, size_key, brief.strip()[:700], n, MIN_PART, MAX_PART, total))


def fallback_outline(brief, total, n):
    names = ['Opening', 'Setup'] + ['Part %d' % i for i in range(3, n)] + ['Ending']
    names = names[:n] if n <= len(names) else names + ['Part %d' % i for i in range(len(names) + 1, n + 1)]
    return [{'title': names[i], 'brief': '%s (part %d of %d of the long video "%s"): continue the story without repeating earlier parts.' % (names[i], i + 1, n, brief[:200]), 'seconds': total / n} for i in range(n)]


def clean_outline(data, total, n):
    parts = []
    for p in (data.get('parts') if isinstance(data, dict) else None) or []:
        if not isinstance(p, dict): continue
        try: sec = float(p.get('seconds'))
        except Exception: sec = TARGET_PART
        parts.append({'title': str(p.get('title') or 'Part')[:80], 'brief': str(p.get('brief') or p.get('title') or '')[:600], 'seconds': sec})
    if len(parts) < 2: raise ValueError('outline has no usable parts')
    parts = parts[:max(n + 3, 4)]
    s = sum(max(1.0, p['seconds']) for p in parts)
    for p in parts:                                   # scale to the wanted total, keep every part inside its limits
        p['seconds'] = min(MAX_PART, max(MIN_PART, p['seconds'] * total / s))
    diff = total - sum(p['seconds'] for p in parts)
    for _ in range(6):                                # spread the rounding rest over the parts that still have room
        room = [p for p in parts if (diff > 0 and p['seconds'] < MAX_PART - 0.01) or (diff < 0 and p['seconds'] > MIN_PART + 0.01)]
        if abs(diff) < 0.05 or not room: break
        add = diff / len(room)
        for p in room: p['seconds'] = min(MAX_PART, max(MIN_PART, p['seconds'] + add))
        diff = total - sum(p['seconds'] for p in parts)
    for p in parts: p['seconds'] = round(p['seconds'], 1)
    return parts


def style_anchor(spec):
    """one line that keeps later parts looking like part 1 (backgrounds + colours + camera)"""
    from . import spec as S
    bg = spec.get('background', '')
    styles = [bg] if isinstance(bg, str) else [str(k.get('style')) for k in bg if isinstance(k, dict) and k.get('style')]
    cols = []
    for L in spec.get('layers', []):
        if isinstance(L, dict):
            for key in ('color', 'color2', 'grad_from', 'grad_to', 'fill'):
                v = L.get(key)
                if isinstance(v, str) and v.startswith('#') and v not in cols and S.parse_color(v): cols.append(v)
    return 'STYLE OF PART 1 (keep the same look): backgrounds %s; main colours %s; %s.' % (', '.join(dict.fromkeys(styles)) or 'as part 1', ', '.join(cols[:5]) or 'as part 1', 'with camera moves' if spec.get('camera') else 'no camera moves')


def part_prompt(brief, idx, n, part, total, anchor, prev_title):
    t = ('LONG VIDEO "%s" (%ds in total, %d parts). You make PART %d of %d (%.0f seconds): %s.\nWhat happens in this part: %s\n'
         % (brief[:300], total, n, idx + 1, n, part['seconds'], part['title'], part['brief']))
    if idx > 0: t += 'The previous part was "%s"; continue from it, never repeat it, no new logo intro.\n' % prev_title
    if idx < n - 1: t += 'Do NOT end the video: no "thanks for watching" or closing logo (more parts follow); end with a clean frame that flows into the next part.\n'
    else: t += 'This is the LAST part: finish with a clear ending.\n'
    if anchor: t += anchor + '\n'
    return t


def _slug(text):
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_')[:40] or 'long_video'


def concat_videos(paths, out):
    lst = out + '.txt'
    open(lst, 'w').write(''.join("file '%s'\n" % os.path.abspath(p).replace("'", "'\\''") for p in paths))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', '-movflags', '+faststart', out], check=True)
    os.remove(lst)


def concat_audio(paths, out):
    lst = out + '.txt'
    open(lst, 'w').write(''.join("file '%s'\n" % os.path.abspath(p).replace("'", "'\\''") for p in paths))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out], check=True)
    os.remove(lst)


def run_long(prompt, total, out_dir, ask, size='16:9', images=None, mem=None, root='.', log=print, sound='kinetic', resume=True, agent_mod=None, key=None, keep=False):
    """-> dict(video, parts, boundaries, name, resumed). Raises when a part could not be designed (the saved parts stay for the next run)."""
    import render as R
    from . import spec as S, engine as E
    import agent as AG
    agent_mod = agent_mod or AG
    from .memory import Memory
    mem = mem or Memory(root)
    total = float(total)
    if not (MIN_PART <= total <= MAX_TOTAL): raise ValueError('long video: 12 to %d seconds' % MAX_TOTAL)
    size_key = E.norm_size(size) or '16:9'
    os.makedirs(out_dir, exist_ok=True)
    wk = WK.Work(root, key or WK.make_key(prompt, total, size_key, 'ai'), enabled=resume)
    state = wk.load()
    resumed = bool(state and any(p.get('spec') for p in state['parts']))
    if state:
        have = sum(1 for p in state['parts'] if p.get('spec'))
        log('[resume] saved work found: %d of %d parts are already designed - continuing' % (have, len(state['parts'])))
    else:
        n = n_parts(total)
        try:
            txt = ask(OUTLINE_SYSTEM, [{'role': 'user', 'parts': [gemini.text_part(outline_prompt(prompt, int(total), n, size_key))]}])
            parts = clean_outline(gemini.extract_json(txt), total, n)
        except Exception as ex:
            if 'budget' in str(ex).lower(): raise
            log('   outline by AI failed (%s) - using a plain split' % ex)
            parts = fallback_outline(prompt, total, n)
        state = {'prompt': prompt, 'total': total, 'size': size_key, 'parts': [dict(p, spec=None) for p in parts], 'done': False, 'created': int(time.time())}
        wk.save(state)
    parts = state['parts']
    N = len(parts)
    anchor = style_anchor(parts[0]['spec']) if parts[0].get('spec') else ''
    for i, p in enumerate(parts):
        if p.get('spec'): continue
        log('[part %d/%d] %s' % (i + 1, N, p['title']))
        sp = agent_mod.run_agent(part_prompt(prompt, i, N, p, int(total), anchor, parts[i - 1]['title'] if i else ''), p['seconds'], os.path.join(out_dir, 'part_%02d' % (i + 1)), ask,
                                 review=False, size=size_key, images=images if i == 0 else None, mem=mem, root=root, log=lambda *a: None, render_final=False, update_memory=False, plan=False)
        p['spec'] = sp
        wk.save(state)                               # saved right away: a stop after this line loses nothing
        log('   part %d/%d designed and saved (%d requests so far)' % (i + 1, N, getattr(ask, 'calls', 0)))
        if i == 0: anchor = style_anchor(sp)
    name = _slug(prompt)
    # ---- render every part, then join
    vids, wavs, bounds, t_acc = [], [], [], 0.0
    ctx = S.Context(root)
    sound = (sound or 'none').strip().lower()
    for i, p in enumerate(parts):
        log('[long-render] part %d/%d' % (i + 1, N))
        pv = os.path.join(out_dir, 'part_%02d.mp4' % (i + 1))
        R.render_video(p['spec'], pv, ctx, quiet=True)
        vids.append(pv)
        if sound != 'none':
            try:
                from . import sound as SND
                w = os.path.join(out_dir, 'part_%02d.wav' % (i + 1)); SND.compose(p['spec'], w, style=sound); wavs.append(w)
            except Exception as ex:
                log('   sound for part %d skipped (%s)' % (i + 1, ex)); wavs = []; sound = 'none'
        t_acc += float(p['spec']['duration']); bounds.append(round(t_acc, 3))
    log('[long-join] %d parts' % N)
    video = os.path.join(out_dir, 'video.mp4')
    concat_videos(vids, video)
    if sound != 'none' and wavs:
        try:
            from . import export as X
            allw = os.path.join(out_dir, 'music_sfx.wav'); concat_audio(wavs, allw)
            X.add_audio(video, allw, os.path.join(out_dir, name + '_with_sound.mp4'))
            log('video with sound -> %s_with_sound.mp4' % name)
        except Exception as ex:
            log('   joining the sound failed (the silent video is still there): %s' % ex)
    for f in vids + wavs:
        try: os.remove(f)
        except OSError: pass
    # one spec for the page / exports: the title + the parts (the full designs stay in the checkpoint-free folder)
    json.dump({'title': name, 'duration': round(t_acc, 2), 'size': size_key, 'long': True, 'parts': [{'title': p['title'], 'seconds': p['seconds'], 'brief': p['brief']} for p in parts], 'cuts': bounds[:-1]},
              open(os.path.join(out_dir, 'long_plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    rep = ['# Long video report', '', 'Brief: %s' % prompt, 'Length: %.0f s in %d parts%s' % (t_acc, N, ' (continued from saved work)' if resumed else ''), '']
    rep += ['%d. %s (%.0f s): %s' % (i + 1, p['title'], p['seconds'], p['brief']) for i, p in enumerate(parts)]
    rep += ['', 'AI requests used in this run: %s' % getattr(ask, 'calls', '?')]
    open(os.path.join(out_dir, 'report.md'), 'w', encoding='utf-8').write('\n'.join(rep))
    if not keep: wk.clear()          # a draft keeps the designs, so pressing Final renders them without any new AI request
    return {'video': video, 'parts': N, 'boundaries': bounds, 'name': name, 'resumed': resumed}
