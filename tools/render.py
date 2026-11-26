#!/usr/bin/env python3
"""Compositor: renders the EDL (edl.json) to a 1920x1080@60 intermediate using shot caches.

python3 -I render.py <edl.json> <cache_dir> <out.mp4> [--workers 4] [--frames a:b] [--preview]
"""
import json, math, os, subprocess, sys, time, argparse, random
import numpy as np
import cv2
sys.path.insert(0, os.path.dirname(__file__))
import engine as E

W, H, FPS = E.W, E.H, E.FPS

# ------------------------------------------------------------------ cache access
class Cache:
    def __init__(self, cache_dir):
        self.dir = cache_dir; self.caps = {}; self.pos = {}; self.last = {}; self.meta = {}

    def info(self, sid):
        if sid not in self.meta:
            p = os.path.join(self.dir, f'{sid}.json')
            self.meta[sid] = json.load(open(p)) if os.path.exists(p) else {}
        return self.meta[sid]

    def frame(self, sid, i):
        """Return float32 RGB frame i (clamped) of cache sid at cache resolution."""
        n = self.info(sid).get('n_frames')
        if n:
            i = max(0, min(n - 1, i))
        key = (sid, i)
        if self.last.get(sid, (None, None))[0] == i:
            return self.last[sid][1]
        cap = self.caps.get(sid)
        if cap is None:
            cap = cv2.VideoCapture(os.path.join(self.dir, f'{sid}.mp4'))
            self.caps[sid] = cap; self.pos[sid] = 0
        if self.pos[sid] != i:
            if not (0 < i - self.pos[sid] < 8):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i); self.pos[sid] = i
            else:
                while self.pos[sid] < i:
                    cap.grab(); self.pos[sid] += 1
        ok, fr = cap.read()
        if not ok:
            fr = self.last.get(sid, (None, np.zeros((1620, 2880, 3), np.uint8)))[1]
            if fr.dtype != np.uint8:
                return fr
        else:
            self.pos[sid] = i + 1
            fr = E.to_f(fr[:, :, ::-1])
        self.last[sid] = (i, fr)
        return fr

# ------------------------------------------------------------------ keyframe helpers
EASE = {'linear': lambda t: E.clamp01(t), 'out': E.ease_out_cubic, 'in': E.ease_in_cubic, 'inout': E.ease_in_out_cubic,
        'outexpo': E.ease_out_expo, 'inexpo': E.ease_in_expo, 'back': E.ease_out_back}

def kf(keys, t, default):
    """keys: [[t, value(s), ease?], ...] value may be number or list. Interpolated with ease of the target key."""
    if not keys:
        return default
    if t <= keys[0][0]:
        return keys[0][1]
    for a, b in zip(keys, keys[1:]):
        if t <= b[0]:
            u = (t - a[0]) / max(1e-9, b[0] - a[0])
            e = EASE[b[2] if len(b) > 2 else 'inout'](u)
            if isinstance(a[1], list):
                return [x + (y - x) * e for x, y in zip(a[1], b[1])]
            return a[1] + (b[1] - a[1]) * e
    return keys[-1][1]

