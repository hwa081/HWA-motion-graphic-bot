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


def render_video(spec, out_mp4, ctx, crf=16, quiet=False):
    check_ffmpeg()
    S.setup(spec)
    fps = int(spec.get('fps', 30))
    n = int(round(float(spec['duration']) * fps))
    os.makedirs(os.path.dirname(os.path.abspath(out_mp4)), exist_ok=True)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (E.W, E.H), '-r', str(fps),
           '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', str(crf), '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', out_mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    try:
        for i in range(n):
            fr = S.render_frame(spec, i / fps, ctx)
            p.stdin.write(fr.tobytes())
            if not quiet and i % 30 == 0:
                print('  frame %d/%d  (%.0fs)' % (i, n, time.time() - t0), flush=True)
        p.stdin.close()
    except BrokenPipeError:
        pass
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
