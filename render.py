#!/usr/bin/env python3
"""Render a JSON scene spec to MP4 (and/or a preview contact sheet).

    python render.py examples/saas_intro.json --out out/video.mp4 --preview out/preview.png
"""
import argparse, json, os, shutil, subprocess, sys, time
import numpy as np, cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from mgl import spec as S
from mgl import engine as E


def load_spec(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def check_ffmpeg():
    if shutil.which('ffmpeg') is None:
        raise SystemExit('ffmpeg not found. Install it (Ubuntu: sudo apt-get install ffmpeg).')


def preview_sheet(spec, out_png, ctx, n=12, cols=4, tile_w=480):
    """n evenly spaced frames in one PNG, each labelled with its time. Returns the list of render warnings."""
    S.setup(spec)
    dur = float(spec['duration'])
    times = [dur * (0.03 + 0.94 * i / max(1, n - 1)) for i in range(n)]
    tiles = []
    for t in times:
        fr = S.render_frame(spec, t, ctx)
        small = cv2.resize(fr, (tile_w, int(tile_w * E.H / E.W)), interpolation=cv2.INTER_AREA)
        small = np.ascontiguousarray(small)
        cv2.putText(small, '%.1fs' % t, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(small, '%.1fs' % t, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2, cv2.LINE_AA)
        tiles.append(small)
    while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    cv2.imwrite(out_png, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
    return ctx.warnings


_JOB = {}
DEFAULTS = {'scale': 1.0, 'fps': None, 'preset': 'medium', 'crf': None}      # run.py sets a draft here (every render_video call then makes a draft)


def _worker_frame(i):
    """runs in a worker process (fork): one finished frame as bytes (+ new warnings)"""
    spec, ctx, fps, size = _JOB['spec'], _JOB['ctx'], _JOB['fps'], _JOB['size']
    n0 = len(ctx.warnings)
    try:
        fr = S.render_frame(spec, i / fps, ctx)
        if size is not None: fr = cv2.resize(fr, size, interpolation=cv2.INTER_AREA)
        return i, fr.tobytes(), list(ctx.warnings[n0:])
    except Exception as ex:                      # one bad frame must not kill the video: the parent repeats the previous frame
        return i, None, ['frame %d failed (%s) - previous frame repeated' % (i, str(ex)[:80])]


def default_workers():
    try: w = int(os.environ.get('RENDER_WORKERS', '') or 0)
    except ValueError: w = 0
    if w > 0: return w
    return max(1, min(4, os.cpu_count() or 1))


def render_video(spec, out_mp4, ctx, crf=None, quiet=False, scale=None, fps=None, preset=None, workers=None):
    """Never gives up on the first problem: parallel -> one worker -> one worker with a lighter encoder; a broken frame repeats the previous one."""
    last = None
    for k, (w, pr) in enumerate([(workers, preset), (1, preset), (1, 'ultrafast')]):
        try:
            if k: print('  [render] retry %d/2 (%s)' % (k, 'one worker' if k == 1 else 'one worker, light encoder'), flush=True)
            return _render_once(spec, out_mp4, ctx, crf, quiet, scale, fps, pr, w)
        except (Exception, SystemExit) as ex:
            last = ex; print('  [render] attempt failed: %s' % str(ex)[:200], flush=True)
            try: os.remove(out_mp4)
            except OSError: pass
    raise last


def _render_once(spec, out_mp4, ctx, crf=None, quiet=False, scale=None, fps=None, preset=None, workers=None):
    """scale < 1 and a lower fps make a fast DRAFT; workers > 1 renders frames in parallel (same pixels as one worker)."""
    check_ffmpeg()
    S.setup(spec)
    scale = DEFAULTS['scale'] if scale is None else scale
    preset = preset or DEFAULTS['preset']
    crf = crf or DEFAULTS['crf'] or 16
    fps = int(fps or DEFAULTS['fps'] or spec.get('fps', 30))
    n = int(round(float(spec['duration']) * fps))
    ow, oh = E.W, E.H
    size = None
    if scale and scale < 0.999:
        ow, oh = max(2, int(E.W * scale) // 2 * 2), max(2, int(E.H * scale) // 2 * 2); size = (ow, oh)
    os.makedirs(os.path.dirname(os.path.abspath(out_mp4)), exist_ok=True)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (ow, oh), '-r', str(fps),
           '-i', '-', '-an', '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', out_mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    workers = workers or default_workers()
    step = 15 if n >= 60 else 5
    last_frame = [None]
    try:
        if workers > 1 and n >= 24 and hasattr(os, 'fork'):
            import multiprocessing as mp
            _JOB.update(spec=spec, ctx=ctx, fps=fps, size=size)
            with mp.get_context('fork').Pool(workers) as pool:
                for i, data, warns in pool.imap(_worker_frame, range(n), chunksize=4):
                    if data is None: data = last_frame[0]
                    if data is None: raise RuntimeError('first frame failed: ' + '; '.join(warns))
                    last_frame[0] = data
                    p.stdin.write(data)
                    for w in warns:
                        if w not in ctx.warnings: ctx.warnings.append(w)
                    if not quiet and i % step == 0:
                        print('  frame %d/%d  (%.0fs, %d workers)' % (i, n, time.time() - t0, workers), flush=True)
        else:
            for i in range(n):
                try:
                    fr = S.render_frame(spec, i / fps, ctx)
                    if size is not None: fr = cv2.resize(fr, size, interpolation=cv2.INTER_AREA)
                    last_frame[0] = fr.tobytes()
                except Exception as ex:
                    if last_frame[0] is None: raise
                    ctx.warnings.append('frame %d failed (%s) - previous frame repeated' % (i, str(ex)[:80]))
                p.stdin.write(last_frame[0])
                if not quiet and i % step == 0:
                    print('  frame %d/%d  (%.0fs)' % (i, n, time.time() - t0), flush=True)
        print('  frame %d/%d  (%.0fs)' % (n, n, time.time() - t0), flush=True) if not quiet else None
        p.stdin.close()
    except BrokenPipeError:
        pass
    except BaseException:
        try: p.kill()
        except Exception: pass
        raise
    rc = p.wait()
    if rc != 0:
        raise SystemExit('ffmpeg failed with exit code %d' % rc)
    return ctx.warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spec')
    ap.add_argument('--out', default='out/video.mp4')
    ap.add_argument('--preview', default=None)
    ap.add_argument('--preview-only', action='store_true')
    a = ap.parse_args()
    spec = load_spec(a.spec)
    errs, warns = S.validate(spec, ROOT)
    for w in warns: print('warning:', w)
    if errs:
        print('SPEC ERRORS:')
        for e in errs: print(' -', e)
        raise SystemExit(1)
    ctx = S.Context(ROOT)
    if a.preview:
        preview_sheet(spec, a.preview, ctx)
        print('preview ->', a.preview)
    if not a.preview_only:
        render_video(spec, a.out, ctx)
        print('video ->', a.out)
    for w in ctx.warnings: print('render warning:', w)


if __name__ == '__main__':
    main()
