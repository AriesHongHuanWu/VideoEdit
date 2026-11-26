#!/usr/bin/env python3
"""Colour pipeline: per-shot white balance / exposure / levels normalisation + unified film look, baked to a 3D LUT.

All values are display-referred Rec.709-ish gamma RGB in [0,1].
"""
import numpy as np

GAMMA = 2.2

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)

def luma(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722

def rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.max(rgb, -1); mn = np.min(rgb, -1); d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rm = m & (mx == r); gm = m & (mx == g) & ~rm; bm = m & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = ((b - r)[gm] / d[gm]) + 2
    h[bm] = ((r - g)[bm] / d[bm]) + 4
    h = h / 6.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h, s, mx

def hsv_to_rgb(h, s, v):
    h6 = (h % 1.0) * 6
    i = np.floor(h6).astype(int) % 6
    f = h6 - np.floor(h6)
    p = v * (1 - s); q = v * (1 - s * f); t = v * (1 - s * (1 - f))
    out = np.zeros(h.shape + (3,), dtype=np.float64)
    for k, (a, b_, c) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        mk = i == k
        out[..., 0][mk] = a[mk]; out[..., 1][mk] = b_[mk]; out[..., 2][mk] = c[mk]
    return out

def tone_curve(x):
    """Filmic S: pressed blacks, firmer mids, soft highlight shoulder."""
    xs = np.array([0.0, 0.03, 0.08, 0.18, 0.40, 0.60, 0.78, 0.90, 1.0])
    ys = np.array([0.0, 0.007, 0.040, 0.140, 0.405, 0.655, 0.835, 0.935, 0.982])
    return np.interp(x, xs, ys)

def creative_look(rgb, strength=1.0):
    """Unified 'one camera' look: film density, filmic contrast, teal-cyan skies & shadows,
    warm amber highlights, olive greens, rich warm tones and reds."""
    x = np.clip(rgb, 0, 1)
    # --- film dye density: saturated colours get slightly darker / denser
    mx = x.max(-1); mn = x.min(-1); sat0 = (mx - mn) / np.maximum(mx, 1e-4)
    x = x * (1 - 0.10 * (sat0 ** 1.5))[..., None]
    L0 = luma(x)
    Lc = tone_curve(L0)
    ratio = np.where(L0 > 1e-5, Lc / np.maximum(L0, 1e-5), 1.0)[..., None]
    y = x * ratio
    y = 0.8 * y + 0.2 * tone_curve(x)
    y = np.clip(y, 0, 1)
    L = luma(y)
    h, s, v = rgb_to_hsv(y)
    hd = h * 360
    # skies / blues -> teal-cyan, a touch deeper and richer
    wb = smoothstep(170, 195, hd) * (1 - smoothstep(250, 280, hd))
    hd = hd + wb * (193 - hd) * 0.6
    s = s * (1 + 0.14 * wb)
    v = v * (1 - 0.06 * wb * smoothstep(0.4, 0.9, v))
    # cyans/water: keep teal, slightly richer
    wc = smoothstep(150, 170, hd) * (1 - smoothstep(190, 205, hd))
    s = s * (1 + 0.08 * wc)
    # greens -> olive, calmer
    wg = smoothstep(65, 90, hd) * (1 - smoothstep(145, 170, hd))
    hd = hd - wg * 12
    s = s * (1 - 0.22 * wg)
    # oranges / skin / brick: warm and rich (pull slightly toward orange)
    wo = smoothstep(4, 16, hd) * (1 - smoothstep(44, 60, hd))
    hd = hd + wo * (26 - hd) * 0.15
    s = s * (1 + 0.10 * wo)
    # yellows (tungsten casts) -> calmer
    wy = smoothstep(45, 55, hd) * (1 - smoothstep(66, 80, hd))
    s = s * (1 - 0.18 * wy)
    # reds richer
    wr = np.clip(1 - smoothstep(6, 18, hd) + smoothstep(342, 354, hd), 0, 1)
    s = s * (1 + 0.14 * wr)
    # film saturation curve + vibrance
    sat_curve = 1.08 - 0.30 * (1 - smoothstep(0.02, 0.20, L)) - 0.30 * smoothstep(0.80, 1.0, L)
    s = s * sat_curve
    s = np.clip(s + 0.14 * s * (1 - s) * smoothstep(0.08, 0.3, L), 0, 1)
    y = hsv_to_rgb(hd / 360.0, s, v)
    L = luma(y)
    # split toning: teal shadows, warm amber highlights, gentle warm mids
    ws = (1 - smoothstep(0.03, 0.45, L)) * smoothstep(0.0, 0.035, L)
    wh = smoothstep(0.48, 0.95, L)
    wm = smoothstep(0.22, 0.48, L) * (1 - smoothstep(0.58, 0.85, L))
    y = y + ws[..., None] * np.array([-0.040, 0.006, 0.040])
    y = y + wh[..., None] * np.array([0.042, 0.014, -0.050])
    y = y + wm[..., None] * np.array([0.012, 0.003, -0.012])
    y = np.clip(y, 0, 1)
    return rgb * (1 - strength) + y * strength

def normalise(rgb, p):
    """Per-shot primary correction. p: gains (linear), exposure (linear), black / white (linear levels)."""
    lin = np.power(np.clip(rgb, 0, 1), GAMMA)
    g = np.array(p.get('gains', (1, 1, 1))) * p.get('exposure', 1.0)
    lin = lin * g
    b = p.get('black', 0.0); w = p.get('white', 1.0)
    lin = (lin - b) / max(1e-4, (w - b))
    lin = np.clip(lin, 0, None)
    over = lin > 0.8
    lin = np.where(over, 0.8 + 0.2 * np.tanh((lin - 0.8) / 0.2), lin)
    return np.power(np.clip(lin, 0, 1), 1 / GAMMA)

def build_lut(p, n=33, look_strength=1.0):
    grid = np.linspace(0, 1, n)
    # .cube order: R fastest
    b, g, r = np.meshgrid(grid, grid, grid, indexing='ij')
    rgb = np.stack([r, g, b], -1).reshape(-1, 3)
    out = creative_look(normalise(rgb, p), look_strength)
    return out.reshape(n, n, n, 3), n

def write_cube(path, lut, n, title='look'):
    with open(path, 'w') as f:
        f.write(f'TITLE "{title}"\nLUT_3D_SIZE {n}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        flat = lut.reshape(-1, 3)
        for v in flat:
            f.write(f'{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n')

def estimate_params(frames_rgb, wb_strength=None, target_mid=0.42, exp_strength=0.65):
    """Gray-world on near-neutral mid-tones (linear light). Strong casts (tungsten interiors) are corrected
    harder than mild daylight casts, which keeps golden light golden but removes muddy yellow-green."""
    acc = []; lums = []
    for fr in frames_rgb:
        lin = np.power(np.clip(fr, 0, 1), GAMMA)
        L = luma(fr)
        mx = fr.max(-1); mn = fr.min(-1)
        sat = (mx - mn) / np.maximum(mx, 1e-4)
        m = (L > 0.10) & (L < 0.88) & (sat < 0.40)
        if m.sum() > 500:
            acc.append(np.median(lin[m], 0) * 0.5 + lin[m].mean(0) * 0.5)
        lums.append(L.reshape(-1))
    gains = np.array([1.0, 1.0, 1.0])
    if acc:
        mean = np.mean(acc, 0)
        raw = (mean.mean() / np.maximum(mean, 1e-4)); raw = raw / raw[1]
        cast = float(np.abs(np.log(raw)).max())
        k = wb_strength if wb_strength is not None else float(np.clip(0.45 + cast * 2.2, 0.45, 0.85))
        gains = np.clip(1 + (raw - 1) * k, 0.78, 1.30)
    allL = np.concatenate(lums)
    med = float(np.median(allL))
    e_lin = 1.0
    if med > 1e-3:
        e_gamma = (target_mid / med) ** exp_strength
        e_lin = float(np.clip(e_gamma ** GAMMA, 0.6, 2.6))
    p1 = float(np.percentile(allL, 0.7))
    black = max(0.0, (p1 ** GAMMA) * 0.7 - 0.0004)
    p995 = float(np.percentile(allL, 99.6))
    white = 1.0
    if p995 < 0.92:
        white = max(0.72, (p995 / 0.95) ** GAMMA)
    return dict(gains=tuple(float(x) for x in gains), exposure=float(e_lin), black=float(black), white=float(white), median=med)

def apply_lut_np(img, lut, n):
    """Trilinear LUT on float RGB image (for previews/tests)."""
    x = np.clip(img, 0, 1) * (n - 1)
    i0 = np.floor(x).astype(int); i1 = np.minimum(i0 + 1, n - 1); f = x - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]; r1, g1, b1 = i1[..., 0], i1[..., 1], i1[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    def L(b, g, r): return lut[b, g, r]
    c000 = L(b0, g0, r0); c100 = L(b0, g0, r1); c010 = L(b0, g1, r0); c110 = L(b0, g1, r1)
    c001 = L(b1, g0, r0); c101 = L(b1, g0, r1); c011 = L(b1, g1, r0); c111 = L(b1, g1, r1)
    c00 = c000 * (1 - fr) + c100 * fr; c10 = c010 * (1 - fr) + c110 * fr
    c01 = c001 * (1 - fr) + c101 * fr; c11 = c011 * (1 - fr) + c111 * fr
    c0 = c00 * (1 - fg) + c10 * fg; c1 = c01 * (1 - fg) + c11 * fg
    return c0 * (1 - fb) + c1 * fb
