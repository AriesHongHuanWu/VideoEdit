#!/usr/bin/env python3
"""Render selected global frames of an EDL into a labelled contact sheet. frames_sheet.py <proj> <out.jpg> f1,f2,..."""
import sys, os, json, numpy as np, cv2
sys.path.insert(0, os.path.dirname(__file__))
import render as R, engine as E
P, out, fl = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3].split(',')]
edl = json.load(open(os.path.join(P, 'edl.json'))); cache = R.Cache(os.path.join(P, 'cache'))
tracks = {k: json.load(open(p)) for k, p in edl['tracks'].items() if os.path.exists(p)}
ctx = {'tracks': tracks, 'cache': cache}; grain = E.Grain(n=3)
tiles = []
for gi in fl:
    img = R.render_frame(edl, gi, cache, ctx, grain)
    seg = next(s for s in edl['segments'] if s['f0'] <= gi < s['f1'])
    t = E.to_u8(cv2.resize(img, (384, 216), interpolation=cv2.INTER_AREA))[:, :, ::-1].copy()
    cv2.putText(t, f"{gi} {gi/60:.2f}s {seg.get('shot') or seg.get('card') or seg['type']}", (4, 14), 0, 0.38, (0, 255, 255), 1, cv2.LINE_AA)
    tiles.append(t)
cols = 8
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
