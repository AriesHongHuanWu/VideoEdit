#!/usr/bin/env python3
"""Summarize ingest result JSONs into compact per-clip text (motion/sharpness/exposure) for logging."""
import json, sys, os, glob, math
import numpy as np

def seg_motion(times, motion, a, b):
    dx = []; dy = []; sc = []; rot = []
    for t, m in zip(times, motion):
        if m is None or not (a <= t < b):
            continue
        if m.get('inl', 0) < 0.25:
            continue
        dt = m.get('dt', 0.5)
        dx.append(m['dx'] / dt); dy.append(m['dy'] / dt); sc.append((m['scale'] - 1) / dt); rot.append(m['rot'] / dt)
    if not dx:
        return None
    return float(np.median(dx)), float(np.median(dy)), float(np.median(sc)), float(np.median(rot)), float(np.std(dx) + np.std(dy))

def describe(dx, dy, sc, rot, jit):
    # dx,dy in px/s at 480px-wide frame; scene motion. camera pan is opposite.
    parts = []
    if abs(dx) > 12:
        parts.append(('pan-L' if dx > 0 else 'pan-R') + f'({abs(dx):.0f})')
    if abs(dy) > 10:
        parts.append(('tilt-up' if dy > 0 else 'tilt-down') + f'({abs(dy):.0f})')
    if abs(sc) > 0.012:
        parts.append(('push-in' if sc > 0 else 'pull-out') + f'({sc*100:+.1f}%/s)')
    if abs(rot) > 1.5:
        parts.append(f'roll({rot:+.1f}deg/s)')
    if not parts:
        parts.append('static')
    if jit > 60:
        parts.append(f'shaky({jit:.0f})')
    return ' '.join(parts)

def summarize(path):
    r = json.load(open(path))
    m = r['meta']; times = r['times']; met = r['metrics']; mot = r['motion']
    dur = m['duration']
    dji = m.get('dji', {}) or {}
    wb = [x for x in (dji.get('wb_k') or []) if x]
    iso = [x for x in (dji.get('iso') or []) if x]
    sh = [x for x in (dji.get('shutter_den') or []) if x]
    sharp = np.array([x['sharp'] for x in met]); luma = np.array([x['luma'] for x in met])
    lines = []
    head = (f"{m['name']} | {dur:.1f}s | {m['width']}x{m['height']} {m['fps']} {m['pix_fmt']} bitdepth={dji.get('vid_bitdepth')} | "
            f"shot {m['creation_time']} | WB {min(wb) if wb else '?'}-{max(wb) if wb else '?'}K ISO {min(iso) if iso else '?'}-{max(iso) if iso else '?'} "
            f"shutter 1/{int(min(sh)) if sh else '?'}-1/{int(max(sh)) if sh else '?'} | luma {luma.mean():.0f} | sharp median {np.median(sharp):.0f}")
    lines.append(head)
    # segment motion every ~3s (or whole clip if short)
    step = 3.0 if dur > 9 else max(1.0, dur / 3)
    segs = []
    a = 0.0
    while a < dur - 0.3:
        b = min(dur, a + step)
        sm = seg_motion(times, mot, a, b)
        # sharpness in segment relative to clip median
        k = [i for i, t in enumerate(times) if a <= t < b]
        rs = (np.median(sharp[k]) / (np.median(sharp) + 1e-6)) if k else float('nan')
        lu = float(np.mean(luma[k])) if k else float('nan')
        desc = describe(*sm) if sm else 'n/a'
        segs.append(f"{a:.0f}-{b:.0f}s: {desc}; sharp x{rs:.2f}; luma {lu:.0f}")
        a = b
    lines.append('  ' + ' || '.join(segs))
    return '\n'.join(lines)

if __name__ == '__main__':
    res_dir = sys.argv[1]
    names = sys.argv[2:] if len(sys.argv) > 2 else None
    files = sorted(glob.glob(os.path.join(res_dir, '*.json')))
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        if names and stem not in names:
            continue
        try:
            print(summarize(f))
        except Exception as e:
            print(stem, 'ERROR', e)
