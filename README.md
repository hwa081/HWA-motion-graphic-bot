# motion-graphic-bot

GitHub ke cloud par chalne wala motion-graphics bot. Aap prompt likhte hain (aur chahein to images, reference videos), Gemini (free key) video ka plan banata hai,
library usay MP4 mein render karti hai, bot khud ghaltiyan pakar kar theek karta hai, aur **har video se seekh kar `memory/` folder mein yaad rakhta hai**.
Aap ke PC par kuch install nahi hota.

```
prompt + images + reference video + brand kit
  -> memory (lessons, pasandeeda designs, style guide)  -> Gemini JSON plan  -> validator
  -> asset search (photo/illustration/vector/icon/Canva)  -> automatic QA  -> AI review  -> MP4
  -> report + yaad rakhna (design card, lessons)  -> aap ki rating se aur seekhna
```

## 0. Studio page (GitHub Pages): Google Flow jaisa front page (naya)
Repo ka front page ab ek **Studio** hai: dark grid, neeche prompt bar ("What do you want to create?"), left sidebar (All media / Videos / Library / Tools / Settings / Trash).
Wahi se bot chalta hai, keys lagti hain, connection check hota hai. (Editor nahi hai, aap ke kehne par.)

**Live karna (ek baar):**
1. Repo **Public** rakhein (video page raw.githubusercontent.com se chalti hain; public repo par Actions minutes bhi free hain).
2. Section 1 ke mutabiq saari files upload karein, **`docs/` folder aur `.github/workflows/render.yml` bhi** (agar `.github` upload na ho to `render.yml.txt` ka text nayi file mein paste karein).
3. **Settings -> Actions -> General -> Workflow permissions -> Read and write**.
4. **Settings -> Pages -> Build and deployment -> Source: Deploy from a branch -> Branch `main`, folder `/docs`** -> Save. 1-2 minute baad page `https://<user>.github.io/<repo>/` par khulta hai.
5. Token banayein: GitHub -> Settings -> Developer settings -> **Fine-grained tokens** -> sirf is repo ke liye, Repository permissions: **Actions: Read and write, Secrets: Read and write, Variables: Read and write, Contents: Read and write**.
6. Page kholein -> **Settings** -> GitHub card mein `user/repo` aur token paste karein -> **Test**. Token sirf aap ke browser (localStorage) mein rehta hai, kahin nahi jata.
7. Gemini key (aur Pixabay / Pexels / koi aur AI) paste karke **Test & save**. Keys browser mein **encrypt** ho kar **GitHub Secrets** mein jaati hain (libsodium sealed box); wapas dikhai nahi jaatin. Baqi settings (default AI, fallback, MAX_REQUESTS, PLAN ...) repo **Variables** mein.
8. Gemini ke ilawa AI: Settings -> "More AI providers" -> preset (OpenAI, Groq, OpenRouter, DeepSeek, Mistral, Together ...) ya apna **OpenAI-compatible URL + model + key**. Prompt bar ke model menu mein aa jata hai; "Fallback" se pehla fail hone par agla chalta hai.
9. **Test all keys in the cloud** (Settings) saari keys asli cloud environment se check karta hai.

**Kaise kaam karta hai:** prompt bhejne par page workflow `render.yml` ko `workflow_dispatch` se chalata hai, run ko dekhta hai (Queued / Running / step ka naam), aur video `outputs/<id>/video.mp4` mein repo mein save hoti hai; grid `outputs/index.json` se bharta hai. x2-x4 variations ek ke baad ek chalti hain.

**Dhyan rakhein:**
* Nayi video repo se ~5 minute tak purani cache dikha sakta hai (raw.githubusercontent.com cache).
* Browser se upload ki limit ~25 MB per file (images / reference videos).
* Token chori na ho: kisi ko na dein; shak ho to GitHub mein delete karke naya banayein.
* Page sirf aap ke liye hai jab token laga ho; baqi log page dekh to sakte hain par bot nahi chala sakte.

