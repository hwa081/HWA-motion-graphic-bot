"""Output formats for the finished video.

    wfp      Filmora project (.wfp): the video sits on the timeline, ready to edit / add voice / music / render.
    fcpxml   Final Cut Pro XML 1.9 (.fcpxml)  - DaVinci Resolve, Final Cut Pro, Filmora (Import FCPXML) ...
    xml      Final Cut Pro 7 / Premiere "xmeml" (.xml) - Premiere Pro, DaVinci Resolve, Filmora, Vegas ...
    gif / webm / poster / frames / mp4-light   extra copies of the same video.

Every project file points to the MP4 by path. `media_dir` is the folder on YOUR PC where you will keep the MP4
(default C:/Users/HWA/Downloads/motion-bot). If the MP4 is somewhere else, the editor shows "Locate" once - choose the file.

The .wfp is built from the structure of real Filmora 15 projects (see mgl/templates/filmora_wfp.json); a generated
project can only be proven by opening it in Filmora, so if Filmora ever refuses the .wfp, use the .fcpxml / .xml next to it.
"""
import base64, copy, hashlib, io, json, math, os, re, shutil, subprocess, time, uuid, zipfile
from urllib.parse import quote
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
TICK = 10000000  # Filmora time unit: 100 ns
DEFAULT_MEDIA_DIR = 'C:/Users/HWA/Downloads/motion-bot'
ALL_FORMATS = ('wfp', 'fcpxml', 'xml', 'srt', 'gif', 'webm', 'poster', 'frames', 'mp4-light')
DEFAULT_FORMATS = ('wfp', 'fcpxml', 'xml')


# ------------------------------------------------------------------ helpers
def _run(cmd, **kw):
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)


def probe(path):
    """Facts about the video, from ffprobe."""
    out = _run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path]).stdout
    j = json.loads(out)
    v = next(s for s in j['streams'] if s['codec_type'] == 'video')
    a = next((s for s in j['streams'] if s['codec_type'] == 'audio'), None)
    num, den = (v.get('r_frame_rate') or '30/1').split('/')
    fps = float(num) / float(den or 1)
    dur = float(j['format'].get('duration') or v.get('duration') or 0)
    info = {'path': path, 'width': int(v['width']), 'height': int(v['height']), 'fps': fps, 'fps_num': int(num), 'fps_den': int(den or 1),
            'duration': dur, 'frames': int(v.get('nb_frames') or round(dur * fps)), 'size': os.path.getsize(path),
            'bitrate': int(j['format'].get('bit_rate') or 0), 'has_audio': a is not None,
            'vcodec': v.get('codec_name'), 'acodec': a.get('codec_name') if a else None,
            'a_rate': int(a.get('sample_rate', 48000)) if a else 0, 'a_ch': int(a.get('channels', 2)) if a else 0,
            'a_bitrate': int(a.get('bit_rate') or 0) if a else 0,
            'md5': _md5(path)}
    return info


def _md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 20), b''):
            h.update(ch)
    return h.hexdigest()


def _guid():
    """Filmora style GUID: {XXXXXXXX-XXXX-xxxx-XXXX-XXXXXXXXXXXX} (3rd group lower case, the rest upper case)"""
    a = str(uuid.uuid4()).upper().split('-')
    return '{%s-%s-%s-%s-%s}' % (a[0], a[1], a[2].lower(), a[3], a[4])


def _win_path(media_dir, filename):
    return media_dir.replace('\\', '/').rstrip('/') + '/' + filename


def _pad64(s):
    b = s.encode('ascii')
    return base64.b64encode(b + b'\0' * (64 - len(b))).decode(), 64


def _b64(b):
    return base64.b64encode(b).decode(), len(b)


def _i32(n):
    return _b64(int(n).to_bytes(4, 'little', signed=True))


def _ud_set(userData, key, data_size):
    data, size = data_size
    for d in userData:
        if d['key'] == key:
            d['data'], d['size'] = data, size
            return
    userData.append({'data': data, 'key': key, 'size': size})


