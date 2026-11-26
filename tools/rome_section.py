# Rome / Naples / Florence material (folder 2) and Burano (22 May), logged from the 4K originals.
# Place names on screen are only those confirmed in frame: Sant'Agnese in Agone hoarding (Piazza Navona),
# Galleria Umberto I + Piazza del Plebiscito + Sfogliatella Mary (Napoli), Duomo + Ponte Vecchio (Firenze),
# Osteria da Fortunata plates printed "ROMA", Burano's painted houses.
import os

# ---------------------------------------------------------------- shots (clip, source in-point s)
# Roma 23.05 / 28.05
S('r_obelisk', 'DJI_0264', 1.6, note='obelisk fountain against blue sky and clouds, low angle (HUD #3)')
S('r_fountain', 'DJI_0264', 0.2, note='crowd around the obelisk fountain')
S('r_pines', 'DJI_0292', 3.4, note='crowd walking toward an avenue of umbrella pines, golden light')
S('r_vitto', 'DJI_0668', 0.6, note='Vittoriano fountain and marble terraces, flags (Glass Text)')
S('r_vitto2', 'DJI_0657', 9.8, crop={'zoom': 1.7, 'x': 0.29, 'y': 0.5}, note='Vittoriano steps and colonnade (cropped)')
S('r_venezia', 'DJI_0657', 0.5, note='statues over Piazza Venezia')
S('r_navona', 'DJI_0318', 0.4, note="Sant'Agnese in Agone and the Four Rivers obelisk at dusk")
S('r_navona_dusk', 'DJI_0318', 21.0, note='Piazza Navona wide at blue hour (final hero)')
S('r_corner', 'DJI_0290', 1.8, note='sticker-covered street corner, low angle')
S('r_street', 'DJI_0251', 3.0, note='taxis crossing a Roman street')
S('r_pasta', 'DJI_0303', 9.0, note='pasta on an Osteria da Fortunata plate printed ROMA')
S('r_ragu', 'DJI_0303', 16.0, note='ragu pasta, printed plate rim')
# Napoli 24.05
S('n_galleria', 'DJI_0370', 0.2, note='Galleria Umberto I glass vault entrance')
S('n_dome', 'DJI_0383', 6.6, note='San Francesco di Paola coffered dome, symmetric')
S('n_plebiscito', 'DJI_0385', 1.2, note='Piazza del Plebiscito and the Royal Palace, cumulus sky')
S('n_sfog', 'DJI_0372', 2.2, note='la Sfogliatella Mary counter and queue')
S('n_flare', 'DJI_0396', 1.4, speed=[[0, 2.2], [0.30, 2.2], [0.62, 0.5]], note='narrow street walking into the sun flare (speed ramp)')
# Firenze 27.05
S('f_duomo', 'DJI_0601', 3.2, note='Santa Maria del Fiore and the dome')
S('f_ponte', 'DJI_0616', 20.0, note='Ponte Vecchio centre, Cellini bust and the Arno')
S('f_odeon', 'DJI_0629', 2.0, note='Odeon facade, rusticated stone')
S('f_market', 'DJI_0603', 0.6, note='leather market stalls')
S('f_street', 'DJI_0614', 1.0, note='narrow Florentine street, stone palazzi')
# Burano 22.05
S('b_canal', 'DJI_0222', 18.0, note='Burano canal between painted houses')
S('b_canal2', 'DJI_0226', 16.0, note='Burano canal with boats and painted houses')
S('b_bridge', 'DJI_0227', 0.4, note='brick bridge and painted facades')
S('b_boats', 'DJI_0226', 18.6, note='turquoise boats in a Burano canal')
S('b_arch', 'DJI_0225', 0.4, note='pink sottoportego arch, silhouettes')

rome['strip'] = 'r_obelisk'
rome['band'] = ['r_navona', 'n_dome', 'f_duomo']
rome['burano'] = 'b_canal'
rome['places'] = 'MILANO  ·  VENEZIA  ·  ROMA  ·  NAPOLI  ·  FIRENZE'
rome['dates'] = '20 — 28.05.2026'
P_ = None


