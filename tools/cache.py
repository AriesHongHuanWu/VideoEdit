#!/usr/bin/env python3
"""Shot cache builder: source segment -> per-shot graded, time-remapped 60 fps frames at 2880x1620.

Speed ramps use optical-flow frame interpolation (DIS) for slow sections and shutter-style frame
blending for fast sections. Sources below 50 fps are always flow-interpolated to 60 fps.
"""
import json, math, os, subprocess, sys
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(__file__))
import look

CW, CH = 2880, 1620
OUT_FPS = 60.0

def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                        'stream=width,height,avg_frame_rate,r_frame_rate:format=duration', '-of', 'json', path],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)
    s = d['streams'][0]
    num, den = s['avg_frame_rate'].split('/')
    fps = float(num) / float(den)
    return int(s['width']), int(s['height']), fps, float(d['format']['duration'])

def speed_at(tau, keys):
    """keys: list of (t_rel, speed) ; smooth (cosine) interpolation between keys."""
    if isinstance(keys, (int, float)):
        return float(keys)
    if tau <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if tau <= t1:
            u = (tau - t0) / max(1e-9, t1 - t0)
            u = 0.5 - 0.5 * math.cos(math.pi * u)
            return v0 + (v1 - v0) * u
    return keys[-1][1]

def source_times(src_in, n_out, speed, sub=8):
    """Integrate speed curve -> source time for each output frame start (and per-frame span)."""
    times = []; spans = []
    s = src_in
    dt = 1.0 / OUT_FPS
    for k in range(n_out):
        tau = k * dt
        times.append(s)
        acc = 0.0
        for j in range(sub):
            acc += speed_at(tau + (j + 0.5) * dt / sub, speed) * dt / sub
        spans.append(acc)
        s += acc
    return times, spans

def crop_filter(sw, sh, crop):
    """Return ffmpeg crop expression to reach 16:9 (crop = dict(y=0..1 vertical centre, x=..., zoom=1))."""
    crop = crop or {}
    target_ar = 16 / 9
    z = crop.get('zoom', 1.0)
    if sw / sh > target_ar + 1e-3:
        cw = int(sh * target_ar / z); ch = int(sh / z)
    else:
        cw = int(sw / z); ch = int(sw / target_ar / z)
    cw -= cw % 2; ch -= ch % 2
    cx = crop.get('x', 0.5); cy = crop.get('y', 0.5)
    x = int(min(max(cx * sw - cw / 2, 0), sw - cw)); y = int(min(max(cy * sh - ch / 2, 0), sh - ch))
    if cw == sw and ch == sh:
        return None
    return f'crop={cw}:{ch}:{x}:{y}'

def sample_frames(path, t0, t1, crop, n=4, w=640):
    sw, sh, fps, dur = probe(path)
    out = []
    for k in range(n):
        t = t0 + (t1 - t0) * (k + 0.5) / n
        cf = crop_filter(sw, sh, crop)
        vf = (cf + ',' if cf else '') + f'scale={w}:-2'
        r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', path, '-frames:v', '1', '-vf', vf,
                            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True)
        hh = int(round(w * 9 / 16 / 2) * 2)
        buf = np.frombuffer(r.stdout, np.uint8)
        if buf.size >= w * hh * 3:
            img = buf[: w * hh * 3].reshape(hh, w, 3)
            out.append(img.astype(np.float64) / 255.0)
    return out

class FrameReader:
    def __init__(self, path, t_start, t_end, vf, fps):
        self.fps = fps
        self.t0 = max(0.0, t_start)
        dur = max(0.05, t_end - self.t0)
        cmd = ['ffmpeg', '-v', 'error', '-ss', f'{self.t0:.4f}', '-i', path, '-t', f'{dur:.4f}', '-map', '0:v:0',
               '-vf', vf, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=CW * CH * 3 * 2)
        self.frames = {}
        self.next_idx = 0
        self.eof = False

    def get(self, i):
        i = max(0, i)
        while not self.eof and self.next_idx <= i:
            raw = self.p.stdout.read(CW * CH * 3)
            if len(raw) < CW * CH * 3:
                self.eof = True; break
            self.frames[self.next_idx] = np.frombuffer(raw, np.uint8).reshape(CH, CW, 3)
            self.next_idx += 1
        # drop old frames
        for k in [k for k in self.frames if k < i - 6]:
            del self.frames[k]
        if i in self.frames:
            return self.frames[i]
        if self.frames:
            return self.frames[max(self.frames)]
        raise RuntimeError('no frames decoded')

    def close(self):
        try:
            self.p.stdout.close(); self.p.kill()
        except Exception:
            pass

_dis = None

