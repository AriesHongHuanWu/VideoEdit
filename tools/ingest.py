#!/usr/bin/env python3
"""Ingest pipeline: download each Drive file -> 540p keyframe preview + metrics + contact sheet -> delete original.

Run with: python3 -I ingest.py <manifest.tsv> <workdir>
Resumable: skips files whose result JSON already exists.
"""
import json, os, subprocess, sys, time, threading, queue, shutil, struct, re, glob, math, traceback
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

MANIFEST = sys.argv[1]
WORK = sys.argv[2]
ORIG = os.path.join(WORK, 'orig')        # untrusted downloads
TMP = os.path.join(WORK, 'tmp')
PREV = os.path.join(WORK, 'preview')
SHEET = os.path.join(WORK, 'sheets')
RES = os.path.join(WORK, 'results')
for d in (ORIG, TMP, PREV, SHEET, RES):
    os.makedirs(d, exist_ok=True)
STATUS = os.path.join(WORK, 'status.log')
DISK_BUDGET = 5.5e9   # max bytes of originals on disk at once
N_DL = int(os.environ.get('N_DL', '1'))
N_PROC = 3
lock = threading.Lock()
inflight = 0

def log(msg):
    with lock:
        with open(STATUS, 'a') as f:
            f.write(time.strftime('%H:%M:%S ') + msg + '\n')

def load_manifest():
    items = []
    for line in open(MANIFEST):
        p = line.rstrip('\n').split('\t')
        if len(p) < 5:
            continue
        folder, name, fid, size, created = p[:5]
        if re.search(r' 2\.MP4$', name):
            continue  # byte-identical duplicates (same size as the original name)
        items.append(dict(folder=folder, name=name, id=fid, size=int(size), uploaded=created))
    return items

def safe_stem(name):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(name)[0])

# ---------------- DJI protobuf metadata -----------------
def varint(b, i):
    r = 0; s = 0
    while True:
        c = b[i]; i += 1; r |= (c & 0x7f) << s; s += 7
        if not c & 0x80:
            return r, i

def pb_parse(b):
    """Return list of (field, wiretype, value) ; nested messages left as bytes."""
    out = []; i = 0
    while i < len(b):
        key, i = varint(b, i)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, i = varint(b, i)
        elif wt == 1:
            v = b[i:i+8]; i += 8
        elif wt == 5:
            v = b[i:i+4]; i += 4
        elif wt == 2:
            L, i = varint(b, i); v = b[i:i+L]; i += L
        else:
            raise ValueError('wt')
        out.append((fn, wt, v))
    return out

def pb_get(b, path):
    """path like [3,2,6,1]; returns first value found (raw)."""
    try:
        cur = b
        for k, fn in enumerate(path):
            found = None
            for f, wt, v in pb_parse(cur):
                if f == fn:
                    found = (wt, v); break
            if found is None:
                return None
            wt, v = found
            if k == len(path) - 1:
                if wt == 5:
                    return struct.unpack('<f', v)[0]
                if wt == 1:
                    return struct.unpack('<d', v)[0]
                if wt == 2:
                    try:
                        return v.decode()
                    except Exception:
                        return v.hex()
                return v
            cur = v
    except Exception:
        return None