def _fresh_ids(o):
    """New instance ids for every effect inside a cloned clip (thisUId + the GUID in userData key 3)."""
    if isinstance(o, dict):
        if 'thisUId' in o:
            o['thisUId'] = str(uuid.uuid4())
            for d in o.get('userData') or []:
                if d['key'] == 3 and d.get('size') == 64 and 'id' in o:
                    d['data'], d['size'] = _pad64(_guid())
        for v in o.values():
            _fresh_ids(v)
    elif isinstance(o, list):
        for v in o:
            _fresh_ids(v)


KNOWN_SPEED_MD5 = {   # (duration, checksum) pairs seen in real Filmora files; the checksum recipe itself is not public
    '7.92000000': '258edf4bf73f5e116ebec38ac4c9e353', '18.64000000': '362677293de9e9fcdd43e7d039c522b9',
    '27.64000000': '66fa602bec8758b24462840257453fdc', '204.32000000': '14cea1ab999e7e3b607c4641e58d6040'}


def _speed_param(total_sec):
    t = '%.8f' % (math.ceil(total_sec * 100 - 1e-6) / 100.0)
    body = '{"_time": 0.0,"Interpolation": 6,"_value": 1.0},{"_time": %s,"Interpolation": 6,"_value": 1.0}' % t
    md5 = KNOWN_SPEED_MD5.get(t) or hashlib.md5(body.encode()).hexdigest()   # NOTE: Filmora's own checksum recipe is not public; see README "wfp" notes
    return '{"Version": 3,"ParameterType": 0,"keyframeSets": [%s],"MD5": "%s","_totalTime": %s}' % (body, md5, t)


def _segments(info, cuts):
    """[(start_frame, end_frame)] covering the whole video, split at `cuts` (seconds)."""
    n = info['frames']
    pts = sorted({int(round(c * info['fps'])) for c in (cuts or []) if 0 < c < info['duration']})
    pts = [p for p in pts if 0 < p < n]
    edges = [0] + pts + [n]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b > a]


