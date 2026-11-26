#!/usr/bin/env python3
"""Quota-friendly ingest for the remaining clips: fetch only keyframes (byte ranges) from Drive into
sparse local files, then run the same preview/metrics/contact-sheet analysis as ingest.py.

python3 -I ingest_sparse.py <manifest.tsv> <workdir>
"""
import json, os, re, subprocess, sys, time, traceback
sys.path.insert(0, os.path.dirname(__file__))
MANIFEST, WORK = sys.argv[1], sys.argv[2]
sys.argv = [sys.argv[0], MANIFEST, WORK]
import ingest as IG
import sparse_fetch as SF

SPARSE = os.path.join(WORK, 'sparse'); LAYOUT = os.path.join(WORK, 'layout')
os.makedirs(SPARSE, exist_ok=True); os.makedirs(LAYOUT, exist_ok=True)

# patch the frame extraction in IG.process to use demuxer-level keyframe discard (holes are never read)
_orig_run = subprocess.run
def _run(cmd, *a, **k):
    if isinstance(cmd, list) and cmd and cmd[0] == 'ffmpeg' and '-skip_frame' in cmd:
        i = cmd.index('-skip_frame'); cmd = cmd[:i] + ['-discard:v', 'nokey'] + cmd[i + 2:]
    if isinstance(cmd, list) and cmd and cmd[0] == 'ffmpeg' and 'fps=6' in ' '.join(cmd):
        # short-clip full decode is impossible on sparse files -> keyframes instead
        j = cmd.index('-i')
        cmd = cmd[:j] + ['-discard:v', 'nokey'] + cmd[j:]
        cmd = [c.replace('fps=6,', '') for c in cmd]
        if '-fps_mode' not in cmd:
            cmd = cmd[:-1] + ['-fps_mode', 'passthrough', cmd[-1]]
    return _orig_run(cmd, *a, **k)
IG.subprocess.run = _run

def main():
    items = IG.load_manifest()
    todo = [it for it in items if not os.path.exists(os.path.join(IG.RES, IG.safe_stem(it['name']) + '.json'))]
    # folder 2 (shot after Venice -> likely Rome) first, then folder 1
    todo.sort(key=lambda it: (0 if it['folder'].startswith('F2') else 1, it['name']))
    IG.log(f"SPARSE START todo={len(todo)}")
    hold = {}          # name -> not-before time
    streak = 0
    while todo:
        now = time.time()
        ready = [it for it in todo if hold.get(it['name'], 0) <= now]
        if not ready:
            time.sleep(30); continue
        it = ready[0]
        dst = os.path.join(SPARSE, IG.safe_stem(it['name']) + '.mp4')
        try:
            t = time.time()
            lay = SF.get_layout(it['id'], it['size'], LAYOUT)
            dur = lay['video']['dts'][-1] if lay['video']['dts'] else 0
            nth = 1 if dur <= 6 else (2 if dur <= 15 else 4)
            lay, got = SF.fetch(it['id'], it['size'], dst, LAYOUT, keyframes_only=True, every_nth_key=nth, log=IG.log)
            IG.log(f"SPARSE ok {it['name']} {got/1e6:.1f}MB keyframes (1/{nth}) in {time.time()-t:.1f}s")
            streak = 0
        except SF.QuotaError:
            streak += 1
            hold[it['name']] = time.time() + 900
            IG.log(f"SPARSE quota on {it['name']} (streak {streak}); hold 15 min")
            if streak >= 3:
                IG.log("SPARSE global pause 10 min")
                time.sleep(600); streak = 0
            else:
                time.sleep(30)
            continue
        except Exception as e:
            IG.log(f"SPARSE fetch FAILED {it['name']}: {e}")
            hold[it['name']] = time.time() + 300
            time.sleep(10)
            continue
        todo.remove(it)
        try:
            r = IG.process(it, dst)
            IG.log(f"PROC ok {it['name']} dur={r['meta']['duration']:.1f}s frames={len(r['times'])} in {r['proc_sec']:.1f}s (sparse)")
        except Exception as e:
            IG.log(f"PROC FAILED {it['name']}: {e} {traceback.format_exc()[-400:]!r}")
        time.sleep(15)
    IG.log("SPARSE ALL DONE")

if __name__ == '__main__':
    main()
