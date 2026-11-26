#!/usr/bin/env python3
"""Per-frame mattes for a shot cache.

person:  python3 -I masks.py person <cache.mp4> <out_dir> [model.tflite]
         MediaPipe selfie-multiclass person probability, temporally smoothed, edge-refined (guided filter),
         written as 1920x1080 8-bit PNGs (00000.png ...). Used for rotoscope text (text behind person).
motion:  python3 -I masks.py motion <cache.mp4> <out_dir> x0 y0 x1 y1 [thresh]
         Median-background difference inside a normalised ROI (locked-off shots), used for the clone effect.
"""
import os, sys
import numpy as np
import cv2

W, H = 1920, 1080

def read_frames(path, w=W, h=H):
    cap = cv2.VideoCapture(path); out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA))
    return out

def guided(I, p, r=8, eps=1e-3):
    I = I.astype(np.float32); p = p.astype(np.float32)
    mean = lambda x: cv2.boxFilter(x, -1, (r, r))
    mI, mp_, mIp, mII = mean(I), mean(p), mean(I * p), mean(I * I)
    a = (mIp - mI * mp_) / (mII - mI * mI + eps); b = mp_ - a * mI
    return mean(a) * I + mean(b)

def person(cache, out_dir, model):
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    os.makedirs(out_dir, exist_ok=True)
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=mpt.BaseOptions(model_asset_path=model), output_confidence_masks=True))
    frames = read_frames(cache)
    prev = None
    for i, f in enumerate(frames):
        rgb = np.ascontiguousarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        r = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        cms = [np.array(m.numpy_view()).squeeze() for m in r.confidence_masks]
        pm = (1.0 - cms[0]).astype(np.float32) if len(cms) > 1 else cms[0].astype(np.float32)
        pm = cv2.resize(pm, (W, H))
        if prev is not None:
            pm = 0.65 * pm + 0.35 * prev        # temporal smoothing
        prev = pm
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        ref = np.clip(guided(gray, pm, r=10, eps=2e-3), 0, 1)
        ref = np.clip((ref - 0.35) / 0.3, 0, 1)
        cv2.imwrite(os.path.join(out_dir, f'{i:05d}.png'), (ref * 255).astype(np.uint8))
    seg.close()
    print('person masks', len(frames))

def motion(cache, out_dir, roi, thresh=28):
    os.makedirs(out_dir, exist_ok=True)
    frames = read_frames(cache)
    stack = np.stack([cv2.GaussianBlur(f, (5, 5), 0) for f in frames[:: max(1, len(frames) // 40)]])
    bg = np.median(stack, axis=0).astype(np.uint8)
    x0, y0, x1, y1 = [int(v * s) for v, s in zip(roi, (W, H, W, H))]
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    for i, f in enumerate(frames):
        d = cv2.absdiff(cv2.GaussianBlur(f, (5, 5), 0), bg).max(axis=2)
        m = (d > thresh).astype(np.uint8) * 255
        roi_m = np.zeros_like(m); roi_m[y0:y1, x0:x1] = 255
        m = cv2.bitwise_and(m, roi_m)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k); m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=2)
        m = cv2.dilate(m, k, iterations=1)
        m = cv2.GaussianBlur(m, (0, 0), 3)
        cv2.imwrite(os.path.join(out_dir, f'{i:05d}.png'), m)
    cv2.imwrite(os.path.join(out_dir, 'background.png'), bg)
    print('motion masks', len(frames))

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'person':
        person(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else
               '/tmp/claude-0/-home-user-VideoEdit/8531dbc8-a772-580f-8538-3f205e4051d8/scratchpad/models/selfie_multiclass.tflite')
    else:
        roi = [float(x) for x in sys.argv[4:8]]
        motion(sys.argv[2], sys.argv[3], roi, int(sys.argv[8]) if len(sys.argv) > 8 else 28)