## 1. Files GitHub par daalen (sirf ek baar)
> Zip ko pehle **computer par extract** karein (GitHub zip khud nahi kholta). Computer ke browser se karein.

1. https://github.com/hwa081/motion-graphic-bot kholein -> **Add file -> Upload files**.
2. Extract kiye folder ke **andar ki sab cheezein** (folders `mgl`, `fonts`, `examples`, `assets`, `recipes`, `scripts`, `tests`, `.github` aur files `agent.py`, `render.py`, `run.py`, `LIBRARY.md`, `requirements.txt`, `README.md` ...) drag karein -> **Commit changes**.
3. Check: repo mein `.github/workflows/render.yml` hona chahiye. Agar `.github` nahi gaya: **Add file -> Create new file**, naam `.github/workflows/render.yml`, aur `render.yml.txt` ka poora text paste karein.
4. **Zaroori setting:** repo **Settings -> Actions -> General -> Workflow permissions -> Read and write permissions** -> Save. (Is ke baghair bot memory wapas save nahi kar sakta.)

## 2. Pehla test (bina key, bina AI)
Actions tab -> **Make video** -> Run workflow -> mode **demo** -> Run. 3-5 minute baad run ke **Artifacts** se `video-1` download karein (`video.mp4`, `preview.png`).

## 3. Keys (Settings -> Secrets and variables -> Actions -> New repository secret)
| Secret | Kaam | Kahan se |
|---|---|---|
| `GEMINI_API_KEY` | **zaroori** (AI) | https://aistudio.google.com/apikey (free) |
| `PIXABAY_API_KEY` | photos, illustrations, vectors | https://pixabay.com/api/docs/ (free) |
| `PEXELS_API_KEY` | extra photos | https://www.pexels.com/api/ (free) |

Icons ke liye key ki zaroorat nahi (Iconify). **Keys kabhi chat ya file mein na likhein.**
Test: mode **check** (Gemini) aur mode **assets-check** (photo/icon libraries) -> log mein OK/FAILED likha aata hai.

## 4. Modes (Run workflow mein "mode")
| mode | kya karta hai |
|---|---|
| **ai** | prompt se video banata hai (JSON plan, library ke components). Tez, kam quota. `size`, `duration`, `files` (images / reference video) |
| **code** | **Code Studio**: AI khud Python scene code likhta hai, sandbox mein chalata hai, frames **dekhta** hai, errors/QA parh kar theek karta hai (kai turns), aur nayi library cheezein `custom/` mein bana kar register karta hai. Zyada azaad, zyada quota |
| **export** | purani MP4 se `.wfp` / `.fcpxml` / `.xml` / gif ... banata hai (5c) |
| **lighten** | `.wfp` project file halki karta hai, data wahi rehta hai (5c) |
| **design** | library ka koi tayyar design render karta hai (`design_id`), ya `prompt` se milte-julte designs ki list (5d) |
| **designs-pdf** | 116 designs ki storyboard PDF dobara banata hai (5d) |
| **feedback** | pichli video ko `rating` (1-5) aur `prompt` mein apna note do; bot seekh kar lesson yaad rakhta hai |
| **learn** | `reference` folder ki videos analyse karta hai, design yaad rakhta hai, style guide banata hai |
| **index-canva** | `assets/canva/` ki aap ki Canva exports ko AI se tag karwata hai (taake search mein milen) |
| **assets-check / check** | libraries / Gemini key ka live test |
| **qa** | kisi JSON plan ki quality report (bina key) |
| **compare / remix / study / evolve** | example se muqabla / purane designs se naya plan / nayi technique sikhana / wishlist ka effect banana (5e) |
| **spec / demo / reference** | JSON se render / demo / purani reference intro |

## 5. Aap ki list ke points: kaise use karein
**Har scene ka alag style.** Library mein 7 background styles, 17 entrance animations, 5 transitions, charts, device mockups, particles, 3D cards, chips, counters ... hain. Bot ko "variety" ka rule diya hua hai, automatic QA same animations/scenes dohrane par pakarta hai, aur memory mein pichli 3 videos ka style hota hai taake nayi video **alag** bane.

