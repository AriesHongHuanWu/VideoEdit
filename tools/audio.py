#!/usr/bin/env python3
"""Audio: synthesized SFX, filter sweeps, sidechain, loudness/true-peak mastering."""
import numpy as np
import soundfile as sf
from scipy import signal
import pyloudnorm as pyln

SR = 48000
rng = np.random.default_rng(1234)

def db(x):
    return 10 ** (x / 20.0)

def t_axis(dur):
    return np.arange(int(round(dur * SR))) / SR

def env_ad(n, a, d, curve=4.0):
    """attack (s) linear, then exponential-ish decay over d seconds."""
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-6), np.exp(-curve * (t - a) / max(d, 1e-6)))
    return e

def bandpass(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, hi], btype='bandpass', fs=SR, output='sos')
    return signal.sosfilt(sos, x, axis=0)

def lowpass(x, fc, order=4):
    sos = signal.butter(order, fc, btype='lowpass', fs=SR, output='sos')
    return signal.sosfilt(sos, x, axis=0)

def highpass(x, fc, order=4):
    sos = signal.butter(order, fc, btype='highpass', fs=SR, output='sos')
    return signal.sosfilt(sos, x, axis=0)

def stereo(x, pan=0.0, width=0.0):
    """mono -> stereo with constant-power pan (-1..1) and optional decorrelated width."""
    l = np.cos((pan + 1) * np.pi / 4); r = np.sin((pan + 1) * np.pi / 4)
    out = np.stack([x * l, x * r], -1) * np.sqrt(2)
    if width > 0:
        d = signal.lfilter([1, 0, 0, 0, 0, 0, 0, 0.0], [1], x)  # placeholder delay
        side = np.roll(x, int(0.011 * SR)) * width
        out[:, 0] += side * 0.5; out[:, 1] -= side * 0.5
    return out

def synth_ir(dur=1.6, decay=2.4, lp=6000, seed=5):
    r = np.random.default_rng(seed)
    n = int(dur * SR); t = np.arange(n) / SR
    ir = r.standard_normal((n, 2)) * np.exp(-decay * t)[:, None]
    ir = lowpass(ir, lp, 2)
    ir[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))[:, None]
    return ir / np.abs(ir).sum(0).max() * 6

def reverb(x, wet=0.25, dur=1.6, decay=2.4, lp=6000):
    if x.ndim == 1:
        x = np.stack([x, x], -1)
    ir = synth_ir(dur, decay, lp)
    y = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[: len(x) + len(ir) - 1] for c in range(2)], -1)
    out = np.zeros_like(y); out[: len(x)] += x * (1 - wet * 0.3)
    return out + y * wet

def norm_peak(x, peak_db):
    m = np.abs(x).max() + 1e-9
    return x / m * db(peak_db)

# ------------------------------------------------------------------ SFX
def sub_boom(dur=1.5, f0=62.0, f1=31.0, peak=-3.0):
    t = t_axis(dur)
    f = f1 + (f0 - f1) * np.exp(-t / 0.18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph)
    x = np.tanh(1.6 * x) / np.tanh(1.6)      # warmth / harmonics
    e = env_ad(len(t), 0.004, dur, curve=3.2)
    x = x * e
    x = lowpass(x, 180, 2)
    return stereo(norm_peak(x, peak))

def impact(dur=1.4, peak=-2.0, bright=1.0, seed=11):
    r = np.random.default_rng(seed)
    t = t_axis(dur); n = len(t)
    noise = r.standard_normal(n)
    crack = bandpass(noise, 300, 7000) * env_ad(n, 0.0008, 0.06, curve=5)
    thump_f = 45 + 110 * np.exp(-t / 0.035)
    thump = np.sin(2 * np.pi * np.cumsum(thump_f) / SR) * env_ad(n, 0.001, 0.25, curve=5)
    metal = sum(np.sin(2 * np.pi * fr * t + r.random() * 6) * a for fr, a in [(410, .5), (1130, .35), (2380, .2), (3170, .12)])
    metal = metal * env_ad(n, 0.001, 0.45, curve=6) * 0.35 * bright
    x = crack * 0.9 + thump * 1.0 + metal
    x = stereo(x)
    x = reverb(x, wet=0.35, dur=1.8, decay=2.2, lp=5000)[: n]
    return norm_peak(x, peak)

