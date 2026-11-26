#!/usr/bin/env python3
"""Make compact per-clip log sheets (<=18 frames, 240x135) from 540p keyframe previews."""
import json, os, sys, glob, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WORK = sys.argv[1]
OUT = os.path.join(WORK, 'logsheets'); os.makedirs(OUT, exist_ok=True)
F = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 13)
FB = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 15)

def frames_from_preview(prev, n_total):
    import cv2
    cap = cv2.VideoCapture(prev)
    fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    return fr

def main():
    import cv2
    res = sorted(glob.glob(os.path.join(WORK, 'results', '*.json')))
    for rp in res:
        stem = os.path.splitext(os.path.basename(rp))[0]
        out = os.path.join(OUT, stem + '.jpg')
        if os.path.exists(out):
            continue
        r = json.load(open(rp)); m = r['meta']; times = r['times']
        prev = os.path.join(WORK, 'preview', stem + '_540p.mp4')
        if not os.path.exists(prev):
            continue
        frames = frames_from_preview(prev, len(times))
        n = min(len(frames), len(times))
        if n == 0:
            continue
        k = min(18, n)
        idx = np.unique(np.linspace(0, n - 1, k).round().astype(int))
        tw, th = 240, 135
        cols = 6; rows = math.ceil(len(idx) / cols)
        W = cols * tw; H = 22 + rows * (th + 16)
        sheet = Image.new('RGB', (W, H), (18, 18, 18)); d = ImageDraw.Draw(sheet)
        d.text((4, 3), f"{m['name']}  {m['duration']:.1f}s  {(m['creation_time'] or '')[:16]}", fill=(255, 255, 255), font=FB)
        sharp = np.array([x['sharp'] for x in r['metrics']])
        for j, i in enumerate(idx):
            f = frames[i]; h0, w0 = f.shape[:2]
            s = min(tw / w0, th / h0)
            im = cv2.resize(f, (max(1, int(w0 * s)), max(1, int(h0 * s))), interpolation=cv2.INTER_AREA)
            pim = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
            x = (j % cols) * tw; y = 22 + (j // cols) * (th + 16)
            sheet.paste(pim, (x + (tw - pim.width) // 2, y))
            rel = sharp[i] / (np.median(sharp) + 1e-6) if i < len(sharp) else 0
            d.text((x + 3, y + th), f"{times[i]:.1f}s sh{rel:.1f}", fill=(255, 220, 110), font=F)
        sheet.save(out, quality=80)
    print('logsheets:', len(glob.glob(os.path.join(OUT, '*.jpg'))))

if __name__ == '__main__':
    main()
