#!/usr/bin/env python3
"""Complete 2D transitions that straddle a cut (no 3D, no black backgrounds).

Every transition receives the fully composed outgoing frame A and incoming frame B at the same output time,
the progress u in [0, 1) across the window [cut - n_out, cut + n_in), uc = n_out / (n_out + n_in) (the beat,
where B becomes dominant) and du = one frame in u units.

Motion blur is analytic and cheap:
  * layers that move along x / y are box-blurred along the motion with length = displacement x 180-degree shutter;
  * moving wipes over static pictures use soft mask edges whose width is the edge displacement x shutter;
  * the zoom-through uses a radial blur matched to the per-frame scale change.
"""
import math
import numpy as np
import cv2
import engine as E

W, H = E.W, E.H
SHUT = 0.5                     # 180-degree shutter


def c01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else float(x))


def prog(u, uc, p_in=4.0, p_out=4.0):
    """Two-sided ease through the cut: accelerates into uc (value 0.5) and decelerates after it."""
    if u <= uc:
        return 0.5 * (c01(u / uc) ** p_in) if uc > 1e-6 else 0.5
    if uc >= 1 - 1e-6:
        return 1.0
    return 0.5 + 0.5 * (1 - (1 - c01((u - uc) / (1 - uc))) ** p_out)


def per_frame(fn, u, du):
    """Change of fn over one frame centred on u."""
    return fn(min(1.0, u + du / 2)) - fn(max(0.0, u - du / 2))


def box(img, L, axis):
    L = int(round(abs(L)))
    if L < 2:
        return img
    L = min(L, 1200)
    return cv2.blur(img, (L, 1) if axis == 'x' else (1, L), borderType=cv2.BORDER_REPLICATE)


def ramp(xs, edge, L, rising=True):
    """Soft step of width L at `edge` (1 above the edge when rising)."""
    L = max(1.0, L)
    v = (xs - edge) / L + 0.5
    return np.clip(v if rising else -v + 1.0, 0, 1)


def scale_about(img, s, cx, cy):
    if abs(s - 1) < 1e-4:
        return img
    M = cv2.getRotationMatrix2D((cx, cy), 0, s)
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def layer_over(base, layer, alpha, L, axis):
    """Composite a moving layer with motion blur: blur premultiplied colour and alpha along the motion."""
    a = alpha[..., None] if alpha.ndim == 2 else alpha
    pm = layer * a
    if L >= 2:
        pm = box(pm, L, axis)
        a = box(np.ascontiguousarray(a[..., 0]), L, axis)[..., None]
    return base * (1 - a) + pm


