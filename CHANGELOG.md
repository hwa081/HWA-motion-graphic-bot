# Motion Graphic Bot - merged version

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
