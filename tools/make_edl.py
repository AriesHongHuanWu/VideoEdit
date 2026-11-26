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
S('v_narrow', 'DJI_0182', 6.2, note='gondola bow, narrow brick canal')
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

# ------------------------------------------------------------------ HOOK  (b0 - b4)
hook_hud = rome.get('hook_hud', 'v_hud')
T.add(0, fb(1), seg_shot(hook_hud, cache_offset=rome.get('hook_hud_off', 30), zoom=[[0, 1.0], [0.36, 1.04, 'linear']],
                         fx=[{'type': 'flash_pop', 'at': 0.0}, {'type': 'hud', 'track': 'hook', 'label': rome.get('hook_label', 'TRK_01'), 't0': 0.0, 't1': 1.0}]))
T.tracks['hook'] = os.path.join(P, 'track_hook.json')
T.sound(0.0, 'boom', gain=0); T.sound(0.0, 'impact', gain=-1); T.sound(0.06, 'click', gain=-8, f=3600); T.sound(0.10, 'chatter', dur=0.25, gain=-12)
T.frames(4, dict(type='card', card='red'))
T.sound(tb(1), 'click', gain=-10, f=2400)
T.until_beat(1.5, seg_shot('m_prima', fx=[{'type': 'duotone'}]))
T.sound(tb(1) + 4 / 60, 'shutter', gain=-9)
T.until_beat(2, seg_shot(rome.get('hook_inv', 'v_dome'), fx=[{'type': 'bw_invert'}]))
T.sound(tb(1.5), 'shutter', gain=-9, seed=62)
T.frames(3, dict(type='card', card='white', fx=[{'type': 'white'}]))
T.until_beat(3, seg_shot('v_clone', cache_offset=0, fx=[{'type': 'zoom_out', 't0': 0.0, 't1': 0.28, 'z0': 1.6}]))
T.sound(tb(2) + 0.02, 'whoosh', dur=0.32, gain=-9, pan_from=0.0, pan_to=0.0, peak_pos=0.25)
T.until_beat(3.5, seg_shot('v_simeone', fx=[{'type': 'letterbox', 't0': 0.0, 't1': 0.14, 'h': 150}]))
T.sound(tb(3), 'whoosh', dur=0.28, gain=-10)
T.until_beat(4, seg_shot('m_vault', cache_offset=50, fx=[{'type': 'red_invert'}]))
T.sound(tb(3.5), 'shutter', gain=-9, seed=63)

# ------------------------------------------------------------------ INTRO "postcards from ITALIA" (b4 - b16)
strips = [{'shot': 'm_vault2'}, {'shot': 'm_prima', 'offset': 10}, {'shot': 'v_simeone', 'offset': 20}, {'shot': 'v_bow'},
          {'shot': 'v_campanile', 'cx': 0.56}, {'shot': rome.get('strip', 'v_rialto')}]
band = [{'shot': 'v_hud', 'offset': 40}, {'shot': rome['band'][0]}, {'shot': 'v_bowsalute'}, {'shot': rome['band'][1]},
        {'shot': 'v_gondolas'}, {'shot': rome['band'][2]}]
T.until_beat(16, dict(type='intro', strips=strips, band=band, p1=tb(6.5) - tb(4), p2=tb(7.5) - tb(4), p3=tb(10) - tb(4),
                      band_step=tb(11) - tb(10), stagger=0.05, title_size=330, halation=0.16))
T.sound(tb(4) + 0.12, 'whoosh', dur=0.35, gain=-12, pan_from=-0.8, pan_to=0.6)
T.sound(tb(7.2), 'whoosh', dur=0.35, gain=-12, pan_from=0.5, pan_to=-0.5, peak_pos=0.5)
T.sound(tb(8), 'chatter', dur=tb(10) - tb(8), rate=24, gain=-12)
T.sound(tb(10), 'boom', gain=-6, dur=1.2, f0=55, f1=30); T.sound(tb(10), 'click', gain=-7, f=2900)

# ------------------------------------------------------------------ MILANO (b16 - b23)
T.until_beat(18, seg_shot('m_vault', zoom=[[0, 1.0], [tb(2), 1.07, 'linear']],
                         fx=[{'type': 'flash_pop', 'at': 0.0}, {'type': 'title_top', 'text': 'MILANO', 't0': 0.03, 't1': 9, 'margin': 40}]))
