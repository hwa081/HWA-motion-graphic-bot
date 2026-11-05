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


EXTRA_PATTERNS = ('*.wfp', '*.fcpxml', '*.xml', '*.srt', '*.gif', '*.webm', '*_poster.png', '*_frames.zip', '*_light.mp4')
MAX_FILES_MB = 60


def _extras(out_dir, dst, oid):
    """editor / preview files next to the video -> outputs/<id>/files/ ; returns ([{name,path,size}], name of the media file the project files expect)"""
    found, total = [], 0
    for pat in EXTRA_PATTERNS:
        for f in sorted(glob.glob(os.path.join(out_dir, pat))):
            if os.path.basename(f) in ('preview.png',) or f in found: continue
            found.append(f)
    res = []
    for f in found:
        sz = os.path.getsize(f)
        if total + sz > MAX_FILES_MB * 1e6: continue
        os.makedirs(os.path.join(dst, 'files'), exist_ok=True)
        shutil.copyfile(f, os.path.join(dst, 'files', os.path.basename(f))); total += sz
        res.append({'name': os.path.basename(f), 'path': 'outputs/%s/files/%s' % (oid, os.path.basename(f)), 'size': sz})
    uniq = sorted(glob.glob(os.path.join(out_dir, '*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9].mp4')))
    return res, (os.path.basename(uniq[-1]) if uniq else '')


def publish(root, out_dir, mode, job='', prompt='', size='', duration='', ai='', keep=30, only_if_job=True, project='', quality='', parent='', formats=''):
    """-> the index entry that was written, or None when there is nothing to publish"""
    video = _pick_video(out_dir) if mode in VIDEO_MODES else None
    report = next((os.path.join(out_dir, r) for r in REPORTS if os.path.isfile(os.path.join(out_dir, r))), None)
    err_rep = os.path.join(out_dir, 'error_report.md')
    if video is None and os.path.isfile(err_rep) and job: report = err_rep
    if video is None and (report is None or (only_if_job and not job)): return None
    if video is None and mode in ('demo', 'spec', 'check', 'assets-check'): return None
    oid = re.sub(r'[^A-Za-z0-9_-]', '', job) or datetime.datetime.utcnow().strftime('r%Y%m%d-%H%M%S')
    base = os.path.join(root, 'outputs'); dst = os.path.join(base, oid)
    os.makedirs(dst, exist_ok=True)
    entry = {'id': oid, 'job': job, 'kind': 'video' if video else 'report', 'title': (prompt or mode)[:90], 'prompt': prompt[:400], 'mode': mode, 'size': size, 'dur': duration, 'ai': ai,
             'date': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'ok': True, 'trashed': False}
    if project: entry['project'] = project
    if quality: entry['quality'] = quality
    if os.path.isfile(os.path.join(out_dir, 'long_plan.json')): entry['long'] = True
    if parent: entry['parent'] = parent
    if formats: entry['formats'] = formats
    if video:
        mb = os.path.getsize(video) / 1e6
        if mb > MAX_VIDEO_MB:
            entry['kind'] = 'report'; entry['ok'] = False
            entry['note'] = 'video is %.0f MB, too big for the repository (limit about %d MB); it is in the Actions artifact' % (mb, MAX_VIDEO_MB)
        else:
            shutil.copyfile(video, os.path.join(dst, 'video.mp4')); entry['video'] = 'outputs/%s/video.mp4' % oid
            try:
                fl, media = _extras(out_dir, dst, oid)
                if fl: entry['files'] = fl
                entry['video_name'] = media or os.path.basename(video)
            except Exception as ex:
                print('extra files not published: %s' % ex)
            if _poster(video, os.path.join(dst, 'poster.jpg')): entry['poster'] = 'outputs/%s/poster.jpg' % oid
        sp = os.path.join(out_dir, 'spec.json')
        if os.path.isfile(sp) and os.path.getsize(sp) < 400_000:
            shutil.copyfile(sp, os.path.join(dst, 'spec.json')); entry['spec'] = 'outputs/%s/spec.json' % oid
    if report == err_rep and video is None:
        entry['ok'] = False
        try:
            allv = open(err_rep, encoding='utf-8').read().splitlines()
            idx = [i for i, l in enumerate(allv) if l.startswith(('ERROR', 'STOPPED', 'could not'))]
            if idx:
                i = idx[-1]
                # the reason often continues on the next indented lines (e.g. "all models failed:" + one line per model)
                tail = [allv[i].strip()]
                for l in allv[i + 1:i + 5]:
                    if l.startswith('  ') and l.strip(): tail.append(l.strip())
                    else: break
                entry['note'] = ' | '.join(tail)[:420]
            else:
                entry['note'] = 'The run stopped before the video was ready'
        except Exception: entry['note'] = 'The run stopped before the video was ready'
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
