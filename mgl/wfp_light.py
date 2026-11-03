"""Lossless "lighten" for Filmora .wfp project files.

A .wfp is a ZIP of JSON files + small PNG previews (the real media stays outside, referenced by path).
So the project file never contains pixels of your video: making it lighter can NOT change render quality.
What we do (every step is verified, the parsed data must stay identical):

  level 1  (safe, default)  re-pack ZIP with maximum Deflate (many Filmora files are stored uncompressed),
                            minify JSON (whitespace only - repeated keys and number spelling are kept exactly), drop the OS junk entries.
  level 2  (+ previews)     re-encode the PNG previews losslessly (pixel-identical, smaller) - Filmora only uses
                            them for gallery thumbnails.
  level 3  (+ small previews) media gallery thumbnails are shrunk to at most 480 px wide (and photo-like ones reduced to a
                            256-colour palette; they are only the little pictures in the media bin; Filmora always renders from your real files, never from them)
                            and the cover bundle / cover cache that Filmora re-creates on its own is dropped.
                            Timeline, clips, effects and media references are untouched.

The original file is never modified; the result is written to a new file and checked by re-reading both.
"""
import io, json, os, zipfile

JUNK_PREFIXES = ('__MACOSX/',)
JUNK_NAMES = ('.DS_Store', 'Thumbs.db', 'desktop.ini')


def _is_json(name):
    return name.lower().endswith(('.json', '.wesproj'))


def _pairs(data):
    """Parse JSON keeping duplicate keys and number spelling (Filmora writes repeated keys, e.g. several "media_item")."""
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=lambda p: ('obj', p), parse_float=lambda x: ('f', x),
                      parse_int=lambda x: ('i', x))


def _strip_ws(text):
    """Remove whitespace that sits OUTSIDE JSON strings - nothing else is touched (keys, order, duplicates, numbers)."""
    out, in_str, esc = [], False, False
    for ch in text:
        if in_str:
            out.append(ch)
            if esc: esc = False
            elif ch == '\\': esc = True
            elif ch == '"': in_str = False
        elif ch == '"':
            in_str = True; out.append(ch)
        elif ch not in ' \t\r\n':
            out.append(ch)
    return ''.join(out)


def _minify(data):
    """Return (minified bytes, parsed) if data is valid JSON, else (None, None). Whitespace-only change."""
    try:
        text = data.decode('utf-8-sig')
        parsed = _pairs(data)
    except Exception:
        return None, None
    out = _strip_ws(text).encode('utf-8')
    if _pairs(out) != parsed:      # must be structurally identical, duplicates included
        return None, None
    return out, parsed


def _png_lossless(data):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        buf = io.BytesIO()
        im.save(buf, 'PNG', optimize=True, compress_level=9)
        out = buf.getvalue()
        im2 = Image.open(io.BytesIO(out)); im2.load()
        if im2.mode == im.mode and im2.size == im.size and im2.tobytes() == im.tobytes() and len(out) < len(data):
            return out
    except Exception:
        pass
    return data


def _png_small(data, max_w=480):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)); im.load()
        if im.width > max_w:
            h = max(1, round(im.height * max_w / im.width))
            im = im.convert('RGBA' if 'A' in im.getbands() else 'RGB').resize((max_w, h), Image.LANCZOS)
        elif len(data) > 20000 and im.mode in ('RGB', 'RGBA'):   # photo-like preview: 256-colour palette is plenty for a 320 px thumbnail
            im = im.convert('RGB').quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        else:
            return _png_lossless(data)
        buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True, compress_level=9)
        out = buf.getvalue()
        return out if len(out) < len(data) else data
    except Exception:
        return data


