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
        if seg['type'] == 'intro':
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
