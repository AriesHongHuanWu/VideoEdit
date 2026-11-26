#!/usr/bin/env python3
"""Effects / graphics engine for the ITALIA montage. Float32 RGB frames in [0,1], 1920x1080."""
import math, functools, os, random
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 60
ROOT = '/tmp/claude-0/-home-user-VideoEdit/8531dbc8-a772-580f-8538-3f205e4051d8/scratchpad'
FONT_DIR = os.path.join(ROOT, 'fonts')
RED = np.array([196, 18, 0], np.float32) / 255.0          # #C41200
WINE = np.array([74, 8, 18], np.float32) / 255.0          # deep wine red #4A0812
WHITE = np.array([1, 1, 1], np.float32)
BLACK = np.array([0, 0, 0], np.float32)

FONT = {
    'anton': os.path.join(FONT_DIR, 'Anton-Regular.ttf'),
    'inter': os.path.join(FONT_DIR, 'Inter-Regular.ttf'),
    'inter_med': os.path.join(FONT_DIR, 'Inter-Medium.ttf'),
    'inter_semi': os.path.join(FONT_DIR, 'Inter-SemiBold.ttf'),
    'inter_bold': os.path.join(FONT_DIR, 'Inter-Bold.ttf'),
    'mono': os.path.join(FONT_DIR, 'JetBrainsMono-Regular.ttf'),
    'mono_med': os.path.join(FONT_DIR, 'JetBrainsMono-Medium.ttf'),
}

# ----------------------------------------------------------------- easing
def clamp01(x):
    return max(0.0, min(1.0, x))

def lerp(a, b, t):
    return a + (b - a) * t

def ease_out_cubic(t):
    t = clamp01(t); return 1 - (1 - t) ** 3

def ease_in_cubic(t):
    t = clamp01(t); return t ** 3

def ease_in_out_cubic(t):
    t = clamp01(t); return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2

def ease_out_expo(t):
    t = clamp01(t); return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)

def ease_in_expo(t):
    t = clamp01(t); return 0.0 if t <= 0 else 2 ** (10 * t - 10)

def ease_out_back(t, s=1.9):
    t = clamp01(t); t1 = t - 1; return 1 + (s + 1) * t1 ** 3 + s * t1 ** 2

def spring(t, freq=4.5, damp=6.0):
    """Damped spring from 0 -> 1 (overshoots). t in seconds."""
    if t <= 0:
        return 0.0
    return 1 - math.exp(-damp * t) * math.cos(2 * math.pi * freq * t)

# ----------------------------------------------------------------- basic ops
def to_f(u8):
    return u8.astype(np.float32) * (1.0 / 255.0)

def to_u8(f):
    return (np.clip(f, 0, 1) * 255.0 + 0.5).astype(np.uint8)

def luma(img):
    return img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722

def solid(color, w=W, h=H):
    out = np.empty((h, w, 3), np.float32); out[:] = color; return out

