"""Native Filmora .wfp builder: shapes (pen / rectangle) and text as real editable layers, no video import.

Method (from the wfp guide): NEVER build from nothing. Clone a real Filmora project (mgl/templates/native_sample.wfp),
keep every structure exactly as Filmora wrote it and only change values: times, colours, positions, text, keyframes.

Scene = {"duration": 5.0, "layers": [ ... ]}   (layers are bottom -> top)
  {"type": "rect", "x": 960, "y": 540, "w": 1920, "h": 1080, "color": "#0B1020", "start": 0, "end": 5,
   "keys": {"x": [(t, px)], "y": [(t, px)], "sx": [(t, percent)], "sy": [(t, percent)], "rot": [(t, deg)], "opacity": [(t, 0..100)]}}
  {"type": "text", "text": "HELLO", "x": 960, "y": 540, "size": 72, "color": "#FFFFFF", "start": 0.5, "end": 5, "keys": {...}}
Key times t are seconds from the scene start. Positions are pixels on a 1920x1080 frame (centre of the layer).
UNVERIFIED: not opened in Filmora by the bot itself - the user must confirm. Keyframes are written without tangents (checksum formula verified).
"""
import copy, hashlib, json, os, re, struct, time, uuid, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, 'templates', 'native_sample.wfp')
W, H, FPS, U = 1920.0, 1080.0, 25, 10000000


def _g():
    return str(uuid.uuid4())


def _G():
    a = str(uuid.uuid4()).upper().split('-')
    return '{%s-%s-%s-%s-%s}' % (a[0], a[1], a[2].lower(), a[3], a[4])


def bgr(color):
    if isinstance(color, int): return color
    c = color.lstrip('#'); r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (b << 16) | (g << 8) | r


def kf(points):
    """Filmora keyframe string without tangents; MD5 = md5 of little-endian float64 triples (time, 1.0, value)."""
    pts = [(float(t), float(v)) for t, v in sorted(points)]
    md5 = hashlib.md5(b''.join(struct.pack('<ddd', t, 1.0, v) for t, v in pts)).hexdigest()
    body = ','.join('{"_time": %s,"Interpolation": 1,"_value": %s}' % (repr(t), repr(v)) for t, v in pts)
    return '{"Version": 3,"ParameterType": 0,"keyframeSets": [%s],"MD5":"%s"}' % (body, md5)


def _ud_get(o, key):
    for u in o['userData']:
        if u['key'] == key: return u
    return None


def _ud_text(o, key, text, pad=64):
    u = _ud_get(o, key)
    raw = text.encode('utf-8'); raw = raw + b'\0' * (pad - len(raw)) if pad else raw
    import base64
    u['data'] = base64.b64encode(raw).decode('ascii'); u['size'] = len(raw)


def _regen_ids(node):
    """fresh thisUId for every clip / effect, fresh uuid inside custom masks"""
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k == 'thisUId': node[k] = _g()
            elif isinstance(v, str) and '"uuid"' in v: node[k] = re.sub(r'"uuid": "[0-9a-f-]{36}"', lambda _: '"uuid": "%s"' % _g(), v)
            else: _regen_ids(v)
    elif isinstance(node, list):
        for x in node: _regen_ids(x)


def _find_fx(clip, fid):
    for ch in clip['effectChainList']:
        for e in ch['effectList']:
            if e['id'] == fid: return e
    return None


def _set_param(e, name, value):
    for p in e['paramList']:
        if p['name'] == name:
            p['fxParam']['unValue'] = value; return
    e['paramList'].append({'fxParam': {'paramType': 3, 'unValue': value}, 'name': name})


def _pipbuf(clip, op_keys, rel0):
    pb = json.loads(clip['pipBuf'])
    if op_keys:
        pts = [((t - rel0) * U, v) for t, v in op_keys]
        pb['OpacityKeyFrame'] = kf(pts); pb['Opacity'] = float(pts[0][1])
    else:
        pb['OpacityKeyFrame'] = kf([]) if False else '{"Version": 3,"ParameterType": 0,"keyframeSets": [],"MD5":"d41d8cd98f00b204e9800998ecf8427e"}'
        pb['Opacity'] = 100.0
    s = json.dumps(pb, separators=(',', ':'))
    clip['pipBuf'] = s; clip['pipBufSize'] = len(s.encode('utf-8')) + 1