**Image upload karke animate karwana.** Image ko repo ke `assets/` folder mein upload karein (**Add file -> Upload files**). Phir mode **ai**, `files` mein `assets/mera_photo.png`, prompt mein likhein ke kya karna hai (jaise "is screenshot ko laptop mockup mein dikha kar zoom karo"). Bot image dekhta hai (Gemini vision) aur uske mutabiq animation chunta hai: Ken Burns zoom/pan, 3D tilt, device frame, pop/float.

**Reference video do, apne liye customize.** Video ko repo mein `reference/` folder mein rakhein (25 MB se chhoti). Mode **ai**, `files` = `reference/promo.mp4`, prompt mein apna content/brand likhein. Bot uska structure, pacing, motion aur transitions rakhta hai, content aap ka hota hai. Wo video ek baar analyse ho kar yaad bhi ho jati hai.

**Kai reference videos ek saath.** Sab ko `reference/` folder mein daalen, mode **learn**. Har run mein `LEARN_LIMIT` (default 5) nayi videos analyse hoti hain (free quota bachane ke liye); baqi ke liye dobara chalayen. Phir bot sab ko compare kar ke `memory/style_guide.md` likhta hai (common patterns, naam wale design recipes, professional rules) jo har agle video ke prompt mein shamil hota hai.

**Bot design yaad rakhta hai aur improve hota hai.** `memory/` folder (repo mein khud commit hota hai):
`designs.json` (har video ka card), `specs/` (poora plan), `lessons.json` (kya behtar bana / kya wrong; baar baar ki ghalti ka weight barhta hai),
`styles.json` + `style_guide.md` (references), `assets.json` (konsi image kyun chuni), `learning_log.md` (parhne wali history), `brand.json`.
Har run ke baad `report.md` mein likha hota hai: **shuru mein kya wrong tha, bot ne kya theek kiya, kya baqi hai, naye lessons**.

**Feedback.** Video dekh kar: mode **feedback**, `rating` 1-5, `prompt` mein likhein "kya pasand aaya / kya nahi" (design id khali = latest). Is ka wazan sab se zyada hota hai.

**Brand kit.** `memory/brand.json` ko GitHub mein edit karein (naam, rang `#rrggbb`, logo path, tagline, always/never). Bot har video mein use karta hai.

**Canva.** Canva ki official API mein elements library (stock images/shapes) shamil nahi, is liye bot Canva library mein "search" nahi kar sakta. Is ka hal:
1. Canva mein design/element banayen -> **Share -> Download -> PNG (transparent background)** -> repo ke `assets/canva/` mein upload.
2. Mode **index-canva** (AI tags likhta hai) -> ab bot `canva` section mein se search kar ke chun leta hai.
Baqi sections: `photo` (Pixabay/Pexels), `illustration`, `vector` (Pixabay), `icon` (Iconify). Har section ke candidates ka AI muqabla kar ke **ek behtareen** chunta hai, wajah `report.md` mein aur faisla `memory/assets.json` mein hota hai (dobara wahi search ho to bina quota kharch kiye wahi image).
Downloaded files `assets/library/` mein aur unka credit `assets/library/CREDITS.md` mein.

**Sizes.** `size`: 16:9 (1920x1080), 9:16 (1080x1920), 1:1 (1080x1080). Har video mein badal sakte hain. Bot size ke hisaab se alag layout banata hai (9:16 mein text safe area mein).