def _thumb_png(video, w, h, at=0.4):
    try:
        out = _run(['ffmpeg', '-v', 'error', '-ss', str(at), '-i', video, '-frames:v', '1', '-vf', 'scale=%d:%d:force_original_aspect_ratio=decrease' % (w, h),
                    '-f', 'image2pipe', '-vcodec', 'png', '-']).stdout
        if out:
            return out
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ Filmora .wfp
def build_wfp(video, out_path, media_dir=DEFAULT_MEDIA_DIR, name=None, cuts=None, info=None, light=3):
    info = info or probe(video)
    T = json.load(open(os.path.join(HERE, 'templates', 'filmora_wfp.json'), encoding='utf-8'))
    fname = os.path.basename(video)
    name = name or os.path.splitext(os.path.basename(out_path))[0]
    stem = os.path.splitext(fname)[0]
    win = _win_path(media_dir, fname)
    fps = info['fps']
    segs = _segments(info, cuts)
    ticks = lambda frames: int(round(frames * TICK / fps))
    total = ticks(info['frames'])
    now = int(time.time())

    ids = {k: _guid() for k in ('media', 'timeline_media', 'timeline_uuid', 'timeline_clip_media')}
    src_uuid = str(uuid.uuid4())
    bus = str(uuid.uuid4())
    tl_id = 5

    # --- resource (media description inside the timeline file)
    res = copy.deepcopy(T['res_av'] if info['has_audio'] else T['res_v'])
    res['filename'] = 'file:/' + win
    res['sourceUuid'] = src_uuid
    res['mediaLength'] = ticks(info['frames'])
    res['bitRate'] = info['bitrate']
    res['createDate'] = res['modifyDate'] = now
    vs = res['vidStreamInfo'][0]
    vs.update({'width': info['width'], 'height': info['height'], 'xRatio': info['width'], 'yRatio': info['height'],
               'frameRate': {'den': info['fps_den'], 'num': info['fps_num']}, 'maxFrameRate': {'den': info['fps_den'] * 1000, 'num': info['fps_num'] * 1000},
               'totalFrames': info['frames'], 'streamLength': ticks(info['frames']), 'bitRate': info['bitrate']})
    if info['has_audio']:
        au = res['audStreamInfo'][0]
        au.update({'sampleRate': info['a_rate'], 'channels': info['a_ch'], 'streamLength': ticks(info['frames']), 'duration': info['duration']})

    # --- tracks / clips
    clips_v, clips_a, clip_guids = [], [], []
    pos = 0
    for i, (fa, fb) in enumerate(segs):
        a_t, b_t = ticks(fa), ticks(fb)
        length = b_t - a_t
        cg = _guid(); clip_guids.append(cg)
        c = copy.deepcopy(T['clip_video']); _fresh_ids(c)
        c.update({'filename': 'file:/' + win, 'sourceUuid': src_uuid, 'inPoint': a_t, 'outPoint': b_t, 'tlBegin': pos, 'tlEnd': pos + length})
        c['speed'] = {'offset': round(a_t / TICK, 3), 'offsetEnd': round(b_t / TICK, 3), 'reverse': False, 'speedParam': _speed_param(length / TICK)}
        ud = c['userData']
        _ud_set(ud, 50, _b64(stem.encode('utf-8'))); _ud_set(ud, 10, _b64(ids['media'].encode()))
        _ud_set(ud, 3, _pad64(cg)); _ud_set(ud, 1, _i32(i + 1)); _ud_set(ud, 103, _i32(i + 2))
        clips_v.append(c)
        if info['has_audio']:
            ag = cg   # the audio and video halves of one clip share the clip GUID (as in real Filmora files)
            ca = copy.deepcopy(T['clip_audio']); _fresh_ids(ca)
            ca.update({'filename': 'file:/' + win, 'sourceUuid': src_uuid, 'inPoint': a_t, 'outPoint': b_t, 'tlBegin': pos, 'tlEnd': pos + length})
            ca['speed'] = {'offset': round(a_t / TICK, 3), 'offsetEnd': round(b_t / TICK, 3), 'reverse': False, 'speedParam': _speed_param(length / TICK)}
            uda = ca['userData']
            _ud_set(uda, 10, _b64(ids['media'].encode())); _ud_set(uda, 3, _pad64(ag))
            _ud_set(uda, 1, _i32(len(segs) + i + 1)); _ud_set(uda, 103, _i32(len(segs) + i + 2))
            clips_a.append(ca)
        pos += length

    ta0 = copy.deepcopy(T['track_audio_empty']); ta0['busUuids'] = [bus]; ta0['uuid'] = str(uuid.uuid4())
    ta1 = copy.deepcopy(T['track_audio']); ta1['busUuids'] = [bus]; ta1['uuid'] = str(uuid.uuid4()); ta1['clipList'] = clips_a
    tv = copy.deepcopy(T['track_video']); tv['uuid'] = str(uuid.uuid4()); tv['clipList'] = clips_v

    top = copy.deepcopy(T['tl_top'])
    top.update({'audioBusInfos': [{'balance': 0.5, 'busUid': bus, 'gain': 0.0}], 'frameRate': {'den': info['fps_den'], 'num': info['fps_num']},
                'resolutionWidth': info['width'], 'resolutionHeight': info['height']})
    g = math.gcd(info['width'], info['height']) or 1
    top['aspectRatioX'], top['aspectRatioY'] = info['width'] // g, info['height'] // g
    ud_main = copy.deepcopy(T['main_userData'])
    _ud_set(ud_main, 50, _b64(name.encode('utf-8')[:60] + b'\0'))
    _ud_set(ud_main, 11000, _pad64(ids['timeline_uuid'])); _ud_set(ud_main, 3, _pad64(ids['timeline_media']))
    _ud_set(ud_main, 30309, _b64(ids['timeline_uuid'].encode()))
    _ud_set(ud_main, 140, _b64(uuid.uuid4().hex.encode()))
    _ud_set(ud_main, 30306, _b64(json.dumps([{'index': 0, 'isActive': True, 'pageIndex': 1, 'timelineId': ids['timeline_uuid']}], separators=(',', ':')).encode()))
    timeline = dict(top)
    timeline.update({'timelineId': tl_id, 'type': 0, 'userData': ud_main, 'trackInfos': [ta0, ta1, tv]})
    wes = dict(T['wes_top'])
    wes.update({'currentTimelineId': tl_id, 'resources': [res], 'serialNumber': 300, 'timelineInfos': [timeline]})
    # Filmora writes object keys in alphabetical order; do the same for the parts we build ourselves
    timeline['trackInfos'] = [dict(sorted(t_.items())) for t_ in timeline['trackInfos']]
    tl_sorted = dict(sorted((k, v) for k, v in timeline.items() if k not in ('type', 'userData', 'trackInfos')))
    tl_sorted.update({'type': timeline['type'], 'userData': timeline['userData'], 'trackInfos': timeline['trackInfos']})   # real Filmora files end with type, userData, trackInfos
    wes['timelineInfos'] = [tl_sorted]
    wes = dict(sorted(wes.items()))

    # --- extra.json (clip guid -> media)
    extra = {k: T['extra_base'][k] for k in ('fontNameInfo', 'usedBizFont', 'usedTemplateResInfo') if k in T['extra_base']}
    extra['mediaClipsMapInfo'] = {cg: {'mediaId': ids['media'], 'subClips': {}} for cg in clip_guids}
    extra['allMarkersInfo'] = {'beatDetectInfo': {cg: {'algorithmType': 0, 'level': 0} for cg in clip_guids}}
    extra.update({'pendingMarkersInfo': {}, 'highlightInfo': {}, 'TextSentence': {'TextSentence': []}})   # same key order as a real Filmora extra.json

    # --- media.json for the video
    mj = copy.deepcopy(T['media_json_v'] if info['has_audio'] else T['media_json_v_noaudio'])
    mj['file_name'] = win
    sb = mj['sourceInfo']['basicInfo']
    sb.update({'mediaLength': ticks(info['frames']), 'bitRate': info['bitrate'], 'createDate': now})
    mv = mj['sourceInfo']['vidStreamInfos'][0]
    mv.update({'width': info['width'], 'height': info['height'], 'xRatio': info['width'], 'yRatio': info['height'], 'totalFrames': info['frames'],
               'streamLength': ticks(info['frames']), 'frameRate': {'den': info['fps_den'], 'num': info['fps_num']}, 'lastframeRate': {'den': info['fps_den'], 'num': info['fps_num']},
               'maxFrameRate': {'den': info['fps_den'] * 1000, 'num': info['fps_num'] * 1000}, 'bitRate': info['bitrate']})
    if info['has_audio']:
        mj['sourceInfo']['audStreamInfos'][0].update({'sampleRate': info['a_rate'], 'channels': info['a_ch'], 'duration': info['duration'], 'streamLength': ticks(info['frames'])})

    # --- medias_info.json
    medias = {'media_structure': {'visible': 'true', 'SerializeDataOnlyProjectUsered': 'false',
                                  'Folder': {'visible': 'true', 'SerializeDataOnlyProjectUsered': 'false', 'media_item': ids['media']},
                                  'media_item': ids['timeline_media']},
              'media_items': {
                  ids['media']: {'download_url': win, 'id': ids['media'], 'media_type': 8 if info['has_audio'] else 2, 'media_length': ticks(info['frames']), 'name': stem,
                                 'mediaCreationInfo': '{"creationType":0}', 'import_time': now, 'src_md5': info['md5'], 'stream_idx': 0 if info['has_audio'] else -1,
                                 'mark_info_list': [{'mark_in': -1, 'mark_out': -1}], 'scence_info': []},
                  ids['timeline_media']: {'name': name, 'download_url': '', 'id': ids['timeline_media'], 'timeline_uuid': ids['timeline_uuid'], 'media_type': 1048576,
                                          'create_time': now, 'duration': total, 'enable_modify_mediaId': 0, 'mark_info_list': [{'mark_in': -1, 'mark_out': -1}]}}}

    # --- project_info.json
    pi = copy.deepcopy(T['project_info'])
    r = info['width'] / float(info['height'])
    pi.update({'project_file_name': name, 'project_date_create': now, 'project_date_modify': now, 'project_timeline_duration': total,
               'project_timeline_framerate': [info['fps_num'], info['fps_den']], 'project_timeline_resolution': [info['width'], info['height']],
               'project_timeline_ratio': [top['aspectRatioX'], top['aspectRatioY']], 'timeline_mediaId': ids['timeline_media'], 'project_guid': _guid(),
               'proj_zip_save_path': 'C:/Users/Public/Documents/%s.wfp' % name, 'proj_cover_proj_path': '', 'project_source': uuid.uuid4().hex,
               'project_cover': False, 'project_custom_cover': False})

    files = {
        'ProjectFolder/project_info.json': pi,
        'ProjectFolder/Medias/medias_info.json': medias,
        'ProjectFolder/Medias/%s/media.json' % ids['media']: mj,
        'ProjectFolder/Medias/%s/extra.json' % ids['timeline_media']: extra,
        'ProjectFolder/Medias/%s/timeline.wesproj' % ids['timeline_media']: wes,
    }
    th = _thumb_png(video, 320, 180) or base64.b64decode(T['blank_thumb_b64'])
    fs = _thumb_png(video, 160, 90) or base64.b64decode(T['blank_thumb_b64'])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + '.raw'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def put(n, data):
            zi = zipfile.ZipInfo(n, date_time=time.localtime()[:6]); zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3; zi.external_attr = 0o100644 << 16      # regular file, rw-r--r-- (like Filmora's own zips)
            z.writestr(zi, data)
        def js(n, obj): return json.dumps(obj, ensure_ascii=False, indent=4 if n.endswith('project_info.json') else None, separators=None if n.endswith('project_info.json') else (',', ':'))
        order = ['ProjectFolder/project_info.json']
        put(order[0], js(order[0], files[order[0]]))
        put('ProjectFolder/Anon/AppData/Windows/functionExtraData.json', T['function_extra'])
        put('ProjectFolder/Anon/Cover/thumb.fsthumb', fs)
        for n in ('ProjectFolder/Medias/medias_info.json', 'ProjectFolder/Medias/%s/media.json' % ids['media']):
            put(n, js(n, files[n]))
        tl = 'ProjectFolder/Medias/%s/' % ids['timeline_media']
        put(tl + 'timeline.wesproj', js('', files[tl + 'timeline.wesproj'])); put(tl + 'extra.json', js('', files[tl + 'extra.json']))
        put('ProjectFolder/Medias/%s/thumbnail.png' % ids['media'], th)
        put(tl + 'thumbnail.png', base64.b64decode(T['blank_thumb_b64']))
    if light:
        from mgl import wfp_light
        st = wfp_light.lighten(tmp, out_path, level=int(light))
        os.remove(tmp)
    else:
        os.replace(tmp, out_path)
    return out_path


