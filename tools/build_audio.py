#!/usr/bin/env python3
"""Build the final soundtrack from the song + EDL sound design.

python3 -I build_audio.py <track.wav> <edl.json> <out.wav>
EDL keys used: audio = {song_start, dur, lpf_intro:[t_down0,t_down1,t_up0,t_up1,f_low], hpf_build:[t0,t1,f0,f1],
                        gaps:[[t0,t1],...], lowdip:[t0,t1,f1], outro:[t_lpf0,t_lpf1,f_end,t_fade0,t_fade1]}
               sfx = [{t, type, gain, ...}, ...]
"""
import json, sys, os
import numpy as np
import soundfile as sf
from scipy import signal
sys.path.insert(0, os.path.dirname(__file__))
import audio as A

SR = A.SR

def tv_filter(x, fc_fn, kind, t_from, t_to, order=2, block=128):
    """Time-varying Butterworth filter applied only between t_from and t_to (fc_fn(t) -> Hz)."""
    y = x.copy(); n0, n1 = int(t_from * SR), min(len(x), int(t_to * SR))
    zi = None
    for i in range(n0, n1, block):
        t = i / SR
        fc = float(np.clip(fc_fn(t), 20, SR / 2 * 0.95))
        sos = signal.butter(order, fc, btype=kind, fs=SR, output='sos')
        if zi is None:
            zi = np.zeros((sos.shape[0], 2, x.shape[1]))
            # warm start the filter with the dry signal to avoid a click at entry
            zi = signal.sosfilt_zi(sos)[:, :, None] * x[i][None, None, :]
        seg, zi = signal.sosfilt(sos, x[i:i + block], axis=0, zi=zi)
        y[i:i + block] = seg
    # short crossfade at the exit to avoid discontinuity
    f = int(0.004 * SR)
    if n1 + f < len(x):
        w = np.linspace(0, 1, f)[:, None]
        y[n1:n1 + f] = y[n1:n1 + f] * (1 - w) + x[n1:n1 + f] * w
    return y

def exp_interp(f0, f1, u):
    u = min(1.0, max(0.0, u))
    return f0 * (f1 / f0) ** u

def main():
    track, edl_p, out = sys.argv[1], sys.argv[2], sys.argv[3]
    edl = json.load(open(edl_p)); au = edl['audio']
    y, sr = sf.read(track, always_2d=True)
    assert sr == SR, sr
    s0 = au['song_start']; dur = au['dur']
    music = y[int(s0 * SR): int((s0 + dur) * SR)].astype(np.float64)
    if len(music) < int(dur * SR):
        music = np.pad(music, ((0, int(dur * SR) - len(music)), (0, 0)))
    # tiny fade-in to avoid a click
    music[:96] *= np.linspace(0, 1, 96)[:, None]
    # 1) intro low-pass dive and reopen
    if au.get('lpf_intro'):
        d0, d1, u0, u1, flo = au['lpf_intro']
        def fc(t):
            if t < d1:
                return exp_interp(20000, flo, (t - d0) / (d1 - d0))
            if t < u0:
                return flo
            return exp_interp(flo, 20000, ((t - u0) / (u1 - u0)) ** 1.6)
        music = tv_filter(music, fc, 'lowpass', d0, u1, order=2)
    # 2) buildup high-pass sweep (thins the low end toward the drop)
    if au.get('hpf_build'):
        b0, b1, f0, f1 = au['hpf_build']
        music = tv_filter(music, lambda t: exp_interp(f0, f1, ((t - b0) / (b1 - b0)) ** 1.3), 'highpass', b0, b1, order=2)
    # 3) low-end dip before the final hit
    if au.get('lowdip'):
        l0, l1, lf = au['lowdip']
        music = tv_filter(music, lambda t: exp_interp(25, lf, (t - l0) / (l1 - l0)), 'highpass', l0, l1, order=2)
    # 4) outro: LPF close + fade
    if au.get('outro'):
        o0, o1, fe, fa0, fa1 = au['outro']
        music = tv_filter(music, lambda t: exp_interp(20000, fe, (t - o0) / (o1 - o0)), 'lowpass', o0, dur, order=2)
        g = np.ones(len(music)); a, b = int(fa0 * SR), int(fa1 * SR)
        g[a:b] = np.linspace(1, 0, b - a) ** 1.5; g[b:] = 0
        music *= g[:, None]
    # 5) silence gaps (1-3 frames before big hits) with 2 ms ramps
    for g0, g1 in au.get('gaps', []):
        a, b = int(g0 * SR), int(g1 * SR); r = int(0.002 * SR)
        music[a:b] = 0
        music[max(0, a - r):a] *= np.linspace(1, 0, a - max(0, a - r))[:, None]
        music[b:b + r] *= np.linspace(0, 1, r)[:, None]
    # ---------------- SFX bus
    n = len(music)
    sfx = np.zeros((n, 2)); key = np.zeros((n, 2))
    lib = {}
    for ev in edl.get('sfx', []):
        typ = ev['type']; t = ev['t']; gain = ev.get('gain', 0.0)
        if typ == 'boom':
            s = A.sub_boom(dur=ev.get('dur', 1.6), f0=ev.get('f0', 62), f1=ev.get('f1', 31), peak=-3)
            A.place(sfx, s, t, gain); A.place(key, s, t, gain)
        elif typ == 'impact':
            s = A.impact(dur=ev.get('dur', 1.4), peak=-3, bright=ev.get('bright', 1.0), seed=ev.get('seed', 11))
            A.place(sfx, s, t, gain); A.place(key, s, t, gain - 3)
        elif typ == 'whoosh':
            d = ev.get('dur', 0.42)
            s = A.whoosh(dur=d, peak=-6, pan_from=ev.get('pan_from', -0.6), pan_to=ev.get('pan_to', 0.6), seed=ev.get('seed', 21),
                         peak_pos=ev.get('peak_pos', 0.7))
            A.place(sfx, s, t - d * ev.get('peak_pos', 0.7), gain)    # peak lands on t
        elif typ == 'riser':
            d = ev['dur']; s = A.riser(dur=d, peak=-6); A.place(sfx, s, t - d, gain)   # ends at t
        elif typ == 'click':
            s = A.click(peak=-6, f=ev.get('f', 3200), seed=ev.get('seed', 41), pan=ev.get('pan', 0.0)); A.place(sfx, s, t, gain)
        elif typ == 'chatter':
            s = A.data_chatter(dur=ev.get('dur', 0.5), rate=ev.get('rate', 16), peak=-6, seed=ev.get('seed', 51)); A.place(sfx, s, t, gain)
        elif typ == 'shutter':
            s = A.shutter(peak=-6, seed=ev.get('seed', 61)); A.place(sfx, s, t, gain)
    # ---------------- sidechain + mix
    music = A.sidechain_low(music, key, depth_db=au.get('sc_depth', -10.0), xover=150.0, full_depth_db=au.get('sc_full', -2.0))
    mix = music * A.db(au.get('music_gain', 0.0)) + sfx * A.db(au.get('sfx_gain', 0.0))
    mix, L, tp = A.master(mix, target_lufs=au.get('lufs', -14.0), tp=au.get('tp', -1.5))
    sf.write(out, mix.astype(np.float32), SR, subtype='FLOAT')
    print(f'audio: {len(mix)/SR:.2f}s  integrated {L:.2f} LUFS  true-peak {tp:.2f} dBTP')

if __name__ == '__main__':
    main()