T.sound(tb(16), 'impact', gain=-5, bright=0.7); T.sound(tb(16) + 0.03, 'whoosh', dur=0.25, gain=-12, pan_from=0, pan_to=0, peak_pos=0.3)
T.until_beat(19, seg_shot('m_prima', zoom=[[0, 1.0], [tb(1), 1.12, 'out']]))                       # camera-motion push
T.until_beat(20.5, seg_shot('m_italo', zoom=[[0, 1.02], [tb(1.5), 1.08, 'linear']]))                 # push-in continues
T.until_beat(21, seg_shot('m_stairs', fx=[{'type': 'bw'}]))                                          # high-contrast B&W quick shot
T.sound(tb(20.5), 'shutter', gain=-10, seed=64)
T.until_beat(23, seg_shot('m_shed', fx=[{'type': 'letterbox', 't0': 0.0, 't1': tb(1.7), 'h': 140}]))
T.sound(tb(21), 'whoosh', dur=0.3, gain=-11, pan_from=0, pan_to=0, peak_pos=0.35)
# ------------------------------------------------------------------ VENEZIA (b23 - b40)
T.until_beat(24, seg_shot('v_first', fx=[{'type': 'whip', 't0': 0.0, 't1': 0.13, 'dx': 1500}]))
T.sound(tb(23), 'whoosh', dur=0.3, gain=-9, pan_from=-0.7, pan_to=0.7, peak_pos=0.2)
T.until_beat(26, dict(type='split', shot='v_simeone', cache_offset=12, text='VENEZIA', sub='CANAL GRANDE', size=165, inset_scale=0.54, inset_cx=575, text_x=1125))
T.sound(tb(24), 'impact', gain=-7, bright=0.5)
T.until_beat(27.5, seg_shot('v_hud', fx=[{'type': 'hud', 'track': 'taxi', 'label': 'TRK_02  TAXI', 't0': 0.0, 't1': 9}]))
T.tracks['taxi'] = os.path.join(P, 'track_taxi.json')
T.sound(tb(26), 'click', gain=-7, f=3300); T.sound(tb(26) + 0.17, 'chatter', dur=0.3, gain=-13)
T.until_beat(28, seg_shot('v_campanile', fx=[{'type': 'duotone'}]))
T.sound(tb(27.5), 'shutter', gain=-10, seed=65)
T.until_beat(30, seg_shot('v_bow', zoom=[[0, 1.0], [tb(2), 1.05, 'linear']], fx=[{'type': 'overexpose', 't0': 0.0, 't1': 0.07, 'shape': 'down', 'amount': 0.9}]))
T.until_beat(31, seg_shot('v_rialto'))
T.until_beat(32, seg_shot('v_moise'))
T.until_beat(34, seg_shot('v_gondolier', fx=[{'type': 'roto_text', 'text': 'VENEZIA', 'size': 560, 'x': 960, 'y': 520, 't0': 0.02, 't1': 9,
                                               'matte_dir': os.path.join(P, 'mask_gondolier')}]))
T.sound(tb(32), 'boom', gain=-9, dur=0.9, f0=70, f1=40)
T.until_beat(36, seg_shot('v_clone', cache_offset=110, fx=[{'type': 'clone', 'offsets': [-80, 90], 'appear': [tb(0.5), tb(1)],
                                                             'mask_dir': os.path.join(P, 'mask_clone'), 't0': 0, 't1': 9}]))
T.sound(tb(34.5), 'click', gain=-9, f=2600); T.sound(tb(35), 'click', gain=-9, f=3100)
T.until_beat(38, seg_shot('v_bridges', fx=[{'type': 'red_inset', 't0': 0.0, 't1': tb(1), 'scale': 0.72}]))
T.sound(tb(36), 'whoosh', dur=0.28, gain=-11, pan_from=0, pan_to=0); T.sound(tb(37), 'impact', gain=-12, bright=0.4)
T.until_beat(40, seg_shot('v_arcade', zoom=[[0, 1.0], [tb(2), 1.06, 'linear']],
                         fx=[{'type': 'text', 'text': 'SAN MARCO', 'size': 300, 'x': 960, 'y': 560, 'mode': 'exclusion', 't0': 0.04, 't1': 9, 'tracking': 4}]))