# ------------------------------------------------------------------ FCPXML 1.9
def _frac(frames, info):
    """FCPXML rational time: frames * den / num seconds."""
    return '%d/%ds' % (frames * info['fps_den'], info['fps_num'])


def _file_url(media_dir, fname):
    p = _win_path(media_dir, fname)
    if re.match(r'^[A-Za-z]:/', p):
        return 'file:///' + quote(p, safe='/:')
    return 'file://' + quote(os.path.abspath(p) if not p.startswith('/') else p, safe='/:')


def build_fcpxml(video, out_path, media_dir=DEFAULT_MEDIA_DIR, name=None, cuts=None, info=None):
    info = info or probe(video)
    fname = os.path.basename(video)
    name = name or os.path.splitext(fname)[0]
    segs = _segments(info, cuts)
    fd = '%d/%ds' % (info['fps_den'], info['fps_num'])
    clips, pos = [], 0
    for i, (a, b) in enumerate(segs):
        clips.append('        <asset-clip ref="r2" name="%s" offset="%s" start="%s" duration="%s" format="r1" tcFormat="NDF"%s/>'
                     % (escape(name) + (' %d' % (i + 1) if len(segs) > 1 else ''), _frac(pos, info), _frac(a, info), _frac(b - a, info),
                        ' audioRole="dialogue"' if info['has_audio'] else ''))
        pos += b - a
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9">\n  <resources>\n'
           '    <format id="r1" name="FFVideoFormat%dx%d" frameDuration="%s" width="%d" height="%d" colorSpace="1-1-1 (Rec. 709)"/>\n'
           '    <asset id="r2" name="%s" uid="%s" start="0s" duration="%s" hasVideo="1" format="r1" videoSources="1"%s>\n'
           '      <media-rep kind="original-media" src="%s"/>\n    </asset>\n  </resources>\n  <library>\n    <event name="%s">\n'
           '      <project name="%s">\n        <sequence format="r1" duration="%s" tcStart="0s" tcFormat="NDF"%s>\n          <spine>\n%s\n          </spine>\n'
           '        </sequence>\n      </project>\n    </event>\n  </library>\n</fcpxml>\n'
           % (info['width'], info['height'], fd, info['width'], info['height'], escape(name), info['md5'].upper(), _frac(info['frames'], info),
              (' hasAudio="1" audioSources="1" audioChannels="%d" audioRate="%d"' % (info['a_ch'], info['a_rate'])) if info['has_audio'] else '',
              _file_url(media_dir, fname), escape(name), escape(name), _frac(info['frames'], info),
              (' audioLayout="stereo" audioRate="%s"' % ('48k' if info['a_rate'] >= 48000 else '44.1k')) if info['has_audio'] else '', '\n'.join(clips)))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, 'w', encoding='utf-8').write(xml)
    return out_path


