#!/usr/bin/env python3
"""Track a target through a shot cache for the HUD.

python3 -I track.py <cache.mp4> <out.json> <x_norm> <y_norm> [box_norm=0.06] [start_frame=0]
Tracks a cloud of features inside a box around the target with pyramidal Lucas-Kanade; the target
moves with the median feature displacement (robust), re-seeding features when they get sparse.
Also records 4 'constellation' sub-points around the target.
"""
import json, sys
import numpy as np
import cv2

def main():
    path, out = sys.argv[1], sys.argv[2]
    tx, ty = float(sys.argv[3]), float(sys.argv[4])
    box = float(sys.argv[5]) if len(sys.argv) > 5 else 0.06
    start = int(sys.argv[6]) if len(sys.argv) > 6 else 0
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(cv2.resize(f, (960, 540), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY))
    Wd, Hd = 960, 540
    lk = dict(winSize=(25, 25), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    pos = np.array([tx * Wd, ty * Hd], np.float32)
    def seed(img, p):
        bw = box * Wd
        m = np.zeros_like(img)
        x0, y0 = int(max(0, p[0] - bw)), int(max(0, p[1] - bw)); x1, y1 = int(min(Wd, p[0] + bw)), int(min(Hd, p[1] + bw))
        m[y0:y1, x0:x1] = 255
        pts = cv2.goodFeaturesToTrack(img, 60, 0.01, 4, mask=m)
        return pts
    pts = seed(frames[start], pos)
    # sub points: 4 strong corners in a wider ring around the target
    ring = np.zeros_like(frames[start]); bw2 = box * 3.2 * Wd
    cv2.circle(ring, (int(pos[0]), int(pos[1])), int(bw2), 255, -1)
    cv2.circle(ring, (int(pos[0]), int(pos[1])), int(box * 1.4 * Wd), 0, -1)
    subs0 = cv2.goodFeaturesToTrack(frames[start], 4, 0.05, int(box * 1.6 * Wd), mask=ring)
    subs = subs0.reshape(-1, 2) if subs0 is not None else np.zeros((0, 2), np.float32)
    track = [None] * len(frames); sub_tracks = [[None] * len(frames) for _ in range(len(subs))]
    track[start] = [float(pos[0] / Wd), float(pos[1] / Hd)]
    for k, s in enumerate(subs):
        sub_tracks[k][start] = [float(s[0] / Wd), float(s[1] / Hd)]
    for i in range(start + 1, len(frames)):
        a, b = frames[i - 1], frames[i]
        if pts is not None and len(pts) >= 6:
            nxt, st, err = cv2.calcOpticalFlowPyrLK(a, b, pts, None, **lk)
            good = st.reshape(-1) == 1
            if good.sum() >= 4:
                d = (nxt[good] - pts[good]).reshape(-1, 2)
                pos = pos + np.median(d, axis=0)
                pts = nxt[good].reshape(-1, 1, 2)
        if pts is None or len(pts) < 12:
            pts = seed(b, pos)
        if len(subs):
            nxt, st, err = cv2.calcOpticalFlowPyrLK(a, b, subs.reshape(-1, 1, 2).astype(np.float32), None, **lk)
            subs = nxt.reshape(-1, 2)
            for k, s in enumerate(subs):
                sub_tracks[k][i] = [float(s[0] / Wd), float(s[1] / Hd)] if st[k] else None
        pos[0] = np.clip(pos[0], 0, Wd - 1); pos[1] = np.clip(pos[1], 0, Hd - 1)
        track[i] = [float(pos[0] / Wd), float(pos[1] / Hd)]
    # backfill frames before start
    for i in range(start):
        track[i] = track[start]
    # light smoothing (5-frame) to remove LK jitter
    arr = np.array([p for p in track], np.float32)
    k = np.ones(5) / 5
    sm = np.stack([np.convolve(np.pad(arr[:, j], 2, mode='edge'), k, 'valid') for j in range(2)], -1)
    json.dump({'pts': sm.tolist(), 'subs': sub_tracks, 'n': len(frames)}, open(out, 'w'))
    print('tracked', len(frames), 'frames; start', track[start], 'end', track[-1])

if __name__ == '__main__':
    main()
