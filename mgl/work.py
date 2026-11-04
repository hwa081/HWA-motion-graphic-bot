"""mgl.work - checkpoints, so a stopped run continues where it stopped.

A run can stop at any time (free AI quota used up, 6-hour limit, a crash, you pressed cancel). The expensive part is the AI work, so after every
finished step the bot saves  work/<key>.json  (the design(s) it already has). The key is made from the brief (prompt + length + size + mode), so
sending the SAME brief again - or pressing Continue on the page - picks the saved work up and goes straight on.
The file is saved in the repository (commit step at the end of the run) and, at once, on the branch "bot-progress" (survives a hard crash).
When the video is finished the checkpoint is removed.
"""
import hashlib, json, os, time

DIR = 'work'


def make_key(prompt, duration, size, mode):
    raw = '|'.join([' '.join(str(prompt).lower().split()), str(duration), str(size), str(mode)])
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


class Work:
    def __init__(self, root, key, enabled=True):
        self.root, self.key, self.enabled = root, key, enabled
        self.path = os.path.join(root, DIR, key + '.json')
        self.remote_path = '%s/%s.json' % (DIR, key)

    def _remote(self):
        try:
            from . import progress
            return progress.remote_for(self.remote_path)
        except Exception:
            return None

    def load(self):
        """-> saved state (dict) or None"""
        if not self.enabled: return None
        try:
            d = json.load(open(self.path, encoding='utf-8'))
            if isinstance(d, dict) and not d.get('done'): return d
        except Exception:
            pass
        r = self._remote()
        if r:
            try:
                d = r.get()
                if isinstance(d, dict) and not d.get('done'):
                    self._write(d); return d
            except Exception:
                pass
        return None

    def _write(self, state):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        json.dump(state, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(tmp, self.path)

    def save(self, state):
        if not self.enabled: return
        state = dict(state, key=self.key, updated=int(time.time()))
        self._write(state)
        r = self._remote()
        if r:
            try: r.put(state)
            except Exception: pass

    def clear(self):
        try: os.remove(self.path)
        except OSError: pass
        r = self._remote()
        if r:
            try: r.delete()
            except Exception: pass