def _transform(clip, keys, start, base):
    """keys: x,y px; sx,sy percent; rot deg. base: static fallbacks."""
    e = _find_fx(clip, 'video/effect/transform')
    maps = []
    def static(name, v): _set_param(e, name, float(v))
    spec = {'Position_x': ('x', lambda v: v / W), 'Position_y': ('y', lambda v: v / H), 'Scale_x': ('sx', lambda v: v), 'Scale_y': ('sy', lambda v: v), 'Rotation': ('rot', lambda v: v)}
    for name, (k, conv) in spec.items():
        pts = keys.get(k)
        if pts:
            rel = [(t - start, conv(v)) for t, v in pts]
            static(name, rel[0][1])
            if len(rel) > 1: maps.append({'key': 3, 'keyFrame': {'parameter': kf(rel)}, 'name': name})
        else:
            static(name, conv(base[k]))
    e['paramMapList'] = maps


def _frame(t):
    return int(round(t * FPS)) * (U // FPS)


def _rect_clip(proto, L):
    c = copy.deepcopy(proto); _regen_ids(c)
    s, e = _frame(L['start']), _frame(L['end'])
    c['tlBegin'], c['tlEnd'], c['inPoint'], c['outPoint'] = s, e, 0, e - s
    w, h = L['w'] / W, L['h'] / H
    r = _find_fx(c, 'graphic/effect/path_graphic_rect')
    for n, v in (('start_x', 0.5 - w / 2), ('start_y', 0.5 - h / 2), ('width', w), ('height', h)): _set_param(r, n, v)
    for fx in ('graphic/effect/path_fill',):
        _find_fx(c, fx)['paramList'][0]['fxParam']['unValue'] = bgr(L.get('color', '#FFFFFF'))
    keys = L.get('keys', {})
    _transform(c, keys, L['start'], {'x': L['x'], 'y': L['y'], 'sx': 100.0, 'sy': 100.0, 'rot': 0.0})
    _pipbuf(c, keys.get('opacity'), L['start'])
    return c


def _text_clip(proto_main, proto_nested, L, new_tid):
    m = copy.deepcopy(proto_main); n = copy.deepcopy(proto_nested)
    _regen_ids(m); _regen_ids(n)
    s, e = _frame(L['start']), _frame(L['end']); ln = e - s
    m['tlBegin'], m['tlEnd'], m['inPoint'], m['outPoint'], m['timelineId'] = s, e, 0, ln, new_tid
    n['timelineId'] = new_tid
    # fresh GUIDs so no two objects share an id
    clip_guid = _G(); _ud_text(m, 3, clip_guid)
    u55 = _ud_get(m, 55); j = json.loads(u55['data'] and __import__('base64').b64decode(u55['data']).rstrip(b'\0').decode('utf-8'))
    j['Key_AncestralGuid'] = _G().lower(); j['Key_TimelineGuid'] = _G().lower()
    raw = json.dumps(j, separators=(',', ':'), ensure_ascii=False).encode('utf-8') + b'\0'
    u55['data'] = __import__('base64').b64encode(raw).decode('ascii'); u55['size'] = len(raw)
    _ud_text(n, 11000, _G()); _ud_text(n, 3, _G())
    nc = n['trackInfos'][0]['clipList'][0]
    nc['tlBegin'], nc['tlEnd'], nc['inPoint'], nc['outPoint'] = 0, ln, 0, ln
    n['trackInfos'][0]['uuid'] = _g()
    _ud_text(nc, 3, _G())
    sb = json.loads(nc['scriptBuf']); sb['Text'] = L['text']
    for td in sb['TextData']:
        td['CharData'] = L['text']
        if 'size' in L:
            for k in ('FontSize', 'FontHSize', 'FontVSize'): td['Basic'][k] = float(L['size'])
        td['Basic']['TextColor'] = [{'Color': bgr(L.get('color', '#FFFFFF'))}]
    s2 = json.dumps(sb, separators=(',', ':'), ensure_ascii=False)
    nc['scriptBuf'] = s2; nc['scriptBufSize'] = len(s2.encode('utf-8')) + 1
    # static transform inside the nested timeline (no leftover animation of the sample)
    te = _find_fx(nc, 'video/effect/transform')
    if te is not None: te['paramMapList'] = []
    keys = L.get('keys', {})
    _transform(m, keys, L['start'], {'x': L['x'], 'y': L['y'], 'sx': 100.0, 'sy': 100.0, 'rot': 0.0})
    _pipbuf(m, keys.get('opacity'), L['start'])
    return m, n, clip_guid


def build(out_path, name, scene, sample=SAMPLE, sync_duration=True):
    z = zipfile.ZipFile(sample)
    names = [i.filename for i in z.infolist()]
    wes_n = next(x for x in names if x.endswith('timeline.wesproj')); ex_n = next(x for x in names if x.endswith('extra.json'))
    wes = json.loads(z.read(wes_n).decode('utf-8')); extra = json.loads(z.read(ex_n).decode('utf-8'))
    tls = {t['timelineId']: t for t in wes['timelineInfos']}
    main = tls[wes['currentTimelineId']]; tr = main['trackInfos']
    shapes = [c for t in tr for c in t['clipList'] if c['type'] == 26]
    proto_rect = next(c for c in shapes if (_find_fx(c, 'graphic/effect/path_graphic_rect') or {}).get('paramList') and
                      [p for p in _find_fx(c, 'graphic/effect/path_graphic_rect')['paramList'] if p['name'] == 'width'][0]['fxParam']['unValue'] < 0.02)
    texts = [c for t in tr for c in t['clipList'] if c['type'] == 7]
    proto_text, proto_nested = texts[0], copy.deepcopy(tls[texts[0]['timelineId']])
    a_proto, v_proto = tr[3], tr[4]
    new_tracks = [copy.deepcopy(tr[0]), copy.deepcopy(tr[1])]
    nested, mapping, nid = [], {}, 6
    for L in scene['layers']:
        if L['type'] == 'text':
            clip, nt, g = _text_clip(proto_text, proto_nested, L, nid); nested.append(nt); mapping[g] = 'Basic_1'; nid += 1
        elif L['type'] == 'rect':
            clip = _rect_clip(proto_rect, L)
        else:
            raise ValueError('unknown layer type %s' % L['type'])
        a = copy.deepcopy(a_proto); v = copy.deepcopy(v_proto)
        a['uuid'], v['uuid'] = _g(), _g()
        v['trackTag'] = len(new_tracks); a['trackTag'] = len(new_tracks) + 1     # like the sample: video track at an even index, its empty audio track right after
        v['clipList'] = [clip]; a['clipList'] = []
        new_tracks += [v, a]
    main['trackInfos'] = new_tracks
    wes['timelineInfos'] = [main] + nested
    wes['serialNumber'] = wes.get('serialNumber', 300) + len(scene['layers'])
    extra['mediaClipsMapInfo'] = {g: {'mediaId': m, 'subClips': {}} for g, m in mapping.items()}
    extra['allMarkersInfo'] = {'beatDetectInfo': {g: {'algorithmType': 0, 'level': 0} for g in mapping}}
    dur = _frame(scene['duration'])
    zi = []
    for i in z.infolist():
        d = z.read(i.filename)
        if i.filename == wes_n: d = json.dumps(wes, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        elif i.filename == ex_n: d = json.dumps(extra, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        elif i.filename.endswith('project_info.json'):
            # SAFE METADATA: only what was tested to open in Filmora (name + save path). Dates, guid, source stay as in the sample.
            pi = json.loads(d.decode('utf-8'))
            pi['project_file_name'] = name
            pi['proj_zip_save_path'] = 'C:/Users/Public/Documents/%s.wfp' % name
            if sync_duration: pi['project_timeline_duration'] = dur
            d = json.dumps(pi, indent=4, ensure_ascii=False).encode('utf-8')
        elif i.filename.endswith('medias_info.json'):
            mi = json.loads(d.decode('utf-8'))
            for it in mi['media_items'].values():
                it['name'] = name
                if sync_duration: it['duration'] = dur
            d = json.dumps(mi, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        zi.append((i, d))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as o:
        for i, d in zi:
            ni = zipfile.ZipInfo(i.filename, date_time=time.localtime()[:6]); ni.compress_type = zipfile.ZIP_DEFLATED
            ni.create_system = 3; ni.external_attr = i.external_attr
            o.writestr(ni, d)
    return validate(out_path)


def validate(path):
    """structure checks from the guide: zip ok, JSON parses, unique thisUId, size fields, nested timelines exist, no overlap"""
    problems = []
    z = zipfile.ZipFile(path)
    if z.testzip(): problems.append('zip damaged')
    wes = json.loads(z.read(next(x for x in z.namelist() if x.endswith('timeline.wesproj'))).decode('utf-8'))
    ids, tlids = [], {t['timelineId'] for t in wes['timelineInfos']}
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == 'thisUId': ids.append(v)
                else: walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(wes)
    if len(ids) != len(set(ids)): problems.append('duplicate thisUId')
    clips = 0
    for t in wes['timelineInfos']:
        for tr in t['trackInfos']:
            last = -1
            for c in sorted(tr['clipList'], key=lambda c: c['tlBegin']):
                clips += 1
                if c['tlBegin'] < last: problems.append('overlap on a track')
                last = c['tlEnd']
                if 'pipBuf' in c and c.get('pipBufSize') != len(c['pipBuf'].encode('utf-8')) + 1: problems.append('pipBufSize')
                if 'scriptBuf' in c and c.get('scriptBufSize') != len(c['scriptBuf'].encode('utf-8')) + 1: problems.append('scriptBufSize')
                if c['type'] == 7 and c['timelineId'] not in tlids: problems.append('missing nested timeline %s' % c['timelineId'])
    return {'path': path, 'clips': clips, 'timelines': len(tlids), 'problems': sorted(set(problems))}


def demo_scene():
    """5 s intro: dark background, 3 bars sliding in, a rotating square, title + subtitle (all native editable layers)"""
    L = [{'type': 'rect', 'x': 960, 'y': 540, 'w': 1920, 'h': 1080, 'color': '#0B1020', 'start': 0, 'end': 5}]
    for i, (y, col) in enumerate(((380, '#FF6A00'), (540, '#22D3EE'), (700, '#A78BFA'))):
        t0 = 0.2 + i * 0.2
        L.append({'type': 'rect', 'x': 960, 'y': y, 'w': 900, 'h': 24, 'color': col, 'start': t0, 'end': 5,
                  'keys': {'x': [(t0, 100), (t0 + 0.7, 960)], 'opacity': [(t0, 0), (t0 + 0.3, 100)]}})
    L.append({'type': 'rect', 'x': 1500, 'y': 540, 'w': 220, 'h': 220, 'color': '#FF6A00', 'start': 0.4, 'end': 5,
              'keys': {'sx': [(0.4, 10), (1.4, 100)], 'sy': [(0.4, 10), (1.4, 100)], 'rot': [(0.4, 0), (1.4, 180)], 'opacity': [(0.4, 0), (0.7, 100)]}})
    L.append({'type': 'text', 'text': 'MOTION BOT', 'x': 800, 'y': 520, 'size': 72, 'color': '#FFFFFF', 'start': 0.9, 'end': 5,
              'keys': {'y': [(0.9, 580), (1.5, 520)], 'opacity': [(0.9, 0), (1.5, 100)]}})
    L.append({'type': 'text', 'text': 'made natively for Filmora', 'x': 800, 'y': 620, 'size': 36, 'color': '#22D3EE', 'start': 1.4, 'end': 5,
              'keys': {'opacity': [(1.4, 0), (2.0, 100)]}})
    return {'duration': 5.0, 'layers': L}
