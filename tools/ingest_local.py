#!/usr/bin/env python3
"""Run the ingest analysis (540p preview, metrics, contact sheet, DJI metadata) on local, verified originals.
Originals are kept. python3 -I ingest_local.py <manifest.json> <workdir> <orig_dir> <names...|@list>"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
man_path, WORK, ORIGDIR = sys.argv[1], sys.argv[2], sys.argv[3]
names = []
for a in sys.argv[4:]:
    names += [l.strip() for l in open(a[1:])] if a.startswith('@') else [a]
sys.argv = [sys.argv[0], '/dev/null', WORK]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest as IG
man = {f['name']: f for f in json.load(open(man_path))['files']}
items = []
for n in names:
    if not n:
        continue
    f = man[n]
    items.append(dict(folder=f['group'], name=n, id='', size=f['size'], uploaded=''))
def job(it):
    res = os.path.join(IG.RES, IG.safe_stem(it['name']) + '.json')
    if os.path.exists(res):
        return it['name'], 'have'
    src = os.path.join(ORIGDIR, it['name'].replace('.MP4', '.mp4'))
    for _ in range(600):                       # wait for the download to land
        if os.path.exists(src) and not any(os.path.exists(src + s) for s in ('.dl', '.part01', '.part02')):
            break
        time.sleep(5)
    t = time.time()
    try:
        r = IG.process(it, src)
        IG.log(f"LOCAL PROC ok {it['name']} dur={r['meta']['duration']:.1f}s in {time.time()-t:.1f}s")
        return it['name'], 'ok'
    except Exception as e:
        IG.log(f"LOCAL PROC FAILED {it['name']}: {e}")
        return it['name'], f'fail {e}'
with ThreadPoolExecutor(3) as ex:
    for n, st in ex.map(job, items):
        print(n, st, flush=True)
