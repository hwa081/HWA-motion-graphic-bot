"""studio.sandbox - runs AI-written scene code in a separate, restricted process.

* gets a COPY of the library (mgl/, fonts/, assets/, custom/) in a temporary folder - no .git, no memory/, no keys
* environment is stripped (no GEMINI_API_KEY, no GitHub token), HOME = the temp folder
* network disabled inside the process, CPU time / memory / file-size limits, hard timeout, process group is killed on timeout
This is a safety net for an ephemeral CI machine, not a security boundary against a malicious program.
"""
import json, os, re, shutil, signal, subprocess, sys, tempfile

WRITE_OK = re.compile(r'^(scene\.py|parts/[a-z][a-z0-9_]{0,30}\.py|custom/[a-z][a-z0-9_]{2,30}\.py)$')
READ_OK = re.compile(r'^(scene\.py|parts/[a-z0-9_]+\.py|custom/[a-z0-9_]+\.(py|md)|docs/[A-Za-z_]+\.md|examples/[a-z0-9_]+\.(py|json)|mgl/[a-z]+\.py)$')
MAX_FILE = 70_000
MAX_FILES = 24


def _limits(cpu_seconds):
    def f():
        import resource
        os.setsid()
        resource.setrlimit(resource.RLIMIT_AS, (8 << 30, 8 << 30))
        resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_seconds) + 10, int(cpu_seconds) + 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 << 30, 2 << 30))
        resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
    return f


class Sandbox:
    def __init__(self, project_root, log=print):
        self.project = project_root
        self.root = tempfile.mkdtemp(prefix='studio-')
        self.log = log
        for d in ('mgl', 'fonts', 'assets', 'custom', 'examples'):
            src = os.path.join(project_root, d)
            if os.path.isdir(src): shutil.copytree(src, os.path.join(self.root, d), ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        os.makedirs(os.path.join(self.root, 'studio'), exist_ok=True)
        shutil.copy(os.path.join(project_root, 'studio', 'runner.py'), os.path.join(self.root, 'studio', 'runner.py'))
        os.makedirs(os.path.join(self.root, 'docs'), exist_ok=True)
        for f, dst in (('studio/CODE_API.md', 'docs/CODE_API.md'), ('LIBRARY.md', 'docs/LIBRARY.md')):
            if os.path.exists(os.path.join(project_root, f)): shutil.copy(os.path.join(project_root, f), os.path.join(self.root, dst))
        os.makedirs(os.path.join(self.root, 'parts'), exist_ok=True)
        os.makedirs(os.path.join(self.root, 'out'), exist_ok=True)

    # ---------------------------------------------------------------- files
    def write(self, rel, content):
        rel = str(rel).replace('\\', '/').lstrip('./')
        if not WRITE_OK.match(rel):
            return False, 'path not allowed: %r. You may write scene.py, parts/<name>.py and custom/<name>.py only.' % rel
        if not isinstance(content, str) or not content.strip(): return False, 'content is empty'
        if len(content) > MAX_FILE: return False, 'file too large (%d characters, max %d) - split it into parts/<name>.py modules' % (len(content), MAX_FILE)
        n = sum(len(fs) for _, _, fs in os.walk(os.path.join(self.root, 'parts'))) + len(os.listdir(os.path.join(self.root, 'custom')))
        if n > MAX_FILES: return False, 'too many files'
        try:
            compile(content, rel, 'exec')
        except SyntaxError as ex:
            return False, 'SyntaxError in %s line %s: %s\n%s' % (rel, ex.lineno, ex.msg, (ex.text or '').rstrip())
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f: f.write(content)
        return True, 'wrote %s (%d lines)' % (rel, content.count('\n') + 1)

    def read(self, rel, start=0, max_chars=9000):
        rel = str(rel).replace('\\', '/').lstrip('./')
        if not READ_OK.match(rel): return None, 'path not readable: %r (allowed: scene.py, parts/, custom/, docs/*.md, examples/, mgl/*.py)' % rel
        p = os.path.join(self.root, rel)
        if not os.path.isfile(p): return None, 'no such file: %s' % rel
        txt = open(p, encoding='utf-8', errors='replace').read()
        part = txt[int(start):int(start) + max_chars]
        more = ' ... [%d more characters; call read_file again with start=%d]' % (len(txt) - int(start) - len(part), int(start) + len(part)) if int(start) + len(part) < len(txt) else ''
        return part + more, None

    def scene_source(self):
        p = os.path.join(self.root, 'scene.py')
        return open(p, encoding='utf-8').read() if os.path.exists(p) else None

    # ---------------------------------------------------------------- run
    def run(self, action, params=None, timeout=120):
        out_dir = os.path.join(self.root, 'out')
        for f in ('result.json',):
            try: os.remove(os.path.join(out_dir, f))
            except OSError: pass
        pfile = os.path.join(self.root, 'params.json')
        json.dump(params or {}, open(pfile, 'w'))
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': self.root, 'PYTHONPATH': self.root, 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
               'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2'}
        p = subprocess.Popen([sys.executable, 'studio/runner.py', action, pfile], cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             preexec_fn=_limits(timeout))
        try:
            so, se = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception: p.kill()
            p.communicate()
            return {'ok': False, 'action': action, 'error': 'TimeoutError: the scene did not finish within %d seconds (infinite loop, or far too slow per frame)' % timeout, 'traceback': ''}
        rp = os.path.join(out_dir, 'result.json')
        if os.path.exists(rp):
            res = json.load(open(rp, encoding='utf-8'))
        else:
            tail = (se or '').strip().splitlines()[-12:]
            res = {'ok': False, 'action': action, 'error': 'the process died without a result (exit code %s) - often too much memory or an import crash' % p.returncode, 'traceback': '\n'.join(tail)}
        res['stdout'] = (so or '')[-1500:]
        return res

    def out_file(self, name):
        p = os.path.join(self.root, 'out', name)
        return p if os.path.exists(p) else None

    def register_custom(self, name, project_root=None, size='16:9'):
        """smoke-test custom/<name>.py in the sandbox; if it passes copy it to the project's custom/ folder and update INDEX.md"""
        project_root = project_root or self.project
        rel = 'custom/%s.py' % name
        if not os.path.exists(os.path.join(self.root, rel)): return False, 'no file %s - write it first' % rel
        res = self.run('smoke', {'module': name, 'size': size}, timeout=60)
        if not res.get('ok'): return False, 'smoke test failed: %s\n%s' % (res.get('error'), res.get('traceback', ''))
        dst = os.path.join(project_root, 'custom'); os.makedirs(dst, exist_ok=True)
        shutil.copy(os.path.join(self.root, rel), os.path.join(dst, name + '.py'))
        idx = os.path.join(dst, 'INDEX.md')
        lines = open(idx, encoding='utf-8').read().splitlines() if os.path.exists(idx) else ['# Custom components written by the bot', '',
                                                                                         'Import inside a scene:  `from custom.<name> import *`', '']
        lines = [l for l in lines if not l.startswith('- `%s`' % name)]
        lines.append('- `%s` - %s' % (name, ' '.join(res['doc'].split())[:400]))
        open(idx, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        shutil.copy(idx, os.path.join(self.root, 'custom', 'INDEX.md'))
        return True, 'registered custom/%s.py (smoke test ok, %.2fs)' % (name, res.get('seconds', 0))

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)