# ------------------------------------------------------------------ BUILDUP (b40 - b48)
T.until_beat(41, seg_shot('v_taxi', fx=[{'type': 'whip', 't0': 0.0, 't1': 0.12, 'dx': -1500}]))
T.sound(tb(40), 'whoosh', dur=0.3, gain=-10, pan_from=0.7, pan_to=-0.7, peak_pos=0.2)
T.until_beat(42, seg_shot('v_salute'))
for k, sid in enumerate(['v_doge', 'v_lamp', 'v_gondolas', 'v_narrow']):
    T.until_beat(42.5 + 0.5 * k, seg_shot(sid))
T.until_beat(46, seg_shot('v_motorboat', fx=[{'type': 'shutter', 't0': 0.0, 't1': 9, 'hold': tb(0.25)}]))
for k in range(8):
    T.sound(tb(44 + 0.25 * k), 'shutter', gain=-10, seed=70 + k)
T.add(T.cursor, fb(48) - 2, seg_shot('v_bowsalute', fx=[{'type': 'overexpose', 't0': tb(1.0), 't1': tb(2) - 2 / 60, 'shape': 'up', 'amount': 1.0}]))
T.frames(2, dict(type='card', card='black', fx=[{'type': 'black'}]))
# ------------------------------------------------------------------ DROP: ROMA card (b48)
T.until_beat(49.5, dict(type='card', card='roma', text='ROMA', size=600, halation=0.12))
T.sound(tb(48), 'boom', gain=0, dur=1.8); T.sound(tb(48), 'impact', gain=0, dur=1.5)

# ------------------------------------------------------------------ ROMA + CLIMAX (b49.5 - b80)
if 'build' in rome:
    rome['build'](T, fb, tb, seg_shot, P)
else:
    seq = [('r5', 1.5), ('r1', 2), ('r6', 1), ('r2', 1), ('r7', 2), ('r3', 1), ('r8', 1), ('r4', 2), ('r10', 1), ('r11', 1.5),
           ('r12', 1), ('r9', 1), ('r1', 0.5), ('r2', 0.5), ('r3', 0.5), ('r4', 0.5), ('r5', 0.5), ('r6', 0.5), ('r7', 0.25), ('r8', 0.25),
           ('r10', 0.25), ('r11', 0.25), ('r12', 0.5), ('r9', 0.5), ('r1', 1), ('r2', 1), ('r3', 1), ('r4', 0.5), ('r5', 0.5), ('r6', 0.5)]
    k = 49.5
    for sid, d in seq:
        k2 = min(80, k + d)
        T.until_beat(k2, seg_shot(sid))
        k = k2
        if k >= 80:
            break
    if T.cursor < fb(80):
        T.until_beat(80, seg_shot('r1'))
# ------------------------------------------------------------------ FINAL HIT: full red, then end card
T.frames(6, dict(type='card', card='red', halation=0.0))
T.sound(tb(80), 'boom', gain=0, dur=2.2); T.sound(tb(80), 'impact', gain=0, dur=2.0)
END_FRAMES = 150
T.frames(END_FRAMES, dict(type='card', card='end', places=rome.get('places', 'MILANO  ·  VENEZIA  ·  ROMA'),
                          dates=rome.get('dates', 'MAY 2026'), size=330, halation=0.1, grain=0.026))
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
          dict(kind='person', shot='v_gondolier', out='mask_gondolier'),
          dict(kind='motion', shot='v_clone', out='mask_clone', roi=[0.55, 0.3, 1.0, 1.0], thresh=26)]
fxjobs += rome.get('fxjobs', [dict(kind='track', shot=hook_hud, out='track_hook.json', x=0.745, y=0.47, box=0.05, start=30)])
json.dump(fxjobs, open(os.path.join(P, 'fxjobs.json'), 'w'), indent=1)
print(f'EDL: {len(edl["segments"])} segments, {n_frames} frames ({n_frames/60:.2f}s), {len(shots)} cached shots, {len(edl["sfx"])} sfx')