# ------------------------------------------------------------------ FCP7 / Premiere xmeml
def build_xmeml(video, out_path, media_dir=DEFAULT_MEDIA_DIR, name=None, cuts=None, info=None):
    info = info or probe(video)
    fname = os.path.basename(video)
    name = name or os.path.splitext(fname)[0]
    segs = _segments(info, cuts)
    tb = int(round(info['fps']))
    ntsc = 'TRUE' if abs(info['fps'] - tb) > 0.01 else 'FALSE'
    rate = '<rate><timebase>%d</timebase><ntsc>%s</ntsc></rate>' % (tb, ntsc)
    url = _file_url(media_dir, fname).replace('file:///', 'file://localhost/')
    n = info['frames']
    file_xml = ('<file id="file-1"><name>%s</name><pathurl>%s</pathurl>%s<duration>%d</duration><timecode>%s<string>00:00:00:00</string><frame>0</frame>'
                '<displayformat>NDF</displayformat></timecode><media><video><samplecharacteristics>%s<width>%d</width><height>%d</height>'
                '<anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></video>%s</media></file>'
                % (escape(fname), escape(url), rate, n, rate, rate, info['width'], info['height'],
                   ('<audio><samplecharacteristics><depth>16</depth><samplerate>%d</samplerate></samplecharacteristics><channelcount>%d</channelcount></audio>'
                    % (info['a_rate'], info['a_ch'])) if info['has_audio'] else ''))
    vclips, aclips, pos = [], [], 0
    for i, (a, b) in enumerate(segs):
        L = b - a
        link = ''
        if info['has_audio']:
            link = ('<link><linkclipref>clipitem-v%d</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>%d</clipindex></link>'
                    '<link><linkclipref>clipitem-a%d</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>%d</clipindex></link>'
                    % (i + 1, i + 1, i + 1, i + 1))
        body = ('<name>%s</name><enabled>TRUE</enabled><duration>%d</duration>%s<start>%d</start><end>%d</end><in>%d</in><out>%d</out>'
                % (escape(name), n, rate, pos, pos + L, a, b))
        vclips.append('<clipitem id="clipitem-v%d">%s%s%s</clipitem>' % (i + 1, body, file_xml if i == 0 else '<file id="file-1"/>', link))
        if info['has_audio']:
            aclips.append('<clipitem id="clipitem-a%d">%s<file id="file-1"/><sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>%s</clipitem>'
                          % (i + 1, body, link))
        pos += L
    audio = ('<audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics><depth>16</depth><samplerate>%d</samplerate></samplecharacteristics></format>'
             '<track>%s</track></audio>' % (info['a_rate'] or 48000, ''.join(aclips))) if info['has_audio'] else ''
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4"><sequence id="sequence-1"><name>%s</name><duration>%d</duration>%s'
           '<timecode>%s<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode><media><video><format><samplecharacteristics>%s'
           '<width>%d</width><height>%d</height><anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>'
           '</samplecharacteristics></format><track>%s</track></video>%s</media></sequence></xmeml>\n'
           % (escape(name), n, rate, rate, rate, info['width'], info['height'], ''.join(vclips), audio))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, 'w', encoding='utf-8').write(xml)
    return out_path