def whoosh(dur=0.45, peak=-10.0, pan_from=-0.7, pan_to=0.7, f_lo=350, f_hi=3200, seed=21, peak_pos=0.65):
    r = np.random.default_rng(seed)
    n = int(dur * SR); t = np.arange(n) / SR
    noise = r.standard_normal(n)
    # time-varying bandpass via block processing
    out = np.zeros(n); block = 256; zi = None
    for i in range(0, n, block):
        u = i / n
        c = f_lo + (f_hi - f_lo) * (np.sin(np.pi * min(1, u / peak_pos) / 2) if u < peak_pos else 1 - 0.6 * (u - peak_pos) / (1 - peak_pos))
        lo, hi = max(60, c * 0.55), min(SR / 2 - 100, c * 1.8)
        sos = signal.butter(2, [lo, hi], btype='bandpass', fs=SR, output='sos')
        if zi is None:
            zi = signal.sosfilt_zi(sos) * 0
        seg, zi = signal.sosfilt(sos, noise[i:i + block], zi=zi)
        out[i:i + block] = seg
    e = np.where(t < dur * peak_pos, (t / (dur * peak_pos)) ** 2.2, np.exp(-5 * (t - dur * peak_pos) / (dur * (1 - peak_pos))))
    x = out * e
    pans = np.linspace(pan_from, pan_to, n)
    l = np.cos((pans + 1) * np.pi / 4); rr = np.sin((pans + 1) * np.pi / 4)
    st = np.stack([x * l, x * rr], -1)
    return norm_peak(st, peak)

def riser(dur=2.9, peak=-9.0, seed=31):
    r = np.random.default_rng(seed)
    n = int(dur * SR); t = np.arange(n) / SR; u = t / dur
    noise = r.standard_normal(n)
    out = np.zeros(n); block = 256; zi = None
    for i in range(0, n, block):
        c = 300 * (9000 / 300) ** (i / n)
        sos = signal.butter(2, [max(80, c * 0.6), min(SR / 2 - 100, c * 1.6)], btype='bandpass', fs=SR, output='sos')
        if zi is None:
            zi = signal.sosfilt_zi(sos) * 0
        seg, zi = signal.sosfilt(sos, noise[i:i + block], zi=zi)
        out[i:i + block] = seg
    f = 140 * (1100 / 140) ** u
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.5 + np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR) * 0.3
    trem = 1 + 0.25 * np.sin(2 * np.pi * (4 + 14 * u ** 2) * t)
    x = (out * 0.8 + tone * 0.35) * (u ** 2.4) * trem
    x[-int(0.004 * SR):] *= np.linspace(1, 0, int(0.004 * SR))
    st = stereo(x)
    st = reverb(st, wet=0.25, dur=1.0, decay=3.0)[:n]
    return norm_peak(st, peak)

def click(peak=-16.0, f=3200, dur=0.03, seed=41, pan=0.0):
    r = np.random.default_rng(seed)
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.006) + 0.25 * r.standard_normal(n) * np.exp(-t / 0.0015)
    x = highpass(x, 600, 2)
    return norm_peak(stereo(x, pan), peak)

def data_chatter(dur=0.6, rate=16, peak=-19.0, seed=51, pan=0.2):
    r = np.random.default_rng(seed)
    n = int(dur * SR); out = np.zeros((n, 2))
    k = int(dur * rate)
    for i in range(k):
        pos = int(r.uniform(0, n - int(0.03 * SR)))
        c = click(peak=0, f=r.choice([1800, 2400, 3100, 4200, 5200]), dur=0.02, seed=int(r.integers(1e6)), pan=float(r.uniform(-0.4, 0.4)) + pan * 0.3)
        out[pos:pos + len(c)] += c * r.uniform(0.4, 1.0)
    return norm_peak(out, peak)

def shutter(peak=-11.0, seed=61):
    r = np.random.default_rng(seed)
    n = int(0.16 * SR); out = np.zeros(n)
    def clk(pos, bright, length):
        m = int(length * SR); t = np.arange(m) / SR
        z = bandpass(r.standard_normal(m), 1200, 9000) * np.exp(-t / (length / 5)) * bright
        th = np.sin(2 * np.pi * 260 * t) * np.exp(-t / 0.008) * 0.5
        out[pos:pos + m] += (z + th)[: n - pos]
    clk(0, 1.0, 0.018)
    clk(int(0.055 * SR), 0.7, 0.022)
    return norm_peak(stereo(out, 0.0), peak)

# ------------------------------------------------------------------ processing
def sweep_filter(x, t0, t1, f_start, f_end, kind, sr=SR, order=2, hold_after=True):
    """Apply time-varying LP/HP between t0 and t1 (exponential cutoff), in place; outside the window
    the filter is bypassed (before t0) and either held at f_end (hold_after) or bypassed after t1."""
    n0, n1 = int(t0 * sr), int(t1 * sr)
    y = x.copy()
    block = 128
    zi = None
    end = len(x) if hold_after else n1
    for i in range(n0, end, block):
        u = min(1.0, (i - n0) / max(1, n1 - n0))
        fc = f_start * (f_end / f_start) ** u
        fc = min(max(fc, 20), sr / 2 * 0.95)
        sos = signal.butter(order, fc, btype=kind, fs=sr, output='sos')
        if zi is None:
            zi = np.zeros((sos.shape[0], 2, x.shape[1]))
        seg, zi = signal.sosfilt(sos, x[i:i + block], axis=0, zi=zi)
        y[i:i + block] = seg
    return y

