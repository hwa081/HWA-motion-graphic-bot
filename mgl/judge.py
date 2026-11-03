"""mgl.judge - one comparable quality number for a spec (no AI), so the bot can keep the BEST version.

Without it a "fix" round can make a video worse (the model fixes the text overlap and breaks the pacing) and the bot would not notice.
score = 100 - 14 per QA error - 3 per warning - originality penalty (+ reference fidelity and AI review when known)
"""


def quality(qa, novelty=None, fidelity=None, review=None):
    s = 100.0 - 14 * len(qa.get('errors', [])) - 3 * len(qa.get('warnings', []))
    if novelty and novelty.get('too_close'): s -= 12
    if fidelity is not None: s += (fidelity - 60) * 0.35            # 0..100 fidelity: +-14 around 60
    if review is not None: s += (review - 7) * 3
    return round(s, 1)


class Best:
    """keeps the best spec seen so far; a newer candidate wins ties (it is the newer idea) but never a clear loss"""
    def __init__(self):
        self.spec = None; self.score = None; self.tag = ''; self.meta = None; self.reverted = 0

    def offer(self, spec, score, tag='', meta=None):
        """True if `spec` is now the best; False if it is worse than the best so far (the caller keeps using .spec)"""
        if self.spec is None or score >= self.score:
            self.spec, self.score, self.tag, self.meta = spec, score, tag, meta
            return True
        self.reverted += 1
        return False
