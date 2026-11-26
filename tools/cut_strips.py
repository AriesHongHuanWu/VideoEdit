import sys, cv2, numpy as np
src, out_prefix, t_end = sys.argv[1], sys.argv[2], float(sys.argv[3])
cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS)
frames = []
while True:
    ok, f = cap.read()
    if not ok: break
    frames.append(f)
n = len(frames)
small = [cv2.resize(f, (64, 36)).astype(np.float32) for f in frames]
diff = [0] + [float(np.abs(small[i] - small[i - 1]).mean()) for i in range(1, n)]
cuts = [i for i in range(2, n - 2) if diff[i] > 18 and diff[i] >= max(diff[i - 1], diff[i + 1]) and i / fps < t_end]
rows = []
for c in cuts:
    row = []
    for k in range(c - 2, c + 4):
        k = min(max(k, 0), n - 1)
        t = cv2.resize(frames[k], (176, 99) if frames[k].shape[1] > frames[k].shape[0] else (99, 176), interpolation=cv2.INTER_AREA)
        if t.shape[1] < 176:
            t = cv2.copyMakeBorder(t, 0, 0, 0, 176 - t.shape[1], cv2.BORDER_CONSTANT)
            t = cv2.resize(t, (176, 99))
        cv2.putText(t, f"{k}", (2, 10), 0, 0.3, (0, 255, 255), 1)
        row.append(t)
    lab = np.zeros((99, 60, 3), np.uint8); cv2.putText(lab, f"{c/fps:.2f}", (2, 50), 0, 0.42, (255, 255, 255), 1)
    rows.append(np.hstack([lab] + row))
per = 16
for j in range(0, len(rows), per):
    cv2.imwrite(f"{out_prefix}_{j // per}.jpg", np.vstack(rows[j:j + per]), [cv2.IMWRITE_JPEG_QUALITY, 80])
print('fps', fps, 'cuts', len(cuts), [round(c / fps, 2) for c in cuts])
