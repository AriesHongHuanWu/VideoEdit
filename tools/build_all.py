#!/usr/bin/env python3
"""Orchestrate the final build.  python3 -I build_all.py <project_dir> <stage> [stage...]
stages: fetch caches fx render audio encode verify all
project_dir contains edl.json, shots.json, fxjobs.json (tracks/masks) produced by make_edl.py.
"""
import json, os, subprocess, sys, time, math
from concurrent.futures import ProcessPoolExecutor
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
ROOT = '/tmp/claude-0/-home-user-VideoEdit/8531dbc8-a772-580f-8538-3f205e4051d8/scratchpad'
MANIFEST = os.path.join(ROOT, 'all_files.tsv')
SRC = os.path.join(ROOT, 'work', 'final_src'); LAYOUT = os.path.join(ROOT, 'work', 'layout')
MUSIC = os.path.join(ROOT, 'music', 'track.wav')

def log(msg):
    print(time.strftime('%H:%M:%S ') + msg, flush=True)

def manifest():
    m = {}
    for line in open(MANIFEST):
        p = line.rstrip('\n').split('\t')
        m[p[1].replace('.MP4', '')] = dict(id=p[2], size=int(p[3]))
    return m

def shot_span(shot):
    import cache as C
    times, spans = C.source_times(shot['src_in'], shot['n_frames'], shot.get('speed', 1.0))
    return max(0.0, min(times) - 0.06), max(t + s for t, s in zip(times, spans)) + 0.15

def stage_fetch(P):
    import sparse_fetch as SF
    os.makedirs(SRC, exist_ok=True)
    man = manifest(); shots = json.load(open(os.path.join(P, 'shots.json')))
    spans = {}
    for s in shots:
        spans.setdefault(s['clip'], []).append(shot_span(s))
    total = 0
    for clip, sp in sorted(spans.items()):
        info = man[clip]
        dst = os.path.join(SRC, clip + '.mp4')
        while True:
            try:
                lay, got = SF.fetch(info['id'], info['size'], dst, LAYOUT, spans=sp, log=log)
                total += got; break
            except SF.QuotaError:
                log(f'quota while fetching {clip}; waiting 120 s'); time.sleep(120)
            except Exception as e:
                log(f'fetch error {clip}: {e}; retry in 30 s'); time.sleep(30)
    log(f'fetch done: {total/1e6:.1f} MB for {len(spans)} clips')

def _build_cache(args):
    shot, P = args
    import cache as C
    cdir = os.path.join(P, 'cache'); ldir = os.path.join(P, 'luts')
    meta = os.path.join(cdir, shot['id'] + '.json')
    if os.path.exists(meta):
        m = json.load(open(meta))
        if m.get('n_frames') == shot['n_frames'] and m.get('src_in') == shot['src_in'] and m.get('spec') == json.dumps(shot, sort_keys=True):
            return shot['id'], 'cached'
    t = time.time()
    src = os.path.join(SRC, shot['clip'] + '.mp4')
    if os.environ.get('ROUGH'):
        src = os.path.join(ROOT, 'work', 'preview', shot['clip'] + '_540p.mp4')
    C.build(shot, src, cdir, ldir)
    m = json.load(open(meta)); m['spec'] = json.dumps(shot, sort_keys=True); json.dump(m, open(meta, 'w'))
    return shot['id'], f'{time.time()-t:.1f}s'

def stage_caches(P, workers=3):
    shots = json.load(open(os.path.join(P, 'shots.json')))
    with ProcessPoolExecutor(workers) as ex:
        for sid, st in ex.map(_build_cache, [(s, P) for s in shots]):
            log(f'cache {sid}: {st}')

def stage_fx(P):
    jobs = json.load(open(os.path.join(P, 'fxjobs.json')))
    for j in jobs:
        cache = os.path.join(P, 'cache', j['shot'] + '.mp4')
        if j['kind'] == 'track':
            out = os.path.join(P, j['out'])
            subprocess.run(['python3', '-I', os.path.join(TOOLS, 'track.py'), cache, out, str(j['x']), str(j['y']), str(j.get('box', 0.05)), str(j.get('start', 0))], check=True)
        elif j['kind'] == 'person':
            subprocess.run(['python3', '-I', os.path.join(TOOLS, 'masks.py'), 'person', cache, os.path.join(P, j['out'])], check=True)
        elif j['kind'] == 'motion':
            subprocess.run(['python3', '-I', os.path.join(TOOLS, 'masks.py'), 'motion', cache, os.path.join(P, j['out'])] + [str(v) for v in j['roi']] + [str(j.get('thresh', 28))], check=True)
        log(f"fx job {j['kind']} {j['shot']} done")

