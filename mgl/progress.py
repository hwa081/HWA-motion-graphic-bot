"""mgl.progress - live progress for the Studio page ("how much is done, what is left").

The bot already prints what it does ([spec] attempt 2/3, [render] ..., frame 120/240). Instead of touching every step, stdout is wrapped:
every printed line is read, turned into  stage + percent + detail (+ time left while rendering),  and written to
progress/<job>.json on a separate branch "bot-progress" (so the Pages site on main is NOT rebuilt for every update).
The page polls that file. Everything is best effort: no token / no network -> the run just goes on without live progress.
"""
import base64, json, os, re, sys, threading, time, urllib.request, urllib.error

BRANCH = 'bot-progress'
_CONF = {'repo': None, 'token': None}
STAGES = ['Start', 'Plan', 'Design', 'Check', 'Render', 'Files', 'Save']
MIN_INTERVAL = 5.0


def parse_line(line, state):
    """update state (dict: stage int, pct float, detail str, eta) from one printed line. Percent never goes down."""
    l = line.strip()
    if not l: return False
    st = state
    def to(stage, pct, detail=None):
        st['stage'] = max(st.get('stage', 0), stage); st['pct'] = max(st.get('pct', 0), pct)
        if detail is not None: st['detail'] = detail
        return True
    m = re.match(r'\[turn (\d+)/(\d+)\]', l)
    if m: k, n = int(m.group(1)), max(1, int(m.group(2))); return to(2, 6 + 58.0 * k / n, 'Code Studio: turn %d of %d (writes the scene, looks at it, fixes it)' % (k, n))
    m = re.match(r'\[part (\d+)/(\d+)\]', l)
    if m: k, n = int(m.group(1)), max(1, int(m.group(2))); return to(2, 8 + 56.0 * (k - 1) / n, 'Long video: designing part %d of %d' % (k, n))
    m = re.match(r'\[long-render\] part (\d+)/(\d+)', l)
    if m: k, n = int(m.group(1)), max(1, int(m.group(2))); return to(4, 66 + 26.0 * (k - 1) / n, 'Long video: rendering part %d of %d' % (k, n))
    if l.startswith('[long-join]'): return to(5, 93, 'Joining the parts into one video')
    if l.startswith('[resume]'): return to(1, 10, 'Continuing from the saved work')
    m = re.match(r'\[spec\] attempt (\d+)/(\d+)', l)
    if m: k, n = int(m.group(1)), max(1, int(m.group(2))); return to(2, 14 + 12.0 * (k - 1) / n, 'AI writes the design (try %d of %d)' % (k, n))
    if l.startswith('reference'): return to(1, 6, 'Looking at your reference video')
    if l.startswith('[remix]'): return to(1, 8, 'Borrowing ideas from old designs')
    if l.startswith('[plan]'): return to(1, 12, 'Director plan: ' + l[6:].strip()[:80])
    if l.startswith('asset '): return to(2, 30, 'Finding images')
    if l.startswith('[qa] fix round'): return to(3, 44, 'Fixing problems the checker found')
    if l.startswith('[qa]'): return to(3, 38, 'Automatic quality check')
    if l.startswith('[compare]'): return to(3, 46, 'Comparing with the reference')
    m = re.match(r'\[review\] round (\d+)', l)
    if m: return to(3, 50 + 6.0 * (int(m.group(1)) - 1), 'AI looks at a preview and improves it (round %s)' % m.group(1))
    if l.startswith('score '): return to(3, st.get('pct', 0))
    if l.startswith('[render]'): return to(4, 66, 'Rendering the video')
    m = re.match(r'frame (\d+)/(\d+)\s+\((\d+)s', l)
    if m:
        i, n, el = int(m.group(1)), max(1, int(m.group(2))), float(m.group(3))
        st['frames'] = [i, n]
        pct = 66 + 26.0 * i / n
        st['eta'] = int(el * (n - i) / i) if i > 0 and el > 1 else None
        return to(4, pct, 'Rendering frames %d / %d' % (i, n))
    if l.startswith('sound ('): return to(5, 93, 'Adding sound')
    if l.startswith('Exporting:'): return to(5, 95, 'Making ' + l.split(':', 1)[1].strip())
    if l.startswith('done ->'): return to(5, 96, 'Finishing')
    if l.startswith('published'): return to(6, 99, 'Saving the result')
    return False


class _Remote:
    def __init__(self, repo, token, job, path=None):
        self.repo, self.token, self.job = repo, token, job
        self.path = path or 'progress/%s.json' % job
        self.sha = None; self.ready = False

    def get(self):
        """-> parsed JSON of the file on the bot-progress branch, or None"""
        code, d = self._req('GET', '/contents/%s?ref=%s' % (self.path, BRANCH))
        if code != 200 or not d.get('content'): return None
        self.sha = d.get('sha')
        return json.loads(base64.b64decode(d['content']).decode('utf-8'))

    def _req(self, method, url, body=None):
        r = urllib.request.Request('https://api.github.com/repos/%s%s' % (self.repo, url), method=method,
                                   data=None if body is None else json.dumps(body).encode(),
                                   headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                                            'Content-Type': 'application/json', 'User-Agent': 'motion-graphic-bot'})
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                t = resp.read().decode('utf-8', 'ignore'); return resp.status, (json.loads(t) if t else {})
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read().decode('utf-8', 'ignore'))
            except Exception: return e.code, {}

    def ensure_branch(self):
        code, _ = self._req('GET', '/git/ref/heads/' + BRANCH)
        if code == 200: self.ready = True; return
        code, d = self._req('GET', '/git/ref/heads/' + (os.environ.get('GITHUB_REF_NAME') or 'main'))
        if code != 200: return
        code, _ = self._req('POST', '/git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': d['object']['sha']})
        self.ready = code in (200, 201, 422)

    def put(self, data):
        if not self.ready: self.ensure_branch()
        if not self.ready: return False
        body = {'message': 'progress', 'branch': BRANCH, 'content': base64.b64encode(json.dumps(data).encode()).decode()}
        if self.sha: body['sha'] = self.sha
        code, d = self._req('PUT', '/contents/' + self.path, body)
        if code in (200, 201): self.sha = (d.get('content') or {}).get('sha'); return True
        if code in (409, 422):                          # stale sha: fetch the current one and retry once
            c2, d2 = self._req('GET', '/contents/%s?ref=%s' % (self.path, BRANCH))
            if c2 == 200 and d2.get('sha'):
                body['sha'] = d2['sha']; code, d = self._req('PUT', '/contents/' + self.path, body)
                if code in (200, 201): self.sha = (d.get('content') or {}).get('sha'); return True
        return False

    def delete(self):
        if not self.ready: self.ensure_branch()
        if not self.ready: return
        if not self.sha:
            code, d = self._req('GET', '/contents/%s?ref=%s' % (self.path, BRANCH))
            if code != 200: return
            self.sha = d.get('sha')
        self._req('DELETE', '/contents/' + self.path, {'message': 'progress done', 'branch': BRANCH, 'sha': self.sha})


