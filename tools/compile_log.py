#!/usr/bin/env python3
"""Compile the footage log (素材日誌) from reviewer JSONL + ingest metadata.
python3 -I compile_log.py <scratch_root> <out_dir>
"""
import csv, glob, json, os, sys

root, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
logs = {}
for f in sorted(glob.glob(os.path.join(root, 'log', '*.jsonl'))):
    for line in open(f):
        if line.strip():
            d = json.loads(line); logs[d['file']] = d
meta = {}
for f in glob.glob(os.path.join(root, 'work', 'results', '*.json')):
    r = json.load(open(f)); m = r.get('meta', {})
    if m.get('name'):
        meta[m['name']] = m
rows = []
for name in sorted(set(list(logs) + list(meta))):
    d = logs.get(name, {}); m = meta.get(name, {})
    rows.append(dict(
        file=name,
        shot=(d.get('shot') or (m.get('creation_time') or '')[:16]).replace('T', ' '),
        duration=f"{m.get('duration', d.get('duration', 0)):.1f}",
        format=f"{m.get('width', '')}x{m.get('height', '')} {m.get('fps', '')} {m.get('pix_fmt', '')}" if m else '',
        location=d.get('location', 'unknown' if d else 'not logged'),
        content=d.get('content', m.get('note', '')),
        camera_motion=d.get('camera_motion', ''),
        composition=d.get('composition', ''),
        clarity=d.get('clarity', ''),
        best=' / '.join(f"{b['start']:.1f}-{b['end']:.1f}s ({b.get('why', '')})" for b in d.get('best_moments', [])),
        tags=','.join(d.get('tags', [])),
        use_score=d.get('use_score', ''),
        notes=d.get('notes', ''),
    ))
with open(os.path.join(out, 'footage_log.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
md = ['# 素材日誌 Footage log', '',
      f'{len(rows)} clips. Composition / clarity are 1–5; use score is 1–10. Camera motion is measured from keyframes '
      '(0.5–2 s apart) and checked visually. Locations are named only when a landmark or sign in frame confirms them.', '']
day = None
for r in sorted(rows, key=lambda r: (r['shot'], r['file'])):
    d = r['shot'][:10]
    if d != day:
        day = d
        md += ['', f'## {d or "unknown date"}', '', '| File | Dur | Location | Content | Camera motion | Comp | Clarity | Best moments | Score |',
               '|---|---|---|---|---|---|---|---|---|']
    esc = lambda s: str(s).replace('|', '/').replace('\n', ' ')
    md.append(f"| {r['file']} | {r['duration']}s | {esc(r['location'])} | {esc(r['content'])} | {esc(r['camera_motion'])} | "
              f"{r['composition']} | {r['clarity']} | {esc(r['best'])} | {r['use_score']} |")
open(os.path.join(out, 'footage_log.md'), 'w').write('\n'.join(md) + '\n')
print('rows', len(rows), 'logged', sum(1 for r in rows if r['location'] != 'not logged'))