# ------------------------------------------------------------------ push: B shoves A out of frame, red seam
def push(A, B, u, uc, du, dir=1, axis='x', seam=14, p=4.0, blur=1.0, seam_col=None):
    f = lambda x: prog(x, uc, p, p)
    D = W if axis == 'x' else H
    o = int(round(f(u) * D))
    out = np.empty_like(A)
    if axis == 'x':
        if dir > 0:                              # content travels left, B enters from the right
            out[:, :W - o] = A[:, o:]; out[:, W - o:] = B[:, :o]; s = W - o
        else:                                    # content travels right, B enters from the left
            out[:, o:] = A[:, :W - o]; out[:, :o] = B[:, W - o:]; s = o
        if seam and 0 < s < W:
            out[:, max(0, s - seam // 2):min(W, s + seam // 2)] = E.RED if seam_col is None else seam_col
    else:
        if dir > 0:                              # content travels up, B enters from the bottom
            out[:H - o] = A[o:]; out[H - o:] = B[:o]; s = H - o
        else:                                    # content travels down (tilt up), B enters from the top
            out[o:] = A[:H - o]; out[:o] = B[H - o:]; s = o
        if seam and 0 < s < H:
            out[max(0, s - seam // 2):min(H, s + seam // 2)] = E.RED if seam_col is None else seam_col
    L = abs(per_frame(f, u, du)) * D * SHUT * blur
    return box(out, L, axis)


# ------------------------------------------------------------------ whip: camera whip pan between the two shots
def whip(A, B, u, uc, du, dir=1, axis='x', blur=1.7, p=5.0):
    out = push(A, B, u, uc, du, dir=dir, axis=axis, seam=0, p=p, blur=blur)
    # a touch of exposure lift at the fastest point, like a real whip smear
    k = math.exp(-((u - uc) / 0.12) ** 2)
    return np.clip(out * (1 + 0.10 * k) + 0.02 * k, 0, 1)


# ------------------------------------------------------------------ zoom-through: punch into A, land out of B
def zoom(A, B, u, uc, du, z=0.65, ca=(W / 2, H / 2), cb=(W / 2, H / 2), flash=0.22):
    def sA(x):
        return 1 + z * (c01(x / uc) ** 3.2) if uc > 1e-6 else 1 + z
    def sB(x):
        return 1 + z * ((1 - c01((x - uc) / (1 - uc))) ** 3.2) if uc < 1 - 1e-6 else 1.0
    if u < uc:
        s = sA(u); ds = abs(per_frame(sA, u, du)); img, (cx, cy) = A, ca
    else:
        s = sB(u); ds = abs(per_frame(sB, u, du)); img, (cx, cy) = B, cb
    out = scale_about(img, s, cx, cy)
    rel = ds / s * SHUT * 1.6
    if rel > 0.004:
        out = E.radial_zoom_blur(out, strength=min(0.45, rel), n=int(min(13, 5 + rel * 60)), cx=cx, cy=cy)
    if flash > 0 and abs(u - uc) < du * 1.01:
        out = E.white_mix(out, flash * (1.0 if u >= uc else 0.5))
    return out


# ------------------------------------------------------------------ red bar wipe: a red editorial bar crosses the frame
def redbar(A, B, u, uc, du, dir=1, bw=0.24, label=None, label_size=110, edge=3, p=2.2):
    BW = bw * W
    f = lambda x: prog(x, uc, p, p)
    c = -BW / 2 + (W + BW) * f(u)
    L = max(1.0, abs(per_frame(f, u, du)) * (W + BW) * SHUT)
    xs = np.arange(W, dtype=np.float32)
    if dir < 0:
        xs = W - 1 - xs
    lead, trail = c + BW / 2, c - BW / 2
    mA = ramp(xs, lead, L, True)                  # A ahead of the bar
    mB = ramp(xs, trail, L, False)                # B behind it
    mR = np.clip(1 - mA - mB, 0, 1)
    out = A * mA[None, :, None] + B * mB[None, :, None] + E.RED[None, None, :] * mR[None, :, None]
    if edge:
        for e in (lead, trail):                   # crisp white rules on both bar edges (motion-blurred)
            w = np.clip(1 - np.abs(xs - e) / max(edge, L * 0.5), 0, 1) * min(1.0, edge / max(edge, L * 0.5) * 1.6)
            out = out * (1 - w[None, :, None]) + w[None, :, None]
    if label:
        lay = np.zeros((H, W, 3), np.float32)
        E.draw_text(lay, label, 'anton', label_size, E.WHITE, int(c if dir > 0 else W - 1 - c), H // 2, 'mm', 4)
        al = lay.max(-1)
        out = layer_over(out, lay, al * mR.max() if mR.max() > 0 else al, L, 'x')
    return np.clip(out, 0, 1)


# ------------------------------------------------------------------ slice: B arrives as staggered vertical strips
def slices(A, B, u, uc, du, n=5, d=0.55, order=None, gutter=8, a_push=0.035, axis='v'):
    order = order or ([2, 1, 3, 0, 4] if n == 5 else list(range(n)))
    out = scale_about(A, 1 + a_push * E.ease_in_cubic(u), W / 2, H / 2)
    sw = W / n
    for rank, i in enumerate(order):
        s_i = rank * (1 - d) / max(1, n - 1)
        x0 = int(round(i * sw)); x1 = int(round((i + 1) * sw))
        k = (u - s_i) / d
        if k <= 0:
            continue
        e = lambda kk: 1 - (1 - c01(kk)) ** 4
        dirn = -1 if i % 2 == 0 else 1
        off = (1 - e(k)) * H * dirn
        L = abs(e(k + du / d / 2) - e(k - du / d / 2)) * H * SHUT
        o = int(round(off))
        strip = np.zeros((H, x1 - x0, 3), np.float32); al = np.zeros((H, x1 - x0), np.float32)
        ys0, ys1 = max(0, o), min(H, H + o)
        if ys1 > ys0:
            strip[ys0:ys1] = B[ys0 - o:ys1 - o, x0:x1]; al[ys0:ys1] = 1
        out[:, x0:x1] = layer_over(out[:, x0:x1], strip, al, L, 'y')
    if gutter:
        g = min(c01(u / 0.10), c01((1 - u) / 0.16))
        if g > 0:
            for i in range(1, n):
                x = int(round(i * sw))
                out[:, x - gutter // 2:x + gutter // 2] = out[:, x - gutter // 2:x + gutter // 2] * (1 - g) + E.RED * g
    return out


# ------------------------------------------------------------------ doors: A splits on a red rule and slides apart over B
def doors(A, B, u, uc, du, axis='v', z=0.10, rule=10):
    out = None
    if u < uc:                                   # red rule draws across the split line, A pushes in slightly
        k = E.ease_out_cubic(u / uc) if uc > 0 else 1
        out = scale_about(A, 1 + 0.03 * k, W / 2, H / 2).copy()
        if axis == 'v':
            ln = int(H * k)
            out[H // 2 - ln // 2:H // 2 + ln // 2, W // 2 - rule // 2:W // 2 + rule // 2] = E.RED
        else:
            ln = int(W * k)
            out[H // 2 - rule // 2:H // 2 + rule // 2, W // 2 - ln // 2:W // 2 + ln // 2] = E.RED
        return out
    v = (u - uc) / max(1e-6, 1 - uc)
    e = lambda x: 1 - (1 - c01(x)) ** 2.2
    ev = e(v)
    out = scale_about(B, 1 + z * (1 - ev), W / 2, H / 2)
    Az = scale_about(A, 1.03, W / 2, H / 2)
    half = (W if axis == 'v' else H) // 2
    o = int(round(ev * half * 1.02))
    L = abs(e(v + du / (1 - uc) / 2) - e(v - du / (1 - uc) / 2)) * half * SHUT
    lay = np.zeros_like(A); al = np.zeros((H, W), np.float32)
    if axis == 'v':
        if half - o > 0:
            lay[:, :half - o] = Az[:, o:half]; al[:, :half - o] = 1
            lay[:, half + o:] = Az[:, half:W - o]; al[:, half + o:] = 1
            lay[:, max(0, half - o - rule):half - o] = E.RED; lay[:, half + o:half + o + rule] = E.RED
        return layer_over(out, lay, al, L, 'x')
    if half - o > 0:
        lay[:half - o] = Az[o:half]; al[:half - o] = 1
        lay[half + o:] = Az[half:H - o]; al[half + o:] = 1
        lay[max(0, half - o - rule):half - o] = E.RED; lay[half + o:half + o + rule] = E.RED
    return layer_over(out, lay, al, L, 'y')


# ------------------------------------------------------------------ pip: B pops in as a framed picture, then takes over
def pip(A, B, u, uc, du, s0=0.34, cx=0.70, cy=0.40, border=10, t_exp=0.55, shadow=0.35):
    if u < t_exp:
        k = c01(u / 0.22)
        s = s0 * (E.ease_out_back(k, 2.2) if k < 1 else 1.0)
        x, y = cx * W, cy * H; bw_ = border
    else:
        v = E.ease_in_out_cubic((u - t_exp) / (1 - t_exp))
        s = s0 + (1 - s0) * v
        x = cx * W + (W / 2 - cx * W) * v; y = cy * H + (H / 2 - cy * H) * v; bw_ = int(round(border * (1 - v)))
    out = scale_about(A, 1 + 0.04 * E.ease_in_cubic(min(1.0, u / t_exp)), W / 2, H / 2).copy()
    if s <= 0.01:
        return out
    w, h = int(W * s), int(H * s)
    x0, y0 = int(x - w / 2), int(y - h / 2)
    if shadow > 0 and s < 0.98:                   # soft drop shadow for separation (no 3D)
        sm = np.zeros((H // 4, W // 4), np.float32)
        sm[max(0, (y0 + 14) // 4):(y0 + h + 14) // 4, max(0, (x0 + 18) // 4):(x0 + w + 18) // 4] = 1
        sm = cv2.resize(cv2.GaussianBlur(sm, (0, 0), 6), (W, H))
        out *= (1 - shadow * (1 - s) * sm)[..., None]
    return E.inset_on(out, B, s, cx=x, cy=y, border=bw_, border_col=E.WHITE)


# ------------------------------------------------------------------ flash pop: overexpose out, B pops in from 108 %
def flash(A, B, u, uc, du, z=0.08, peak=1.0):
    if u < uc:
        k = c01(u / uc) if uc > 0 else 1
        return E.overexpose(A, peak * k ** 2)
    v = (u - uc) / max(1e-6, 1 - uc)
    out = scale_about(B, 1 + z * (1 - E.ease_out_expo(v)), W / 2, H / 2)
    return E.white_mix(out, peak * (1 - v) ** 2.2)


KINDS = {'push': push, 'whip': whip, 'zoom': zoom, 'redbar': redbar, 'slice': slices, 'doors': doors, 'pip': pip, 'flash': flash}


def apply(kind, A, B, u, uc, du, **kw):
    return np.clip(KINDS[kind](A, B, u, uc, du, **kw), 0, 1).astype(np.float32)