def _render_chunk(args):
    P, a, b, out, preview = args
    cmd = ['python3', '-I', os.path.join(TOOLS, 'render.py'), os.path.join(P, 'edl.json'), os.path.join(P, 'cache'), out, '--range', f'{a}:{b}']
    if preview:
        cmd.append('--preview')
    r = subprocess.run(cmd, capture_output=True, text=True)
    return out, r.returncode, r.stdout[-200:] + r.stderr[-800:]

def stage_render(P, workers=4, preview=False):
    edl = json.load(open(os.path.join(P, 'edl.json'))); n = edl['n_frames']
    bounds = [round(n * k / workers) for k in range(workers + 1)]
    outs = [os.path.join(P, f'chunk_{k}.mp4') for k in range(workers)]
    t = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for out, rc, msg in ex.map(_render_chunk, [(P, bounds[k], bounds[k + 1], outs[k], preview) for k in range(workers)]):
            log(f'chunk {os.path.basename(out)} rc={rc} {msg.strip()[-160:]}')
            if rc != 0:
                raise SystemExit(msg)
    lst = os.path.join(P, 'chunks.txt')
    open(lst, 'w').write(''.join(f"file '{o}'\n" for o in outs))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', os.path.join(P, 'video_master.mp4')], check=True)
    log(f'render done in {time.time()-t:.0f}s')

def stage_audio(P):
    subprocess.run(['python3', '-I', os.path.join(TOOLS, 'build_audio.py'), MUSIC, os.path.join(P, 'edl.json'), os.path.join(P, 'audio_master.wav')], check=True)

def stage_encode(P, out_name='ITALIA_montage.mp4'):
    v = os.path.join(P, 'video_master.mp4'); a = os.path.join(P, 'audio_master.wav'); out = os.path.join(P, out_name)
    x264 = 'keyint=120:min-keyint=60:bframes=3:ref=4:aq-mode=3:aq-strength=0.9:psy-rd=1.0,0.15:deblock=-1,-1'
    common = ['-c:v', 'libx264', '-profile:v', 'high', '-level:v', '4.2', '-preset', 'slow', '-b:v', '25M', '-maxrate', '32M', '-bufsize', '50M',
              '-pix_fmt', 'yuv420p', '-r', '60', '-x264-params', x264,
              '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv']
    plog = os.path.join(P, 'x264pass')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', v] + common + ['-pass', '1', '-passlogfile', plog, '-an', '-f', 'mp4', '/dev/null'], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', v, '-i', a, '-map', '0:v:0', '-map', '1:a:0'] + common +
                   ['-pass', '2', '-passlogfile', plog, '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-ac', '2',
                    '-movflags', '+faststart', '-metadata', 'title=postcards from ITALIA', '-shortest', out], check=True)
    log(f'encoded {out}')

def stage_verify(P, out_name='ITALIA_montage.mp4'):
    out = os.path.join(P, out_name)
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration,bit_rate:stream=codec_name,profile,width,height,avg_frame_rate,pix_fmt,bit_rate,sample_rate,channels,nb_frames',
                        '-of', 'json', out], capture_output=True, text=True)
    print(r.stdout)
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', out, '-map', '0:a:0', '-af', 'ebur128=peak=true:framelog=quiet', '-f', 'null', '-'], capture_output=True, text=True)
    print('\n'.join(l for l in r.stderr.splitlines()[-14:] if l.strip()))

if __name__ == '__main__':
    P = sys.argv[1]; stages = sys.argv[2:]
    if 'all' in stages:
        stages = ['fetch', 'caches', 'fx', 'render', 'audio', 'encode', 'verify']
    for st in stages:
        log(f'== stage {st}')
        if st == 'render_preview':
            stage_render(P, preview=True)
        else:
            globals()[f'stage_{st}'](P)