class Progress:
    def __init__(self, job, mode, remote=None, stages=None, local_path=None):
        self.job, self.mode = job, mode
        self.state = {'stage': 0, 'pct': 1.0, 'detail': 'Starting the cloud computer', 'eta': None}
        self.t0 = time.time(); self.remote = remote; self.local_path = local_path
        self.stages = stages or STAGES
        self._last = 0.0; self._dirty = True; self._lock = threading.Lock(); self._stop = False; self._th = None

    def snapshot(self, done=False):
        s = dict(self.state)
        return {'job': self.job, 'mode': self.mode, 'stages': self.stages, 'stage': s.get('stage', 0), 'pct': 100 if done else round(min(99.0, s.get('pct', 0)), 1), 'detail': s.get('detail', ''),
                'frames': s.get('frames'), 'eta': s.get('eta'), 'elapsed': int(time.time() - self.t0), 'updated': int(time.time()), 'done': done}

    def feed(self, line):
        with self._lock:
            if parse_line(line, self.state): self._dirty = True

    def _flush(self, done=False):
        snap = self.snapshot(done)
        if self.local_path:
            try:
                os.makedirs(os.path.dirname(self.local_path) or '.', exist_ok=True); json.dump(snap, open(self.local_path, 'w'))
            except Exception: pass
        if self.remote:
            try: self.remote.put(snap)
            except Exception: pass

    def _loop(self):
        while not self._stop:
            time.sleep(1.0)
            with self._lock:
                due = self._dirty and time.time() - self._last >= MIN_INTERVAL
                if due: self._dirty = False; self._last = time.time()
            if due: self._flush()

    def start(self):
        self._flush(); self._last = time.time()
        self._th = threading.Thread(target=self._loop, daemon=True); self._th.start()

    def finish(self):
        self._stop = True
        if self.remote:
            try: self.remote.delete()
            except Exception: pass


class Tee:
    """sys.stdout wrapper: passes everything through and lets Progress read each finished line"""
    def __init__(self, inner, prog):
        self.inner, self.prog, self.buf = inner, prog, ''
        self.tail = []

    def write(self, s):
        n = self.inner.write(s)
        try:
            self.buf += s
            while '\n' in self.buf:
                line, self.buf = self.buf.split('\n', 1); self.prog.feed(line)
                if line.strip(): self.tail = (self.tail + [line.rstrip()[:300]])[-60:]
        except Exception: pass
        return n

    def flush(self): return self.inner.flush()
    def __getattr__(self, k): return getattr(self.inner, k)


def remote_for(path):
    """another file on the bot-progress branch (used by mgl.work for checkpoints); None when there is no token"""
    if _CONF['repo'] and _CONF['token'] and os.environ.get('PROGRESS_REMOTE', 'true') != 'false':
        return _Remote(_CONF['repo'], _CONF['token'], '', path)
    return None


def install(job, mode, env=None, stdout_swap=True):
    """-> Progress (started) or None when there is no job label. Remote updates need PROGRESS_TOKEN (the workflow token) + GITHUB_REPOSITORY."""
    env = env if env is not None else os.environ
    if not (job or '').strip():
        tok = env.get('PROGRESS_TOKEN')
        if tok and env.get('GITHUB_REPOSITORY'): _CONF.update(repo=env['GITHUB_REPOSITORY'], token=tok)
        if hasattr(env, 'pop'): env.pop('PROGRESS_TOKEN', None)
        return None
    remote = None
    tok = env.get('PROGRESS_TOKEN')
    if hasattr(env, 'pop'): env.pop('PROGRESS_TOKEN', None)          # never leave it in the environment (child processes)
    if tok and env.get('GITHUB_REPOSITORY'): _CONF.update(repo=env['GITHUB_REPOSITORY'], token=tok)
    if tok and env.get('GITHUB_REPOSITORY') and env.get('PROGRESS_REMOTE', 'true') != 'false':
        remote = _Remote(env['GITHUB_REPOSITORY'], tok, re.sub(r'[^A-Za-z0-9_-]', '', job))
    stages = STAGES if mode in ('ai', 'code', 'spec', 'final') else ['Start', 'Work', 'Save']
    prog = Progress(job, mode, remote, stages, local_path=env.get('PROGRESS_FILE') or None)
    prog.start()
    if stdout_swap: sys.stdout = Tee(sys.stdout, prog)
    return prog
