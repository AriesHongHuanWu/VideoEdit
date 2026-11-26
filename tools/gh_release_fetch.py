#!/usr/bin/env python3
"""Download selected original clips from the VideoEdit release (public browser URLs), verify SHA-256 against
videoedit/manifest.json, join multi-part assets. python3 -I gh_release_fetch.py <manifest.json> <out_dir> <names...|@listfile>"""
import hashlib, json, os, subprocess, sys
man = json.load(open(sys.argv[1])); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
want = []
for a in sys.argv[3:]:
    want += [l.strip() for l in open(a[1:])] if a.startswith('@') else [a]
want = {w if w.upper().endswith('.MP4') else w + '.MP4' for w in want if w}
files = [f for f in man['files'] if f['name'] in want]
missing = want - {f['name'] for f in files}
if missing:
    print('not in manifest:', sorted(missing))
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()
for f in files:
    dst = os.path.join(out, f['name'].replace('.MP4', '.mp4'))
    if os.path.exists(dst) and os.path.getsize(dst) == f['size'] and sha(dst) == f['sha256']:
        print('have', f['name']); continue
    parts = []
    for a in f['assets']:
        p = dst + '.' + a['name'].split('.')[-1] if len(f['assets']) > 1 else dst + '.dl'
        for attempt in range(4):
            r = subprocess.run(['curl', '-sS', '-L', '--fail', '-C', '-', '-o', p, a['url']], capture_output=True, text=True)
            if r.returncode == 0 and os.path.getsize(p) == a['size']:
                break
        parts.append(p)
    with open(dst, 'wb') as o:
        for p in parts:
            with open(p, 'rb') as i:
                while True:
                    b = i.read(1 << 22)
                    if not b:
                        break
                    o.write(b)
            os.remove(p)
    ok = os.path.getsize(dst) == f['size'] and sha(dst) == f['sha256']
    print(('ok ' if ok else 'BAD ') + f['name'], f['size'], flush=True)
    if not ok:
        os.remove(dst)