def over(base, rgb, alpha, x=0, y=0):
    """Composite rgb (h,w,3) with alpha (h,w) onto base at (x,y), clipped. In-place on base; returns base."""
    h, w = alpha.shape[:2]
    x0, y0 = max(0, x), max(0, y); x1, y1 = min(base.shape[1], x + w), min(base.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return base
    sx0, sy0 = x0 - x, y0 - y; sx1, sy1 = sx0 + (x1 - x0), sy0 + (y1 - y0)
    a = alpha[sy0:sy1, sx0:sx1, None]
    src = rgb[sy0:sy1, sx0:sx1] if rgb.ndim == 3 else rgb
    region = base[y0:y1, x0:x1]
    region *= (1 - a)
    region += src * a
    return base

def exclusion(a, b):
    return a + b - 2 * a * b

def screen(a, b):
    return 1 - (1 - a) * (1 - b)

def bw(img, contrast=1.0):
    L = luma(img)
    return np.repeat(L[..., None], 3, -1)

def bw_hard(img):
    """High-contrast black & white: strong S curve, crushed blacks, bright whites."""
    L = luma(img)
    lo, hi = np.percentile(L[::8, ::8], [3, 97])
    x = np.clip((L - lo) / max(1e-3, hi - lo), 0, 1)
    x = x * x * (3 - 2 * x)          # smoothstep S
    x = x * x * (3 - 2 * x) * 0.55 + x * 0.45
    return np.repeat(x[..., None], 3, -1).astype(np.float32)

def bw_invert(img):
    return 1.0 - bw_hard(img)

def duotone(img, dark=RED, light=WHITE, gamma=1.0):
    L = bw_hard(img)[..., 0] ** gamma
    return (dark[None, None, :] * (1 - L[..., None]) + light[None, None, :] * L[..., None]).astype(np.float32)

def red_tint_invert(img):
    """Inverted B&W tinted red (like the NYC reference transition frames)."""
    inv = bw_invert(img)[..., 0]
    return (RED[None, None] * (1 - inv[..., None]) + np.array([1.0, 0.92, 0.92], np.float32)[None, None] * inv[..., None]).astype(np.float32)

def overexpose(img, amount):
    """amount 0..1 : photographic over-exposure towards white (highlights blow first)."""
    if amount <= 0:
        return img
    gain = 1 + 6.0 * amount
    out = 1 - np.exp(-img * gain * 1.3)
    out = out / (1 - math.exp(-gain * 1.3))
    return np.clip(out * (1 - amount * 0.35) + amount * 0.35, 0, 1).astype(np.float32)

def white_mix(img, a):
    return (img * (1 - a) + a).astype(np.float32)

# ----------------------------------------------------------------- texture
class Grain:
    def __init__(self, n=40, seed=7, w=W, h=H):
        rng = np.random.default_rng(seed)
        self.bank = []
        for _ in range(n):
            g = rng.standard_normal((h, w)).astype(np.float32)
            g = cv2.GaussianBlur(g, (0, 0), 0.62)
            g /= g.std() + 1e-6
            c = rng.standard_normal((h // 2, w // 2, 3)).astype(np.float32)
            c = cv2.resize(cv2.GaussianBlur(c, (0, 0), 0.8), (w, h))
            c /= c.std() + 1e-6
            self.bank.append((g.astype(np.float16), c.astype(np.float16)))

    def apply(self, img, k, amount=0.022, chroma=0.12):
        g, c = self.bank[k % len(self.bank)]
        L = luma(img)
        resp = (0.30 + 2.6 * L * (1 - L))[..., None]   # finer, mostly in the mids
        noise = (g.astype(np.float32)[..., None] + chroma * c.astype(np.float32))
        return np.clip(img + noise * amount * resp, 0, 1)

def halation(img, amount=0.22, thresh=0.72):
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    L = luma(small)
    m = np.clip((L - thresh) / (1 - thresh), 0, 1) ** 1.4
    hl = small * m[..., None]
    b1 = cv2.GaussianBlur(hl, (0, 0), 6)
    b2 = cv2.GaussianBlur(hl, (0, 0), 22)
    glow = b1 * 0.6 + b2 * 0.55
    glow = glow * np.array([1.0, 0.55, 0.32], np.float32)          # warm-red halation
    glow = cv2.resize(glow, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    return np.clip(screen(img, glow * amount * 2.2), 0, 1)

@functools.lru_cache(maxsize=4)
def _vignette_mask(w, h, strength):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2) / (w / 2); ny = (yy - h / 2) / (h / 2)
    r = np.sqrt(nx * nx * 0.9 + ny * ny * 1.1)
    return (1 - strength * np.clip((r - 0.55) / 0.85, 0, 1) ** 1.6).astype(np.float32)

def vignette(img, strength=0.18):
    return img * _vignette_mask(img.shape[1], img.shape[0], strength)[..., None]

def chroma_split(img, px=4):
    out = img.copy()
    out[..., 0] = np.roll(img[..., 0], px, axis=1)
    out[..., 2] = np.roll(img[..., 2], -px, axis=1)
    return out

def scanlines(img, strength=0.12, period=4):
    m = np.ones(img.shape[0], np.float32)
    m[::period] = 1 - strength
    return img * m[:, None, None]

# ----------------------------------------------------------------- text
@functools.lru_cache(maxsize=256)
def text_mask(text, font='anton', size=200, tracking=0, pad=20):
    """Return float32 alpha mask (h,w) of rendered text (tight, with pad)."""
    f = ImageFont.truetype(FONT[font], size)
    # measure with per-char tracking
    widths = []
    for ch in text:
        bb = f.getbbox(ch)
        widths.append(f.getlength(ch))
    total = sum(widths) + tracking * max(0, len(text) - 1)
    asc, desc = f.getmetrics()
    img = Image.new('L', (int(total + 2 * pad), int(asc + desc + 2 * pad)), 0)
    d = ImageDraw.Draw(img)
    x = pad
    for ch, wch in zip(text, widths):
        d.text((x, pad), ch, font=f, fill=255)
        x += wch + tracking
    a = np.asarray(img).astype(np.float32) / 255.0
    ys, xs = np.where(a > 0.02)
    if len(ys) == 0:
        return a
    y0, y1 = max(0, ys.min() - pad // 2), min(a.shape[0], ys.max() + pad // 2 + 1)
    x0, x1 = max(0, xs.min() - pad // 2), min(a.shape[1], xs.max() + pad // 2 + 1)
    return np.ascontiguousarray(a[y0:y1, x0:x1])

def fit_text_size(text, font, target_w, tracking=0, lo=10, hi=1400):
    """Binary search font size so that the tight text width ~= target_w."""
    for _ in range(18):
        mid = (lo + hi) / 2
        w = text_mask(text, font, int(mid), tracking).shape[1]
        if w > target_w:
            hi = mid
        else:
            lo = mid
    return int(lo)

def draw_text(base, text, font, size, color, x, y, anchor='lt', tracking=0, alpha=1.0, mode='normal'):
    m = text_mask(text, font, size, tracking) * alpha
    h, w = m.shape
    if anchor[0] == 'm':
        x = x - w // 2
    elif anchor[0] == 'r':
        x = x - w
    if anchor[1] == 'm':
        y = y - h // 2
    elif anchor[1] == 'b':
        y = y - h
    if mode == 'exclusion':
        # exclusion with a flat colour: region -> excl(base, color)
        x0, y0 = max(0, x), max(0, y); x1, y1 = min(base.shape[1], x + w), min(base.shape[0], y + h)
        if x1 > x0 and y1 > y0:
            a = m[y0 - y:y1 - y, x0 - x:x1 - x, None]
            reg = base[y0:y1, x0:x1]
            ex = exclusion(reg, np.asarray(color, np.float32)[None, None])
            base[y0:y1, x0:x1] = reg * (1 - a) + ex * a
        return base, (x, y, w, h)
    col = np.empty((h, w, 3), np.float32); col[:] = color
    over(base, col, m, x, y)
    return base, (x, y, w, h)

SCRAMBLE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

def decode_text(final, progress, seed=0, frame=0):
    """Decode/scramble: letters lock left->right as progress goes 0->1; unlocked letters are random each frame."""
    n = len(final)
    out = []
    rng = random.Random(seed * 1000 + frame // 2)   # change every 2 frames
    for i, ch in enumerate(final):
        lock_at = (i + 1) / (n + 0.6)
        if progress >= lock_at or ch == ' ':
            out.append(ch)
        else:
            out.append(rng.choice(SCRAMBLE))
    return ''.join(out)

# ----------------------------------------------------------------- glass text
def glass_text(frame, text, font='anton', size=520, cx=W // 2, cy=H // 2, tracking=0, refr=1.10, blur=14, opacity=1.0):
    m = text_mask(text, font, size, tracking)
    h, w = m.shape
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    # refracted background: magnified + blurred + slightly brighter/cooler
    M = cv2.getRotationMatrix2D((cx, cy), 0, refr)
    mag = cv2.warpAffine(frame, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    small = cv2.resize(mag, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), blur / 2)
    glass = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
    glass = np.clip(glass * 1.08 + 0.05, 0, 1)
    # full-frame mask
    full = np.zeros((H, W), np.float32)
    xs0, ys0 = max(0, x0), max(0, y0); xs1, ys1 = min(W, x0 + w), min(H, y0 + h)
    full[ys0:ys1, xs0:xs1] = m[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
    # bevel: gradient of blurred mask -> light from top-left
    mb = cv2.GaussianBlur(full, (0, 0), 3.0)
    gx = cv2.Sobel(mb, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(mb, cv2.CV_32F, 0, 1, ksize=3)
    lightdir = np.array([0.6, 0.8]); lightdir /= np.linalg.norm(lightdir)
    shade = (gx * lightdir[0] + gy * lightdir[1])
    hi = np.clip(shade * 2.2, 0, 1) * full
    lo = np.clip(-shade * 1.6, 0, 1) * full
    # thin bright rim along the edge
    edge = np.clip(mb * (1 - mb) * 4, 0, 1) * full
    # outer soft shadow for separation
    sh = cv2.GaussianBlur(full, (0, 0), 18)
    sh = np.roll(np.roll(sh, 10, 0), 6, 1) * (1 - full)
    out = frame * (1 - 0.35 * sh[..., None] * opacity)
    inner = glass + hi[..., None] * 0.9 + edge[..., None] * 0.35 - lo[..., None] * 0.25
    a = (full * opacity)[..., None]
    out = out * (1 - a) + np.clip(inner, 0, 1) * a
    return np.clip(out, 0, 1).astype(np.float32)

# ----------------------------------------------------------------- frame transforms
def place(cache_frame, zoom=1.0, cx=0.5, cy=0.5, rot=0.0, dx=0.0, dy=0.0, out_w=W, out_h=H):
    """Map a cache frame (any size, 16:9) to output with zoom (1 = fill), centre (normalised), rotation (deg), offset px."""
    ch, cw = cache_frame.shape[:2]
    base_scale = out_w / cw                      # scale making cache fill output width
    s = base_scale * zoom
    if abs(rot) < 1e-3 and s <= 1.0:
        # fast path: area-resize then crop
        nw, nh = int(round(cw * s)), int(round(ch * s))
        nw = max(nw, out_w); nh = max(nh, out_h)
        img = cv2.resize(cache_frame, (nw, nh), interpolation=cv2.INTER_AREA)
        px = cx * nw - out_w / 2 - dx; py = cy * nh - out_h / 2 - dy
        px = int(round(min(max(px, 0), nw - out_w))); py = int(round(min(max(py, 0), nh - out_h)))
        return img[py:py + out_h, px:px + out_w]
    # general affine path (pre-shrink for quality)
    pre = 1.0
    src = cache_frame
    if s < 0.8:
        pre = s / 0.95
        src = cv2.resize(cache_frame, (int(cw * pre), int(ch * pre)), interpolation=cv2.INTER_AREA)
    sc = s / pre
    sh_, sw_ = src.shape[:2]
    # clamp centre so the zoomed frame covers output when rot==0
    half_w = out_w / (2 * sc * sw_); half_h = out_h / (2 * sc * sh_)
    cxc = min(max(cx, half_w), 1 - half_w) if half_w < 0.5 else 0.5
    cyc = min(max(cy, half_h), 1 - half_h) if half_h < 0.5 else 0.5
    M = cv2.getRotationMatrix2D((cxc * sw_, cyc * sh_), rot, sc)
    M[0, 2] += out_w / 2 - cxc * sw_ + dx
    M[1, 2] += out_h / 2 - cyc * sh_ + dy
    return cv2.warpAffine(src, M, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

def shake_offsets(t, amp=8.0, rot_amp=0.4, seed=3):
    """Smooth pseudo-random handheld shake (px, px, deg)."""
    def n(f, ph):
        return (math.sin(2 * math.pi * f * t + ph) * 0.6 + math.sin(2 * math.pi * f * 2.3 * t + ph * 1.7) * 0.3 + math.sin(2 * math.pi * f * 5.1 * t + ph * 0.3) * 0.1)
    r = random.Random(seed)
    p = [r.random() * 6.28 for _ in range(3)]
    return amp * n(1.3, p[0]), amp * 0.8 * n(1.1, p[1]), rot_amp * n(0.9, p[2])

def motion_blur_samples(fn, t0, t1, n=7):
    """Average fn(t) over [t0,t1] (fn returns float frame) for transform motion blur."""
    acc = None
    for i in range(n):
        t = t0 + (t1 - t0) * (i + 0.5) / n
        f = fn(t)
        acc = f if acc is None else acc + f
    return acc / n

def radial_zoom_blur(img, strength=0.06, n=8, cx=W / 2, cy=H / 2):
    """Zoom blur by averaging scaled copies (strength = max relative scale)."""
    acc = img.copy()
    for i in range(1, n):
        s = 1 + strength * i / (n - 1)
        M = cv2.getRotationMatrix2D((cx, cy), 0, s)
        acc += cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / n

def directional_blur(img, dx_px, n=9):
    if abs(dx_px) < 1:
        return img
    acc = np.zeros_like(img)
    for i in range(n):
        off = dx_px * (i / (n - 1) - 0.5)
        M = np.float32([[1, 0, off], [0, 1, 0]])
        acc += cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT)
    return acc / n

# ----------------------------------------------------------------- red magazine elements
def letterbox(img, h_px, color=RED):
    h_px = int(round(max(0, h_px)))
    if h_px <= 0:
        return img
    img[:h_px] = color
    img[-h_px:] = color
    return img

def inset_on(bg, img, scale, cx=W / 2, cy=H / 2, border=0, border_col=WHITE):
    w, h = int(W * scale), int(H * scale)
    small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    x, y = int(cx - w / 2), int(cy - h / 2)
    if border > 0:
        bg[max(0, y - border):y + h + border, max(0, x - border):x + w + border] = border_col
    x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x + w), min(H, y + h)
    bg[y0:y1, x0:x1] = small[y0 - y:y1 - y, x0 - x:x1 - x]
    return bg

# ----------------------------------------------------------------- HUD
def _dash_circle(canvas, c, r, color, t, dots=48, dot_r=2, phase=0.0, arc=1.0, thick=-1):
    for i in range(dots):
        a = 2 * math.pi * (i / dots) + phase
        if (i / dots) > arc:
            continue
        x = int(c[0] + r * math.cos(a)); y = int(c[1] + r * math.sin(a))
        cv2.circle(canvas, (x, y), dot_r, color, thick, lineType=cv2.LINE_AA)

def hud_layer(target, t, label='TRK_01', coord=None, appear=1.0, seed=0, scale=1.0, sub_points=()):
    """Computer-vision HUD on a transparent canvas. target=(x,y) output px; t = seconds since HUD start.
    Returns (rgb float, alpha float)."""
    can = np.zeros((H, W, 4), np.uint8)
    cx, cy = int(target[0]), int(target[1])
    a = clamp01(appear)
    wcol = (255, 255, 255, int(245 * a)); rcol = (0, 18, 196, int(255 * a))  # BGR + A
    wdim = (255, 255, 255, int(170 * a))
    sc = 1.25 * scale
    r1 = int(64 * sc * (0.55 + 0.45 * ease_out_back(min(1, t / 0.18))))
    r2 = int(104 * sc * (0.5 + 0.5 * ease_out_cubic(min(1, t / 0.25))))
    # rotating dotted orbit + dashed outer ring + partial solid arc
    _dash_circle(can, (cx, cy), r1, wcol, t, dots=32, dot_r=3, phase=t * 1.8)
    for k in range(24):
        a0 = (k * 15 - t * 55) % 360
        cv2.ellipse(can, (cx, cy), (r2, r2), 0, a0, a0 + 7, wdim, 2, cv2.LINE_AA)
    cv2.ellipse(can, (cx, cy), (int(r2 * 1.22), int(r2 * 1.22)), 0, (t * 90) % 360, (t * 90) % 360 + 80, wcol, 2, cv2.LINE_AA)
    # corner brackets (CV bounding box)
    b = int(r1 * 0.78); L = int(r1 * 0.32)
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        px, py = cx + sx * b, cy + sy * b
        cv2.line(can, (px, py), (px - sx * L, py), wcol, 2, cv2.LINE_AA)
        cv2.line(can, (px, py), (px, py - sy * L), wcol, 2, cv2.LINE_AA)
    # centre red node + crosshair
    s = int(8 * sc)
    cv2.rectangle(can, (cx - s, cy - s), (cx + s, cy + s), rcol, -1, cv2.LINE_AA)
    cv2.line(can, (cx - int(r1 * 0.5), cy), (cx - s - 4, cy), wdim, 1, cv2.LINE_AA)
    cv2.line(can, (cx + s + 4, cy), (cx + int(r1 * 0.5), cy), wdim, 1, cv2.LINE_AA)
    # leader line (draw-on)
    grow = ease_out_cubic(min(1, max(0, (t - 0.04) / 0.18)))
    side = 1 if cx < W * 0.62 else -1
    up = -1 if cy > H * 0.3 else 1
    ex = cx + side * int(250 * sc); ey = cy + up * int(150 * sc)
    mx_, my_ = cx + side * int(120 * sc), ey
    pts = [(cx + side * int(r1 * 0.72), cy + up * int(r1 * 0.72)), (mx_, my_), (ex, ey)]
    seg_len = [math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])]
    Lg = sum(seg_len) * grow
    if Lg > 0:
        if Lg <= seg_len[0]:
            f = Lg / seg_len[0]
            p = (int(lerp(pts[0][0], pts[1][0], f)), int(lerp(pts[0][1], pts[1][1], f)))
            cv2.line(can, pts[0], p, wcol, 2, cv2.LINE_AA)
        else:
            cv2.line(can, pts[0], pts[1], wcol, 2, cv2.LINE_AA)
            f = (Lg - seg_len[0]) / seg_len[1]
            p = (int(lerp(pts[1][0], pts[2][0], f)), int(lerp(pts[1][1], pts[2][1], f)))
            cv2.line(can, pts[1], p, wcol, 2, cv2.LINE_AA)
    if grow >= 0.98:
        cv2.rectangle(can, (ex - 6, ey - 6), (ex + 6, ey + 6), rcol, -1, cv2.LINE_AA)
    # constellation of tracked sub points
    for k, sp in enumerate(sub_points):
        px_, py_ = int(sp[0]), int(sp[1])
        cv2.rectangle(can, (px_ - 4, py_ - 4), (px_ + 4, py_ + 4), wcol, 1, cv2.LINE_AA)
        cv2.line(can, (cx, cy), (px_, py_), wdim, 1, cv2.LINE_AA)
    rgb = can[..., :3][..., ::-1].astype(np.float32) / 255.0
    alpha = can[..., 3].astype(np.float32) / 255.0
    txt_a = clamp01((t - 0.16) / 0.1) * a
    if txt_a > 0 and coord is not None:
        lab = f"x: {int(coord[0])}  y: {int(coord[1])}"
        nchar = int(len(lab) * clamp01((t - 0.16) / 0.14))
        lab_vis = lab[:max(1, nchar)]
        tx = ex + (14 if side > 0 else -14)
        anchor = 'lb' if side > 0 else 'rb'
        rgb, alpha = _text_on_layer(rgb, alpha, label, 'mono_med', int(24 * scale), tx, ey - 6, anchor, txt_a)
        rgb, alpha = _text_on_layer(rgb, alpha, lab_vis, 'mono', int(24 * scale), tx, ey + 30, anchor, txt_a)
    return rgb, alpha

def _text_on_layer(rgb, alpha, text, font, size, x, y, anchor, a):
    m = text_mask(text, font, size, 0, 6) * a
    h, w = m.shape
    if anchor[0] == 'r':
        x -= w
    if anchor[1] == 'b':
        y -= h
    x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x + w), min(H, y + h)
    if x1 > x0 and y1 > y0:
        mm = m[y0 - y:y1 - y, x0 - x:x1 - x]
        rgb[y0:y1, x0:x1] = rgb[y0:y1, x0:x1] * (1 - mm[..., None]) + mm[..., None]
        alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], mm)
    return rgb, alpha

def apply_layer(img, rgb, alpha):
    a = alpha[..., None]
    return img * (1 - a) + rgb * a

# ----------------------------------------------------------------- diffusion: 柔光 (soft glow) and 散光 (light scatter)
def soft_glow(img, amount=0.55, radius=22, thresh=0.42, tint=(1.0, 0.93, 0.84), mist=0.10):
    """Pro-Mist style 柔光: highlights and upper mids bloom softly, micro-contrast eases, blacks lift a touch."""
    h, w = img.shape[:2]
    small = cv2.resize(img, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    L = luma(small)
    wgt = np.clip((L - thresh) / (1 - thresh), 0, 1) ** 1.3
    src = small * wgt[..., None]
    b1 = cv2.GaussianBlur(src, (0, 0), radius / 4)
    b2 = cv2.GaussianBlur(src, (0, 0), radius)
    glow = (b1 * 0.55 + b2 * 0.75) * np.array(tint, np.float32)
    glow = cv2.resize(glow, (w, h), interpolation=cv2.INTER_LINEAR)
    out = screen(img, np.clip(glow * amount, 0, 1))
    if mist > 0:
        soft = cv2.GaussianBlur(img, (0, 0), 2.2)
        out = out * (1 - mist * amount) + soft * (mist * amount)
        out = out * (1 - 0.035 * amount) + 0.035 * amount * np.array([0.93, 0.9, 0.88], np.float32)
    return np.clip(out, 0, 1).astype(np.float32)

@functools.lru_cache(maxsize=16)
def _streak_kernel(length, angle_deg, falloff=0.33):
    n = int(length) | 1
    k = np.zeros((n, n), np.float32)
    c = n // 2
    a = math.radians(angle_deg)
    for i in range(-c, c + 1):
        x = int(round(c + i * math.cos(a))); y = int(round(c - i * math.sin(a)))
        if 0 <= x < n and 0 <= y < n:
            k[y, x] = math.exp(-abs(i) / max(1.0, c * falloff))
    return k / k.sum()

def light_scatter(img, amount=0.6, length=0.30, rays=((0, 1.0, 1.0), (90, 0.4, 0.45), (45, 0.25, 0.3), (135, 0.25, 0.3)),
                  tint=(1.0, 0.95, 0.9), gain=3.2):
    """散光: light streaks / star rays from small specular highlights only (water glints, lamps, the sun).
    Large bright areas (sky, skylights, white walls) are excluded with a local top-hat + area test."""
    h, w = img.shape[:2]
    small = cv2.resize(img, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    L = luma(small)
    bg = cv2.GaussianBlur(L, (0, 0), 5)
    spec = np.clip((L - bg - 0.06) / 0.22, 0, 1) * np.clip((L - 0.70) / 0.25, 0, 1)
    big = cv2.GaussianBlur((L > 0.88).astype(np.float32), (0, 0), 9)
    spec *= np.clip(1 - (big - 0.2) / 0.3, 0, 1)
    src = small * (spec ** 1.5)[..., None]
    acc = np.zeros_like(src)
    for ang, rel_len, weight in rays:
        k = _streak_kernel(max(5, int(w / 4 * length * rel_len)), ang)
        acc += cv2.filter2D(src, -1, k, borderType=cv2.BORDER_CONSTANT) * weight
    acc += cv2.GaussianBlur(src, (0, 0), 2.5) * 0.8
    acc = acc * gain * np.array(tint, np.float32)
    acc = cv2.resize(acc, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(screen(img, np.clip(acc * amount, 0, 1)), 0, 1).astype(np.float32)

# ----------------------------------------------------------------- transitions / hits
def glitch(img, strength=1.0, seed=0):
    """CRT / chromatic-aberration hit: RGB split, a few displaced horizontal slices, scanlines."""
    rng = random.Random(seed)
    out = chroma_split(img, int(6 + 10 * strength))
    h = img.shape[0]
    for _ in range(int(3 + 4 * strength)):
        y0 = rng.randint(0, h - 40); hh = rng.randint(8, 60); dx = rng.randint(-40, 40)
        out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], int(dx * strength), axis=1)
    return scanlines(out, 0.10 + 0.08 * strength, 3)

def red_panel(img, x0, x1, label=None, label_alpha=1.0, edge=True, label_size=150):
    """Solid editorial-red panel covering columns [x0, x1) with a crisp white leading edge."""
    a, b = int(max(0, x0)), int(min(img.shape[1], x1))
    if b > a:
        img[:, a:b] = RED
        if edge:
            for e in (a, b - 3):
                if 0 < e < img.shape[1] - 3 and (e == a and a > 0 or e == b - 3 and b < img.shape[1]):
                    img[:, e:e + 3] = WHITE
        if label:
            cx = (a + b) // 2
            draw_text(img, label, 'anton', label_size, WHITE, cx, H // 2 + (18 if label_size > 400 else 0), 'mm', 6 if label_size > 400 else 3, alpha=label_alpha)
    return img

_crt_cache = {}
def crt_background(t, w=W, h=H, tint=(0.05, 0.035, 0.035)):
    """Dark CRT / waveform texture: scanlines, faint animated oscilloscope trace, vignette, flicker."""
    key = (w, h)
    if key not in _crt_cache:
        base = np.empty((h, w, 3), np.float32); base[:] = tint
        lines = np.ones(h, np.float32); lines[::3] = 0.55
        base *= lines[:, None, None]
        _crt_cache[key] = base * _vignette_mask(w, h, 0.55)[..., None]
    img = _crt_cache[key].copy()
    xs = np.arange(w, dtype=np.float32)
    for k, (amp, freq, ph, a) in enumerate([(60, 3.2, 1.7, 0.22), (28, 7.5, -2.3, 0.12)]):
        y = (h / 2 + amp * np.sin(xs / w * freq * 2 * math.pi + t * ph * 4) * np.sin(xs / w * math.pi)).astype(np.int32)
        for d in (-1, 0, 1):
            yy = np.clip(y + d, 0, h - 1)
            img[yy, xs.astype(np.int32)] += np.array([0.55, 0.06, 0.04], np.float32) * a * (1 - 0.4 * abs(d))
    img *= 0.96 + 0.04 * math.sin(t * 50)
    return np.clip(img, 0, 1)

# ----------------------------------------------------------------- 3D: camera helpers
def rot_matrix(yaw=0.0, pitch=0.0, roll=0.0):
    y, p, r = math.radians(yaw), math.radians(pitch), math.radians(roll)
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    Rz = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
    return Rz @ Rx @ Ry

def _project(pts3, f, cx, cy):
    z = np.maximum(pts3[:, 2], 1e-3)
    return np.stack([f * pts3[:, 0] / z + cx, f * pts3[:, 1] / z + cy], -1)

def _warp_bbox(src, Hm, out_w, out_h, corners_src, border=4):
    """warpPerspective limited to the projected bounding box; returns (patch, x0, y0)."""
    pc = cv2.perspectiveTransform(corners_src.reshape(-1, 1, 2).astype(np.float64), Hm).reshape(-1, 2)
    x0 = int(max(0, math.floor(pc[:, 0].min()) - border)); y0 = int(max(0, math.floor(pc[:, 1].min()) - border))
    x1 = int(min(out_w, math.ceil(pc[:, 0].max()) + border)); y1 = int(min(out_h, math.ceil(pc[:, 1].max()) + border))
    if x1 <= x0 or y1 <= y0:
        return None, 0, 0
    T = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], np.float64)
    patch = cv2.warpPerspective(src, T @ Hm, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return patch, x0, y0

# ----------------------------------------------------------------- 3D extruded text
def text3d_layer(text, font='anton', size=360, depth=70, yaw=0.0, pitch=0.0, roll=0.0, scale=1.0, pos=(W / 2, H / 2),
                 front=(1.0, 1.0, 1.0), side=(0.78, 0.76, 0.78), side_back=(0.32, 0.30, 0.34), tracking=6,
                 sweep=None, focal=1900.0, ss=2, layers=40, shadow=0.45, out_w=W, out_h=H, front_grad=0.18):
    """High-quality extruded 3D type. Returns (rgb, alpha) float32 at out_w x out_h.
    sweep: 0..1 position of a specular light band across the front face (None = off)."""
    m = text_mask(text, font, int(size * ss), int(tracking * ss), 24)
    mh, mw = m.shape
    Wc, Hc = out_w * ss, out_h * ss
    f = focal * ss; cx, cy = pos[0] * ss, pos[1] * ss
    R = rot_matrix(yaw, pitch, roll)
    Z0 = f                                   # z of the front face at scale 1 -> 1:1 pixels
    S = np.array([[scale, 0, -mw / 2 * scale], [0, scale, -mh / 2 * scale], [0, 0, 1]], np.float64)
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]], np.float64)
    corners = np.array([[0, 0], [mw, 0], [mw, mh], [0, mh]], np.float64)
    def H_at(d):
        M = np.column_stack([R[:, 0], R[:, 1], R[:, 2] * d + np.array([0, 0, Z0])])
        return K @ M @ S
    rgb = np.zeros((Hc, Wc, 3), np.float32); alpha = np.zeros((Hc, Wc), np.float32)
    dmax = depth * ss
    side = np.array(side, np.float32); side_back = np.array(side_back, np.float32)
    # extrusion: back to front
    for i in range(layers, 0, -1):
        d = dmax * i / layers
        patch, x0, y0 = _warp_bbox(m, H_at(d), Wc, Hc, corners)
        if patch is None:
            continue
        k = i / layers
        col = side * (1 - k) + side_back * k
        a = patch; h_, w_ = a.shape
        reg_rgb = rgb[y0:y0 + h_, x0:x0 + w_]; reg_a = alpha[y0:y0 + h_, x0:x0 + w_]
        reg_rgb *= (1 - a[..., None]); reg_rgb += a[..., None] * col
        np.maximum(reg_a, a, out=reg_a)
    # front face with lighting
    patch, x0, y0 = _warp_bbox(m, H_at(0.0), Wc, Hc, corners)
    if patch is not None:
        h_, w_ = patch.shape
        yy = np.linspace(0, 1, h_, dtype=np.float32)[:, None]
        base = np.array(front, np.float32)[None, None, :] * (1 - front_grad * yy)[..., None]
        # bevel rim light (top-left) and inner edge shade
        mb = cv2.GaussianBlur(patch, (0, 0), 1.6 * ss)
        gx = cv2.Sobel(mb, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(mb, cv2.CV_32F, 0, 1, ksize=3)
        rim = np.clip((gx * 0.6 + gy * 0.8) * 2.0, 0, 1) * patch
        shade = np.clip(-(gx * 0.6 + gy * 0.8) * 1.2, 0, 1) * patch
        col = base + rim[..., None] * 0.25 - shade[..., None] * 0.18
        if sweep is not None:
            xs = np.linspace(0, 1, w_, dtype=np.float32)[None, :]
            band = np.exp(-((xs + yy * 0.35 - (sweep * 1.6 - 0.3)) / 0.07) ** 2)
            col = col + band[..., None] * 0.55
        col = np.clip(col, 0, 1.2)
        a = patch
        reg_rgb = rgb[y0:y0 + h_, x0:x0 + w_]; reg_a = alpha[y0:y0 + h_, x0:x0 + w_]
        reg_rgb *= (1 - a[..., None]); reg_rgb += a[..., None] * col
        np.maximum(reg_a, a, out=reg_a)
    # contact / drop shadow (soft, offset down-right)
    sh = None
    if shadow > 0:
        sh = cv2.GaussianBlur(alpha, (0, 0), 14 * ss)
        sh = np.roll(np.roll(sh, int(18 * ss), 0), int(10 * ss), 1) * shadow
    # downsample (supersampling AA)
    rgb_o = cv2.resize(rgb, (out_w, out_h), interpolation=cv2.INTER_AREA)
    a_o = cv2.resize(alpha, (out_w, out_h), interpolation=cv2.INTER_AREA)
    sh_o = cv2.resize(sh, (out_w, out_h), interpolation=cv2.INTER_AREA) if sh is not None else None
    # un-premultiply colour where alpha>0
    rgb_o = np.where(a_o[..., None] > 1e-4, rgb_o / np.maximum(a_o[..., None], 1e-4), 0)
    return np.clip(rgb_o, 0, 1).astype(np.float32), np.clip(a_o, 0, 1).astype(np.float32), sh_o

def composite_text3d(img, rgb, alpha, sh=None):
    out = img
    if sh is not None:
        out = out * (1 - np.clip(sh, 0, 0.85)[..., None])
    return out * (1 - alpha[..., None]) + rgb * alpha[..., None]

# ----------------------------------------------------------------- 3D transitions (cube / flip / swing)
def _face_warp(img, quad, Wc, Hc):
    src = np.float32([[0, 0], [img.shape[1], 0], [img.shape[1], img.shape[0]], [0, img.shape[0]]])
    Hm = cv2.getPerspectiveTransform(src, np.float32(quad))
    patch, x0, y0 = _warp_bbox(img, Hm.astype(np.float64), Wc, Hc, src.astype(np.float64), border=2)
    m = np.ones(img.shape[:2], np.float32)
    mpatch, _, _ = _warp_bbox(m, Hm.astype(np.float64), Wc, Hc, src.astype(np.float64), border=2)
    return patch, mpatch, x0, y0

def transition3d(A, B, u, kind='cube', direction=1, ss=2, samples=5, shutter=0.85, du=0.05, bg=(0.012, 0.012, 0.014)):
    """Render a 3D transition frame at progress u (0..1) between full frames A and B (float32 1920x1080).
    Spatial supersampling (ss) + temporal sub-samples (motion blur)."""
    Wc, Hc = W * ss, H * ss
    f = 1.0 * W * ss          # focal (px) ~ 53 deg horizontal FOV
    Aup = cv2.resize(A, (Wc, Hc), interpolation=cv2.INTER_LINEAR); Bup = cv2.resize(B, (Wc, Hc), interpolation=cv2.INTER_LINEAR)
    a, b = Wc / 2, Hc / 2
    em = ease_in_out_cubic(clamp01(u))
    sm = cv2.resize(A * (1 - em) + B * em, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
    backdrop = cv2.resize(cv2.GaussianBlur(sm, (0, 0), 6), (Wc, Hc), interpolation=cv2.INTER_LINEAR) * 0.32
    backdrop = backdrop * _vignette_mask(Wc, Hc, 0.6)[..., None]
    acc = np.zeros((Hc, Wc, 3), np.float32)
    offs = np.linspace(-0.5, 0.5, samples) * du * shutter if samples > 1 else [0.0]
    for o in offs:
        uu = clamp01(u + o); e = ease_in_out_cubic(uu)
        canvas = backdrop.copy()
        faces = []
        if kind == 'cube':
            pull = 0.42 * Wc * math.sin(math.pi * e) ** 1.2
            R = rot_matrix(yaw=direction * 90.0 * e)
            C = np.array([0, 0, f + a + pull])
            fa = np.array([[-a, -b, -a], [a, -b, -a], [a, b, -a], [-a, b, -a]])                  # front (A)
            if direction > 0:
                fb = np.array([[a, -b, -a], [a, -b, a], [a, b, a], [a, b, -a]])                 # right side (B)
            else:
                fb = np.array([[-a, -b, a], [-a, -b, -a], [-a, b, -a], [-a, b, a]])             # left side (B)
            for img, quad, nrm in ((Aup, fa, np.array([0, 0, -1.0])), (Bup, fb, np.array([direction * 1.0, 0, 0]))):
                P = (R @ quad.T).T + C
                n_w = R @ nrm
                cen = P.mean(0)
                facing = -np.dot(n_w, cen / np.linalg.norm(cen))
                if facing <= 0.01:
                    continue
                faces.append((cen[2], img, _project(P, f, Wc / 2, Hc / 2), 0.30 + 0.70 * facing))
        elif kind == 'flip':
            pull = 0.30 * Wc * math.sin(math.pi * e) ** 1.2
            R = rot_matrix(yaw=direction * 180.0 * e)
            C = np.array([0, 0, f + pull])
            front = np.array([[-a, -b, 0], [a, -b, 0], [a, b, 0], [-a, b, 0]])
            back = np.array([[a, -b, 0], [-a, -b, 0], [-a, b, 0], [a, b, 0]])      # mirrored so B reads correctly
            for img, quad, nrm in ((Aup, front, np.array([0, 0, -1.0])), (Bup, back, np.array([0, 0, 1.0]))):
                P = (R @ quad.T).T + C
                n_w = R @ nrm
                facing = -np.dot(n_w, P.mean(0) / np.linalg.norm(P.mean(0)))
                if facing <= 0.01:
                    continue
                faces.append((P.mean(0)[2], img, _project(P, f, Wc / 2, Hc / 2), 0.35 + 0.65 * facing))
        elif kind == 'swing':
            # B sits behind; A swings open on its left (dir=1) or right hinge like a door
            canvas[:] = Bup * (0.55 + 0.45 * e)
            hinge = -a if direction > 0 else a
            ang = -direction * 105.0 * e
            R = rot_matrix(yaw=ang)
            quad = np.array([[-a, -b, 0], [a, -b, 0], [a, b, 0], [-a, b, 0]], np.float64)
            q = quad.copy(); q[:, 0] -= hinge
            P = (R @ q.T).T; P[:, 0] += hinge; P += np.array([0, 0, f])
            n_w = R @ np.array([0, 0, -1.0])
            facing = -np.dot(n_w, P.mean(0) / np.linalg.norm(P.mean(0)))
            if facing > 0.01:
                faces.append((P.mean(0)[2], Aup, _project(P, f, Wc / 2, Hc / 2), 0.25 + 0.75 * facing))
        for _, img, quad, shade in sorted(faces, key=lambda t: -t[0]):     # far to near
            patch, mpatch, x0, y0 = _face_warp(img, quad, Wc, Hc)
            if patch is None:
                continue
            h_, w_ = mpatch.shape
            reg = canvas[y0:y0 + h_, x0:x0 + w_]
            reg *= (1 - mpatch[..., None]); reg += patch * shade * mpatch[..., None]
        acc += canvas
    acc /= len(offs)
    return cv2.resize(acc, (W, H), interpolation=cv2.INTER_AREA)

# ----------------------------------------------------------------- cutout helpers
def sticker(img_rgb, mask, outline=6, color=WHITE, shadow=0.5, shadow_off=(14, 10)):
    """Cut-out subject with a clean white outline and soft drop shadow. Returns (rgb, alpha, shadow_alpha)."""
    m = np.clip(mask, 0, 1).astype(np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * outline + 1, 2 * outline + 1))
    dil = cv2.GaussianBlur(cv2.dilate(m, k), (0, 0), 1.2)
    rgb = img_rgb * m[..., None] + np.asarray(color, np.float32)[None, None] * (dil - m)[..., None] * (dil > m)[..., None]
    alpha = np.maximum(m, dil)
    sh = cv2.GaussianBlur(alpha, (0, 0), 12)
    sh = np.roll(np.roll(sh, shadow_off[1], 0), shadow_off[0], 1) * shadow
    return rgb, alpha, sh

def sky_mask(img):
    """Rough sky matte: bright, low-texture, blue/cyan or near-white regions connected to the top edge."""
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor((np.clip(small, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    hh, ss_, vv = hsv[..., 0] * 2, hsv[..., 1] / 255, hsv[..., 2] / 255
    tex = cv2.GaussianBlur(np.abs(cv2.Laplacian(vv, cv2.CV_32F)), (0, 0), 2)
    cand = (vv > 0.45) & (tex < 0.06) & ((((hh > 165) & (hh < 245)) & (ss_ > 0.12)) | (ss_ < 0.12) & (vv > 0.75))
    cand = cand.astype(np.uint8)
    n, lab = cv2.connectedComponents(cand)
    top = set(np.unique(lab[0:3, :])) - {0}
    m = np.isin(lab, list(top)).astype(np.float32)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.resize(cv2.GaussianBlur(m, (0, 0), 1.5), (W, H), interpolation=cv2.INTER_LINEAR)
    return np.clip(m, 0, 1)


def label(img, text, sub=None, t=1.0, x=72, y=H - 118, idx=None):
    """Editorial location label: thin red rule that draws on, typed caps (Inter) + optional small index/sub line."""
    a = clamp01(t / 0.12)
    rule = int(150 * ease_out_cubic(clamp01(t / 0.18)))
    if rule > 0:
        img[y - 14:y - 10, x:x + rule] = img[y - 14:y - 10, x:x + rule] * (1 - a) + RED * a
    n = int(len(text) * clamp01((t - 0.06) / 0.22))
    if n > 0:
        draw_text(img, text[:n], 'inter_bold', 30, WHITE, x, y, 'lt', 6, alpha=a)
    if sub and t > 0.2:
        draw_text(img, sub, 'mono', 20, WHITE, x, y + 44, 'lt', 2, alpha=clamp01((t - 0.2) / 0.15) * 0.85)
    if idx:
        draw_text(img, idx, 'mono_med', 20, RED, x + rule + 14 if rule else x, y - 24, 'lt', 2, alpha=a)
    return img