def lighten(src, dst, level=2):
    """Write a lighter copy of `src` to `dst`. Returns a dict with before/after sizes and what was done."""
    if level not in (1, 2, 3):
        raise ValueError('level must be 1, 2 or 3')
    stats = {'src': src, 'dst': dst, 'level': level, 'before': os.path.getsize(src), 'files': 0,
             'json_min': 0, 'png_opt': 0, 'dropped': [], 'verified': False}
    entries = []  # (name, bytes, parsed_json_or_None)
    with zipfile.ZipFile(src) as z:
        bad = z.testzip()
        if bad:
            raise ValueError('source .wfp is damaged (%s)' % bad)
        for info in z.infolist():
            name = info.filename
            if info.is_dir():
                continue
            base = name.rsplit('/', 1)[-1]
            if name.startswith(JUNK_PREFIXES) or base in JUNK_NAMES:
                stats['dropped'].append(name); continue
            if level >= 3 and name.lower().endswith('.wfpbundle'):
                stats['dropped'].append(name); continue
            data = z.read(name)
            parsed = None
            if _is_json(name) and not name.endswith('project_info.json'):   # Filmora writes this one indented; leave it as is
                mini, parsed = _minify(data)
                if mini is not None and len(mini) < len(data):
                    data = mini; stats['json_min'] += 1
                elif mini is None:
                    parsed = None
            elif level >= 2 and name.lower().endswith('.png'):
                new = _png_small(data) if level >= 3 and name.endswith('thumbnail.png') else _png_lossless(data)
                if len(new) < len(data):
                    stats['png_opt'] += 1
                data = new
            entries.append((name, data, parsed))
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    tmp = dst + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # project_info.json first, like Filmora writes it
        entries.sort(key=lambda e: (0 if e[0].endswith('project_info.json') else 1))
        for name, data, _ in entries:
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); zi.create_system = 3; zi.external_attr = 0o100644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            stats['files'] += 1
    # ---- verification: every kept file must read back identical (JSON: same parsed value) ----
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(tmp) as b:
        if b.testzip():
            raise ValueError('internal error: rebuilt zip is damaged')
        names_b = set(b.namelist())
        for info in a.infolist():
            n = info.filename
            if info.is_dir() or n in stats['dropped']:
                continue
            if n not in names_b:
                raise ValueError('internal error: %s missing in result' % n)
            da, db = a.read(n), b.read(n)
            if _is_json(n):
                try:
                    same = _pairs(da) == _pairs(db)
                except Exception:
                    same = (da == db)
                if not same:
                    raise ValueError('internal error: JSON changed in %s' % n)
            elif n.lower().endswith('.png') and level >= 2:
                from PIL import Image
                ia, ib = Image.open(io.BytesIO(da)), Image.open(io.BytesIO(db))
                if level >= 3 and n.endswith('thumbnail.png') and ia.size != ib.size:
                    if abs(ia.width / ia.height - ib.width / ib.height) > 0.02 or ib.width > 480:
                        raise ValueError('internal error: thumbnail shape changed in %s' % n)
                elif level >= 3 and n.endswith('thumbnail.png') and ia.size == ib.size:
                    pass   # palette-reduced preview, same size
                elif ia.size != ib.size or ia.mode != ib.mode or ia.tobytes() != ib.tobytes():
                    raise ValueError('internal error: PNG pixels changed in %s' % n)
            elif da != db:
                raise ValueError('internal error: %s changed' % n)
    stats['kept_original'] = False
    if os.path.getsize(tmp) >= stats['before'] and level < 3:
        os.remove(tmp)                      # never hand back a bigger file: already as small as it gets
        import shutil; shutil.copyfile(src, dst); stats['kept_original'] = True
    else:
        os.replace(tmp, dst)
    stats['after'] = os.path.getsize(dst)
    stats['verified'] = True
    stats['saved_pct'] = round(100.0 * (stats['before'] - stats['after']) / max(1, stats['before']), 1)
    return stats


def report(st):
    return ('%s -> %s | %.0f KB -> %.0f KB (%.1f%% lighter%s) | level %d | json minified: %d, png re-encoded: %d, dropped: %d | '
            'checked: project data identical' % (os.path.basename(st['src']), os.path.basename(st['dst']), st['before'] / 1024.0,
                                              st['after'] / 1024.0, st['saved_pct'], ', already minimal - original kept' if st.get('kept_original') else '', st['level'], st['json_min'], st['png_opt'], len(st['dropped'])))


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('usage: python -m mgl.wfp_light in.wfp out.wfp [level 1-3]'); sys.exit(2)
    print(report(lighten(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2)))
