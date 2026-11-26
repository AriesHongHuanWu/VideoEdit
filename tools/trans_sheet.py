#!/usr/bin/env python3
"""Contact sheet of every straddling transition: one row per cut, frames across the window.
python3 -I trans_sheet.py <project_dir> <out.jpg> [first_row] [n_rows] [cols]"""
import json, os, sys
import numpy as np
import cv2
sys.path.insert(0, os.path.dirname(__file__))
import render as R
import engine as E

P, OUT = sys.argv[1], sys.argv[2]
r0 = int(sys.argv[3]) if len(sys.argv) > 3 else 0
nr = int(sys.argv[4]) if len(sys.argv) > 4 else 99
cols = int(sys.argv[5]) if len(sys.argv) > 5 else 7
edl = json.load(open(os.path.join(P, 'edl.json')))
cache = R.Cache(os.path.join(P, 'cache'))
tracks = {k: json.load(open(p)) for k, p in edl.get('tracks', {}).items() if os.path.exists(p)}
ctx = {'tracks': tracks, 'cache': cache}
grain = E.Grain(n=8, seed=3)
segs = edl['segments']
rows = []
cuts = [(i, s) for i, s in enumerate(segs) if s.get('tr')][r0:r0 + nr]
tw, th = 384, 216
for i, B in cuts:
    tr = B['tr']; no, ni = tr['n_out'], tr['n_in']
    a, b = B['f0'] - no - 1, B['f0'] + ni
    idx = np.unique(np.round(np.linspace(a, b, cols)).astype(int))
    tiles = []
    for gi in idx:
        img = R.render_frame(edl, int(gi), cache, ctx, grain)
        t = cv2.resize(E.to_u8(img), (tw, th), interpolation=cv2.INTER_AREA)[:, :, ::-1].copy()
        name = f"{tr['kind']} {int(gi) - B['f0']:+d}"
        cv2.putText(t, name, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        tiles.append(t)
    while len(tiles) < cols:
        tiles.append(np.zeros((th, tw, 3), np.uint8))
    prev = segs[i - 1].get('shot', segs[i - 1]['type']); nxt = B.get('shot', B['type'])
    lab = np.zeros((18, tw * cols, 3), np.uint8)
    cv2.putText(lab, f"#{i} {prev} -> {nxt}  @ {B['f0'] / 60:.2f}s", (6, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    rows.append(np.vstack([lab, np.hstack(tiles)]))
cv2.imwrite(OUT, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
print('rows', len(rows))
