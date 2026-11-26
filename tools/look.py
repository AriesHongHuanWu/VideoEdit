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
    """Filmic S: slightly pressed blacks, stronger mid contrast, soft highlight roll-off."""
    xs = np.array([0.0, 0.03, 0.10, 0.22, 0.42, 0.62, 0.80, 0.92, 1.0])
    ys = np.array([0.0, 0.013, 0.074, 0.192, 0.425, 0.66, 0.835, 0.932, 0.975])
    return np.interp(x, xs, ys)

def creative_look(rgb, strength=1.0):
    """Unified look: contrast, warm highlights, teal shadows/sky, film saturation."""
    x = np.clip(rgb, 0, 1)
    L0 = luma(x)
    # contrast on luminance, keep chroma ratio (avoid hue shifts), then blend a bit of per-channel curve for punch
    Lc = tone_curve(L0)
    ratio = np.where(L0 > 1e-5, Lc / np.maximum(L0, 1e-5), 1.0)[..., None]
    y = x * ratio
    y = 0.75 * y + 0.25 * tone_curve(x)
    y = np.clip(y, 0, 1)
    L = luma(y)
    # hue work
    h, s, v = rgb_to_hsv(y)
    hd = h * 360
    # blues / sky (190-260) -> toward teal-cyan 196, slightly richer
    wb = smoothstep(175, 200, hd) * (1 - smoothstep(245, 275, hd))
    hd = hd + wb * (196 - hd) * 0.45
    s = s * (1 + 0.10 * wb)
    # greens (75-165) -> slightly warmer/olive and calmer
    wg = smoothstep(70, 95, hd) * (1 - smoothstep(150, 175, hd))
    hd = hd - wg * 10
    s = s * (1 - 0.18 * wg)
    # oranges / skin (10-50): keep hue, gentle richness
    wo = smoothstep(5, 18, hd) * (1 - smoothstep(42, 58, hd))
    s = s * (1 + 0.06 * wo)
    # reds richer
    wr = 1 - smoothstep(8, 20, hd) + smoothstep(340, 352, hd)
    wr = np.clip(wr, 0, 1)
    s = s * (1 + 0.10 * wr)
    # film saturation: less in deep shadows & near-white
    sat_curve = 1.10 - 0.28 * (1 - smoothstep(0.02, 0.20, L)) - 0.25 * smoothstep(0.82, 1.0, L)
    s = s * sat_curve
    # vibrance: lift low-saturation colours more than already-saturated ones
    s = np.clip(s + 0.16 * s * (1 - s) * smoothstep(0.08, 0.3, L), 0, 1)
    y = hsv_to_rgb(hd / 360.0, s, v)
    L = luma(y)
    # split toning (additive, luminance weighted)
    ws = (1 - smoothstep(0.04, 0.42, L)) * smoothstep(0.0, 0.04, L)
    wh = smoothstep(0.50, 0.92, L)
    y = y + ws[..., None] * np.array([-0.030, 0.006, 0.030])
    y = y + wh[..., None] * np.array([0.032, 0.010, -0.040])
    # gentle overall warmth in mids
    wm = smoothstep(0.2, 0.5, L) * (1 - smoothstep(0.6, 0.9, L))
    y = y + wm[..., None] * np.array([0.010, 0.002, -0.010])
    y = np.clip(y, 0, 1)
    return rgb * (1 - strength) + y * strength

def normalise(rgb, p):
    """Per-shot correction. p: dict(gains=(r,g,b) linear, exposure=linear mult, black=lin black level, white=lin white)."""
    lin = np.power(np.clip(rgb, 0, 1), GAMMA)
    g = np.array(p.get('gains', (1, 1, 1))) * p.get('exposure', 1.0)
    lin = lin * g
    # levels in linear: subtract part of the black floor, stretch whites gently
    b = p.get('black', 0.0); w = p.get('white', 1.0)
    lin = (lin - b) / max(1e-4, (w - b))
    lin = np.clip(lin, 0, None)
    # soft clip highlights that exceed 1 after gains
    over = lin > 0.85
    lin = np.where(over, 0.85 + 0.15 * np.tanh((lin - 0.85) / 0.15), lin)
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

def estimate_params(frames_rgb, wb_strength=0.6, target_mid=0.42, exp_strength=0.5):
    """frames_rgb: list of float RGB [0,1] (gamma) sample frames from the shot.
    Gray-world on mid-tones in linear light; partial correction to keep ambience."""
    acc = []; lums = []
    for fr in frames_rgb:
        lin = np.power(np.clip(fr, 0, 1), GAMMA)
        L = luma(fr)
        m = (L > 0.12) & (L < 0.85)
        # exclude strongly saturated pixels (sky/foliage/neon) from gray estimate
        mx = fr.max(-1); mn = fr.min(-1)
        sat = (mx - mn) / np.maximum(mx, 1e-4)
        m &= sat < 0.45
        if m.sum() > 500:
            acc.append(lin[m].mean(0))
        lums.append(L.reshape(-1))
    if acc:
        mean = np.mean(acc, 0)
        gray = mean.mean()
        gains = gray / np.maximum(mean, 1e-4)
        gains = gains / gains[1]
        gains = 1 + (gains - 1) * wb_strength
        gains = np.clip(gains, 0.80, 1.25)
    else:
        gains = np.array([1.0, 1.0, 1.0])
    allL = np.concatenate(lums)
    med = float(np.median(allL))
    # exposure: move median toward target (in gamma domain), partial
    if med > 1e-3:
        e_gamma = (target_mid / med) ** exp_strength
        e_lin = np.clip(e_gamma ** GAMMA, 0.65, 2.4)
    else:
        e_lin = 1.0
    p1 = float(np.percentile(allL, 0.8));
    black = max(0.0, (p1 ** GAMMA) * 0.6 - 0.0005)
    p995 = float(np.percentile(allL, 99.7))
    white = 1.0
    if p995 < 0.9:   # dull highlights -> stretch a little
        white = max(0.75, (p995 / 0.93) ** GAMMA)
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