def crossfade_regions(dry, wet, t_in, t_out, fade=0.01):
    """Return dry outside [t_in, t_out], wet inside, with short crossfades."""
    n = len(dry); g = np.zeros(n)
    a, b = int(t_in * SR), int(t_out * SR); f = int(fade * SR)
    g[a:b] = 1
    if f > 0:
        g[max(0, a - f):a] = np.linspace(0, 1, a - max(0, a - f))
        g[b:min(n, b + f)] = np.linspace(1, 0, min(n, b + f) - b)
    return dry * (1 - g[:, None]) + wet * g[:, None]

def envelope(x, attack=0.003, release=0.25):
    e = np.abs(x).max(-1) if x.ndim == 2 else np.abs(x)
    out = np.zeros_like(e)
    a = np.exp(-1 / (attack * SR)); r = np.exp(-1 / (release * SR))
    # vectorised-ish: process in python loop over decimated envelope
    dec = 32
    ed = e[: len(e) // dec * dec].reshape(-1, dec).max(1)
    od = np.zeros_like(ed); s = 0.0
    ad, rd = a ** dec, r ** dec
    for i, v in enumerate(ed):
        s = v + (s - v) * (ad if v > s else rd)
        od[i] = s
    out[: len(od) * dec] = np.repeat(od, dec)
    out[len(od) * dec:] = od[-1] if len(od) else 0
    return out

def sidechain_low(music, key, depth_db=-9.0, xover=150.0, full_depth_db=-2.5):
    """Duck the music's low band (and slightly the full band) by the key envelope."""
    sos = signal.butter(4, xover, btype='lowpass', fs=SR, output='sos')
    low = signal.sosfiltfilt(sos, music, axis=0)
    high = music - low
    env = envelope(key, 0.002, 0.28)
    env = env / (env.max() + 1e-9)
    env = np.clip(env * 1.4, 0, 1)
    g_low = db(depth_db * env)
    g_full = db(full_depth_db * env)
    return (low * g_low[:, None] + high) * g_full[:, None]

def true_peak(x, os_=4):
    up = signal.resample_poly(x, os_, 1, axis=0)
    return 20 * np.log10(np.abs(up).max() + 1e-12)

def limiter(x, ceiling_db=-1.3, lookahead=0.003, release=0.08, os_=4):
    """Simple true-peak-aware lookahead limiter (gain computed on oversampled peaks)."""
    up = signal.resample_poly(x, os_, 1, axis=0)
    pk = np.abs(up).max(-1)
    pk = pk[: len(pk) // os_ * os_].reshape(-1, os_).max(1)
    pk = np.pad(pk, (0, len(x) - len(pk)), mode='edge') if len(pk) < len(x) else pk[: len(x)]
    ceil = db(ceiling_db)
    need = np.minimum(1.0, ceil / np.maximum(pk, 1e-9))
    la = int(lookahead * SR)
    # lookahead: min over window ahead
    from scipy.ndimage import minimum_filter1d
    g = minimum_filter1d(need, size=2 * la + 1, origin=0)
    g = np.concatenate([g[la:], np.full(la, g[-1])])
    # release smoothing (only lets gain rise slowly)
    r = np.exp(-1 / (release * SR))
    out = np.empty_like(g); s = 1.0
    dec = 16
    gd = g[: len(g) // dec * dec].reshape(-1, dec).min(1)
    od = np.empty_like(gd); rd = r ** dec
    for i, v in enumerate(gd):
        s = v if v < s else v + (s - v) * rd
        od[i] = s
    out[: len(od) * dec] = np.repeat(od, dec); out[len(od) * dec:] = od[-1]
    # smooth the staircase
    out = signal.savgol_filter(out, 31, 2)
    out = np.minimum(out, 1.0)
    return x * out[:, None]

def loudness(x):
    meter = pyln.Meter(SR)
    return meter.integrated_loudness(x)

def master(x, target_lufs=-14.0, tp=-1.3):
    for _ in range(3):
        L = loudness(x)
        x = x * db(target_lufs - L)
        x = limiter(x, ceiling_db=tp)
    return x, loudness(x), true_peak(x)

def place(bus, sfx, t, gain_db=0.0):
    i = int(round(t * SR))
    if i >= len(bus):
        return
    m = min(len(sfx), len(bus) - i)
    if i < 0:
        sfx = sfx[-i:]; m = min(len(sfx), len(bus)); i = 0
    bus[i:i + m] += sfx[:m] * db(gain_db)