def flow_interp(a, b, t):
    """Occlusion-aware interpolation between uint8 frames a,b at fraction t.
    Bidirectional DIS flow; where the two warps disagree (occlusions, fast edges) the result falls back
    to the temporally nearest real frame instead of a warped mix, which removes most 'rubber' artifacts."""
    global _dis
    if _dis is None:
        _dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    s = 3
    ga = cv2.cvtColor(cv2.resize(a, (CW // s, CH // s), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(cv2.resize(b, (CW // s, CH // s), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    f01 = _dis.calc(ga, gb, None); f10 = _dis.calc(gb, ga, None)
    ft0 = -(1 - t) * t * f01 + t * t * f10
    ft1 = (1 - t) * (1 - t) * f01 - t * (1 - t) * f10
    ft0 = cv2.resize(ft0, (CW, CH)) * s; ft1 = cv2.resize(ft1, (CW, CH)) * s
    gx, gy = np.meshgrid(np.arange(CW, dtype=np.float32), np.arange(CH, dtype=np.float32))
    wa = cv2.remap(a, gx + ft0[..., 0], gy + ft0[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    wb = cv2.remap(b, gx + ft1[..., 0], gy + ft1[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    mix = cv2.addWeighted(wa, 1 - t, wb, t, 0)
    # disagreement mask (computed small, blurred) -> fall back to nearest real frame there
    d = cv2.absdiff(cv2.resize(wa, (CW // 4, CH // 4)), cv2.resize(wb, (CW // 4, CH // 4))).max(axis=2).astype(np.float32)
    m = np.clip((d - 18) / 30, 0, 1)
    m = cv2.resize(cv2.GaussianBlur(m, (0, 0), 2), (CW, CH))[..., None]
    nearest = a if t < 0.5 else b
    out = mix.astype(np.float32) * (1 - m) + nearest.astype(np.float32) * m
    return np.clip(out, 0, 255).astype(np.uint8)

def build(shot, src_path, out_dir, lut_dir):
    """shot: dict(id, clip, src_in, n_frames, speed, crop, grade(optional dict overrides), interp)"""
    os.makedirs(out_dir, exist_ok=True); os.makedirs(lut_dir, exist_ok=True)
    sid = shot['id']
    out_path = os.path.join(out_dir, f'{sid}.mp4')
    sw, sh, fps, dur = probe(src_path)
    n = int(shot['n_frames'])
    times, spans = source_times(shot['src_in'], n, shot.get('speed', 1.0))
    t_lo = min(times) - 0.05; t_hi = max(t + s for t, s in zip(times, spans)) + 0.1
    if fps < 10:   # low-rate stand-in (preview) sources: make sure the window spans real frames
        t_lo -= 0.6; t_hi += 0.6
    t_lo = max(0.0, t_lo)
    t_hi = min(t_hi, dur - 0.02)
    # per-shot LUT
    samples = sample_frames(src_path, max(0, min(times)), min(dur - 0.05, max(times) + 0.02), shot.get('crop'), n=4)
    p = look.estimate_params(samples)
    g = shot.get('grade', {})
    for k, v in g.items():
        if k in ('exposure_mult',):
            p['exposure'] *= v
        elif k in ('gains_mult',):
            p['gains'] = tuple(a * b for a, b in zip(p['gains'], v))
        elif k == 'wb_strength':
            pass
        else:
            p[k] = v
    lut, nl = look.build_lut(p, n=33, look_strength=g.get('look', 1.0))
    lut_path = os.path.join(lut_dir, f'{sid}.cube')
    look.write_cube(lut_path, lut, nl, sid)
    cf = crop_filter(sw, sh, shot.get('crop'))
    vf = (cf + ',' if cf else '') + f'scale={CW}:{CH}:flags=lanczos,format=rgb24,lut3d=file={lut_path}:interp=tetrahedral'
    rd = FrameReader(src_path, t_lo, t_hi, vf, fps)
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{CW}x{CH}',
                            '-r', '60', '-i', '-', '-c:v', 'libx264', '-preset', 'fast', '-crf', '11',
                            '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', out_path],
                           stdin=subprocess.PIPE)
    low_fps = fps < 50
    mode = shot.get('interp', 'auto')
    for k in range(n):
        pos = (times[k] - rd.t0) * fps
        span = spans[k] * fps                       # source frames covered by this output frame
        if span >= 1.8 and mode != 'nearest':
            # fast: shutter blend of frames within half the span (180 deg)
            m = max(2, min(12, int(round(span * 0.5))))
            acc = np.zeros((CH, CW, 3), np.float32)
            for j in range(m):
                acc += rd.get(int(round(pos + span * 0.5 * j / m)))
            frame = (acc / m).astype(np.uint8)
        else:
            i0 = int(math.floor(pos)); frac = pos - i0
            need_flow = (mode == 'flow') or (mode == 'auto' and (low_fps or span < 0.9))
            if need_flow and 0.06 < frac < 0.94:
                frame = flow_interp(rd.get(i0), rd.get(i0 + 1), frac)
            else:
                frame = rd.get(int(round(pos)))
        enc.stdin.write(np.ascontiguousarray(frame).tobytes())
    enc.stdin.close(); enc.wait(); rd.close()
    meta = dict(id=sid, clip=shot['clip'], src_in=shot['src_in'], n_frames=n, src_times=[round(x, 4) for x in times],
                params=p, src_fps=fps, src_size=[sw, sh])
    with open(os.path.join(out_dir, f'{sid}.json'), 'w') as f:
        json.dump(meta, f)
    return out_path

if __name__ == '__main__':
    shot = json.loads(sys.argv[1])
    print(build(shot, sys.argv[2], sys.argv[3], sys.argv[4]))
