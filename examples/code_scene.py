"""Example code scene: a custom numpy effect (ripple rings) + library layers + camera-like zoom. 8 s landscape."""
from mgl.api import *

DURATION = 8
SIZE = '16:9'


def rings(f, t, x, y, color, n=5, speed=0.9, max_r=520, width=5, op=1.0):
    """expanding concentric rings (anti-aliased) drawn with cv2 - 1 pass, fast"""
    m = np.zeros((f.shape[0], f.shape[1]), np.float32)
    for i in range(n):
        u = ((t * speed) + i / n) % 1.0
        r = u * max_r
        a = (1 - u) ** 1.5
        cv2.circle(m, (int(x * 16), int(y * 16)), int(r * 16), float(a), width, cv2.LINE_AA, 4)
    over(f, np.broadcast_to(np.array(color, np.float32), f.shape) * m[..., None], m, 0, 0, op)


def draw(f, t):
    W, H = canvas()
    light = sm(seg(t, 4.6, 5.0)) * (1 - sm(seg(t, 7.2, 7.5)))
    f[:] = mix(bg('neon_night', t), bg('light_pastel', t), light)
    zoom = 1.0 + 0.06 * seg(t, 0, 4.8)
    # scene 1: rings behind a letters headline
    if t < 5.2:
        k = 1 - sm(seg(t, 4.6, 5.2))
        rings(f, t, W / 2, H / 2, (0.5, 0.75, 1.0), op=0.9 * k)
        layer(f, t, {"type": "text", "text": "Ripple effect", "font": "bold_italic", "size": 150 * zoom, "x": W / 2, "y": H / 2 - 40,
                     "start": 0.3, "end": 5.2, "reveal": {"mode": "letters", "step": 0.05, "dur": 0.45}, "out": {"anim": "fade", "dur": 0.5}})
        layer(f, t, {"type": "text", "text": "written as code, checked by the bot", "font": "medium_italic", "size": 46, "x": W / 2, "y": H / 2 + 110,
                     "color": [0.8, 0.88, 1.0], "start": 1.2, "end": 5.2, "in": "slide_up", "out": {"anim": "fade", "dur": 0.5}})
    # scene 2: counter + chips on a light background
    if t > 4.8:
        layer(f, t, {"type": "text", "text": "{n}%", "font": "bold_italic", "size": 230, "x": W / 2, "y": H / 2 - 40, "color": [0.1, 0.1, 0.16],
                     "start": 5.0, "end": 8.0, "count": {"from": 0, "to": 98, "dur": 1.6, "format": "{:d}"}, "in": {"anim": "bounce", "dur": 0.7},
                     "gradient": {"from": [0.3, 0.4, 1.0], "to": [0.9, 0.3, 0.7]}})
        for i, (em, lab) in enumerate((("\U0001F680", "Fast"), ("\u2728", "Clean"), ("\U0001F9E0", "Smart"))):
            layer(f, t, {"type": "chip", "emoji": em, "label": lab, "x": W / 2 + (i - 1) * 470, "y": H / 2 + 230, "scale": 0.9, "start": 5.5 + i * 0.2, "end": 8.0,
                         "in": {"anim": "pop", "dur": 0.5}, "float": {"y": 8, "speed": 0.7, "phase": i}})
