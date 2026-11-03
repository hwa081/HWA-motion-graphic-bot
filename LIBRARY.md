# Motion graphics library - scene spec reference

You describe a video as ONE JSON object. The renderer turns it into an MP4 (no sound).
Output ONLY the JSON object. No markdown, no comments, no explanations.

{{CANVAS}}

## Coordinates and units
* Origin top-left. Times are in seconds. `x`,`y` = centre of an element. For text, `y` is the vertical centre of the line.
* Colours: `[r,g,b]` with values 0..1 (or 0..255), `"#rrggbb"`, or a name (white, black, red, green, blue, yellow, orange, pink, purple, teal, cyan, gray).
* Angles in degrees; positive `rot` turns clockwise.

## Top level
```
{ "title": "optional", "duration": 10, "size": "16:9" | "9:16" | "1:1", "fps": 30,
  "background": "dark_aurora" | [keys],  "camera": [keys],  "layers": [ ... ] }
```
`layers` are drawn in order (first = bottom). `duration` 0.5..60.

### background
Styles: `dark_aurora` (black + green/teal), `light_pastel` (white + pink/mint), `neon_night` (navy + purple/pink/blue), `ocean` (deep blue + cyan),
`sunset` (purple + orange/pink), `mono_dark`, `mono_light`. Change over time with keys; `fade` = crossfade seconds starting at `t`:
`"background": [{"t":0,"style":"dark_aurora"},{"t":6,"style":"light_pastel","fade":0.5}]`. Light styles need dark text, dark styles need light text.

### camera
Keys `{t, zoom, x, y}` (zoom 0.2..6, x/y = world point at screen centre); the view glides between keys. Everything moves with the camera unless `"fixed": true`
(headlines that must not move or get cropped should be fixed). Transitions, particles and grid are always screen-space.

## Common layer fields
| field | meaning |
|---|---|
| `type` | text, rrect, circle, line, icon, emoji, chip, card, image, chart, device, progress, blob, particles, grid, transition |
| `start`,`end` | visible between these times (defaults 0 and duration) |
| `x`,`y`,`scale`,`rot`,`opacity`,`blur` | transform (rot works on text, rrect, chip, card, image) |
| `in`,`out` | entrance/exit: `{"anim":"pop","dur":0.5}` or `"pop"`. anim = none, fade, blur, pop, slide_up, slide_down, slide_left, slide_right, zoom, spin, bounce, tilt, rise, wipe_right, wipe_left, wipe_up, wipe_down. `out` plays the same animation in reverse before `end` |
| `keys` | animate any numeric property: `{"x":[[0,300],[1.5,900,"out"]]}`; point = `[time,value]` or `[time,value,ease]` (ease INTO that point: smooth, linear, out, in, inout, back). Colours too (`color`,`grad_from`,`grad_to`,`color2`) |
| `float` | constant gentle drift: `{"y":14,"x":0,"speed":1,"phase":0}` (great for devices, logos, cards) |
| `fixed` | `true` = ignore the camera |

Animatable properties: x, y, scale, rot, opacity, blur (all), plus text: size, color, grad_from, grad_to; rrect: w, h, r; circle: r; line: width; icon: size, color, angle;
emoji: size; chip: w, h; card: yaw, roll, number; image: w, h, zoom, pan_x, pan_y, tilt_x, tilt_y; blob: r, color, color2; chart: progress, w, h; device: w; progress: value, w, h.

## Layer types
**text** `{"type":"text","text":"Hello","font":"bold_italic","size":120,"x":..,"y":..,"anchor":"c","color":[1,1,1]}`
fonts: bold_italic (headlines), medium_italic, italic, bold, medium, regular. Width is about characters x size x 0.6: it must stay under 90% of the canvas width (split long lines into two layers).
`gradient`: `{"from":c,"to":c,"mid":c}`. `reveal`: `{"mode":"words","step":0.3}` | `{"mode":"chars","step":0.05}` (typing) | `{"mode":"letters","step":0.04}` (letters rise one by one).
`count`: animated number, text must contain `{n}`: `{"text":"${n}k","count":{"from":0,"to":128,"dur":1.8,"format":"{:,.0f}"}}`. `shadow` 0..1.