## 5b. Code Studio (mode `code`): "code likh kar video banane wala bot"
Mode **ai** library ke fixed components se video banata hai. Mode **code** is se aage jata hai, coding agent ki tarah:
1. Gemini `scene.py` likhta hai (numpy / OpenCV / Pillow; library ke helpers `from mgl.api import *`, aur `layer(...)` se JSON components bhi).
2. Code **sandbox** mein chalta hai: error aaye to traceback model ko wapas milta hai; `preview` se model 12 frames ka sheet **dekhta** hai; `qa` se text cut-off/overlap/contrast/blank/static ki jaanch.
3. Model har turn mein poori file dobara bhej kar theek karta hai, jab tak qa saaf na ho (`finish` bina preview + qa ke refuse hota hai).
4. Jo effect library mein nahi (ripple, wave, glitch, globe ...), model `custom/<naam>.py` mein likhta hai, smoke-test se guzar kar **register** hota hai, aur **agli har video** mein use ho sakta hai (`custom/INDEX.md`). Yehi bot ka apni library ko khud barhana hai.
5. Aakhir mein final MP4 + `scene.py` + `report.md` (kitne turns, kaun si errors aayin, kya naya banaya) milte hain, aur memory/lessons update hote hain.

Settings (Variables): `CODE_TURNS` (default 16 turns), `CODE_REQUESTS` (default turns + 6 Gemini requests). Aam video 6-12 turns leti hai, yaani **free quota ka zyada hissa** lagta hai; pehle mode **ai** try karein, jab kuch naya chahiye to **code**.

**Hifazat (sandbox):** model ka code alag process mein chalta hai, library ki **copy** ke saath (repo ki `.git`, `memory/`, keys nahi), environment saaf (GEMINI_API_KEY waghera nazar nahi aate), network band, time/memory/file-size limits, aur infinite loop par process maar diya jata hai. Workflow mein checkout GitHub token disk par nahi rakhta; token sirf aakhri "memory save" step mein lagta hai. Yeh ek CI machine ke liye hifazati jaal hai, kisi shararti program ke khilaf mukammal qila nahi.

**Haqeeqat:** free Gemini meri tarah behtar code nahi likhta; kabhi kabhi turns zaya karta hai ya design average rehta hai. Is liye qa + preview + turn limit lagaye gaye hain. `report.md` mein dekh sakte hain kahan masla aaya, aur mujhe wo `scene.py` dikha dein to main library ko behtar bana sakta hoon.


## 5c. Output formats: Filmora `.wfp`, `.xml`, aur baqi (naya)
Har video ke saath ab editor ke liye project files bhi banti hain (Run workflow mein **formats** aur **media_dir**):

| format | kya milta hai | kahan khulta hai |
|---|---|---|
| `wfp` | Filmora project (timeline par video, scene badalne ki jagah par cuts) | Filmora 15 (aap ke `.wfp` ki banawat par bana hai) |
| `fcpxml` | Final Cut Pro XML 1.9 | DaVinci Resolve, Final Cut Pro, Filmora (Import FCPXML, agar aap ke version mein hai) |
| `xml` | FCP7 / Premiere "xmeml" | Premiere Pro, DaVinci Resolve, Vegas, Filmora (Import XML) |
| `gif`, `webm`, `poster`, `frames`, `mp4-light` | GIF, WebM (VP9), poster PNG, PNG frames ka zip (max 300), halka MP4 (CRF 20: master se ~30% chhota, SSIM 0.998 = nazar nahi aata) | kahin bhi |

`srt` = subtitles (plan ke text layers ke time se; sirf mode ai/spec/demo, code mode mein plan nahi hota). **Music/awaaz:** mp3/wav/m4a repo mein upload karein, workflow ke `audio` mein path (jaise `assets/music.mp3`): video ko haath nahi lagta (copy), awaaz video ki lambai tak loop hoti hai, aakhir mein fade-out, aur `.wfp`/XML mein audio track bhi aati hai.

Default: `wfp,fcpxml,xml`. `all` sab, `none` kuch nahi. Mode **export** kisi purani MP4 se yehi files banata hai (MP4 ko repo mein upload karein, `files` mein path).

**Zaroori:** project files MP4 ko *path* se dhoondti hain. `media_dir` (default `C:/Users/HWA/Downloads/motion-bot`) wo folder hai jahan aap apne PC par MP4 rakhenge. MP4 ka naam unique hota hai (`<naam>_<tarikh>.mp4`). Agar MP4 kahin aur rakhi to editor ek baar **Locate / Relink** poochega: MP4 chun lein.
**Sach:** `.wfp` Filmora ki asli files ki banawat se bani hai aur structure/ids ka test pass hai, lekin isay sirf Filmora kholne par hi pakka kaha ja sakta hai (is sandbox mein Filmora nahi). Agar `.wfp` na khule to saath wali `.fcpxml` / `.xml` use karein aur batayein, main theek kar dunga.

