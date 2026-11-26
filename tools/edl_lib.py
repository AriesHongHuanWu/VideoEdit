#!/usr/bin/env python3
"""Helpers for building the beat-synced EDL (edit decision list)."""
import json, math

FPS = 60
BPM = 165.0
BEAT = 60.0 / BPM                  # 0.363636 s
FPB = FPS * BEAT                   # 21.818 frames per beat
SONG_START = 11.648                # song time of edit t=0 (bar downbeat on the fitted grid)

def fb(k):
    """beat -> frame index (rounded to nearest frame)"""
    return int(round(k * FPB))

def tb(k):
    return fb(k) / FPS

class Timeline:
    def __init__(self):
        self.segs = []; self.shots = {}; self.sfx = []; self.cursor = 0; self.tracks = {}; self.notes = []

    def shot(self, sid, clip, src_in, speed=1.0, crop=None, grade=None, note=''):
        self.shots[sid] = dict(id=sid, clip=clip, src_in=src_in, speed=speed, crop=crop, grade=grade or {}, need=0, note=note)
        return sid

    def _need(self, sid, nframes):
        self.shots[sid]['need'] = max(self.shots[sid]['need'], nframes)

    def add(self, f0, f1, seg):
        assert f0 == self.cursor, f'gap/overlap at frame {f0} (cursor {self.cursor}) {seg}'
        assert f1 > f0, seg
        seg = dict(seg); seg['f0'] = f0; seg['f1'] = f1; seg['dur'] = (f1 - f0) / FPS
        self.segs.append(seg); self.cursor = f1
        n = f1 - f0
        if seg['type'] in ('shot', 'split') and 'shot' in seg:
            off = seg.get('cache_offset', 0)
            extra = 0
            for fx in seg.get('fx', []):
                if fx['type'] == 'clone':
                    extra = max(extra, max(fx['offsets']))
            self._need(seg['shot'], off + n + extra + 2)
        if seg['type'] == 'vsplit':
            for p in seg['panels']:
                self._need(p['shot'], p.get('offset', 0) + n + 2)
        if seg['type'] == 'intro':
            if seg.get('base'):
                self._need(seg['base']['shot'], seg['base'].get('offset', 0) + int(seg['p2'] * FPS) + 4)
            for st in seg['strips']:
                self._need(st['shot'], st.get('offset', 0) + int(seg['p2'] * FPS) + 4)
            for i, bs in enumerate(seg['band']):
                self._need(bs['shot'], bs.get('offset', 0) + int(seg['band_step'] * FPS) + 4)
        return seg

    def beats(self, k0, k1, seg):
        return self.add(fb(k0), fb(k1), seg)

    def frames(self, n, seg):
        return self.add(self.cursor, self.cursor + n, seg)

    def until_beat(self, k1, seg):
        return self.add(self.cursor, fb(k1), seg)

    def trans(self, kind, n_out=6, n_in=6, **kw):
        """Attach a designed transition across the cut between the last two segments."""
        A, B = self.segs[-2], self.segs[-1]
        dA = A['dur']; o = n_out / FPS; i = n_in / FPS
        fa, fb_ = A.setdefault('fx', []), B.setdefault('fx', [])
        d = kw.get('dir', 1)
        if kind == 'whip':
            fa.append(dict(type='whip', t0=dA - o, t1=dA, dx=-d * 1750, out=True))
            fb_.append(dict(type='whip', t0=0.0, t1=i, dx=d * 1750))
        elif kind == 'zoom':
            fa.append(dict(type='push_out', t0=dA - o, t1=dA, z1=kw.get('z', 1.45)))
            fb_.append(dict(type='zoom_out', t0=0.0, t1=i, z0=kw.get('z', 1.45)))
        elif kind == 'redwipe':
            if n_out > 0:
                fa.append(dict(type='redpanel', mode='cover', t0=dA - o, t1=dA, dir=d))
            if kw.get('reveal', True):
                fb_.append(dict(type='redpanel', mode='reveal', t0=0.0, t1=i, dir=d, label=kw.get('label'), label_size=kw.get('label_size', 150)))
        elif kind == 'lb':
            fa.append(dict(type='lb_close', t0=dA - o, t1=dA))
            fb_.append(dict(type='lb_open', t0=0.0, t1=i))
        elif kind == 'flash':
            fa.append(dict(type='overexpose', t0=dA - o, t1=dA, shape='up', amount=1.0))
            fb_.append(dict(type='flash_pop', at=0.0))
        elif kind == 'glitch':
            fa.append(dict(type='glitch', t0=dA - o, t1=dA, strength=0.8))
            fb_.append(dict(type='glitch', t0=0.0, t1=i, strength=0.8))
        return kind

    def trans3d(self, kind='cube', n=10, direction=1, samples=5):
        """3D transition straddling the cut (n frames each side). Outgoing shot gets n extra cached frames,
        incoming shot is pre-rolled by n frames so both keep moving through the transition."""
        A, B = self.segs[-2], self.segs[-1]
        B['t3d'] = dict(kind=kind, n=n, dir=direction, samples=samples)
        if A['type'] in ('shot', 'split') and 'shot' in A:
            self._need(A['shot'], A.get('cache_offset', 0) + (A['f1'] - A['f0']) + n + 2)
        if B['type'] in ('shot', 'split') and 'shot' in B:
            B['cache_offset'] = B.get('cache_offset', 0) + n
            self._need(B['shot'], B['cache_offset'] + (B['f1'] - B['f0']) + 2)
        return kind

    def cutout(self, kind, n_before=10, n_after=0, mask_dir=None, **kw):
        """Cut-out (matte) transition from the previous segment into the last one."""
        B = self.segs[-1]
        B['tcut'] = dict(kind=kind, n_before=n_before, n_after=n_after, mask_dir=mask_dir, **kw)
        return kind

    def title3d(self, **fx):
        self.segs[-1].setdefault('fx3d', []).append(fx)

    def sound(self, t, typ, **kw):
        d = dict(t=t, type=typ); d.update(kw); self.sfx.append(d)

    def export(self, edl_path, shots_path, audio, post, n_frames):
        assert self.cursor == n_frames, (self.cursor, n_frames)
        edl = dict(n_frames=n_frames, fps=FPS, segments=self.segs, tracks=self.tracks, post=post, audio=audio, sfx=sorted(self.sfx, key=lambda e: e['t']))
        json.dump(edl, open(edl_path, 'w'), indent=1)
        shots = []
        for sid, s in self.shots.items():
            if s['need'] <= 0:
                continue
            s = dict(s); s['n_frames'] = s.pop('need')
            shots.append(s)
        json.dump(shots, open(shots_path, 'w'), indent=1)
        return edl, shots