# ------------------------------------------------------------------ shot rendering
def shot_frame(seg, cache, tl, fi, tracks):
    """Render a 'shot' segment at local time tl (s) / local frame fi."""
    sid = seg['shot']; off = seg.get('cache_offset', 0)
    z = kf(seg.get('zoom'), tl, 1.0); c = kf(seg.get('center'), tl, [0.5, 0.5]); rot = kf(seg.get('rot'), tl, 0.0)
    dx = dy = 0.0
    if seg.get('shake'):
        sx, sy, sr = E.shake_offsets(tl + seg.get('shake_seed', 0) * 3.1, seg['shake'], seg.get('shake_rot', 0.35), seed=seg.get('shake_seed', 3))
        dx += sx; dy += sy; rot += sr
    # flash-pop zoom (105% -> 100%)
    for fx in seg.get('fx', []):
        if fx['type'] == 'flash_pop':
            u = (tl - fx.get('at', 0.0)) / fx.get('dur', 0.13)
            if 0 <= u <= 1:
                z *= 1 + (fx.get('scale', 1.05) - 1) * (1 - E.ease_out_cubic(u))
        if fx['type'] == 'zoom_out':
            u = (tl - fx['t0']) / (fx['t1'] - fx['t0'])
            if u <= 1:
                z *= fx.get('z0', 1.5) + (1 - fx.get('z0', 1.5)) * E.ease_out_expo(max(0, u))
        if fx['type'] == 'punch':  # 100% -> 105% snap on bass hits, eased back
            for tp in fx['times']:
                if tl >= tp:
                    z *= 1 + fx.get('amount', 0.05) * math.exp(-(tl - tp) / fx.get('decay', 0.09))
        if fx['type'] == 'push_out':   # zoom-through (outgoing half): accelerate into the frame
            u = (tl - fx['t0']) / (fx['t1'] - fx['t0'])
            if 0 <= u <= 1:
                z *= 1 + (fx.get('z1', 1.4) - 1) * E.ease_in_expo(u)
        if fx['type'] == 'whip':   # positional whip offset with motion blur (in or out)
            u = (tl - fx['t0']) / (fx['t1'] - fx['t0'])
            if 0 <= u <= 1:
                k = E.ease_in_expo(u) if fx.get('out') else 1 - E.ease_out_expo(u)
                dx += fx.get('dx', 0) * k; dy += fx.get('dy', 0) * k; rot += fx.get('droll', 0) * k
    def render_at(fidx, zz, cc, rr, ddx, ddy):
        src = cache.frame(sid, off + fidx)
        return E.place(src, zoom=zz, cx=cc[0], cy=cc[1], rot=rr, dx=ddx, dy=ddy)
    img = render_at(fi, z, c, rot, dx, dy)
    # motion blur for whips / zoom outs
    for fx in seg.get('fx', []):
        if fx['type'] == 'whip':
            u = (tl - fx['t0']) / (fx['t1'] - fx['t0'])
            if 0 <= u <= 1:
                k = E.ease_in_expo(u) if fx.get('out') else 1 - E.ease_out_expo(u)
                vel = abs(fx.get('dx', 0)) * (1.0 if 0.05 < u < 0.95 else 0.5) * (0.35 + k)
                img = E.directional_blur(img, math.copysign(min(260, vel * 0.25), fx.get('dx', 1)), n=11)
        if fx['type'] == 'zoom_out':
            u = (tl - fx['t0']) / (fx['t1'] - fx['t0'])
            if 0 <= u < 0.85:
                img = E.radial_zoom_blur(img, strength=0.10 * (1 - u), n=9)
        if fx['type'] == 'push_out':
            u = (tl - fx['t0']) / (fx['t1'] - fx['t0'])
            if 0.15 < u <= 1:
                img = E.radial_zoom_blur(img, strength=0.12 * u, n=9)
    return img