# ------------------------------------------------------------------ extra copies
def make_gif(video, out_path, width=640, fps=12):
    vf = 'fps=%d,scale=%d:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a' % (fps, width)
    _run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-vf', vf, '-loop', '0', out_path])
    return out_path


def make_webm(video, out_path):
    _run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-c:v', 'libvpx-vp9', '-crf', '20', '-b:v', '0', '-row-mt', '1', '-pix_fmt', 'yuv420p', '-an', out_path])
    return out_path


def make_poster(video, out_path, info=None):
    info = info or probe(video)
    _run(['ffmpeg', '-v', 'error', '-y', '-ss', '%.2f' % (info['duration'] * 0.4), '-i', video, '-frames:v', '1', out_path])
    return out_path


def make_frames_zip(video, out_path, max_frames=300):
    tmp = out_path + '_frames'
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    try:
        _run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-frames:v', str(max_frames), os.path.join(tmp, 'frame_%05d.png')])
        with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_STORED) as z:
            for f in sorted(os.listdir(tmp)):
                z.write(os.path.join(tmp, f), f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_path


def make_mp4_light(video, out_path):
    """Smaller H.264 copy for sharing: CRF 20 + slow preset is visually the same as the CRF 16 master, at ~half the size."""
    _run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-c:a', 'copy', out_path])
    return out_path


# ------------------------------------------------------------------ subtitles + music
def _srt_time(t):
    ms = int(round(t * 1000))
    return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def make_srt(spec, out_path):
    """Subtitles from the text layers of the plan (their own start/end times). Raises if there is no text."""
    rows = []
    for L in (spec or {}).get('layers', []):
        if isinstance(L, dict) and L.get('type') == 'text' and str(L.get('text', '')).strip():
            try:
                a = float(L.get('start', 0)); b = float(L.get('end', (spec or {}).get('duration', a + 2)))
            except (TypeError, ValueError):
                continue
            txt = str(L['text']).strip()
            if '{n}' in txt and isinstance(L.get('count'), dict):      # counters: show the final number
                try: txt = txt.replace('{n}', L['count'].get('format', '{:,.0f}').format(float(L['count'].get('to', 0))))
                except Exception: pass
            if b > a:
                rows.append((a, b, re.sub(r'\s*\n\s*', '\n', txt)))
    if not rows:
        raise ValueError('this video has no text layers (code-mode videos have no plan to read subtitles from)')
    rows.sort()
    with open(out_path, 'w', encoding='utf-8') as f:
        for i, (a, b, t) in enumerate(rows, 1):
            f.write('%d\n%s --> %s\n%s\n\n' % (i, _srt_time(a), _srt_time(b), t))
    return out_path


def add_audio(video, audio, out_path, fade=0.6):
    """Mux a music / voice file under the (silent) video: video stream is copied untouched, audio fades out at the end."""
    info = probe(video)
    d = max(0.0, info['duration'] - fade)
    _run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-stream_loop', '-1', '-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
          '-af', 'afade=t=in:d=0.3,afade=t=out:st=%.2f:d=%.2f' % (d, fade), '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-t', '%.3f' % info['duration'], out_path])
    return out_path