### Sound: `kinetic` (sirf typography SFX, music nahi) ya music + SFX (naya, automatic)
Mode ai/spec/demo ab video ke saath **music aur SFX** bhi banata hai (workflow ka `sound`: **`kinetic`** = sirf typography SFX, bina music (default) | **`ui`** = UI/SaaS animation SFX, bina music | `uplift` / `calm` / `tech` = music + SFX | `none`). Sab kuch numpy se bana hota hai (koi sample, koi copyright nahi).
* **kinetic:** har pop/zoom headline par stamp, har lafz par click, har harf par typewriter tick, slide/wipe par whoosh (text jis taraf ho usi taraf pan hota hai), text jaate waqt halka reverse-swish, counter par tik-tik + ding, transitions par riser + whoosh + impact. Music bilkul nahi.
* **ui:** UI/SaaS animation sounds, music nahi: card/device landing par soft drop + swipe, toast/notification par bell, cursor ke har click par click, toggle ON par toggle sound, chart/progress bharte waqt rising ticks, check icon aur counter ke end par success chime, typing par keyboard keys. Text (headline) par koi awaaz nahi.
* **Music (uplift/calm/tech):** pad chords + bass + arpeggio + drums. Pehle scene mein halki, har scene ke saath barhti, aakhri scene mein shaant. Scene = background badalna.
* **SFX plan se khud lagte hain:** har transition par riser + whoosh + impact, pop/bounce entrance par pop, letters/typing par tick, counter par tik-tik + ding, chart par rising sweep, bare headline par low hit, closing mein shimmer.
* Output: `<naam>_with_sound.mp4` (picture bit-for-bit wahi, sirf audio add), `music_sfx.wav` (alag, Filmora mein edit ke liye), aur `.wfp`/XML isi `_with_sound.mp4` ko use karte hain. Silent `video.mp4` bhi rehti hai.
* Apna music chahiye: file repo mein upload karein aur `audio` mein path likhein; tab bot ki music/SFX nahi lagti, aap ki file lagti hai.
* Code mode mein plan nahi hota, is liye wahan awaaz sirf `audio` file se aati hai.

### Project file halki karna (mode **lighten**)
`.wfp` mein aap ki video/photos hoti hi nahi (sirf unka path), is liye isay halka karne se **render quality par koi asar nahi** padta. `.wfp` ko repo mein `projects/` mein upload karein, mode **lighten**, `files` = `projects/mera.wfp`, `level`:
1. **safe**: dobara compress + faltu spaces. Data bit-for-bit wahi (dohray keys bhi). 
2. level 1 + PNG thumbnails lossless dobara encode.
3. level 2 + media-bin ke chhote thumbnails halke (320 px ke preview, 256 rang). Timeline, clips, effects, media links bilkul wahi. **Aam taur par 40% tak halka.**
Original file ko haath nahi lagta, naya `<naam>_light.wfp` milta hai, aur har file dobara parh kar check hoti hai.
Render halka karne ka asal tareeqa: bot ki video ek hi MP4 clip hoti hai (kam layers = tez render). Agar timeline mein 50+ pen/shape clips ya kai nested timelines hon (jaise ED138 project), render un se sust hota hai, un ko Filmora mein **Export -> MP4** kar ke ek clip bana lein.