def apply_fx(img, seg, tl, fi, ctx, base_fn):
    """Per-segment effects after the base image is built. base_fn(t) re-renders the base (for shutter freeze)."""
    for fx in seg.get('fx', []):
        t0 = fx.get('t0', 0.0); t1 = fx.get('t1', 1e9)
        typ = fx['type']
        if typ == 'flash_pop':
            u = (tl - fx.get('at', 0.0)) * FPS
            if 0 <= u < 4:
                img = E.white_mix(img, [1.0, 0.65, 0.3, 0.1][int(u)])
        elif typ in ('bw', 'bw_invert', 'duotone', 'red_invert', 'chroma') and t0 <= tl < t1:
            img = {'bw': E.bw_hard, 'bw_invert': E.bw_invert, 'duotone': E.duotone, 'red_invert': E.red_tint_invert,
                   'chroma': lambda x: E.chroma_split(x, fx.get('px', 6))}[typ](img)
        elif typ == 'overexpose' and t0 <= tl < t1:
            u = (tl - t0) / max(1e-6, t1 - t0)
            amt = fx.get('amount', 1.0) * (math.sin(math.pi * u) if fx.get('shape', 'bell') == 'bell' else (u if fx['shape'] == 'up' else 1 - u))
            img = E.overexpose(img, amt)
        elif typ == 'white' and t0 <= tl < t1:
            img = E.solid(E.WHITE)
        elif typ == 'black' and t0 <= tl < t1:
            img = E.solid(E.BLACK)
        elif typ == 'red' and t0 <= tl < t1:
            img = E.solid(E.RED)
        elif typ == 'letterbox' and t0 <= tl < t1 + 0.12:
            hmax = fx.get('h', 150)
            if tl < t1:
                h = hmax * E.spring(tl - t0, freq=3.2, damp=9.0)
            else:
                h = hmax * (1 - E.ease_in_cubic((tl - t1) / 0.12))
            img = E.letterbox(img, h)
        elif typ == 'red_inset' and t0 <= tl < t1 + 0.1:
            # red frame inset, pops back to full screen at t1 (over 0.1 s)
            s0 = fx.get('scale', 0.74)
            if tl < t1:
                s = s0 * (0.9 + 0.1 * E.spring(tl - t0, freq=3.0, damp=8.0))
            else:
                s = s0 + (1 - s0) * E.ease_out_cubic((tl - t1) / 0.1)
            bg = E.solid(E.RED)
            img = E.inset_on(bg, img, s, cx=W / 2 + fx.get('dx', 0), cy=H / 2 + fx.get('dy', 0))
        elif typ == 'title_top' and t0 <= tl < t1:
            img = title_top(img, fx, tl - t0)
        elif typ == 'text' and t0 <= tl < t1:
            a = min(1.0, (tl - t0) / max(1e-6, fx.get('fade', 0.06)))
            mode = fx.get('mode', 'normal')
            u = (tl - t0) / max(1e-6, fx.get('anim', seg['dur']) )
            trk = int(fx.get('tracking', 0) + (fx.get('tracking_to', fx.get('tracking', 0)) - fx.get('tracking', 0)) * E.ease_out_cubic(min(1.0, u)))
            dy = int((1 - E.ease_out_expo(min(1.0, (tl - t0) / 0.2))) * fx.get('rise', 0))
            E.draw_text(img, fx['text'], fx.get('font', 'anton'), fx['size'], np.array(fx.get('color', [1, 1, 1]), np.float32),
                        fx['x'], fx['y'] + dy, fx.get('anchor', 'mm'), trk, a, mode=mode)
        elif typ == 'glass' and t0 <= tl < t1:
            u = E.clamp01((tl - t0) / 0.15)
            img = E.glass_text(img, fx['text'], size=fx.get('size', 520), cx=fx.get('cx', W // 2), cy=fx.get('cy', H // 2),
                               tracking=fx.get('tracking', 0), opacity=E.ease_out_cubic(u))
        elif typ == 'roto_text' and t0 <= tl < t1:
            img = roto_text(img, fx, tl - t0, fi, ctx, seg)
        elif typ == 'hud' and t0 <= tl < t1:
            img = hud(img, fx, tl - t0, fi, ctx, seg)
        elif typ == 'shutter' and t0 <= tl < t1:
            img = shutter(img, fx, tl - t0, base_fn, t0)
        elif typ == 'clone' and t0 <= tl < t1:
            img = clone(img, fx, tl, fi, ctx, seg)
        elif typ == 'redpanel' and t0 <= tl < t1:
            u = E.ease_in_out_cubic((tl - t0) / max(1e-6, t1 - t0))
            if fx.get('mode', 'cover') == 'cover':      # panel sweeps in and covers the outgoing shot
                x1 = u * W * 1.02; x0 = x1 - W * 1.02
            else:                                       # panel keeps travelling and reveals the incoming shot
                x0 = u * W * 1.02; x1 = x0 + W * 1.02
            if fx.get('dir', 1) < 0:
                x0, x1 = W - x1, W - x0
            img = E.red_panel(img, x0, x1, fx.get('label'), 1.0, label_size=fx.get('label_size', 150))
        elif typ == 'lb_close' and t0 <= tl < t1 + 0.5:
            u = E.ease_in_cubic(min(1.0, (tl - t0) / max(1e-6, t1 - t0)))
            img = E.letterbox(img, u * (H / 2 + 2))
        elif typ == 'lb_open' and t0 <= tl < t1:
            u = (tl - t0) / max(1e-6, t1 - t0)
            img = E.letterbox(img, (H / 2 + 2) * (1 - E.spring(u * 0.5, freq=1.6, damp=7.0)))
        elif typ == 'glitch' and t0 <= tl < t1:
            img = E.glitch(img, fx.get('strength', 1.0), seed=fi)
        elif typ == 'soft_glow' and t0 <= tl < t1:          # 柔光
            img = E.soft_glow(img, fx.get('amount', 0.55), fx.get('radius', 22), fx.get('thresh', 0.42), mist=fx.get('mist', 0.10))
        elif typ == 'light_scatter' and t0 <= tl < t1:      # 散光
            img = E.light_scatter(img, fx.get('amount', 0.6), fx.get('length', 0.30), gain=fx.get('gain', 3.2))
        elif typ == 'scanlines' and t0 <= tl < t1:
            img = E.scanlines(img, fx.get('strength', 0.15))
    return img

def title_top(img, fx, t):
    text = fx['text']
    size = fx.get('size') or min(E.fit_text_size(text, 'anton', W - 2 * fx.get('margin', 34), fx.get('tracking', 0)), int(H * fx.get('max_h', 0.34) / 0.80))
    m = E.text_mask(text, 'anton', size, fx.get('tracking', 0))
    h, w = m.shape
    # punch-in: slide down from above with slight overshoot
    k = E.ease_out_back(min(1.0, t / 0.16), 1.4)
    y = int(fx.get('y', -12) - (1 - k) * h * 0.55)
    x = (W - w) // 2
    col = np.empty((h, w, 3), np.float32); col[:] = E.RED
    E.over(img, col, m, x, y)
    if fx.get('sub'):
        E.draw_text(img, fx['sub'], 'inter_med', 22, E.WHITE, x + 6, y + h + 8, 'lt', tracking=5)
    return img

def roto_text(img, fx, t, fi, ctx, seg):
    """Giant text behind a person: matte frames in fx['matte'] (per local frame, png alpha at 1920x1080)."""
    base = img.copy()
    a = E.ease_out_cubic(min(1.0, t / 0.14))
    rise = E.ease_out_expo(min(1.0, t / 0.30))
    color = np.array(fx.get('color', [1, 1, 1]), np.float32)
    size = int(fx.get('size', 600) * (1.08 - 0.08 * rise))
    trk = int(fx.get('tracking', 0) + fx.get('tracking_grow', 14) * min(1.0, t / max(0.3, seg['dur'])))
    E.draw_text(img, fx['text'], 'anton', size, color, fx.get('x', W // 2), fx.get('y', H // 2) + int((1 - rise) * 140), 'mm', trk, a)
    mp = os.path.join(fx['matte_dir'], f'{fi + seg.get("cache_offset", 0) + fx.get("matte_offset", 0):05d}.png')
    if os.path.exists(mp):
        mt = cv2.imread(mp, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
        if mt.shape != (H, W):
            mt = cv2.resize(mt, (W, H))
        mt = mt[..., None]
        img = img * (1 - mt) + base * mt
    return img

def hud(img, fx, t, fi, ctx, seg):
    tr = ctx['tracks'].get(fx['track'])
    if tr is None:
        return img
    k = min(len(tr['pts']) - 1, fi + seg.get('cache_offset', 0) + fx.get('track_offset', 0))
    p = tr['pts'][k]
    if p is None:
        return img
    # map cache-normalised point through the shot transform (approx: zoom/center only)
    z = kf(seg.get('zoom'), t + fx.get('t0', 0), 1.0); c = kf(seg.get('center'), t + fx.get('t0', 0), [0.5, 0.5])
    x = (p[0] - c[0]) * W * z + W / 2; y = (p[1] - c[1]) * H * z * (W / H) / (16 / 9) + H / 2
    subs = []
    for sp in tr.get('subs', [])[:4]:
        q = sp[k] if k < len(sp) else None
        if q is not None:
            subs.append(((q[0] - c[0]) * W * z + W / 2, (q[1] - c[1]) * H * z + H / 2))
    appear = min(1.0, t / 0.08)
    rgb, al = E.hud_layer((x, y), t, label=fx.get('label', 'TRK_01'), coord=(x, y), appear=appear, scale=fx.get('scale', 1.0), sub_points=subs)
    return E.apply_layer(img, rgb, al)

def clone(img, fx, tl, fi, ctx, seg):
    """Clone effect: the same moving person appears several times (locked-off shot). Copies come from
    other moments of the same cache, keyed by motion masks; each copy pops in with a white flash."""
    cache = ctx['cache']
    for j, d in enumerate(fx['offsets']):
        appear = fx.get('appear', [0.0] * len(fx['offsets']))[j]
        if tl < appear:
            continue
        k = fi + d + seg.get('cache_offset', 0)
        mp = os.path.join(fx['mask_dir'], f'{k:05d}.png')
        if not os.path.exists(mp):
            continue
        m = cv2.imread(mp, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
        src = cache.frame(seg['shot'], k)
        other = E.place(src)
        a = m[..., None]
        if tl - appear < 2 / FPS:
            other = E.white_mix(other, 0.6)
        img = img * (1 - a) + other * a
    return img

def shutter(img, fx, t, base_fn, t0):
    """Burst of frozen stills: each still held for `hold` s, separated by a 1-frame black blink."""
    hold = fx.get('hold', 0.083)
    k = int(t / hold); u = t - k * hold
    still_t = t0 + k * hold
    frozen = base_fn(still_t)
    if u < 1.0 / FPS:
        return E.solid(E.BLACK) * 0.0 + E.white_mix(frozen, 0.0) * 0.08
    s = 1.0 + 0.02 * (k % 2)
    if s != 1.0:
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, s)
        frozen = cv2.warpAffine(frozen, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    # thin white viewfinder frame
    out = frozen.copy()
    out[18:21, 18:W - 18] = 1; out[H - 21:H - 18, 18:W - 18] = 1; out[18:H - 18, 18:21] = 1; out[18:H - 18, W - 21:W - 18] = 1
    return out

# ------------------------------------------------------------------ special segments
def card(seg, tl, ctx):
    kind = seg['card']
    if kind == 'roma':
        bg = E.solid(E.RED)
        # letters slam: scale 1.18 -> 1.0 with tiny shake
        u = min(1.0, tl / 0.12); s = 1.0 + 0.18 * (1 - E.ease_out_expo(u))
        size = int(seg.get('size', 560) * s)
        E.draw_text(bg, seg.get('text', 'ROMA'), 'anton', size, E.WHITE, W // 2, H // 2 + 18, 'mm', seg.get('tracking', 6))
        if seg.get('sub'):
            E.draw_text(bg, seg['sub'], 'inter_med', 26, E.WHITE, W // 2, H // 2 + 330, 'mm', tracking=10)
        bg = E.scanlines(bg, 0.07, 4)
        if tl < 3 / FPS:
            bg = E.glitch(bg, 1.0 - tl * 15, seed=int(tl * FPS) + 5)
        if tl < 2 / FPS:
            bg = E.white_mix(bg, 0.6 if tl < 1 / FPS else 0.3)
        return bg
    if kind == 'red':
        return E.solid(E.RED)
    if kind == 'end':
        bg = E.solid(E.WINE)
        u = E.ease_out_cubic(min(1.0, tl / 0.35))
        size = int(seg.get('size', 330))
        trk = int(seg.get('tracking', 10) + 26 * (1 - u))
        E.draw_text(bg, 'ITALIA', 'anton', size, E.WHITE, W // 2, H // 2 - 40, 'mm', trk, alpha=min(1.0, tl / 0.12))
        a2 = E.clamp01((tl - 0.35) / 0.3)
        if a2 > 0:
            E.draw_text(bg, seg.get('places', ''), 'inter_semi', 30, E.WHITE, W // 2, H // 2 + 165, 'mm', 9, a2)
            E.draw_text(bg, seg.get('dates', ''), 'inter', 24, E.WHITE, W // 2, H // 2 + 215, 'mm', 10, a2 * 0.85)
        # fade to black at the very end
        te = seg['dur'] - tl
        if te < 0.4:
            bg = bg * (te / 0.4)
        return bg
    return E.solid(E.BLACK)

def split_card(seg, tl, fi, cache, ctx):
    """Red card: left inset image (shot playing), right white place name. Optional expand_out: the red-framed
    inset snaps to full frame at the end (carries into the next shot)."""
    bg = E.solid(E.RED)
    shot_img = shot_frame(seg, cache, tl, fi, ctx['tracks'])
    s = seg.get('inset_scale', 0.52); cx = seg.get('inset_cx', 560)
    pop = 0.92 + 0.08 * E.spring(tl, freq=3.0, damp=8.0)
    a = E.ease_out_cubic(min(1.0, (tl - 0.04) / 0.12))
    eo = seg.get('expand_out', 0)
    if eo and tl > seg['dur'] - eo:
        v = E.ease_in_out_cubic((tl - (seg['dur'] - eo)) / eo)
        s = s + (1 - s) * v; cx = cx + (W / 2 - cx) * v; pop = 1.0; a *= (1 - v)
    E.inset_on(bg, shot_img, s * pop, cx=cx, cy=H / 2)
    x = seg.get('text_x', 1110)
    if a > 0.01:
        E.draw_text(bg, seg['text'], 'anton', seg.get('size', 150), E.WHITE, x + int((1 - a) * 60), H // 2 - 10, 'lm', 2, a)
        if seg.get('sub'):
            E.draw_text(bg, seg['sub'], 'inter_med', 24, E.WHITE, x + 4 + int((1 - a) * 60), H // 2 + 92, 'lt', 6, a)
    return bg

def vsplit(seg, tl, fi, cache, ctx):
    """Vertical split-screen juxtaposition: panels slide into columns on beat hits; optional expand to full."""
    panels = seg['panels']; n = len(panels); cw = W / n; gap = seg.get('gap', 8)
    first = panels[0]
    base_src = cache.frame(first['shot'], first.get('offset', 0) + fi)
    out = E.place(base_src, zoom=first.get('zoom', 1.0), cx=first.get('cx', 0.5)).copy()
    exp = seg.get('expand')            # (panel index, t_start)
    for i, p in enumerate(panels):
        te = p.get('enter', 0.0)
        if tl < te:
            continue
        u = E.ease_out_expo(min(1.0, (tl - te) / p.get('slide', 0.14)))
        src = cache.frame(p['shot'], p.get('offset', 0) + fi)
        img = E.place(src, zoom=p.get('zoom', 1.0), cx=p.get('cx', 0.5), cy=p.get('cy', 0.5))
        x0 = int(round(i * cw)); x1 = int(round((i + 1) * cw))
        if exp and exp[0] == i and tl >= exp[1]:
            v = E.ease_in_out_cubic(min(1.0, (tl - exp[1]) / seg.get('expand_dur', 0.16)))
            x0 = int(x0 * (1 - v)); x1 = int(x1 + (W - x1) * v)
        sx0 = int(W / 2 - (x1 - x0) / 2 + p.get('dx', 0)); sx0 = max(0, min(W - (x1 - x0), sx0))
        col = img[:, sx0:sx0 + (x1 - x0)]
        dirn = {'top': -1, 'bottom': 1}.get(p.get('from', 'bottom'), 0)
        yo = int((1 - u) * H * dirn)
        ys0, ys1 = max(0, yo), min(H, H + yo)
        if ys1 > ys0:
            out[ys0:ys1, x0:x1] = col[ys0 - yo:ys1 - yo]
    if seg.get('gaps', True):
        for i in range(1, n):
            x = int(round(i * cw))
            if exp and tl >= exp[1] + seg.get('expand_dur', 0.16):
                break
            out[:, max(0, x - gap // 2):x + gap // 2] = E.RED
    return out

def intro(seg, tl, fi, cache, ctx):
    """'postcards from ITALIA' opening. Times are local to the segment.
    phases: strips in [0, p1) ; collapse [p1, p2) ; title decode [p2, p3) ; band open [p3, end)."""
    strips = seg['strips']; band = seg['band']
    p1, p2, p3 = seg['p1'], seg['p2'], seg['p3']
    n = len(strips); sw = W / n
    out = E.solid(E.BLACK)
    if tl < p2:
        # vertical strips with staggered slide-in from the left over the base shot; content keeps playing
        b = seg.get('base')
        if b:
            row = E.place(cache.frame(b['shot'], b.get('offset', 0) + fi), zoom=b.get('zoom', 1.0)).copy()
        else:
            row = np.zeros((H, W, 3), np.float32)
        for i, st in enumerate(strips):
            ti = tl - i * seg.get('stagger', 0.05)
            if ti < 0:
                continue
            k = E.ease_out_expo(min(1.0, ti / 0.22))
            x0 = int(i * sw); x1 = int((i + 1) * sw)
            src = cache.frame(st['shot'], st.get('offset', 0) + int(tl * FPS))
            img = E.place(src, zoom=st.get('zoom', 1.0), cx=st.get('cx', 0.5), cy=st.get('cy', 0.5))
            col = img[:, int(W / 2 - sw / 2 + st.get('dx', 0)): int(W / 2 - sw / 2 + st.get('dx', 0)) + (x1 - x0)]
            shift = int((1 - k) * -sw * 1.2)
            xs0 = max(0, x0 + shift); xs1 = min(W, x1 + shift)
            if xs1 > xs0:
                row[:, xs0:xs1] = col[:, xs0 - (x0 + shift): xs1 - (x0 + shift)]
            # thin dark separators
            row[:, max(0, x1 + shift - 2): max(0, x1 + shift)] *= 0.25
        if tl < p1:
            out = row
        else:
            u = E.ease_in_out_cubic((tl - p1) / (p2 - p1))
            hb = int(H * (1 - u) + 4 * u)
            hb = max(2, hb)
            y0 = H // 2 - hb // 2
            out[y0:y0 + hb] = row[y0:y0 + hb]
    else:
        out = E.crt_background(tl)
        # band behind the title: thin -> full, cycling shots each beat
        if tl >= p3:
            u = E.ease_in_out_cubic((tl - p3) / (seg['dur'] - p3))
            hb = int(6 + (H - 6) * (u ** 1.15))
            idx = min(len(band) - 1, int((tl - p3) / seg['band_step']))
            bshot = band[idx]
            src = cache.frame(bshot['shot'], bshot.get('offset', 0) + int((tl - p3 - idx * seg['band_step']) * FPS))
            img = E.place(src, zoom=bshot.get('zoom', 1.08), cx=bshot.get('cx', 0.5), cy=bshot.get('cy', 0.5))
            y0 = H // 2 - hb // 2
            out[y0:y0 + hb] = img[y0:y0 + hb]
        # text
        tt = tl - p2
        a_small = E.clamp01(tt / 0.15) if tl >= p2 - 0.18 else 0
        prog = E.clamp01((tl - p2) / (p3 - p2 - 0.02))
        word = E.decode_text('ITALIA', prog, seed=3, frame=fi) if prog < 1 else 'ITALIA'
        size = seg.get('title_size', 330)
        m = E.text_mask('ITALIA', 'anton', size, 8)
        tw_, th_ = m.shape[1], m.shape[0]
        ty = H // 2 + 10
        E.draw_text(out, word, 'anton', size, E.RED, W // 2, ty, 'mm', 8)
        xl = W // 2 - tw_ // 2; xr = W // 2 + tw_ // 2
        E.draw_text(out, 'postcards', 'inter', 30, E.WHITE, xl + 6, ty - th_ // 2 - 18, 'lb', 2, a_small)
        E.draw_text(out, 'from', 'inter', 30, E.WHITE, xr - 6, ty - th_ // 2 - 18, 'rb', 2, a_small)
    # pre-title: small text appears slightly before decode
    if p1 <= tl < p2:
        pass
    return out

# ------------------------------------------------------------------ main loop
def render_frame(edl, gi, cache, ctx, grain):
    t = gi / FPS
    seg = None
    for s in edl['segments']:
        if s['f0'] <= gi < s['f1']:
            seg = s; break
    if seg is None:
        return E.solid(E.BLACK)
    fi = gi - seg['f0']; tl = fi / FPS
    typ = seg['type']
    if typ == 'shot':
        base_fn = lambda tt: shot_frame(seg, cache, tt, int(round(tt * FPS)), ctx['tracks'])
        img = shot_frame(seg, cache, tl, fi, ctx['tracks'])
        img = apply_fx(img, seg, tl, fi, ctx, base_fn)
    elif typ == 'card':
        img = card(seg, tl, ctx)
        img = apply_fx(img, seg, tl, fi, ctx, lambda tt: img)
    elif typ == 'split':
        img = split_card(seg, tl, fi, cache, ctx)
        img = apply_fx(img, seg, tl, fi, ctx, lambda tt: img)
    elif typ == 'vsplit':
        img = vsplit(seg, tl, fi, cache, ctx)
        img = apply_fx(img, seg, tl, fi, ctx, lambda tt: img)
    elif typ == 'intro':
        img = intro(seg, tl, fi, cache, ctx)
        img = apply_fx(img, seg, tl, fi, ctx, lambda tt: img)
    else:
        img = E.solid(E.BLACK)
    # wipe-in from previous shot (foreground wipe): previous segment continues under a moving mask
    wp = seg.get('wipe_in')
    if wp and tl < wp['dur']:
        prev = next(s for s in edl['segments'] if s['f1'] == seg['f0'])
        pfi = gi - prev['f0']
        pimg = shot_frame(prev, cache, pfi / FPS, pfi, ctx['tracks'])
        u = E.ease_in_out_cubic(tl / wp['dur'])
        edge = wp.get('from', 0) + (wp.get('to', W) - wp.get('from', 0)) * u
        xs = np.arange(W, dtype=np.float32)
        feather = wp.get('feather', 70)
        m = np.clip((edge - xs) / feather + 0.5, 0, 1) if wp.get('dir', 1) > 0 else np.clip((xs - (W - edge)) / feather + 0.5, 0, 1)
        img = pimg * (1 - m[None, :, None]) + img * m[None, :, None]
    # global finishing: halation, vignette, grain
    post = edl.get('post', {})
    hal = seg.get('halation', post.get('halation', 0.2))
    if hal > 0:
        img = E.halation(img, hal)
    vig = seg.get('vignette', post.get('vignette', 0.16))
    if vig > 0:
        img = E.vignette(img, vig)
    img = grain.apply(img, gi, amount=seg.get('grain', post.get('grain', 0.03)))
    return np.clip(img, 0, 1)

def render_range(edl_path, cache_dir, a, b, out_path, preview=False):
    edl = json.load(open(edl_path))
    cache = Cache(cache_dir)
    tracks = {}
    for k, p in edl.get('tracks', {}).items():
        if os.path.exists(p):
            tracks[k] = json.load(open(p))
    ctx = {'tracks': tracks, 'cache': cache}
    grain = E.Grain(n=24, seed=11 + a)
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                            '-c:v', 'libx264', '-preset', 'veryfast' if preview else 'medium', '-crf', '20' if preview else '8',
                            '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', out_path],
                           stdin=subprocess.PIPE)
    t0 = time.time()
    for gi in range(a, b):
        img = render_frame(edl, gi, cache, ctx, grain)
        enc.stdin.write(E.to_u8(img).tobytes())
    enc.stdin.close(); enc.wait()
    return time.time() - t0

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('edl'); ap.add_argument('cache_dir'); ap.add_argument('out')
    ap.add_argument('--range', default=None); ap.add_argument('--preview', action='store_true')
    args = ap.parse_args()
    edl = json.load(open(args.edl))
    a, b = (0, edl['n_frames']) if not args.range else map(int, args.range.split(':'))
    dt = render_range(args.edl, args.cache_dir, a, b, args.out, args.preview)
    print(f'rendered {b-a} frames in {dt:.1f}s')
