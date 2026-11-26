#!/usr/bin/env python3
"""Grade consistency test: per-shot before/after tiles from previews.  python3 -I grade_test.py <shots.json> <out.jpg> [look_module]"""
import json, sys, os, importlib.util
import numpy as np, cv2
ROOT = '/tmp/claude-0/-home-user-VideoEdit/8531dbc8-a772-580f-8538-3f205e4051d8/scratchpad'
sys.path.insert(0, os.path.join(ROOT, 'tools'))
lm = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, 'tools', 'look.py')
spec = importlib.util.spec_from_file_location('lookx', lm); look = importlib.util.module_from_spec(spec); spec.loader.exec_module(look)
shots = [s for s in json.load(open(sys.argv[1])) if not s['id'].startswith('r')]
def frames_at(clip, ts):
    r = json.load(open(os.path.join(ROOT, 'work', 'results', clip + '.json'))); times = r['times']
    cap = cv2.VideoCapture(os.path.join(ROOT, 'work', 'preview', clip + '_540p.mp4')); fr = []
    while True:
        ok, f = cap.read()
        if not ok: break
        fr.append(f)
    out = []
    for t in ts:
        i = int(np.argmin([abs(x - t) for x in times[:len(fr)]])); out.append(fr[i][:, :, ::-1].astype(np.float64) / 255)
    return out
tiles = []
for s in shots:
    dur = s['n_frames'] / 60
    smp = frames_at(s['clip'], [s['src_in'] + dur * k / 3 for k in range(4)])
    p = look.estimate_params([cv2.resize(x, (640, 360)) for x in smp])
    lut, n = look.build_lut(p, n=33)
    src = smp[1]
    out = look.apply_lut_np(src, lut, n)
    a = cv2.resize((src * 255).astype(np.uint8), (320, 180)); b = cv2.resize((np.clip(out, 0, 1) * 255).astype(np.uint8), (320, 180))
    tile = np.hstack([a, b])[:, :, ::-1].copy()
    cv2.putText(tile, s['clip'][4:], (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    tiles.append(tile)
cols = 3
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(sys.argv[2], np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
print('tiles', len(shots))
