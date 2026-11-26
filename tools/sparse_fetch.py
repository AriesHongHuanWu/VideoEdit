#!/usr/bin/env python3
"""Fetch only the needed byte ranges of a public Google Drive MP4 into a sparse local file.

The local file has the original size and layout; regions we did not fetch are holes (zeros).
ffmpeg can then decode any time range whose samples were fetched (bit-identical original data).

Usage (module): layout = get_layout(fid, size, cache_dir); fetch_times(fid, size, dst, [(t0,t1),...])
"""
import json, os, struct, subprocess, sys, time

URL = 'https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t'

class QuotaError(Exception):
    pass

def http_range(fid, start, end, tries=4):
    for k in range(tries):
        r = subprocess.run(['curl', '-sS', '-L', '-r', f'{start}-{end}', '-w', '\n%{http_code}', URL.format(fid=fid)],
                           capture_output=True, timeout=600)
        body, _, code = r.stdout.rpartition(b'\n')
        code = code.decode().strip()
        if code == '206' and len(body) == end - start + 1:
            return body
        if b'Quota exceeded' in body[:4000]:
            raise QuotaError(fid)
        time.sleep(2 + 3 * k)
    raise RuntimeError(f'range fetch failed {fid} {start}-{end} code={code} len={len(body)}')

def parse_boxes(buf, off0=0):
    i = 0; out = []
    while i + 8 <= len(buf):
        size, typ = struct.unpack('>I4s', buf[i:i + 8]); hdr = 8
        if size == 1:
            if i + 16 > len(buf):
                break
            size = struct.unpack('>Q', buf[i + 8:i + 16])[0]; hdr = 16
        elif size == 0:
            size = len(buf) - i
        out.append((typ.decode('latin1'), off0 + i, size, hdr))
        if size < 8:
            break
        i += size
    return out

def find(buf, path):
    """Find first box by path like ['trak','mdia','hdlr'] inside buf (content of a container)."""
    for typ, off, size, hdr in parse_boxes(buf):
        if typ == path[0]:
            content = buf[off + hdr: off + size]
            if len(path) == 1:
                return content
            r = find(content, path[1:])
            if r is not None:
                return r
    return None

def find_all(buf, typ_):
    return [buf[off + hdr: off + size] for typ, off, size, hdr in parse_boxes(buf) if typ == typ_]

def video_samples(moov):
    for trak in find_all(moov, 'trak'):
        hdlr = find(trak, ['mdia', 'hdlr'])
        if hdlr is None or hdlr[8:12] != b'vide':
            continue
        stbl = find(trak, ['mdia', 'minf', 'stbl'])
        stsd = find(stbl, ['stsd'])
        codec = stsd[12:16].decode('latin1')
        if codec not in ('hvc1', 'hev1', 'avc1', 'avc3'):
            continue
        mdhd = find(trak, ['mdia', 'mdhd'])
        ver = mdhd[0]
        timescale = struct.unpack('>I', mdhd[12:16] if ver == 0 else mdhd[20:24])[0]
        stts = find(stbl, ['stts']); n = struct.unpack('>I', stts[4:8])[0]
        deltas = []
        for k in range(n):
            c, d = struct.unpack('>II', stts[8 + 8 * k: 16 + 8 * k]); deltas += [d] * c
        stsz = find(stbl, ['stsz']); uni, cnt = struct.unpack('>II', stsz[4:12])
        sizes = [uni] * cnt if uni else list(struct.unpack('>%dI' % cnt, stsz[12:12 + 4 * cnt]))
        stsc = find(stbl, ['stsc']); n = struct.unpack('>I', stsc[4:8])[0]
        runs = [struct.unpack('>III', stsc[8 + 12 * k: 20 + 12 * k]) for k in range(n)]
        co = find(stbl, ['stco'])
        if co is not None:
            nc = struct.unpack('>I', co[4:8])[0]; chunks = list(struct.unpack('>%dI' % nc, co[8:8 + 4 * nc]))
        else:
            co = find(stbl, ['co64']); nc = struct.unpack('>I', co[4:8])[0]; chunks = list(struct.unpack('>%dQ' % nc, co[8:8 + 8 * nc]))
        stss = find(stbl, ['stss'])
        sync = None
        if stss is not None:
            ns = struct.unpack('>I', stss[4:8])[0]; sync = set(struct.unpack('>%dI' % ns, stss[8:8 + 4 * ns]))
        # expand chunks -> sample offsets
        offs = []; si = 0
        for ci in range(len(chunks)):
            # samples per chunk from runs (first_chunk 1-based)
            spc = None
            for (fc, s, _d) in runs:
                if ci + 1 >= fc:
                    spc = s
            o = chunks[ci]
            for _ in range(spc):
                if si >= cnt:
                    break
                offs.append(o); o += sizes[si]; si += 1
        dts = []; t = 0
        for d in deltas:
            dts.append(t / timescale); t += d
        keys = [(i + 1) in sync if sync is not None else True for i in range(cnt)]
        return dict(codec=codec, timescale=timescale, offsets=offs, sizes=sizes, dts=dts, key=keys)
    raise RuntimeError('no video track')