def dji_meta(path, probe):
    res = {}
    idx = None
    for s in probe.get('streams', []):
        if s.get('codec_tag_string') == 'djmd':
            idx = s['index']; break
    if idx is None:
        return res
    binp = os.path.join(TMP, os.path.basename(path) + '.djmd')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-map', f'0:{idx}', '-c', 'copy', '-f', 'data', binp], check=False)
    sz = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', str(idx), '-show_packets', '-show_entries', 'packet=size', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.split()
    try:
        data = open(binp, 'rb').read()
    except Exception:
        return res
    sizes = [int(x) for x in sz if x.strip().isdigit()]
    pkts = []; off = 0
    for s in sizes:
        pkts.append(data[off:off+s]); off += s
    if not pkts:
        return res
    h = pkts[0]
    res['proto'] = pb_get(h, [1, 1, 1])
    res['fw'] = pb_get(h, [1, 1, 3])
    res['hdr_1_9_1'] = pb_get(h, [1, 9, 1])
    res['vid_w'] = pb_get(h, [2, 3, 1]); res['vid_h'] = pb_get(h, [2, 3, 2])
    res['vid_fps'] = pb_get(h, [2, 3, 3]); res['vid_bitdepth'] = pb_get(h, [2, 3, 5])
    res['vid_2_3_6'] = pb_get(h, [2, 3, 6]); res['vid_2_3_8'] = pb_get(h, [2, 3, 8])
    n = len(pkts)
    picks = sorted(set([0, n // 4, n // 2, 3 * n // 4, n - 1]))
    iso = []; sh = []; wb = []; f5 = []
    for k in picks:
        p = pkts[k]
        iso.append(pb_get(p, [3, 2, 2, 1])); sh.append(pb_get(p, [3, 2, 3, 1]))
        f5.append(pb_get(p, [3, 2, 5, 1])); wb.append(pb_get(p, [3, 2, 6, 1]))
    res['iso'] = iso; res['shutter_den'] = sh; res['wb_k'] = wb; res['f5'] = f5
    try:
        os.remove(binp)
    except Exception:
        pass
    return res

# ---------------- download -----------------
QUOTA_MARK = b'Quota exceeded'

def _ranged_download(item, dst, chunk=32 * 1024 * 1024):
    """Fetch the public file in byte-range chunks from the usercontent endpoint (resumable).
    Returns 'ok', 'quota' or 'error'."""
    url = f"https://drive.usercontent.google.com/download?id={item['id']}&export=download&confirm=t"
    size = item['size']
    have = os.path.getsize(dst) if os.path.exists(dst) else 0
    part = dst + '.chunk'
    with open(dst, 'ab') as out:
        off = have
        while off < size:
            end = min(size, off + chunk) - 1
            ok = False
            for attempt in range(3):
                r = subprocess.run(['curl', '-sS', '-L', '-r', f'{off}-{end}', '-o', part, '-w', '%{http_code}', url],
                                   capture_output=True, text=True, timeout=600)
                code = r.stdout.strip()
                got = os.path.getsize(part) if os.path.exists(part) else 0
                if code == '206' and got == end - off + 1:
                    ok = True; break
                head = open(part, 'rb').read(3000) if got else b''
                if QUOTA_MARK in head:
                    return 'quota'
                time.sleep(3 * (attempt + 1))
            if not ok:
                return 'error'
            with open(part, 'rb') as f:
                out.write(f.read())
            off = end + 1
            time.sleep(0.3)
    try:
        os.remove(part)
    except Exception:
        pass
    return 'ok' if os.path.getsize(dst) == size else 'error'

def download(item, dst):
    """Primary: gdown on the public link (one attempt). If Google refuses it, fall back to ranged
    chunks from the public usercontent endpoint. Returns True / False / 'defer'."""
    url = f"https://drive.google.com/uc?id={item['id']}"
    if os.path.exists(dst) and os.path.getsize(dst) == item['size']:
        return True
    if not os.path.exists(dst):
        try:
            r = subprocess.run(['gdown', '--quiet', url, '-O', dst], capture_output=True, text=True, timeout=3600)
            if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) == item['size']:
                time.sleep(1.0)
                return True
        except Exception as e:
            log(f"DL gdown exception {item['name']}: {e}")
        if os.path.exists(dst):
            os.remove(dst)
        log(f"DL gdown refused {item['name']}; ranged fallback")
    res = _ranged_download(item, dst)
    if res == 'ok':
        log(f"DL ranged ok {item['name']}")
        time.sleep(2.0)
        return True
    log(f"DL ranged {res} {item['name']} (have {os.path.getsize(dst) if os.path.exists(dst) else 0} bytes)")
    return 'defer' if res == 'quota' else False

# ---------------- analysis -----------------
orb = None

def global_motion(g0, g1):
    """Estimate similarity transform g0->g1 on small gray frames. Returns dx,dy (px @ width 480), scale, rot_deg, inlier_ratio."""
    o = cv2.ORB_create(800)
    k0, d0 = o.detectAndCompute(g0, None)
    k1, d1 = o.detectAndCompute(g1, None)
    if d0 is None or d1 is None or len(k0) < 20 or len(k1) < 20:
        return None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    m = bf.match(d0, d1)
    if len(m) < 15:
        return None
    p0 = np.float32([k0[x.queryIdx].pt for x in m]); p1 = np.float32([k1[x.trainIdx].pt for x in m])
    M, inl = cv2.estimateAffinePartial2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None:
        return None
    a, b = M[0, 0], M[1, 0]
    scale = math.hypot(a, b); rot = math.degrees(math.atan2(b, a))
    # translation of the image centre
    cx, cy = g0.shape[1] / 2, g0.shape[0] / 2
    nx = M[0, 0] * cx + M[0, 1] * cy + M[0, 2]; ny = M[1, 0] * cx + M[1, 1] * cy + M[1, 2]
    return dict(dx=float(nx - cx), dy=float(ny - cy), scale=float(scale), rot=float(rot), inl=float(inl.mean()) if inl is not None else 0.0)

def frame_metrics(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(g, cv2.CV_64F).var()
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    b, gg, r = [bgr[..., i].astype(np.float32).mean() for i in range(3)]
    return dict(sharp=float(lap), luma=float(g.mean()), contrast=float(g.std()), sat=float(hsv[..., 1].mean()),
                clip_hi=float((g > 250).mean()), clip_lo=float((g < 6).mean()), rgb=[float(r), float(gg), float(b)])

def font(sz):
    for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']:
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()

F_SMALL = font(15); F_TITLE = font(20)

def make_sheet(stem, frames, times, metrics, header, out):
    n = len(frames)
    if n == 0:
        return
    maxn = 30
    if n > maxn:
        idx = np.linspace(0, n - 1, maxn).round().astype(int)
    else:
        idx = np.arange(n)
    tw, th = 320, 180
    cols = 6
    rows = math.ceil(len(idx) / cols)
    W = cols * tw; H = 34 + rows * (th + 20)
    sheet = Image.new('RGB', (W, H), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    d.text((6, 6), header, fill=(255, 255, 255), font=F_TITLE)
    sh = np.array([m['sharp'] for m in metrics])
    for k, i in enumerate(idx):
        fr = frames[i]
        h0, w0 = fr.shape[:2]
        if h0 > w0:  # portrait: fit inside 320x180 box
            s = th / h0
        else:
            s = min(tw / w0, th / h0)
        im = cv2.resize(fr, (max(1, int(w0 * s)), max(1, int(h0 * s))), interpolation=cv2.INTER_AREA)
        pim = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
        x = (k % cols) * tw; y = 34 + (k // cols) * (th + 20)
        sheet.paste(pim, (x + (tw - pim.width) // 2, y))
        rel = sh[i] / (np.median(sh) + 1e-6)
        d.text((x + 4, y + th + 1), f"{times[i]:6.1f}s  sh{rel:4.2f}", fill=(255, 230, 120), font=F_SMALL)
    sheet.save(out, quality=82)

def process(item, path):
    stem = safe_stem(item['name'])
    t0 = time.time()
    pr = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path], capture_output=True, text=True)
    probe = json.loads(pr.stdout or '{}')
    v = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'video' and s.get('codec_name') != 'mjpeg'), None)
    if v is None:
        raise RuntimeError('no video stream')
    dur = float(probe['format'].get('duration', 0) or 0)
    W, H = int(v['width']), int(v['height'])
    rot = 0
    for sd in v.get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = int(sd['rotation'])
    meta = dict(name=item['name'], folder=item['folder'], id=item['id'], size=item['size'], duration=dur, width=W, height=H,
                rotation=rot, codec=v.get('codec_name'), profile=v.get('profile'), pix_fmt=v.get('pix_fmt'),
                fps=v.get('avg_frame_rate'), color_transfer=v.get('color_transfer'), color_primaries=v.get('color_primaries'),
                creation_time=probe['format'].get('tags', {}).get('creation_time'), encoder=probe['format'].get('tags', {}).get('encoder'),
                has_audio=any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])))
    meta['dji'] = dji_meta(path, probe)
    # --- frame extraction
    fdir = os.path.join(TMP, stem + '_frames')
    shutil.rmtree(fdir, ignore_errors=True); os.makedirs(fdir)
    portrait = (H > W) ^ (abs(rot) == 90)
    scale = 'scale=540:-2' if portrait else 'scale=-2:540'
    full = dur < 6.0
    if full:
        cmd = ['ffmpeg', '-v', 'info', '-y', '-threads', '2', '-i', path, '-map', '0:v:0', '-vf', f'fps=6,{scale}:flags=area,showinfo', '-q:v', '3', os.path.join(fdir, '%05d.jpg')]
    else:
        cmd = ['ffmpeg', '-v', 'info', '-y', '-skip_frame', 'nokey', '-threads', '1', '-i', path, '-map', '0:v:0', '-fps_mode', 'passthrough', '-vf', f'{scale}:flags=area,showinfo', '-q:v', '3', os.path.join(fdir, '%05d.jpg')]
    r = subprocess.run(cmd, capture_output=True, text=True)
    times = [float(x) for x in re.findall(r'pts_time:\s*([0-9.]+)', r.stderr)]
    files = sorted(glob.glob(os.path.join(fdir, '*.jpg')))
    if not files:
        raise RuntimeError('no frames: ' + r.stderr[-400:])
    if len(times) != len(files):
        times = list(np.linspace(0, dur, len(files), endpoint=False))
    frames = [cv2.imread(f) for f in files]
    metrics = [frame_metrics(f) for f in frames]
    # global motion between consecutive sampled frames (on 480-wide gray)
    gm = [None]
    small = [cv2.cvtColor(cv2.resize(f, (f.shape[1] // 2, f.shape[0] // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY) for f in frames]
    for k in range(1, len(small)):
        try:
            g = global_motion(small[k - 1], small[k])
        except Exception:
            g = None
        if g is not None:
            dt = max(1e-3, times[k] - times[k - 1])
            g['dt'] = dt
        gm.append(g)
    # --- preview video at sample rate
    step = float(np.median(np.diff(times))) if len(times) > 2 else 0.5
    rate = max(1.0, round(1.0 / step, 3)) if step > 0 else 2.0
    prev = os.path.join(PREV, stem + '_540p.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(rate), '-i', os.path.join(fdir, '%05d.jpg'),
                    '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-c:v', 'libx264', '-preset', 'medium', '-crf', '24', '-pix_fmt', 'yuv420p', '-r', str(rate), prev], check=False)
    header = f"{item['name']}  {dur:.1f}s  {W}x{H}@{v.get('avg_frame_rate')} {v.get('pix_fmt')}  {meta['creation_time']}  [{item['folder']}]"
    make_sheet(stem, frames, times, metrics, header, os.path.join(SHEET, stem + '.jpg'))
    res = dict(meta=meta, times=times, metrics=metrics, motion=gm, sample_mode='full6fps' if full else 'keyframes', proc_sec=time.time() - t0)
    with open(os.path.join(RES, stem + '.json'), 'w') as f:
        json.dump(res, f)
    shutil.rmtree(fdir, ignore_errors=True)
    return res

# ---------------- orchestration -----------------
def main():
    global inflight
    items = load_manifest()
    todo = [it for it in items if not os.path.exists(os.path.join(RES, safe_stem(it['name']) + '.json'))]
    log(f"START total={len(items)} todo={len(todo)}")
    # interleave large and small files to keep pipeline balanced
    dlq = queue.Queue(); procq = queue.Queue()
    for it in todo:
        dlq.put(it)
    def all_deferred(q):
        with q.mutex:
            return all(x.get('not_before', 0) > time.time() for x in list(q.queue))
    def dl_worker():
        global inflight
        while True:
            try:
                it = dlq.get_nowait()
            except queue.Empty:
                return
            if it.get('not_before', 0) > time.time():
                dlq.put(it)
                if all_deferred(dlq):
                    time.sleep(15)
                continue
            while True:
                with lock:
                    if inflight + it['size'] <= DISK_BUDGET or inflight == 0:
                        inflight += it['size']; break
                time.sleep(2)
            dst = os.path.join(ORIG, safe_stem(it['name']) + '.mp4')
            t = time.time()
            ok = download(it, dst)
            if ok == 'defer':
                n_def = it.get('deferred', 0)
                if n_def < 6:
                    it['deferred'] = n_def + 1
                    it['not_before'] = time.time() + 600
                    dlq.put(it)
                    log(f"DL deferred {it['name']} (#{n_def+1}); retry in 10 min")
                else:
                    log(f"DL FAILED (quota) {it['name']}")
                with lock:
                    inflight -= it['size']
                continue
            if ok:
                log(f"DL ok {it['name']} {it['size']/1e6:.0f}MB in {time.time()-t:.1f}s")
                procq.put((it, dst))
            else:
                log(f"DL FAILED {it['name']}")
                with lock:
                    inflight -= it['size']
    def proc_worker():
        global inflight
        while True:
            job = procq.get()
            if job is None:
                return
            it, dst = job
            try:
                r = process(it, dst)
                log(f"PROC ok {it['name']} dur={r['meta']['duration']:.1f}s frames={len(r['times'])} in {r['proc_sec']:.1f}s")
            except Exception as e:
                log(f"PROC FAILED {it['name']}: {e} {traceback.format_exc()[-500:]!r}")
            finally:
                try:
                    os.remove(dst)
                except Exception:
                    pass
                with lock:
                    inflight -= it['size']
    dls = [threading.Thread(target=dl_worker) for _ in range(N_DL)]
    prs = [threading.Thread(target=proc_worker) for _ in range(N_PROC)]
    for t in dls + prs:
        t.start()
    for t in dls:
        t.join()
    for _ in prs:
        procq.put(None)
    for t in prs:
        t.join()
    log("ALL DONE")

if __name__ == '__main__':
    main()
