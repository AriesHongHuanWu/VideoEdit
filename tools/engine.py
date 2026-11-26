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
            g = cv2.GaussianBlur(g, (0, 0), 0.75)
            g /= g.std() + 1e-6
            c = rng.standard_normal((h // 2, w // 2, 3)).astype(np.float32)
            c = cv2.resize(cv2.GaussianBlur(c, (0, 0), 0.8), (w, h))
            c /= c.std() + 1e-6
            self.bank.append((g.astype(np.float16), c.astype(np.float16)))

    def apply(self, img, k, amount=0.032, chroma=0.25):
        g, c = self.bank[k % len(self.bank)]
        L = luma(img)
        resp = (0.35 + 1.6 * L * (1 - L) * 2.0)[..., None]   # more grain in mids
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
