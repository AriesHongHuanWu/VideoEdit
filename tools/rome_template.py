# Rome section builder (template). Copy to rome_section.py once the Rome clips are logged and fill SLOTS.
# make_edl.py exec()s rome_section.py with T, S, fb, tb and the dict `rome`; it must set rome['build'] and the
# intro/hook substitutions below. Every place name / date written on screen must be confirmed from the frames or metadata.
#
# Slots (shot ids defined with S(...) below):
#   open      establishing landmark, first shot after the ROMA card (red inset -> full)        b49.5 - 51.5
#   hud       moving subject for HUD tracking #3 (scooter, bird, tram, person)                  b51.5 - 53.5
#   glass     landmark wide with clean sky for Glass Text                                       b53.5 - 55.5
#   zoomout   detail that opens into a wide (Zoom Out effect)                                   b55.5 - 57
#   wipe_a/b  pair joined by a foreground wipe (pillar / passer-by / tree)                       b57 - 59
#   q1..q4    quick shots under the held ROMA headline                                          b59 - 61
#   hero2     strongest hero (golden light), PIP pop-in                                         b61 - 64
#   acc1..6   accelerating 1-beat shots, whips / pushes / zoom                                  b64 - 70
#   cl1..10   climax half-beat shots with 6-frame flashes; cl9/cl10 also feed the stutter        b70 - 76
#   ramp      speed-ramped shot (fast -> slow on b77), define with speed=[[0,2.2],[0.3,2.2],[0.6,0.5]] b76 - 78
#   final     final hero with slow push-in, low-end dip, 2-frame gap                            b78 - 80

SLOTS = {}            # e.g. SLOTS['open'] = 'r_colosseo'
LABELS = {}           # e.g. LABELS['open'] = ('COLOSSEO', '23.05.2026', '03')  only when confirmed
GLASS_TEXT = None     # e.g. 'ROMA' or a confirmed landmark name
HUD_TRACK = None      # dict(x=.., y=.., box=.., start=..) normalised point on the hud shot at cache frame `start`


def build(T, fb, tb, seg_shot, hero, kicks, P, TR, KICK):
    import os
    F1 = 1 / 60
    sl = SLOTS
    def lab(slot, t0=0.2):
        if slot in LABELS:
            txt, sub, idx = LABELS[slot]
            return [{'type': 'label', 'text': txt, 'sub': sub, 'idx': idx, 't0': t0, 't1': 9}]
        return []
    # ROMA card -> first shot inset on red -> pops to full on b50.5
    T.until_beat(51.5, hero(sl['open'], 49.5, 51.5, zoom=[[0, 1.0], [tb(2), 1.06, 'linear']],
                            fx=[{'type': 'red_inset', 't0': 0.0, 't1': tb(1), 'scale': 0.70}] + lab('open', tb(1) + 0.1)))
    T.sound(tb(50.5), 'whoosh', dur=0.22, gain=-11, pan_from=0, pan_to=0, peak_pos=0.5)
    # HUD tracking #3
    T.until_beat(53.5, hero(sl['hud'], 51.5, 53.5, fx=[{'type': 'hud', 'track': 'rome_hud', 'label': 'TRK_03', 't0': 0.0, 't1': 9}]))
    TR('push', 6, 7, dir=1)
    T.tracks['rome_hud'] = os.path.join(P, 'track_rome.json')
    T.sound(tb(51.5) + 0.1, 'chatter', dur=0.25, gain=-13)
    # Glass Text on the landmark
    T.until_beat(55.5, hero(sl['glass'], 53.5, 55.5, zoom=[[0, 1.0], [tb(2), 1.05, 'linear']],
                            fx=[{'type': 'glass', 'text': GLASS_TEXT or 'ROMA', 'size': 560, 't0': 0.08, 't1': 9}]))
    TR('whip', 6, 6, dir=-1)
    # Zoom Out: detail opens into the wide on the hit
    T.until_beat(57, hero(sl['zoomout'], 55.5, 57, fx=[{'type': 'zoom_out', 't0': 0.0, 't1': 0.45, 'z0': 1.6}] + lab('zoomout', 0.3)))
    TR('redbar', 7, 7, dir=1)
    # Background Wipe pair (foreground object carries the cut)
    T.until_beat(58, hero(sl['wipe_a'], 57, 58))
    TR('slice', 5, 10)
    T.until_beat(59, dict(seg_shot(sl['wipe_b']), wipe_in={'dur': 0.22, 'dir': 1, 'feather': 90}))
    # held headline over a rapid montage
    ROMA = {'type': 'title_top', 'text': 'ROMA', 't0': 0.0, 't1': 9, 'margin': 40, 'anim': False}
    for k, (slot, k0, k1) in enumerate([('q1', 59, 59.5), ('q2', 59.5, 60), ('q3', 60, 60.5), ('q4', 60.5, 61)]):
        fx = [dict(ROMA, anim=(k == 0)), KICK(0.0, amp=9)]
        T.until_beat(k1, hero(sl[slot], k0, k1, fx=fx))
        T.sound(tb(k0), 'shutter', gain=-12, seed=80 + k)
    # strongest hero via PIP pop-in
    T.until_beat(64, hero(sl['hero2'], 61, 64, zoom=[[0, 1.0], [tb(3), 1.07, 'linear']], fx=lab('hero2')))
    TR('pip', 10, 7, s0=0.34, cx=0.30, cy=0.40)
    # acceleration: 1-beat shots, alternating whip directions, one speed ramp
    kinds = [('whip', {'dir': 1}), ('push', {'axis': 'y', 'dir': -1}), ('whip', {'dir': -1}), ('zoom', {}), ('push', {'dir': 1}), ('whip', {'dir': 1})]
    for k in range(6):
        T.until_beat(65 + k, hero(sl[f'acc{k + 1}'], 64 + k, 65 + k))
        kd, kw = kinds[k]
        TR(kd, 5, 6, **kw)
    # climax: half-beat quick shots (11 frames) with 6-frame flashes on two snares and two whips
    for k in range(10):
        k0, k1 = 70 + 0.5 * k, 70.5 + 0.5 * k
        fx = [KICK(0.0, amp=10)]
        if k in (1, 5):
            fx.append({'type': 'overexpose', 't0': 0.0, 't1': 6 * F1, 'shape': 'down', 'amount': 0.9})
        T.until_beat(k1, hero(sl[f'cl{k + 1}'], k0, k1, fx=fx))
        if k in (3, 7):
            TR('whip', 4, 4, dir=1 if k == 3 else -1)
    # stutter between two climax shots, then a speed ramp that slams into slow motion on b77
    T.until_beat(76, dict(type='stutter', pattern='ABABAABBAB', step=2, A={'shot': sl['cl9'], 'cache_offset': 12},
                          B={'shot': sl['cl10'], 'cache_offset': 12}))
    for k in range(5):
        T.sound(tb(75) + k * 4 / 60, 'click', gain=-12, f=2200 + 300 * k)
    T.until_beat(78, hero(sl['ramp'], 76, 78))
    TR('zoom', 5, 7, z=0.5)
    # final hero: slow push-in under the low-end dip; full red follows on b80
    T.until_beat(80, hero(sl['final'], 78, 80, zoom=[[0, 1.0], [tb(2), 1.12, 'linear']]))
    TR('push', 5, 7, dir=1)


rome['build'] = build
# substitutions used by the hook / intro (best Rome material):
# rome['strip'] = ...; rome['band'] = [.., .., ..]; rome['places'] = 'MILANO  ·  VENEZIA  ·  ROMA'; rome['dates'] = '20 — 2x.05.2026'
