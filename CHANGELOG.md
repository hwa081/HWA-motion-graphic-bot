# Motion Graphic Bot - merged version

## Native Filmora: free pen shapes
- mgl/native_wfp.py: new layer type `pen` (polygon / polyline from points, fill + second colour, stroke, drop shadow, trim draw-on, transform + opacity keyframes), cloned from a real Filmora project (mgl/templates/pen_sample.wfp). `ngon()` makes circles / polygons / stars. `pen_demo_scene()` = demo. Confirmed by the user: the demo opens and plays in Filmora.
- Bezier curves (from the user's second sample, mgl/templates/pen_curves_sample.wfp): a point may carry `left_ctrl_point` (type 1, incoming) and `right_ctrl_point` (type 2, outgoing) with absolute frame coordinates. Layer points: (x, y) corner or (x, y, left, right). Helpers `circle()` (true round, 4 points) and `smooth()` (Catmull-Rom curve through points, open or closed).
- Not known yet: whether fillType 1 is solid or gradient; the rotation pivot.

## Studio v2: progress, projects, files, Draft/Final, long videos, resume, Activity
### Studio v2 - "slow is fine, failing is not"
- AI: patient retries (429 / 5xx / network, up to `AI_PATIENCE_MIN`, default 12 min), model and provider fallback.
- A design with a few broken layers is repaired (broken layers dropped); if the AI never gives a usable design, a simple title video is made instead of failing.
- Render: parallel -> one worker -> light encoder retries; a frame that errors repeats the previous frame.
- If a run still stops, `error_report.md` is published: the tile shows the reason and Continue resumes from the saved work.
- mgl/progress.py: reads what the bot prints (stage, %, frames, ETA) and writes progress/<job>.json on branch bot-progress; page shows bar, stage n/7, time left.
- render.py: parallel frame rendering (same pixels as one worker, tested), DEFAULTS for draft (half size, 15 fps, ultrafast).
- run.py: --project --quality draft|final --parent --resume; draft makes only light files, heavy editor files at Final; publish lists files (wfp, xml, fcpxml, srt, gif ...), video_name, project, quality, parent, formats.
- mgl/work.py: checkpoints work/<key>.json (repo + bot-progress branch); single videos save the design before rendering, so a stop costs no AI requests.
- mgl/longform.py: 61-600 s videos part by part (outline, per-part design saved at once, style anchor from part 1, render, sound, join); stops cleanly on quota/time and continues with the first missing part.
- Page: projects menu, file chips + Draft/Final in the prompt bar, 30 s - 5 min buttons, Continue/Log/Remove on stopped jobs, Activity view, ideas, Drafts / Long videos filters, files download in the viewer.
- Workflow: inputs project, quality, parent, resume; PROGRESS_TOKEN; timeout 345 min; ffmpeg install skipped when present.
- Tests: page 25 pass; bot tests for progress, parallel render, draft/final publish, long video + resume.

## Studio page (GitHub Pages) - Google Flow style front end
- docs/: static site (index.html, css/studio.css, js/{app,crypto,gh,settings,jobs,library}.js, vendor/nacl-fast.min.js, ARCHITECTURE.md). No editor (cancelled).
- Settings page: GitHub token + connection check, Gemini / Pixabay / Pexels keys (tested, then encrypted in-browser and saved as GitHub Secrets), any number of OpenAI-compatible AI providers (AI_KEY_<ID> secrets), default AI + fallback + bot options as repo Variables, "test all keys in the cloud" (mode checks).
- Generate: prompt bar with image/video, ratio, duration, x1-x4, model; attachments uploaded to the repo; workflow_dispatch; client-side queue; progress tiles; results shown from outputs/index.json; viewer with report, stars/feedback, trash, use-as-reference.
- Library (designs, techniques, lessons, wishes) and Tools (compare, remix, study, learn, evolve) read memory/*.json.
- mgl/llm.py: multi-provider LLM layer with fallback; mgl/publish.py: outputs/ publishing; run.py modes checks; workflow run-name + inputs ai/job.
- Tests: tests/test_studio_ui.py (Playwright + fake GitHub, 18 pass), test_all.py extended.

## Smart upgrade (compare, remix, director, guard, notebook)
- mgl/compare.py: example video vs yours, measured (palette, pacing, cuts, motion, brightness, density, layout) -> score + concrete gaps + side-by-side PNG; optional AI judgement; learns lessons + techniques.
- mgl/remix.py: fingerprints, originality gate (too close to a library/memory design or copied text -> fix), remix recipes (borrow 2-3 ideas, mutate what the last videos used).
- mgl/planner.py: director's plan before the spec (concept, signature idea, scenes, wishes). Off by default in agent.run_agent(plan=False), on in run.py (PLAN variable).
- mgl/judge.py: quality number + Best(); revisions that make the video worse are thrown away (regression guard).
- mgl/study.py + memory/notebook.json: techniques (from references, compare, studied text/URL) and a wishlist; modes compare, remix, study, evolve.
- agent.py: with a reference video the bot compares itself (no quota) and fixes towards it; compare.md / compare.png in the output.
- Tests: 12 new, all pass. 3 old tests need resvg-py (SVG renderer) - fail only where it is not installed.

Is version mein dono zips ek ho gaye hain:
- Code Studio (code mode: scene.py likhna, sandbox, preview, QA, custom effects)
- Filmora .wfp / FCPXML / XML export, .wfp lighten (level 1-3), srt/gif/webm/poster/frames
- Sound (ui / kinetic / music), design library (116 ready designs + design_library.pdf), kinetic typography

Tests: 51 pass, 0 fail (clean environment, nakli Gemini server).
Abhi tak asli Gemini, asli Filmora aur asli GitHub Actions par test nahi hua.
Filmora .wfp: media type (audio ke saath 8, bina audio 2), thumb.fsthumb, ID format, key order, zip permissions asli file jaise hain.

## Native Filmora export (mode: native)
- mgl/native_wfp.py: rectangles + text as real editable Filmora layers, cloned from a real Filmora project (mgl/templates/native_sample.wfp).
- Metadata policy: only project name and save path change (tested to open). Duration sync (project length = scene length) is on by default; tested to open.
- Older video-import .wfp export did not open in Filmora; use native mode for Filmora projects.

### Viral SFX style
- New sound style `viral` (now the default): editor-style effects (dark gravel hit, snapshot woosh, camera shutter / multiple shuttle, gone fast, airy slice, bass drop, noise riser, tape stop, sparkle, rewind), no music, placed from the plan (cuts, hero words, images, exits). Page: sound style dropdown next to the Sound checkbox. The SFX pack now also contains the 11 viral sounds.

### Premium UI SFX (default)
- New sound style `premium`, now the default: soft warm app sounds (taps, glass pings in one key, airy whooshes, deep soft thuds, chime, bloom). Everything is low-passed (no energy above ~4 kHz), rounded attacks, quieter mix. `viral` stays as the punchy option.
- Premium: text now sounds like soft typing (a key per letter/word, a short flurry for headlines); the bubble pop is only used for popups (chips, cards, icons, emoji).
- Premium placement v2: typing keys only where text really types in (letter/word reveal); headlines that blur/slide/wipe/pop get a soft whoosh, the one hero headline a soft thud; cards, chips, icons and emoji get the bubble pop; scene changes get a soft whoosh; the bloom marks the closing headline.
- `sfx_pack/` folder: your own sound files are used by name in the premium / viral styles.
- Typing sync: with a typing clip in sfx_pack (premium style) text types exactly on the key hits (reveal `times` now also work for chars / letters); typing_6 from the sample video is included.
