import json, glob, sys, os, cv2, numpy as np
S = sys.argv[1]; out = sys.argv[2]; names = sys.argv[3].split(',')
logs = {}
for f in glob.glob(os.path.join(S, 'log', '*.jsonl')):
    for line in open(f):
        if line.strip():
            d = json.loads(line); logs[d['file'][:-4]] = d
tiles = []
for st in names:
    d = logs.get(st); r = json.load(open(os.path.join(S, 'work', 'results', st + '.json')))
    times = r['times']; cap = cv2.VideoCapture(os.path.join(S, 'work', 'preview', st + '_540p.mp4'))
    frames = []
    while True:
        ok, fr = cap.read()
        if not ok: break
        frames.append(fr)
    bm = d['best_moments'][0] if d and d['best_moments'] else {'start': 0, 'end': times[-1]}
    picks = np.linspace(bm['start'], bm['end'], 3)
    row = []
    for tt in picks:
        i = int(np.argmin([abs(x - tt) for x in times[:len(frames)]]))
        im = cv2.resize(frames[i], (400, 225), interpolation=cv2.INTER_AREA)
        cv2.putText(im, f"{st[4:]} {times[i]:.1f}s", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA)
        row.append(im)
    tiles.append(np.hstack(row))
cols = 2
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 80])