def get_layout(fid, size, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    cp = os.path.join(cache_dir, f'{fid}.layout.json')
    if os.path.exists(cp):
        return json.load(open(cp))
    head = http_range(fid, 0, min(size, 65536) - 1)
    boxes = parse_boxes(head)
    # walk top-level boxes using header jumps
    regions = []  # (offset, bytes) to store locally
    off = 0; moov_off = None; moov_size = None
    while off < size:
        if off + 16 <= len(head):
            hb = head[off:off + 16]
        else:
            hb = http_range(fid, off, min(size, off + 16) - 1)
        bsz, typ = struct.unpack('>I4s', hb[:8])
        if bsz == 1:
            bsz = struct.unpack('>Q', hb[8:16])[0]
        elif bsz == 0:
            bsz = size - off
        if typ == b'moov':
            moov_off, moov_size = off, bsz
        off += bsz
    if moov_off is None:
        raise RuntimeError('moov not found')
    moov = http_range(fid, moov_off, moov_off + moov_size - 1)
    vs = video_samples(moov[8:] if struct.unpack('>I', moov[:4])[0] != 1 else moov[16:])
    lay = dict(size=size, head_len=len(head), moov_off=moov_off, moov_size=moov_size, video=vs)
    # keep the header+moov bytes for sparse files
    with open(os.path.join(cache_dir, f'{fid}.head.bin'), 'wb') as f:
        f.write(head)
    with open(os.path.join(cache_dir, f'{fid}.moov.bin'), 'wb') as f:
        f.write(moov)
    json.dump(lay, open(cp, 'w'))
    return lay

def ensure_sparse(fid, lay, dst, cache_dir):
    if not os.path.exists(dst):
        with open(dst, 'wb') as f:
            f.truncate(lay['size'])
        with open(dst, 'r+b') as f:
            f.write(open(os.path.join(cache_dir, f'{fid}.head.bin'), 'rb').read())
            f.seek(lay['moov_off']); f.write(open(os.path.join(cache_dir, f'{fid}.moov.bin'), 'rb').read())
    done_p = dst + '.ranges.json'
    done = json.load(open(done_p)) if os.path.exists(done_p) else []
    return done, done_p

def merge(ranges, gap=1 << 20):
    ranges = sorted(ranges); out = []
    for a, b in ranges:
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out

def subtract(ranges, have):
    """Remove already-fetched byte ranges."""
    res = []
    for a, b in ranges:
        segs = [[a, b]]
        for ha, hb in have:
            nxt = []
            for s, e in segs:
                if hb < s or ha > e:
                    nxt.append([s, e]); continue
                if s < ha:
                    nxt.append([s, ha - 1])
                if e > hb:
                    nxt.append([hb + 1, e])
            segs = nxt
        res += segs
    return [r for r in res if r[1] >= r[0]]

def sample_ranges_for_times(lay, spans, keyframes_only=False, every_nth_key=1):
    v = lay['video']; dts = v['dts']; key = v['key']; offs = v['offsets']; sz = v['sizes']
    need = []
    if keyframes_only:
        kidx = [i for i, k in enumerate(key) if k]
        for j, i in enumerate(kidx):
            if j % every_nth_key == 0:
                need.append((offs[i], offs[i] + sz[i] - 1))
        return need
    for t0, t1 in spans:
        # first sample index at/after t0 -> back to previous keyframe
        i0 = 0
        while i0 < len(dts) - 1 and dts[i0 + 1] <= t0:
            i0 += 1
        while i0 > 0 and not key[i0]:
            i0 -= 1
        i1 = i0
        while i1 < len(dts) - 1 and dts[i1] <= t1 + 0.05:
            i1 += 1
        for i in range(i0, i1 + 1):
            need.append((offs[i], offs[i] + sz[i] - 1))
    return need

def fetch(fid, size, dst, cache_dir, spans=None, keyframes_only=False, every_nth_key=1, gap=1 << 20, log=print):
    lay = get_layout(fid, size, cache_dir)
    done, done_p = ensure_sparse(fid, lay, dst, cache_dir)
    need = sample_ranges_for_times(lay, spans or [], keyframes_only, every_nth_key)
    need = merge(need, gap if not keyframes_only else 0)
    need = subtract(need, done)
    total = sum(b - a + 1 for a, b in need)
    log(f'fetch {fid}: {len(need)} ranges, {total/1e6:.1f} MB')
    with open(dst, 'r+b') as f:
        for a, b in need:
            # split very large ranges into 32 MB requests
            s = a
            while s <= b:
                e = min(b, s + (32 << 20) - 1)
                data = http_range(fid, s, e)
                f.seek(s); f.write(data)
                done.append([s, e])
                json.dump(merge(done, 0), open(done_p, 'w'))
                s = e + 1
    return lay, total

if __name__ == '__main__':
    fid, size, dst, cache_dir = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    spans = json.loads(sys.argv[5]) if len(sys.argv) > 5 else None
    kf = spans is None
    fetch(fid, size, dst, cache_dir, spans=spans, keyframes_only=kf, every_nth_key=2)
