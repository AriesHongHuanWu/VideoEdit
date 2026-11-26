#!/usr/bin/env python3
"""The edit: 'postcards from ITALIA'.  python3 -I make_edl.py <project_dir> [--rough]
Timeline is built on the fitted 165 BPM grid (beat = 0.3636 s); song starts at 11.648 s (bar downbeat).
Structure: hook (b0-4) -> postcards intro (b4-16) -> Milano/Venezia (b16-40) -> buildup (b40-48)
           -> ROMA card on the drop (b48) -> Roma + climax (b49.5-80) -> full red on the final hit (b80) -> end card.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from edl_lib import Timeline, fb, tb, FPB

P = sys.argv[1]; ROUGH = '--rough' in sys.argv
os.makedirs(P, exist_ok=True)
T = Timeline()
_shot = T.shot
def S(sid, clip, src_in, **kw):
    if sid in GRADE_EARLY:
        kw.setdefault('grade', {}).update(GRADE_EARLY[sid])
    return _shot(sid, clip, src_in, **kw)
GRADE_EARLY = {'m_stairs': {'exposure_mult': 1.15}, 'm_vault2': {'exposure_mult': 1.1}, 'v_gondolier': {'exposure_mult': 1.12}}

# ------------------------------------------------------------------ shots (clip, source in-point s, speed)
# Milano (19-20 May)
S('m_vault', 'DJI_0049', 11.2, note='Milano Centrale main hall, symmetric iron-and-glass vault')
S('m_vault2', 'DJI_0050', 0.4, note='Milano Centrale arch, locked-off (intro strip)')
S('m_prima', 'DJI_0062', 4.3, note='red Italo train, gold lettering under the glass vault')
S('m_italo', 'DJI_0061', 3.0, note='walk between two red Italo trains (push-in)')
S('m_stairs', 'DJI_0048', 9.6, note='staircase under skylit barrel vault')
S('m_shed', 'DJI_0060', 0.5, note='train shed, locked-off, travellers crossing')
# Venezia (20-22 May)
S('v_first', 'DJI_0069', 20.2, note='first view of Venice from Santa Lucia: lamppost + San Simeone Piccolo')
S('v_simeone', 'DJI_0074', 5.4, note='San Simeone Piccolo across the Grand Canal, water taxi crossing')
S('v_hud', 'DJI_0165', 0.2, note='Grand Canal from above, water taxis (HUD target)')
S('v_campanile', 'DJI_0113', 0.6, note='Campanile di San Marco, low angle, deep blue sky')
S('v_bow', 'DJI_0169', 0.6, note='gondola bow POV through a narrow canal')
S('v_rialto', 'DJI_0077', 1.6, note='Rialto Bridge framed by the vaporetto cabin')
S('v_moise', 'DJI_0084', 9.4, note='San Moise facade, tilt up')
S('v_gondolier', 'DJI_0139', 6.0, note='gondolier in striped shirt, covered pier, Salute dome behind (locked-off)')
S('v_clone', 'DJI_0154', 9.0, note='locked-off one-point canal, woman walking away (clone plate)')
S('v_bridges', 'DJI_0177', 5.6, note='gondola POV under a string of bridges')
S('v_arcade', 'DJI_0111', 6.0, note='Procuratie arcade walk, checkered floor')
S('v_taxi', 'DJI_0078', 27.6, note='wooden water taxi crossing the Grand Canal')
S('v_salute', 'DJI_0145', 2.6, note='Santa Maria della Salute facade, worm-eye')
S('v_doge', 'DJI_0118', 4.2, note="Doge's Palace and the Piazzetta")
S('v_lamp', 'DJI_0119', 1.2, note='Venetian lamppost against the lagoon sky')
S('v_gondolas', 'DJI_0099', 9.2, note='gondola rowed through a gondola-lined canal (locked-off)')
S('v_narrow', 'DJI_0182', 6.2, speed=[[0, 2.4], [0.15, 2.4], [0.32, 0.55]], note='gondola bow, narrow brick canal (speed ramp)')
S('v_motorboat', 'DJI_0159', 0.0, note='white motorboat sweeping across sparkling water')
S('v_bowsalute', 'DJI_0171', 8.0, note='gondola bow on the Grand Canal toward the Salute dome')
S('v_dome', 'DJI_0147', 26.2, note='Salute dome interior, symmetric')
S('v_hall', 'DJI_0041', 1.0, note='Milano Centrale ground-floor hall (spare)')

# ------------------------------------------------------------------ ROME (filled after logging)
ROME_FILE = os.path.join(os.path.dirname(__file__), 'rome_section.py')
rome = {}
if os.path.exists(ROME_FILE) and not ROUGH:
    exec(open(ROME_FILE).read(), {'T': T, 'S': S, 'fb': fb, 'tb': tb, 'rome': rome})
else:
    # rough-cut placeholders (Venice stand-ins) so the full timeline can be validated
    for k, (sid, clip, src) in enumerate([('r1', 'DJI_0136', 11.0), ('r2', 'DJI_0143', 2.5), ('r3', 'DJI_0098', 4.5), ('r4', 'DJI_0126', 9.5),
                                          ('r5', 'DJI_0093', 40.5), ('r6', 'DJI_0094', 1.7), ('r7', 'DJI_0164', 21.0), ('r8', 'DJI_0189', 0.0),
                                          ('r9', 'DJI_0211', 3.5), ('r10', 'DJI_0199', 0.0), ('r11', 'DJI_0075', 26.0), ('r12', 'DJI_0180', 0.5)]):
        S(sid, clip, src, note='ROUGH placeholder')
    rome['strip'] = 'r1'; rome['band'] = ['r2', 'r3', 'r4']; rome['hook_hud'] = 'v_hud'; rome['hook_inv'] = 'r9'

SOFT = {'type': 'soft_glow', 'amount': 0.6}            # 柔光 (Pro-Mist style diffusion)
def SCATTER(a=0.6):                                      # 散光 (star / streak light scatter from specular highlights)
    return {'type': 'light_scatter', 'amount': a}
DIFFUSE = {'v_bowsalute': SOFT, 'v_lamp': SOFT, 'v_first': dict(SOFT, amount=0.38, mist=0.05), 'v_simeone': dict(SOFT, amount=0.45), 'v_salute': dict(SOFT, amount=0.5),
           'v_rialto': dict(SOFT, amount=0.4), 'm_stairs': SCATTER(0.7), 'v_motorboat': SCATTER(0.65), 'v_hud': SCATTER(0.45),
           'v_bow': SCATTER(0.4), 'm_vault': dict(SOFT, amount=0.35)}
GRADE = {'m_stairs': {'exposure_mult': 1.15}, 'm_vault2': {'exposure_mult': 1.1}, 'v_gondolier': {'exposure_mult': 1.12}}

def seg_shot(sid, **kw):
    d = dict(type='shot', shot=sid); d.update(kw)
    fx = list(d.get('fx', []))
    if sid in DIFFUSE and not any(f['type'] in ('soft_glow', 'light_scatter') for f in fx):
        fx = [dict(DIFFUSE[sid])] + fx             # diffusion first, graphics on top stay crisp
    d['fx'] = fx
    return d

import math
def kicks(k0, k1):
    """local times (s) of kick hits (beat index mod 8 in {0,3,5}) inside [k0, k1)"""
    return [tb(k) - tb(k0) for k in range(math.ceil(k0), math.ceil(k1)) if k % 8 in (0, 3, 5)]

def hero(sid, k0, k1, fx=(), punch=True, **kw):
    """Hero shot with kick-synced 100->105% scale punches."""
    fx = list(fx)
    if punch:
        ts = [t for t in kicks(k0, k1) if t > 0.02]
        if ts:
            fx.append({'type': 'punch', 'times': ts, 'amount': 0.045})
    return seg_shot(sid, fx=fx, **kw)

# ------------------------------------------------------------------ HOOK  (b0 - b4)
hook_hud = rome.get('hook_hud', 'v_hud')
T.until_beat(2, hero(hook_hud, 0, 2, cache_offset=rome.get('hook_hud_off', 30), zoom=[[0, 1.0], [tb(2), 1.05, 'linear']],
                     fx=[{'type': 'flash_pop', 'at': 0.0}, {'type': 'hud', 'track': 'hook', 'label': rome.get('hook_label', 'TRK_01  TAXI'), 't0': 0.0, 't1': 9}]))
T.tracks['hook'] = os.path.join(P, 'track_hook.json')
T.sound(0.0, 'boom', gain=0); T.sound(0.0, 'impact', gain=-1); T.sound(0.07, 'click', gain=-7, f=3600); T.sound(0.18, 'chatter', dur=0.35, gain=-12)
T.until_beat(3, hero('m_prima', 2, 3, zoom=[[0, 1.0], [tb(1), 1.10, 'out']],
                     fx=[{'type': 'label', 'text': 'MILANO CENTRALE', 'sub': '20.05.2026', 'idx': '01', 't0': 0.06, 't1': 9}]))
T.trans('redwipe', 7, 7, dir=1)                                      # red matte sweeps across and reveals the red train
T.sound(tb(2) - 0.06, 'whoosh', dur=0.3, gain=-9, pan_from=-0.8, pan_to=0.8, peak_pos=0.4)
T.until_beat(4, hero('m_italo', 3, 4, cache_offset=0, zoom=[[0, 1.0], [tb(1), 1.06, 'linear']]))
T.trans('zoom', 8, 9, z=1.5)                                         # zoom-through: train push -> platform push
T.sound(tb(3) - 0.05, 'whoosh', dur=0.28, gain=-10, pan_from=0, pan_to=0, peak_pos=0.55)

# ------------------------------------------------------------------ INTRO "postcards from ITALIA" (b4 - b16)
strips = [{'shot': 'm_vault2'}, {'shot': 'v_simeone', 'offset': 20}, {'shot': 'v_bow'}, {'shot': 'v_campanile', 'cx': 0.56},
          {'shot': 'v_rialto'}, {'shot': rome.get('strip', 'v_salute')}]
band = [{'shot': 'v_hud', 'offset': 40}, {'shot': rome['band'][0]}, {'shot': 'v_bowsalute'}, {'shot': rome['band'][1]},
        {'shot': 'v_gondolas'}, {'shot': rome['band'][2]}]
T.until_beat(16, dict(type='intro', base={'shot': 'm_italo', 'offset': fb(4) - fb(3)}, strips=strips, band=band,
                      p1=tb(6.5) - tb(4), p2=tb(7.5) - tb(4), p3=tb(10) - tb(4), band_step=tb(11) - tb(10), stagger=0.06,
                      title_size=330, halation=0.16))
T.sound(tb(4) + 0.10, 'whoosh', dur=0.35, gain=-12, pan_from=-0.8, pan_to=0.6)
T.sound(tb(7.2), 'whoosh', dur=0.35, gain=-12, pan_from=0.5, pan_to=-0.5, peak_pos=0.5)
T.sound(tb(8), 'chatter', dur=tb(10) - tb(8), rate=24, gain=-12)
T.sound(tb(10), 'boom', gain=-6, dur=1.2, f0=55, f1=30); T.sound(tb(10), 'click', gain=-7, f=2900)

# ------------------------------------------------------------------ MILANO (b16 - b23)
T.until_beat(18, hero('m_vault', 16, 18, zoom=[[0, 1.0], [tb(2), 1.07, 'linear']],
                      fx=[{'type': 'flash_pop', 'at': 0.0}, {'type': 'title_top', 'text': 'MILANO', 't0': 0.03, 't1': 9, 'margin': 40}]))
T.sound(tb(16), 'impact', gain=-5, bright=0.7); T.sound(tb(16) + 0.03, 'whoosh', dur=0.25, gain=-12, pan_from=0, pan_to=0, peak_pos=0.3)
T.until_beat(19.5, hero('m_stairs', 18, 19.5, zoom=[[0, 1.0], [tb(1.5), 1.08, 'linear']], fx=[{'type': 'bw'}]))
T.trans('flash', 3, 4)                                               # bloom into the black-and-white staircase
T.sound(tb(18), 'shutter', gain=-10, seed=64)
T.until_beat(21, hero('v_hall', 19.5, 21, zoom=[[0, 1.02], [tb(1.5), 1.09, 'linear']]))
T.trans('zoom', 7, 8, z=1.35)                                        # push-in continuity
T.sound(tb(19.5) - 0.04, 'whoosh', dur=0.25, gain=-11, pan_from=0, pan_to=0, peak_pos=0.55)
T.until_beat(23, hero('m_shed', 21, 23, fx=[{'type': 'letterbox', 't0': 0.0, 't1': tb(1.6), 'h': 140}]))
T.trans('whip', 6, 6, dir=-1)
T.sound(tb(21), 'whoosh', dur=0.3, gain=-11, pan_from=0, pan_to=0, peak_pos=0.35)
# ------------------------------------------------------------------ VENEZIA (b23 - b40)
T.until_beat(24, hero('v_first', 23, 24))
T.trans3d('cube', n=11, direction=1)                                 # 3D cube turn: Milano -> Venezia
T.sound(tb(23) - 0.02, 'whoosh', dur=0.42, gain=-8, pan_from=-0.8, pan_to=0.8, peak_pos=0.5); T.sound(tb(23) + 0.16, 'impact', gain=-12, bright=0.4)
T.until_beat(26, dict(type='split', shot='v_bow', cache_offset=0, text='VENEZIA', sub='CANAL GRANDE', size=165, inset_scale=0.54,
                      inset_cx=575, text_x=1125, expand_out=0.16))
T.trans('redwipe', 7, 0, dir=1, reveal=False)                        # red sweep becomes the card
T.sound(tb(24) - 0.05, 'whoosh', dur=0.3, gain=-10, pan_from=-0.7, pan_to=0.7, peak_pos=0.5); T.sound(tb(24), 'impact', gain=-8, bright=0.5)
T.until_beat(28.5, hero('v_bow', 26, 28.5, cache_offset=fb(26) - fb(24), zoom=[[0, 1.0], [tb(2.5), 1.06, 'linear']]))   # inset snaps to full, ride continues
T.sound(tb(26) - 0.1, 'whoosh', dur=0.25, gain=-12, pan_from=0, pan_to=0, peak_pos=0.6)
T.until_beat(30, hero('v_campanile', 28.5, 30, fx=[{'type': 'duotone', 't0': 0.0, 't1': 4 / 60}]))
T.trans('glitch', 3, 3)
T.sound(tb(28.5), 'click', gain=-9, f=2200)
T.until_beat(32, hero('v_gondolier', 30, 32))
T.cutout('sky_reveal', n_before=16)                                  # the next shot opens up inside the Campanile's sky
T.title3d(text='GONDOLA', size=330, depth=85, t0=0.02, t1=9, yaw=[[0, 32], [tb(2), -8, 'out']], pitch=[[0, -6], [tb(2), 3, 'out']],
          scale=[[0, 0.82], [0.18, 1.0, 'outexpo']], pos=[[0, [960, 600]], [0.25, [960, 470], 'out']], opacity=[[0, 0.0], [0.08, 1.0]],
          sweep=[[0.15, 0.0], [tb(2), 1.0, 'linear']], behind_matte=os.path.join(P, 'mask_gondolier'))
T.sound(tb(30) - 0.2, 'whoosh', dur=0.3, gain=-11, pan_from=0, pan_to=0, peak_pos=0.7); T.sound(tb(30) + 0.05, 'boom', gain=-10, dur=0.9, f0=70, f1=40)
T.until_beat(34, hero('v_clone', 32, 34, cache_offset=110, punch=False, fx=[{'type': 'clone', 'offsets': [-80, 90], 'appear': [tb(0.5), tb(1)],
                                                                             'mask_dir': os.path.join(P, 'mask_clone'), 't0': 0, 't1': 9}]))
T.cutout('subject_hold', n_before=8, n_after=24, mask_dir=os.path.join(P, 'mask_gondolier'), drift=-90)   # gondolier cut-out stays while the canal arrives
T.sound(tb(32.5), 'click', gain=-8, f=2600); T.sound(tb(33), 'click', gain=-8, f=3100)
T.until_beat(36, hero('v_bridges', 34, 36, zoom=[[0, 1.0], [tb(2), 1.06, 'linear']], fx=[{'type': 'red_inset', 't0': 0.0, 't1': tb(1), 'scale': 0.72}]))
T.trans('whip', 6, 6, dir=1)
T.sound(tb(34), 'whoosh', dur=0.25, gain=-11, pan_from=0, pan_to=0); T.sound(tb(35), 'impact', gain=-12, bright=0.4)
T.until_beat(38, hero('v_arcade', 36, 38, zoom=[[0, 1.0], [tb(2), 1.07, 'linear']],
                      fx=[{'type': 'text', 'text': 'SAN MARCO', 'size': 290, 'x': 960, 'y': 560, 'mode': 'exclusion', 't0': 0.03, 't1': 9,
                           'tracking': 0, 'tracking_to': 26, 'rise': 50}]))
T.trans('zoom', 7, 8, z=1.4)
T.sound(tb(36) - 0.04, 'whoosh', dur=0.25, gain=-11, pan_from=0, pan_to=0, peak_pos=0.55)
T.until_beat(40, hero('v_salute', 38, 40, zoom=[[0, 1.0], [tb(2), 1.05, 'linear']],
                      fx=[{'type': 'label', 'text': 'SANTA MARIA DELLA SALUTE', 'sub': '21.05.2026', 'idx': '02', 't0': 0.12, 't1': 9}]))
T.trans3d('swing', n=10, direction=1)                                # the arcade swings open like a door onto the Salute
T.sound(tb(38) - 0.1, 'whoosh', dur=0.36, gain=-10, pan_from=-0.6, pan_to=0.6, peak_pos=0.55)
# ------------------------------------------------------------------ BUILDUP (b40 - b48): acceleration with designed hits
T.until_beat(41, hero('v_taxi', 40, 41, fx=[{'type': 'hud', 'track': 'taxi2', 'label': 'TRK_02  TAXI', 't0': 0.0, 't1': 9}]))
T.tracks['taxi2'] = os.path.join(P, 'track_taxi2.json')
T.trans3d('flip', n=9, direction=1)                                  # card flip into the buildup
T.sound(tb(40) - 0.05, 'whoosh', dur=0.32, gain=-9, pan_from=0.7, pan_to=-0.7, peak_pos=0.5)
T.until_beat(43, dict(type='vsplit', panels=[{'shot': 'v_doge', 'enter': 0.0, 'from': 'none'}, {'shot': 'v_lamp', 'enter': tb(0.5), 'from': 'top'},
                                             {'shot': 'v_gondolas', 'enter': tb(1.0), 'from': 'bottom'}], expand=(1, tb(1.6)), expand_dur=0.14))
T.trans('lb', 6, 7)
for k, kk in enumerate([41.5, 42]):
    T.sound(tb(kk), 'whoosh', dur=0.18, gain=-14, pan_from=0, pan_to=0, peak_pos=0.6, seed=30 + k)
T.until_beat(44, hero('v_narrow', 43, 44, zoom=[[0, 1.0], [tb(1), 1.08, 'linear']]))
T.trans('glitch', 3, 3)
T.until_beat(46, seg_shot('v_motorboat', fx=[{'type': 'shutter', 't0': 0.0, 't1': 9, 'hold': tb(0.25)}]))
T.trans('flash', 3, 3)
for k in range(8):
    T.sound(tb(44 + 0.25 * k), 'shutter', gain=-10, seed=70 + k)
T.add(T.cursor, fb(48) - 2, hero('v_bowsalute', 46, 48, fx=[{'type': 'overexpose', 't0': tb(1.0), 't1': tb(2) - 2 / 60, 'shape': 'up', 'amount': 1.0}]))
T.trans('whip', 5, 6, dir=-1)
T.frames(2, dict(type='card', card='black', fx=[{'type': 'black'}]))
# ------------------------------------------------------------------ DROP: ROMA card (b48)
T.until_beat(49.5, dict(type='card', card='roma', text='', size=600, halation=0.12))
T.title3d(text='ROMA', size=470, depth=95, t0=0.0, t1=9, yaw=[[0, -26], [0.22, -4, 'out'], [tb(1.5), 3, 'linear']], pitch=[[0, 10], [0.22, 2, 'out']],
          scale=[[0, 1.45], [0.10, 1.0, 'outexpo']], pos=[[0, [960, 560]]], sweep=[[0.04, 0.0], [tb(1.5), 1.0, 'linear']],
          side=(0.84, 0.80, 0.80), side_back=(0.42, 0.10, 0.08), shadow=0.55)
T.sound(tb(48), 'boom', gain=0, dur=1.8); T.sound(tb(48), 'impact', gain=0, dur=1.5)

# ------------------------------------------------------------------ ROMA + CLIMAX (b49.5 - b80)
if 'build' in rome:
    rome['build'](T, fb, tb, seg_shot, hero, kicks, P)
else:
    # rough placeholders (structure only): hero shots with transitions, then accelerating climax
    plan = [('r5', 51.5, None), ('r1', 53.5, 'zoom'), ('r6', 55, 'whip'), ('r2', 57, 'redwipe'), ('r7', 59, 'lb'), ('r3', 60, 'glitch'),
            ('r8', 61, 'whip'), ('r4', 63, 'flash'), ('r10', 64, 'zoom'), ('r11', 66, 'whip'), ('r12', 67, 'whip'), ('r9', 68, 'glitch'),
            ('r1', 69, 'whip'), ('r2', 70, 'whip'), ('r3', 70.5, None), ('r4', 71, None), ('r5', 71.5, None), ('r6', 72, None),
            ('r7', 73, 'zoom'), ('r8', 74, 'whip'), ('r10', 75, 'whip'), ('r11', 76, 'flash'), ('r12', 77, 'whip'), ('r9', 78, 'glitch'),
            ('r1', 79, 'whip'), ('r2', 80, 'zoom')]
    k = 49.5
    for sid, k2, tr in plan:
        T.until_beat(k2, hero(sid, k, k2))
        if tr:
            T.trans(tr, 6, 6, dir=1 if int(k2) % 2 else -1)
        k = k2
# ------------------------------------------------------------------ FINAL HIT: full red, then end card
T.frames(6, dict(type='card', card='red', halation=0.0))
T.sound(tb(80), 'boom', gain=0, dur=2.2); T.sound(tb(80), 'impact', gain=0, dur=2.0)
END_FRAMES = 150
T.frames(END_FRAMES, dict(type='card', card='end', places=rome.get('places', 'MILANO  ·  VENEZIA  ·  ROMA'), title3d=True,
                          dates=rome.get('dates', 'MAY 2026'), size=330, halation=0.1, grain=0.026))
T.title3d(text='ITALIA', size=300, depth=70, t0=0.0, t1=99, yaw=[[0, 18], [0.6, -3, 'out'], [END_FRAMES / 60, -9, 'linear']], pitch=[[0, -4]],
          scale=[[0, 1.12], [0.5, 1.0, 'outexpo']], pos=[[0, [960, 500]]], opacity=[[0, 0.0], [0.15, 1.0]],
          sweep=[[0.3, 0.0], [1.6, 1.0, 'linear']], side=(0.80, 0.74, 0.76), side_back=(0.28, 0.05, 0.08), shadow=0.6)
n_frames = T.cursor

audio = dict(song_start=11.648, dur=n_frames / 60 + 0.05,
             lpf_intro=[tb(6.3), tb(7.5), tb(10), tb(16), 420],
             hpf_build=[tb(40), tb(48) - 2 / 60, 25, 1100],
             gaps=[[tb(48) - 2 / 60, tb(48)], [tb(80) - 2 / 60, tb(80)]],
             lowdip=[tb(78), tb(80) - 2 / 60, 320],
             outro=[tb(80) + 0.25, tb(80) + 1.9, 280, tb(80) + 1.2, n_frames / 60],
             lufs=-14.0, tp=-1.5, sc_depth=-10.0, sc_full=-2.0)
T.sound(tb(48) - 2 / 60, 'riser', dur=tb(48) - tb(40.2), gain=-4)
post = dict(halation=0.2, vignette=0.16, grain=0.022)
edl, shots = T.export(os.path.join(P, 'edl.json'), os.path.join(P, 'shots.json'), audio, post, n_frames)
# fx jobs (tracks / mattes) for build_all
fxjobs = [dict(kind='track', shot='v_hud', out='track_taxi.json', x=0.745, y=0.47, box=0.05),
          dict(kind='track', shot='v_taxi', out='track_taxi2.json', x=0.80, y=0.66, box=0.06, start=9),
          dict(kind='person', shot='v_gondolier', out='mask_gondolier'),
          dict(kind='motion', shot='v_clone', out='mask_clone', roi=[0.55, 0.3, 1.0, 1.0], thresh=26)]
fxjobs += rome.get('fxjobs', [dict(kind='track', shot=hook_hud, out='track_hook.json', x=0.745, y=0.47, box=0.05, start=30)])
json.dump(fxjobs, open(os.path.join(P, 'fxjobs.json'), 'w'), indent=1)
print(f'EDL: {len(edl["segments"])} segments, {n_frames} frames ({n_frames/60:.2f}s), {len(shots)} cached shots, {len(edl["sfx"])} sfx')
