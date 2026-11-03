"""mgl.learn - turns outcomes (QA findings, AI review, user feedback) into lessons the bot reads next time."""
import json
from . import gemini
from .memory import now_iso

# keyword in a QA/review message  ->  (kind, lesson text)
QA_LESSONS = [
    ('Text cut off', 'dont', 'Long text got cut off at the canvas edge. Keep every text line short: width is about characters x size x 0.6 and must stay under 90% of the canvas width.'),
    ('Text overlap', 'dont', 'Stacked text layers overlapped. Keep at least 1.2 x the font size between the y positions of two lines, and time them apart.'),
    ('Low contrast', 'dont', 'Text was hard to read on its background. Use light text on dark backgrounds and near-black text on light backgrounds.'),
    ('too small', 'dont', 'Some text was too small for a phone screen. Use at least 28px (16:9) or 40px (9:16) for every readable line.'),
    ('ends on an empty background', 'dont', 'The video ended with nothing on screen. Keep the closing scene visible until the very end, with no out animation.'),
    ('Empty stretch', 'dont', 'There was an empty stretch between scenes. Start the next scene before the previous one fully disappears.'),
    ('Safe area', 'dont', 'Text sat where app buttons cover vertical videos. Keep text between 8% and 78% of the height in 9:16.'),
    ('Crowded', 'dont', 'Too many layers were visible at once. Show one idea per scene and stagger the rest.'),
    ('entrance animations', 'dont', 'The video repeated the same few entrance animations. Use at least 4 different ones and change the style from scene to scene.'),
    ('one background', 'dont', 'The whole video used one background style. Change background style between scenes with a fade.'),
    ('no transitions', 'dont', 'There were no transitions between scenes. Use wipe, iris, stripes, flash or glitch transitions at scene changes.'),
    ('no camera movement', 'do', 'Add camera movement: a slow push-in during scenes and a bigger move at scene changes.'),
    ('same kinds of layers', 'dont', 'Consecutive scenes looked alike. Give every scene a different layout archetype.'),
    ('Stagger', 'dont', 'Many layers started at the same instant. Stagger group items by 0.1-0.25 s.'),
]


def lessons_from_qa(messages):
    out = []
    for m in messages:
        for key, kind, text in QA_LESSONS:
            if key.lower() in m.lower():
                out.append({'kind': kind, 'text': text, 'weight': 1}); break
    return out


def lessons_from_review(problems, score):
    out = []
    for p in problems[:5]:
        p = str(p).strip()
        if len(p) > 12:
            out.append({'kind': 'dont', 'text': 'Reviewer found (score %.0f/10): %s' % (score, p[:220]), 'weight': 1})
    return out


def lessons_from_success(summary, score, rating=None):
    """only for clearly good results, so memory does not fill with noise"""
    if (rating or 0) >= 4 or (score or 0) >= 9:
        bits = []
        if summary.get('backgrounds'): bits.append('backgrounds ' + '/'.join(map(str, dict.fromkeys(summary['backgrounds']))))
        if summary.get('transitions'): bits.append('transitions ' + '/'.join(summary['transitions']))
        if summary.get('entrance_anims'): bits.append('entrances ' + '/'.join(list(summary['entrance_anims'])[:4]))
        if summary.get('kinds'): bits.append('layouts ' + '/'.join(summary['kinds']))
        if bits:
            return [{'kind': 'do', 'text': 'This combination worked well: ' + '; '.join(bits) + '.', 'weight': 2 if (rating or 0) >= 4 else 1}]
    return []


FEEDBACK_SYSTEM = 'You turn user feedback about a motion-graphics video into short, reusable design rules. Answer with JSON only.'


def feedback(mem, did, rating, note, ask=None, log=print):
    """store the user's rating/note on the design and learn from it. returns dict(lessons=[...], design=card)"""
    d = mem.design(did)
    if d is None:
        raise KeyError('design %s not found (available: %s)' % (did, ', '.join(x['id'] for x in mem.designs[-5:]) or 'none'))
    mem.set_feedback(did, rating, note)
    items = []
    if ask is not None and (note or rating):
        try:
            txt = ask(FEEDBACK_SYSTEM, [{'role': 'user', 'parts': [{'text': (
                'The user rated a generated video %s/5 and wrote: "%s"\n\nThe video\'s brief: %s\nIts design choices: %s\n\n'
                'Write 1-4 reusable rules. For a low rating say what to AVOID or change; for a high rating say what to KEEP. '
                'Each rule must be concrete (numbers, animation names, layout choices) and general enough to apply to other videos.\n'
                'Return JSON: {"lessons":[{"kind":"do"|"dont","text":"...","weight":1-3}]}' % (rating, note or '(no text)', d['prompt'], json.dumps(d['summary'])[:900]))}]}])
            data = gemini.extract_json(txt)
            items = [i for i in (data.get('lessons') or []) if isinstance(i, dict)]
            for i in items: i['weight'] = max(2, int(i.get('weight', 2) or 2))      # explicit user feedback counts more
        except Exception as ex:
            log('   feedback analysis skipped (%s) - storing the note as it is' % ex)
    if not items and note:
        r = int(rating or 3)
        items = [{'kind': 'dont' if r <= 2 else 'do', 'text': ('User feedback: ' + note.strip())[:260], 'weight': 3 if r <= 2 or r >= 4 else 1}]
    n = mem.add_lessons(items, source='feedback')
    mem.log('## %s - feedback on %s\nRating: %s/5. Note: %s\nLessons stored: %s' % (now_iso(), did, rating, note or '-', '; '.join(i['text'] for i in items) or 'none'))
    return {'lessons': items, 'new': n, 'design': d}


def run_summary(prompt, summary, qa_before, qa_after, review_rounds, final_score):
    """text for report.md and learning_log.md: what was better, what was wrong, what changed"""
    wrong = list(dict.fromkeys(qa_before.get('errors', []) + qa_before.get('warnings', [])))
    fixed = [w for w in wrong if w not in (qa_after.get('errors', []) + qa_after.get('warnings', []))]
    left = qa_after.get('errors', []) + qa_after.get('warnings', [])
    lines = ['Brief: %s' % prompt[:160]]
    lines.append('Design: backgrounds %s; entrances %s; transitions %s; camera %s' % (
        ', '.join(dict.fromkeys(map(str, summary.get('backgrounds', [])))), ', '.join(list(summary.get('entrance_anims', {}))[:5]) or '-',
        ', '.join(summary.get('transitions', [])) or 'none', 'yes' if summary.get('camera') else 'no'))
    lines.append('What was wrong at first: %s' % ('; '.join(w[:110] for w in wrong[:6]) or 'nothing found by the automatic checks'))
    lines.append('Fixed by the bot: %s' % ('; '.join(w[:80] for w in fixed[:6]) or '-'))
    lines.append('Still open: %s' % ('; '.join(w[:110] for w in left[:5]) or 'nothing'))
    for rv in review_rounds:
        lines.append('AI review round %d: score %.1f %s' % (rv['round'], rv['score'], ('- ' + '; '.join(rv['problems'][:3])) if rv['problems'] else '- no problems'))
    return '\n'.join(lines)