**rrect** (panels, buttons, pills) `{"w":1200,"h":120,"r":60,"fill":c,"fill_opacity":0.35,"fill2":c,"border":c,"border_opacity":0.3,"border_w":2,"shadow":0.4,"shadow_color":c}`. Glass = white fill 0.08-0.15 + white border 0.3. Glow = `shadow_color` + `shadow_dy 0` + big `shadow_blur`.
**circle** `{"r":80,"fill":c}` same style fields. **line** `{"points":[[x,y],[x,y]],"width":4,"color":c}`.
**icon** `{"name":"send|plus|mic|arrow_up|check|cross|star","size":80,"color":c}`. **emoji** `{"char":"🚀","size":120}`.
**chip** (emoji + label pill, 400x150 at scale 1) `{"emoji":"📊","label":"Reports","scale":1,"rot":-5}`; white on light backgrounds, glass on dark ones.
**card** (tilted 3D-style card, 260x360 at scale 1, use 1.2-1.8) `{"kind":"custom","title":"Revenue","big_text":"${n}k","subtitle":"this month","emoji":"📈","header":c,"body":c,"body2":c,"yaw":-18,"roll":-2}`;
`yaw` positive = right edge nearer. Animate counters with `keys:{"number":[[2,0],[4,128,"out"]]}`. Special designs: kind image | note | event | voice.
**chart** `{"kind":"bar|line|donut","data":[30,55,42],"labels":["Jan","Feb","Mar"],"x":..,"y":..,"w":700,"h":420,"colors":[c,c],"text_color":c,"center_text":"100%","grow":{"start":5,"dur":1.4}}` draws itself.
**progress** `{"kind":"bar|ring","x":..,"y":..,"w":520,"h":26,"color":c,"track":c,"label":"{p}%","grow":{"start":6,"dur":1.4}}` (or animate `value` 0..1).
**device** `{"kind":"phone|laptop|browser","path":"assets/shot.png","w":900,"x":..,"y":..,"float":{"y":10}}` puts an image on the screen of a device frame (width `w`; phone is 2.05x taller).
**blob** soft glowing orb `{"r":400,"color":c,"color2":c,"fill_opacity":0.5,"softness":0.8}` (use 1-3 behind content for depth). **particles** `{"count":60,"color":c,"size":3,"speed":1.2,"seed":3}`.
**grid** `{"kind":"dots|lines|crosses","spacing":64,"color":c,"fill_opacity":0.15,"scroll":{"x":10,"y":5},"vignette":0.8}` (tech background texture).
**transition** (full-screen cover between scenes; needs `start` and `end`, 0.6-1.2 s; the screen is fully covered at the MIDDLE, so end the old scene and start the new one there)
`{"style":"wipe|iris|stripes|flash|glitch","direction":"right|left|up|down","color":c,"start":4.2,"end":5.2}`.

## Pictures: three ways
1. **Uploaded assets** (listed in the task as "Assets available"): `{"type":"image","path":"assets/photo.png","w":900,"h":600,"r":40}`.
   Window mode (both `w` and `h`): `fit` "cover" (default, crops to fill) or "contain"; `zoom` >= 1 and `pan_x`,`pan_y` (-1..1) move inside the window = Ken Burns;
   `tilt_x`,`tilt_y` (-35..35) turn it in 3D; `r` rounds corners; `shadow`; `tint` colour recolours a silhouette/icon.
2. **Search the libraries** instead of `path`: `{"type":"image","search":{"section":"photo","query":"modern office team"},"w":900,"h":600}`.
   sections: `photo` (real photos), `illustration` (drawn art), `vector` (flat graphics), `icon` (monochrome icons; add `"style":"color"` for coloured emoji-like icons; use `tint` to recolour), `canva` (the user's own Canva exports).
   Write specific English queries (2-4 words). The system compares the candidates and picks the best one. Use at most 5 searches per video, keep queries different.
3. **Emoji** layers for quick playful decoration.

### Animating a picture (when the user uploaded images)
* Photo: window `w`x`h` with `zoom` 1 -> 1.3 and `pan_x` -0.5 -> 0.5 over the scene; add `tilt_y` -12 -> 6 for depth; `in` zoom/blur.
* Screenshot / UI: `device` frame (laptop or phone) with `float`, or a card-sized image with `tilt_x/tilt_y`, rounded `r`, `shadow`; `in` rise or spin; a caption beside it.
* Logo / cut-out PNG: `in` pop, then `float`; a `blob` behind it; `out` fade.
* Several images: one per scene, different animation family each, or a staggered row of tilted images.

## Scene archetypes (give every scene a DIFFERENT one and a different animation family)
typographic hero (huge headline, letters/blur) | card fan (3 cards with counters) | chip cluster (4-5 chips) | device mockup (laptop/phone + caption) | chart reveal (bar/line/donut + big number) |
big number (count up + label) | image feature (Ken Burns window + text) | logo reveal (circle + logo pop + tagline) | ui prompt bar (rrect + typed text + send icon) | list/steps (3 stacked rrects slide in) | split screen (two halves, different backgrounds).
Animation families: SOFT = fade, blur, slide_up | ENERGETIC = pop, bounce, spin, rise | CLEAN = wipe_*, zoom, tilt. Use one family for the hero of a scene and another for supporting items; change families between scenes.

## Design rules
1. Scenes of 2-4 s; overlap the end of one with the start of the next by 0.2-0.4 s, or cover the change with a transition layer.
2. Stagger group items 0.1-0.25 s apart. Never start more than 4 layers at the same instant.
3. One idea per scene, at most ~8 visible content layers. Decorative blob/particles/grid layers are extra.
4. Headline 100-170 px on 16:9 (80-120 on 9:16), subtitle 40-60, never below 28. Max ~24 characters per line at size > 100.
5. Contrast: light text on dark backgrounds, near-black text on light backgrounds. Use 2 accent colours at most + neutrals (60-30-10 rule).
6. Use the camera: slow push-in (zoom 1 -> 1.1) in every scene, bigger moves between scenes. Keep headlines `fixed` when the camera zooms.
7. Alternate dark and light backgrounds or change style between scenes (fade 0.3-0.5 s). Use at least 4 different entrance animations in a 10 s video.
8. Finish with a closing scene (brand / call to action) that stays visible until `duration`: its layers end at `duration` and have no `out` animation.
9. Follow the BRAND KIT and LESSONS from memory when they are given.