# ------------------------------------------------------------------ driver
def parse_formats(s):
    s = (s or '').strip().lower()
    if s in ('', 'default'):
        return list(DEFAULT_FORMATS)
    if s in ('none', 'off', 'mp4'):
        return []
    if s == 'all':
        return list(ALL_FORMATS)
    out = []
    for p in re.split(r'[,\s+]+', s):
        p = {'fcp': 'fcpxml', 'premiere': 'xml', 'filmora': 'wfp', 'light': 'mp4-light', 'png': 'frames'}.get(p, p)
        if p in ALL_FORMATS and p not in out:
            out.append(p)
        elif p:
            raise ValueError('unknown format "%s" (choose from: %s, all, none)' % (p, ', '.join(ALL_FORMATS)))
    return out


def cuts_from_spec(spec):
    """Scene changes = background changes (the bot's own "scene" marker)."""
    try:
        return sorted({float(b['t']) for b in spec.get('background', []) if isinstance(b, dict) and float(b.get('t', 0)) > 0.2})
    except Exception:
        return []


def export_all(out_dir, formats=None, media_dir=None, video=None, name=None, cuts=None, spec=None, light=3, audio=None):
    """Create every requested format next to the MP4. Never raises: returns (files, problems)."""
    media_dir = (media_dir or os.environ.get('MEDIA_DIR') or DEFAULT_MEDIA_DIR).strip()
    video = video or os.path.join(out_dir, 'video.mp4')
    if isinstance(formats, str) or formats is None:
        formats = parse_formats(formats if formats is not None else os.environ.get('FORMATS', ''))
    files, problems = [], []
    if not formats:
        return files, problems
    if not os.path.isfile(video):
        return files, ['video not found: %s' % video]
    try:
        info = probe(video)
    except Exception as ex:
        return files, ['could not read the video (%s)' % ex]
    stem = name or 'motion_graphic'
    if audio:
        try:
            mixed = os.path.join(out_dir, '%s_with_audio.mp4' % stem)
            add_audio(video, audio, mixed); video = mixed; info = probe(video); files.append(mixed)
            print('audio added -> %s' % os.path.basename(mixed))
        except Exception as ex:
            problems.append('audio failed: %s' % ((getattr(ex, 'stderr', b'') or b'').decode('utf-8', 'ignore')[-300:] or ex))
    if any(f in formats for f in ('wfp', 'fcpxml', 'xml')) and os.path.basename(video).lower() == 'video.mp4' and not audio:
        # a unique file name, so several videos never fight over "video.mp4" in your editor's media folder
        uniq = os.path.join(out_dir, '%s_%s.mp4' % (stem, time.strftime('%Y%m%d_%H%M')))
        shutil.copy(video, uniq)
        video = uniq
        files.append(uniq)
        info = probe(video)
    if cuts is None and spec:
        cuts = cuts_from_spec(spec)
    jobs = {
        'wfp': lambda: build_wfp(video, os.path.join(out_dir, stem + '.wfp'), media_dir, stem, cuts, info, light),
        'fcpxml': lambda: build_fcpxml(video, os.path.join(out_dir, stem + '.fcpxml'), media_dir, stem, cuts, info),
        'xml': lambda: build_xmeml(video, os.path.join(out_dir, stem + '.xml'), media_dir, stem, cuts, info),
        'srt': lambda: make_srt(spec, os.path.join(out_dir, stem + '.srt')),
        'gif': lambda: make_gif(video, os.path.join(out_dir, stem + '.gif')),
        'webm': lambda: make_webm(video, os.path.join(out_dir, stem + '.webm')),
        'poster': lambda: make_poster(video, os.path.join(out_dir, stem + '_poster.png'), info),
        'frames': lambda: make_frames_zip(video, os.path.join(out_dir, stem + '_frames.zip')),
        'mp4-light': lambda: make_mp4_light(video, os.path.join(out_dir, stem + '_light.mp4')),
    }
    for f in formats:
        try:
            p = jobs[f]()
            files.append(p)
            print('export %-9s -> %s (%.0f KB)' % (f, os.path.basename(p), os.path.getsize(p) / 1024.0))
        except Exception as ex:
            msg = '%s failed: %s' % (f, (getattr(ex, 'stderr', b'') or b'').decode('utf-8', 'ignore')[-300:] or ex)
            problems.append(msg); print('export', msg)
    if any(f in formats for f in ('wfp', 'fcpxml', 'xml')):
        n_seg = len(_segments(info, cuts))
        note = ['# Export notes', '',
                'Video: `%s` (%dx%d, %.3g fps, %.2f s)' % (os.path.basename(video), info['width'], info['height'], info['fps'], info['duration']),
                'The project files point to: `%s`' % _win_path(media_dir, os.path.basename(video)),
                '-> Copy `%s` into that folder on your PC. If you keep it elsewhere, the editor shows **Locate / Relink** once: choose the MP4.' % os.path.basename(video),
                'Timeline: %d clip(s)%s.' % (n_seg, ' (split at scene changes: %s s)' % ', '.join('%.2f' % c for c in (cuts or [])) if n_seg > 1 else ''),
                '', 'Files: ' + ', '.join(os.path.basename(x) for x in files), '']
        if problems:
            note += ['Problems:'] + ['- ' + p for p in problems]
        open(os.path.join(out_dir, 'export_notes.md'), 'w', encoding='utf-8').write('\n'.join(note))
    return files, problems