## 5d. Design Library: 116 tayyar designs jin se bot seekhta hai (naya)
Folder `library/`: **116 designs** = 72 documentary scenes (space, history, ocean, nature, science, technology, economy) + 44 SaaS / UI motion graphics. 29 patterns x 4 variations.
Har design mein: **narration script (jo awaaz bole, us second par visual aaye)**, **storyboard** (kis second par kya aata hai), **4 asli rendered frames**, aur chalne wali **spec JSON**.
* `library/design_library.pdf` - parhne ke liye PDF (har page par 2 designs). `library/designs.json` - bot ka index. `library/specs/<id>.json` - render hone wali spec. `library/previews/` - frames.
* Mode **ai** mein bot automatically aap ke prompt se milte 3 designs (script + storyboard + spec) prompt mein dekhta hai, aur rules follow karta hai: **copy nahi, naya design banao** (2-3 patterns mix, layout/rang/animation/camera/transition badlo). Documentary ho to spec mein `"script": [{"t":..,"text":..}]` bhi likhta hai.
* Mode **design**: `design_id` = `doc-01-title-hero` render karta hai (aur `design_NAME_narration.txt` deta hai). `design_id` khali + `prompt` = best matches ki list.
* Apna naya pattern jodna ho: `libgen/arch_*.py` (builder) + `libgen/var_*.py` (data) badlen, phir `python -m libgen.build --render` aur `python run.py --mode designs-pdf`.
* Library ki tasveerein `assets/designlib/` mein hain (khud bani hui); bot unhein "uploaded assets" nahi samajhta.

## 5e. Smart upgrades: example se seekhna, purane designs se naya banana, soch kar banana (naya)
Bot ab sirf "prompt -> spec" nahi karta. Har video mein ye 6 cheezein chalti hain (zyada tar **bina quota** ke):

| Upgrade | Kya karta hai | Quota |
|---|---|---|
| **Compare (example se muqabla)** | Example video ke saath aap ki video ko **numbers** mein naapta hai: colours, pacing (kitni jaldi scene badalte hain), cuts kis waqt, motion, roshni, kitna detail, layout kahan hai. Score 0-100 + saaf farq ("example har 1.8 s mein cut karta hai, aap ki har 4.1 s mein"). Upar example, neeche aap ki video ki side-by-side tasveer (`compare.png`). | 0 (AI ki raye optional: 1 request) |
| **Reference fix** | Mode **ai** mein reference video do to bot khud apni video example se compare karta hai; score 72 se kam ho to farq model ko bhej kar theek karwata hai. `compare.md` + `compare.png` milte hain. | 0-3 request |
| **Remix engine** | Library ke 116 designs + aap ke pasandeeda designs se **2-3 idea** leta hai aur jaan-boojh kar **badalta hai** (naye backgrounds, animation family, transitions, layout twist, pacing, camera) - wo cheezein jo pichli 3 videos mein use huin, dobara nahi. Har video ka recipe alag. | 0 |
| **Originality gate** | Agar naya design library/memory ke kisi design se 80% milta ho ya lafz-ba-lafz text copy ho to bot isay "copy" maan kar dobara banwata hai. | 0 |
| **Director (planner)** | Spec likhne se pehle ek "creative director" step: concept, **signature idea**, scene-by-scene plan, kya mushkil ho sakta hai. Spec writer isi plan par chalta hai. Jo effect library mein nahi, wo **wishlist** mein jata hai. `PLAN` variable `false` kar ke band kar sakte hain. | +1 request |
| **Regression guard** | Har "fix" ke baad bot ek quality number nikalta hai (QA errors, originality, example se fidelity). Agar fix ne video **kharab** ki to purani behtar version wapas aati hai. | 0 |

**Naye modes** (Run workflow -> mode):
* **compare** - `files` = `reference/example.mp4,out/video.mp4` (ya aakhir mein `spec.json`). `compare_report.md` + `compare.png`. Key ho to AI bhi batata hai ke example ne kya trick use ki; wo **techniques** notebook mein chali jati hain.
* **remix** - `prompt` = topic. Bina key ke naya design plan (`remix.md`): kin designs se idea liya, kya badla.
* **study** - `prompt` = koi tutorial ka text ya **URL** (ya `files` = `.txt/.md`). Bot usay **technique cards** mein badalta hai; saath ka example spec asli validator se guzarta hai (jo render nahi ho sakta wo save nahi hota). Aglay videos mein jo technique brief se milti ho wo prompt mein aa jati hai.
* **evolve** - wishlist ki sab se zyada manga hua effect Code Studio se `custom/` mein bana kar register karta hai (jaise "liquid ripple transition"). Yeh bot ka **khud naya sekhna** hai.

