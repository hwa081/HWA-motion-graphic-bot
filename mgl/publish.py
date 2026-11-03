"""mgl.publish - put the result where the Studio page can show it.

After a run the video (+ poster, spec, report) is copied to outputs/<id>/ and outputs/index.json is updated (newest first).
The workflow commits outputs/ to the repository, the page reads index.json and plays the video from the repository.
Old videos beyond OUTPUT_KEEP (default 30) are deleted so the repository stays small.
"""
import datetime, glob, json, os, re, shutil
import cv2

REPORTS = ['report.md', 'compare_report.md', 'remix.md', 'study_report.md', 'evolve_report.md', 'checks_report.md', 'learn_report.md', 'feedback_report.md',
           'qa.md', 'lighten_report.md', 'design_matches.md', 'export_notes.md']
VIDEO_MODES = ('ai', 'code', 'demo', 'spec', 'design', 'reference')
MAX_VIDEO_MB = 95          # GitHub refuses files over 100 MB
MAX_REPORTS = 200


def _load_index(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _pick_video(out_dir):
    withs = sorted(glob.glob(os.path.join(out_dir, '*_with_sound.mp4')))
    if withs: return withs[0]
    p = os.path.join(out_dir, 'video.mp4')
    return p if os.path.isfile(p) else None


def _poster(video, dst, w=360):
    cap = cv2.VideoCapture(video)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(n * 0.35)))
    ok, fr = cap.read(); cap.release()
    if not ok: return False
    h = int(w * fr.shape[0] / fr.shape[1]); fr = cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)
    return bool(cv2.imwrite(dst, fr, [cv2.IMWRITE_JPEG_QUALITY, 82]))


def _latest_design(root):
    try:
        d = json.load(open(os.path.join(root, 'memory', 'designs.json'), encoding='utf-8'))
        return d[-1]['id'] if d else ''
    except Exception:
        return ''


def publish(root, out_dir, mode, job='', prompt='', size='', duration='', ai='', keep=30, only_if_job=True):
    """-> the index entry that was written, or None when there is nothing to publish"""
    video = _pick_video(out_dir) if mode in VIDEO_MODES else None
    report = next((os.path.join(out_dir, r) for r in REPORTS if os.path.isfile(os.path.join(out_dir, r))), None)
    if video is None and (report is None or (only_if_job and not job)): return None
    if video is None and mode in ('demo', 'spec', 'check', 'assets-check'): return None
    oid = re.sub(r'[^A-Za-z0-9_-]', '', job) or datetime.datetime.utcnow().strftime('r%Y%m%d-%H%M%S')
    base = os.path.join(root, 'outputs'); dst = os.path.join(base, oid)
    os.makedirs(dst, exist_ok=True)
    entry = {'id': oid, 'job': job, 'kind': 'video' if video else 'report', 'title': (prompt or mode)[:90], 'prompt': prompt[:400], 'mode': mode, 'size': size, 'dur': duration, 'ai': ai,
             'date': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'ok': True, 'trashed': False}
    if video:
        mb = os.path.getsize(video) / 1e6
        if mb > MAX_VIDEO_MB:
            entry['kind'] = 'report'; entry['ok'] = False
            entry['note'] = 'video is %.0f MB, too big for the repository (limit about %d MB); it is in the Actions artifact' % (mb, MAX_VIDEO_MB)
        else:
            shutil.copyfile(video, os.path.join(dst, 'video.mp4')); entry['video'] = 'outputs/%s/video.mp4' % oid
            if _poster(video, os.path.join(dst, 'poster.jpg')): entry['poster'] = 'outputs/%s/poster.jpg' % oid
        sp = os.path.join(out_dir, 'spec.json')
        if os.path.isfile(sp) and os.path.getsize(sp) < 400_000:
            shutil.copyfile(sp, os.path.join(dst, 'spec.json')); entry['spec'] = 'outputs/%s/spec.json' % oid
    if report:
        shutil.copyfile(report, os.path.join(dst, 'report.md')); entry['report'] = 'outputs/%s/report.md' % oid
    if mode in ('ai', 'code'):
        did = _latest_design(root)
        if did: entry['design_id'] = did
    idx_path = os.path.join(base, 'index.json')
    idx = [e for e in _load_index(idx_path) if e.get('id') != oid]
    idx.insert(0, entry)
    # prune: keep the newest `keep` videos and MAX_REPORTS reports; trashed ones go first
    vids = [e for e in idx if e.get('video')]
    drop = set()
    if len(vids) > keep:
        order = sorted(vids, key=lambda e: (not e.get('trashed'), e.get('date', '')))          # trashed first, then oldest
        for e in order[:len(vids) - keep]: drop.add(e['id'])
    reps = [e for e in idx if not e.get('video')]
    for e in reps[MAX_REPORTS:]: drop.add(e['id'])
    for oid2 in drop:
        shutil.rmtree(os.path.join(base, oid2), ignore_errors=True)
    idx = [e for e in idx if e['id'] not in drop]
    json.dump(idx, open(idx_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    return entry
