# Studio (web page) - kaise kaam karta hai

```
Aap ka browser (GitHub Pages: https://<user>.github.io/<repo>/)
   |  GitHub token (sirf aap ke browser mein)
   v
GitHub API ----> Secrets / Variables  (API keys: Gemini, Pixabay, Pexels, custom AI)  <- page keys yahan encrypt kar ke bhejta hai
   |-----------> workflow_dispatch  (Run workflow)  ---> GitHub Actions: python run.py (bot)
   |                                                         |
   |<--- runs status (queued / running / done)               |-- video + poster + report -> outputs/<id>/  (repo mein commit)
   |<--- outputs/index.json + outputs/<id>/video.mp4  <------|-- memory/ (designs, lessons, notebook)
```
* Page sirf static files hai (`docs/`): koi server nahi.
* Keys **GitHub Secrets** mein jati hain (libsodium sealed box se encrypt, browser mein). Page unhein dobara parh nahi sakta, sirf "saved" dikhata hai.
* Connection test: key save karne se pehle browser se direct (Gemini / Pixabay / Pexels / custom AI / GitHub). Save ke baad "cloud check" bot khud chalata hai (mode `checks`) aur `outputs/checks.json` mein likhta hai.
* Editor nahi hai (cancel). Page = Flow jaisa: media grid, neeche prompt bar, settings.