**Notebook:** `memory/notebook.json` - `techniques` (reference videos, compare, study se seekhi hui tarkeeben, weight ke saath) aur `wishes` (jo effect chahiye the magar library mein nahi). Mode **learn** ab har reference video se 3 tak reusable techniques bhi nikalta hai.

**Example video ko "company" (compare) karna - tareeqa:**
1. Example video `reference/` mein upload karein.
2. Mode **ai**, `files` = `reference/example.mp4`, prompt = apna content. Bot khud compare kar ke theek karta hai.
3. Ya pehle se bani video check karni ho: mode **compare**, `files` = `reference/example.mp4,<aap ki video ka path>`.
4. `compare.png` dekhein (upar example, neeche aap ki) aur `compare_report.md` mein "Differences" parhein. Jo farq baar baar aaye wo `lessons` mein ban jata hai.

**Sach (haqeeqat):** compare numbers **structure aur feel** naapte hain (rang, raftaar, cuts, motion, layout), content ya fonts ki barabari nahi. Free Gemini Claude Opus jaisa gehra nahi sochta; is liye bot ko sochne ka dhancha (planner, rubric, guard, memory) diya gaya hai taake wo apni ghaltiyan khud pakre aur har video se behtar ho.

## 6. Free quota ka khayal
* Mode **ai**: har run mein Gemini requests ka **budget 14** (`MAX_REQUESTS`). Aam video: 3-8 requests. `review` = false se kam. Mode **code**: `CODE_REQUESTS` (default 22).
* Gemini free tier ki limits badalti rehti hain. Limit lagne par bot intezar karta hai, doosra model try karta hai, aur phir rukta hai. Agle din dobara chalayen.
* GitHub: **public repo** par Actions minutes free hain (private par 2000 minute/mahina). Ek 10 second ki video setup ke saath 2-4 minute leti hai.

## 7. Agar kuch fail ho
Actions -> fail hua run -> **Run** step ki aakhri lines. `report.md` / `qa.md` bhi dekhein.

| Message | Hal |
|---|---|
| `GEMINI_API_KEY is missing` | Secret ka naam bilkul `GEMINI_API_KEY` ho |
| `429` / `all models failed` | free limit; kuch der baad / agle din; ya `review` false |
| `404 model` | **Variables** mein `GEMINI_MODEL` banayen (jaise `gemini-2.5-flash`) |
| `could not get a valid spec` | prompt chhota aur saaf likh kar dobara |
| `nothing found ... network` (assets) | mode **assets-check** chalayen; Pixabay/Pexels key check karein |
| `could NOT push` | Step 1 ki setting #4 (Read and write permissions) |

## 8. Computer par (optional)
```
pip install -r requirements.txt      # ffmpeg aur emoji font alag
python tests/test_all.py             # self-test, internet/key ke baghair
python run.py --mode qa --files examples/showcase.json
python run.py --mode demo
```

## Folder
```
mgl/engine.py   drawing        mgl/spec.py   JSON -> frames, validation     mgl/extras.py  charts, devices, transitions ...
studio/        Code Studio (sandbox + agent + CODE_API.md)   custom/  bot ke likhe naye components
mgl/qa.py       auto quality checks   mgl/memory.py  yaad   mgl/learn.py  lessons   mgl/reference.py  reference videos
mgl/compare.py  example vs yours   mgl/remix.py  new from old   mgl/planner.py  director   mgl/judge.py  regression guard   mgl/study.py  new techniques
mgl/assets.py   photo/icon/Canva search   mgl/gemini.py  Gemini client      agent.py  AI loop     run.py  workflow entry
library/        116 designs (script + storyboard + spec + frames + PDF)   libgen/  library builder   mgl/library.py  search + prompt
LIBRARY.md      the book the AI reads   examples/  4 working specs   recipes/  hand-written reference intro   fonts/  Poppins (OFL)
```
