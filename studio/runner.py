#!/usr/bin/env python3
"""Runs INSIDE the sandbox process (started by studio/sandbox.py):  python studio/runner.py <action> <params.json>
actions: check | frames | frame | qa | video | smoke        results are written to out/result.json (+ images / video in out/)"""
import importlib.util, json, os, re, socket, sys, time, traceback

def _blocked(*a, **k):
    raise PermissionError('network access is disabled in the sandbox')

import ssl, urllib.request   # noqa: F401  (import first, then cut the network)
for _name in ('connect', 'connect_ex', 'sendto', 'bind'):
    setattr(socket.socket, _name, _blocked)
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

import numpy as np, cv2
sys.path.insert(0, os.getcwd())
from mgl import engine as E, qa as QA

OUT = 'out'
os.makedirs(OUT, exist_ok=True)


def finish(res):
    with open(os.path.join(OUT, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False)
    sys.exit(0)


def tb_text(limit=14):
    lines = traceback.format_exc().strip().splitlines()
    keep = [l for l in lines if 'runner.py' not in l]
    return '\n'.join(keep[-limit:])


def load_scene(path='scene.py'):
    src = open(path, encoding='utf-8').read()
    m = re.search(r'^SIZE\s*=\s*[\'"]([^\'"]+)[\'"]', src, re.M)
    E.set_size(m.group(1) if m else '16:9')
    spec = importlib.util.spec_from_file_location('scene', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['scene'] = mod
    spec.loader.exec_module(mod)
    for need in ('DURATION', 'draw'):
        if not hasattr(mod, need): raise AttributeError('scene.py must define %s' % need)
    d = mod.DURATION
    if not isinstance(d, (int, float)) or not (1 <= d <= 60): raise ValueError('DURATION must be a number between 1 and 60 (got %r)' % (d,))
    if not callable(mod.draw): raise TypeError('draw must be a function draw(f, t)')
    if E.norm_size(getattr(mod, 'SIZE', '16:9')) is None: raise ValueError("SIZE must be '16:9', '9:16' or '1:1'")
    E.set_size(getattr(mod, 'SIZE', '16:9'))
    if hasattr(mod, 'setup'): mod.setup()
    return mod


def make_render(mod):
    def render(t):
        f = np.zeros((E.H, E.W, 3), np.float32)
        r = mod.draw(f, float(t))
        if isinstance(r, np.ndarray): f = r
        if f.ndim != 3 or f.shape[0] != E.H or f.shape[1] != E.W or f.shape[2] != 3:
            raise ValueError('draw must leave a frame of shape (%d, %d, 3); got %s' % (E.H, E.W, getattr(f, 'shape', None)))
        if not np.isfinite(f).all(): raise ValueError('the frame contains NaN or infinity at t=%.2f (check divisions / sqrt / log)' % t)
        return (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)
    return render


def sheet(frames, times, cols=4, tile_w=480):
    tiles = []
    for fr, t in zip(frames, times):
        s = cv2.resize(fr, (tile_w, int(tile_w * fr.shape[0] / fr.shape[1])), interpolation=cv2.INTER_AREA)
        s = np.ascontiguousarray(s)
        cv2.putText(s, '%.1fs' % t, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(s, '%.1fs' % t, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2, cv2.LINE_AA)
        tiles.append(s)
    while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
    return np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])


def main():
    action, pfile = sys.argv[1], sys.argv[2]
    params = json.load(open(pfile, encoding='utf-8'))
    res = {'ok': True, 'action': action}
    try:
        if action == 'smoke':
            name = params['module']
            spec = importlib.util.spec_from_file_location('custom_' + name, os.path.join('custom', name + '.py'))
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            E.set_size(params.get('size', '16:9'))
            if not isinstance(getattr(mod, 'DOC', None), str) or len(mod.DOC) < 20: raise AttributeError('custom module needs DOC = "one-paragraph description with the call signature and an example"')
            if not callable(getattr(mod, 'smoke', None)): raise AttributeError('custom module needs a function smoke(f, t) that calls its own effect')
            f = np.zeros((E.H, E.W, 3), np.float32); before = f.copy()
            t0 = time.time(); r = mod.smoke(f, 1.0); dt = time.time() - t0
            if isinstance(r, np.ndarray): f = r
            if not np.isfinite(f).all(): raise ValueError('smoke produced NaN/inf')
            if float(np.abs(f - before).max()) < 0.02: raise ValueError('smoke() drew nothing visible')
            if dt > 3: raise ValueError('smoke() took %.1fs - the effect is too slow (target < 0.5 s per frame)' % dt)
            res.update(doc=mod.DOC, seconds=round(dt, 3))
            finish(res)
        mod = load_scene()
        render = make_render(mod)
        dur = float(mod.DURATION)
        res.update(duration=dur, size=E.canvas_key(), fps=int(getattr(mod, 'FPS', 30)))
        if action == 'check':
            t0 = time.time(); render(0.0); render(dur * 0.5); render(max(0.0, dur - 0.05))
            per = (time.time() - t0) / 3
            res['seconds_per_frame'] = round(per, 3)
            if per > 1.5: res['warning'] = 'about %.1fs per frame - a %.0fs video would take %.0f minutes to render; simplify heavy effects (fewer full-frame passes, smaller arrays)' % (per, dur, per * dur * res['fps'] / 60)
        elif action == 'frames':
            times = [min(max(0.0, float(t)), dur - 0.02) for t in (params.get('times') or [dur * (i + 0.5) / 8 for i in range(8)])][:12]
            frames, per = [], []
            for t in times:
                t0 = time.time(); frames.append(render(t)); per.append(time.time() - t0)
            cv2.imwrite(os.path.join(OUT, 'preview.png'), cv2.cvtColor(sheet(frames, times), cv2.COLOR_RGB2BGR))
            res.update(times=times, seconds_per_frame=round(sum(per) / len(per), 3))
        elif action == 'frame':
            t = min(max(0.0, float(params.get('t', 0))), dur - 0.02)
            fr = render(t)
            if fr.shape[1] > 1280: fr = cv2.resize(fr, (1280, int(1280 * fr.shape[0] / fr.shape[1])), interpolation=cv2.INTER_AREA)
            cv2.imwrite(os.path.join(OUT, 'frame.png'), cv2.cvtColor(fr, cv2.COLOR_RGB2BGR)); res['t'] = t
        elif action == 'qa':
            rep = QA.analyze_frames(render, dur, E.canvas_key(), samples=int(params.get('samples', 14)))
            res.update(errors=rep['errors'][:12], warnings=rep['warnings'][:12])
        elif action == 'video':
            import subprocess
            fps = int(getattr(mod, 'FPS', 30)); n = int(round(dur * fps))
            outp = os.path.join(OUT, params.get('name', 'video.mp4'))
            p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (E.W, E.H), '-r', str(fps), '-i', '-', '-an',
                                  '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', outp], stdin=subprocess.PIPE)
            for i in range(n):
                p.stdin.write(render(i / fps).tobytes())
            p.stdin.close()
            if p.wait() != 0: raise RuntimeError('ffmpeg failed')
            res.update(frames=n, file=os.path.basename(outp))
        else:
            raise ValueError('unknown action %s' % action)
    except SystemExit:
        raise
    except BaseException as ex:
        res = {'ok': False, 'action': action, 'error': '%s: %s' % (type(ex).__name__, ex), 'traceback': tb_text()}
    finish(res)


if __name__ == '__main__':
    main()
