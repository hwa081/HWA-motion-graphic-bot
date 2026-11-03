# Code scene reference (scene.py)

You write ordinary Python (numpy / OpenCV / Pillow) that paints one video frame as a function of time. Start with `from mgl.api import *`.

## Contract
```python
from mgl.api import *
DURATION = 10          # seconds (1..60)
SIZE = '16:9'          # '16:9' 1920x1080 | '9:16' 1080x1920 | '1:1' 1080x1080   (a plain string literal on its own line)
FPS = 30               # optional
def setup(): ...       # optional, runs once (load images, build tables). Do NOT call canvas() at import time, only inside setup/draw.
def draw(f, t):        # f: float32 RGB array (H, W, 3), values 0..1, starts as zeros. t: seconds.
    f[:] = bg('dark_aurora', t)      # paint EVERY pixel, then add things on top. Must be a pure function of t (no state, no randomness without a fixed seed).
```
Coordinates: pixels, origin top-left, canvas() returns (W, H), center() the middle. Colours are (r, g, b) tuples in 0..1.

## Helpers (all in `from mgl.api import *`)
* Backgrounds: `bg(style, t)` -> frame array; styles dark_aurora, light_pastel, neon_night, ocean, sunset, mono_dark, mono_light. `mix(a, b, m)` crossfades arrays. `gradient(c1, c2, angle=90)`.
* Easing, all take 0..1 and return 0..1: `sm` smoothstep, `eo3` ease-out, `ei3` ease-in, `eio` ease-in-out, `eob(x, 1.6)` overshoot. `seg(t, a, b)` = clamp((t-a)/(b-a)), `lerp(a, b, x)`, `lerpc(c1, c2, x)`, `clamp(x, 0, 1)`.
* Text: `draw_text(f, "Hello", font_path('bold_italic'), size_px, x, y, anchor='c', color=(1,1,1), op=1.0, blur=0, grad=None, rot=0, shadow=0)`; anchor 'c'/'l'/'r'; y = vertical centre of the line. Fonts: bold_italic, medium_italic, italic, bold, medium, regular. `text_w(txt, font_path(..), size)` measures width. Width is about chars x size x 0.6: keep text inside the canvas.
* Shapes: `draw_rr(f, cx, cy, w, h, radius, fill=(1,1,1), fa=1.0, fill2=None, border=None, ba=0, bw=2, rot=0, op=1.0, shadow=0, sh_dy=0, sh_blur=20, shadow_color=(0,0,0))` rounded rectangle / pill / circle (radius = w/2). `circle(f, (x,y), r, color, thickness=-1, op=1)`, `aaline(f, p1, p2, color, thickness, op)`, `poly(f, points, color, thickness, closed, op)`, `glow(f, x, y, r, color, op)`, `draw_emoji(f, "🚀", x, y, px, op)`.
* Ready-made pieces: `draw_chip(f, emoji, label, x, y, scale, rot, light, op)`, `draw_card(f, 'custom', 0, x, y, scale, yaw, roll, op, {"title":..,"big_text":..,"header":(r,g,b)})`.
* **`layer(f, t, {...})`** draws any layer of the JSON library (text with reveal/count/gradient, chart, device, progress, blob, particles, grid, chip, card, image, transition ...) exactly as described in docs/LIBRARY.md - use it for anything the JSON library already does well, and write numpy code for the rest. Times inside the dict are scene seconds.
* `spec_frame(spec_dict, t)` renders a full JSON scene (float frame): use as a background or a sub-scene.
* Images: `im = image('assets/photo.png')` (RGBA float, in `setup()`), `paste(f, im, x, y, w=None, h=None, op=1, rot=0)`.
* Effects toolkit: `noise2(x, y, t, seed)` smooth noise 0..1 (arrays ok), `np`, `cv2` (GaussianBlur, warpAffine, remap ...), `PIL`, `math`, `random` (seed it).
* Compositing: `over(f, premultiplied_rgb, alpha, x0, y0, op)`.

## Performance and safety (the sandbox enforces these)
* Target < 0.6 s per frame at 1080p: avoid per-pixel Python loops; use numpy on arrays; compute big grids once in `setup()`; blur at low resolution and upscale.
* No network, no files except assets/ and what you write. No threads. A hard time limit stops runaway code.
* Never produce NaN/inf (guard divisions, sqrt, log). Clamp indices.

## Quality (checked automatically)
Text must not be cut off, overlapping, too small (< 28 px, < 40 px on 9:16), or low contrast; no blank stretches; something must move; the last second must still show the closing scene. Vary scenes: different layouts, animations and backgrounds. Follow the brand kit and lessons you are given.

## Writing reusable components (this is how you improve the library)
If you need an effect that does not exist (liquid blob, 3D globe, ripple, wave text, glitch, particles with physics ...), write it as `custom/<name>.py` (lowercase, 3-30 chars), then call the tool `register`:
```python
from mgl.api import *
DOC = "ripples(f, t, x, y, color=(1,1,1), n=4, speed=1.0, max_r=500, width=6, op=1.0): expanding concentric rings. Example: ripples(f, t, 960, 540, (0.4,0.8,1))"
def ripples(f, t, x, y, color=(1,1,1), n=4, speed=1.0, max_r=500, width=6, op=1.0): ...
def smoke(f, t): ripples(f, t, f.shape[1] // 2, f.shape[0] // 2)     # must draw something visible, fast
```
After `register` succeeds the module is saved for ALL later videos (`from custom.ripples import *`); the list is in custom/INDEX.md.