def build(T, fb, tb, seg_shot, hero, kicks, P, TR, KICK):
    F1 = 1 / 60
    SOFT = {'type': 'soft_glow', 'amount': 0.45}
    def title(text, anim):
        return {'type': 'title_top', 'text': text, 't0': 0.0 if not anim else 0.03, 't1': 9, 'margin': 40, 'anim': anim}

    # ---- ROMA: obelisk inset on red -> full frame, HUD lock-on (TRK_03)
    T.until_beat(51.5, hero('r_obelisk', 49.5, 51.5, zoom=[[0, 1.0], [tb(2), 1.05, 'linear']],
                            fx=[{'type': 'red_inset', 't0': 0.0, 't1': tb(1), 'scale': 0.70},
                                {'type': 'hud', 'track': 'rome_hud', 'label': 'TRK_03', 't0': tb(1) + 0.05, 't1': 9}]))
    T.tracks['rome_hud'] = os.path.join(P, 'track_rome.json')
    T.sound(tb(50.5), 'whoosh', dur=0.22, gain=-11, pan_from=0, pan_to=0, peak_pos=0.5)
    T.sound(tb(50.5) + 0.06, 'click', gain=-8, f=3500); T.sound(tb(50.5) + 0.12, 'chatter', dur=0.25, gain=-13)
    # golden avenue of pines
    T.until_beat(53.5, hero('r_pines', 51.5, 53.5, zoom=[[0, 1.0], [tb(2), 1.06, 'linear']]))
    TR('push', 6, 7, dir=1)
    # Glass Text over the Vittoriano
    T.until_beat(55.5, hero('r_vitto', 53.5, 55.5, zoom=[[0, 1.0], [tb(2), 1.05, 'linear']],
                            fx=[{'type': 'glass', 'text': 'ROMA', 'size': 560, 'cy': 400, 't0': 0.10, 't1': 9}]))
    TR('whip', 6, 6, dir=-1)
    # Zoom Out reveal of Piazza Navona + confirmed label
    T.until_beat(57, hero('r_navona', 55.5, 57, punch=False,
                          fx=[{'type': 'zoom_out', 't0': 0.0, 't1': 0.45, 'z0': 1.6},
                              {'type': 'label', 'text': 'PIAZZA NAVONA', 'sub': '23.05.2026', 'idx': '04', 't0': 0.22, 't1': 9}]))
    TR('redbar', 7, 7, dir=1)
    # strip slice into the street corner, then a Background Wipe into the taxis
    T.until_beat(58, hero('r_corner', 57, 58))
    TR('slice', 5, 10)
    corner = T.segs[-1]
    T.until_beat(59, dict(hero('r_street', 58, 59), wipe_in={'dur': 0.24, 'dir': 1, 'feather': 120}))
    T._need('r_corner', corner.get('cache_offset', 0) + (corner['f1'] - corner['f0']) + int(0.24 * 60) + 3)
    T.sound(tb(58), 'whoosh', dur=0.3, gain=-12, pan_from=-0.6, pan_to=0.6, peak_pos=0.5)
    # held ROMA headline over a rapid montage (camera kicks on every cut)
    for k, (sid, k0, k1) in enumerate([('r_pasta', 59, 59.5), ('r_venezia', 59.5, 60), ('r_ragu', 60, 60.5), ('r_fountain', 60.5, 61)]):
        T.until_beat(k1, hero(sid, k0, k1, fx=[title('ROMA', k == 0), KICK(0.0, amp=9)]))
        T.sound(tb(k0), 'shutter', gain=-12, seed=80 + k)
    # Vittoriano steps arrive as a framed picture and take over
    T.until_beat(64, hero('r_vitto2', 61, 64, zoom=[[0, 1.0], [tb(3), 1.07, 'linear']]))
    TR('pip', 10, 7, s0=0.34, cx=0.70, cy=0.40)

    # ---- NAPOLI: headline held over three cuts
    T.until_beat(65, hero('n_galleria', 64, 65, fx=[{'type': 'flash_pop', 'at': 0.0}, title('NAPOLI', True)]))
    TR('whip', 6, 6, dir=1)
    T.sound(tb(64), 'impact', gain=-6, bright=0.7)
    T.until_beat(66, hero('n_dome', 65, 66, fx=[{'type': 'light_scatter', 'amount': 0.55}, title('NAPOLI', False), KICK(0.0)]))
    T.until_beat(67, hero('n_plebiscito', 66, 67, fx=[title('NAPOLI', False), KICK(0.0, amp=9)]))
    T.sound(tb(65), 'shutter', gain=-11, seed=90); T.sound(tb(66), 'shutter', gain=-11, seed=91)
    # ---- FIRENZE: a red bar carries the name in, headline held over three cuts
    T.until_beat(68, hero('f_duomo', 67, 68, fx=[title('FIRENZE', True)]))
    TR('redbar', 7, 7, dir=-1, label='FIRENZE', label_size=96)
    T.until_beat(69, hero('f_ponte', 68, 69, fx=[title('FIRENZE', False), KICK(0.0)]))
    T.until_beat(70, hero('f_odeon', 69, 70, fx=[title('FIRENZE', False), KICK(0.0, amp=9)]))
    T.sound(tb(68), 'shutter', gain=-11, seed=92); T.sound(tb(69), 'shutter', gain=-11, seed=93)

    # ---- CLIMAX: half-beat shots across the trip, two 6-frame flashes on snares, two whips
    cl = ['b_bridge', 'n_sfog', 'f_market', 'b_boats', 'b_arch', 'f_street', 'b_canal2', 'r_street', 'b_canal', 'n_plebiscito']
    offs = {'r_street': 70, 'b_canal': 140, 'n_plebiscito': 90}
    for k, sid in enumerate(cl):
        k0, k1 = 70 + 0.5 * k, 70.5 + 0.5 * k
        fx = [KICK(0.0, amp=10)]
        if k in (1, 5):
            fx.append({'type': 'overexpose', 't0': 0.0, 't1': 6 * F1, 'shape': 'down', 'amount': 0.85})
        seg = hero(sid, k0, k1, fx=fx, cache_offset=offs.get(sid, 0))
        T.until_beat(k1, seg)
        if k in (4, 8):
            TR('whip', 4, 4, dir=1 if k == 4 else -1)
        elif k not in (0,):
            T.sound(tb(k0), 'click', gain=-11, f=2200 + 150 * k)
    # stutter between Rome and Burano on the last beat before the ramp
    T.until_beat(76, dict(type='stutter', pattern='ABABAABBAB', step=2, A={'shot': 'r_obelisk', 'cache_offset': 150},
                          B={'shot': 'b_canal', 'cache_offset': 30}))
    for k in range(5):
        T.sound(tb(75) + k * 4 / 60, 'click', gain=-12, f=2200 + 300 * k)
    # speed ramp: fast walk that slams into slow motion inside the sun flare
    T.until_beat(78, hero('n_flare', 76, 78, punch=False, fx=[KICK(0.0, amp=8)]))
    T.sound(tb(76), 'impact', gain=-9, bright=0.6)
    # final hero: Piazza Navona at blue hour, slow push-in under the low-end dip
    T.until_beat(80, hero('r_navona_dusk', 78, 80, punch=False, zoom=[[0, 1.0], [tb(2), 1.12, 'linear']], fx=[SOFT]))
    TR('zoom', 6, 8, z=0.55)


rome['build'] = build
rome['fxjobs'] = [dict(kind='track', shot='v_hud', out='track_hook.json', x=0.745, y=0.47, box=0.05, start=30),
                  dict(kind='track', shot='r_obelisk', out='track_rome.json', x=0.462, y=0.28, box=0.05, start=25)]
