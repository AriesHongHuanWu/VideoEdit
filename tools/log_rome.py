#!/usr/bin/env python3
"""Append the 58 clips of 22-28 May (Burano, Roma, Napoli, Firenze) to logs/footage_log.{csv,md}."""
import csv, json, statistics, sys
S = '/tmp/claude-0/-home-user-VideoEdit/8531dbc8-a772-580f-8538-3f205e4051d8/scratchpad'
REPO = '/home/user/VideoEdit'
U = 'unknown'
BUR = 'Burano, Venice lagoon (painted houses)'
LAG = 'Venice lagoon, Burano/Mazzorbo area (exact spot unconfirmed)'
L = {  # file: (location, content, composition 1-5, best, tags, use 1-10, motion override or '')
 220: (U, 'Outdoor cafe table: latte macchiato and plates, companions talking; dip under the table to a sparrow on the paving', 2, '0.5-2.0s', 'food,people,selfie', 2, ''),
 221: (U, 'Lying on a lawn under pines (red building behind), then a close selfie on the grass', 2, '7.0-12.0s', 'park,selfie', 1, ''),
 222: (BUR, 'Walk along a canal lined with pink, yellow, green and blue houses, moored boats, tourists; steady canal view from 17 s', 5, '17.3-23.4s', 'Burano,canal,colour,hero', 9, 'walking, gentle forward'),
 223: ('Venice area shop (unconfirmed)', 'Camera held sideways inside a bakery: biscuit display, customers (rotated 90 degrees)', 1, '', 'interior,rotated', 1, ''),
 224: ('Venice area alley (unconfirmed)', 'Selfie: companions eating fried snacks in an alley', 2, '', 'food,selfie', 1, ''),
 225: (BUR, 'Through a pink sottoportego arch, walking a dark passage toward a bright canal street; silhouettes', 4, '0.4-2.5s', 'Burano,arch,silhouette', 7, 'walking forward'),
 226: (BUR, 'Alleys between painted houses, then a canal with turquoise boats and a brick bridge', 4, '16.0-21.7s', 'Burano,canal,boats,colour', 8, 'walking, pans'),
 227: (BUR, 'Brick bridge over a canal framed by pink, green and blue facades', 5, '0.3-2.3s', 'Burano,bridge,colour,hero', 9, 'slow push'),
 228: ('Burano (likely)', 'Narrow passage between orange walls opening onto striped awnings; a companion steps in', 3, '0.5-4.0s', 'alley,person', 3, ''),
 229: (LAG, 'Lawn and path to the lagoon edge, trees and lamp posts, flat horizon', 3, '8.0-17.5s', 'lagoon,calm', 4, 'slow pan left'),
 230: (LAG, 'Umbrella pines framing the lagoon and a pier', 3, '0.2-3.0s', 'lagoon,pines', 3, ''),
 231: (LAG, 'Wooden footbridge across the lagoon, people and a dog crossing', 3, '0.5-4.0s', 'bridge,lagoon', 4, ''),
 232: (LAG, 'Path through a vineyard and garden, brick bell tower in the distance, companions walking', 3, '8.0-18.5s', 'vineyard,tower', 4, 'walking forward'),
 233: (LAG, 'Vineyard rows leading to the brick bell tower', 4, '0.5-6.0s', 'vineyard,tower', 5, 'slow push'),
 234: (LAG, 'Close-up of pink roses in the vineyard', 4, '1.0-3.7s', 'flowers,detail', 4, 'static'),
 235: (LAG, 'Pink roses, push in, then tilt to the vineyard and a little wooden bridge', 4, '1.2-2.8s', 'flowers,detail', 4, ''),
 236: (LAG, 'Lagoon shore and distant boardwalk, flat light', 2, '', 'lagoon', 2, 'static'),
 237: ('Venice (exact spot unknown)', 'Bakery counter with focaccia and pizza slices, customers ordering', 2, '6.0s', 'food,interior', 2, ''),
 238: ('Venice (exact spot unknown)', 'Crowded gelato counter, companions choosing flavours', 2, '', 'gelato,people', 2, ''),
 239: ('Venice (exact spot unknown)', 'Gelato counter, short take', 2, '', 'gelato', 1, ''),
 240: ('Venice (exact spot unknown)', 'Gelato tasting in a shopping alley, companions (selfie distance)', 2, '', 'gelato,selfie', 1, ''),
 241: ('Venice (exact spot unknown)', 'Close-ups of a gelato cone being shared', 2, '', 'gelato,detail,selfie', 2, ''),
 242: ('Venice (exact spot unknown)', 'Gelato cone, then a selfie under shop lights', 1, '', 'selfie', 1, ''),
 249: ('railway station hall (unconfirmed)', 'Selfie walking under a grid ceiling past ticket gates', 2, '', 'station,selfie', 1, ''),
 251: ('Rome, street by a station (exact street unconfirmed)', 'Low angle across a busy street: white taxis crossing, shopfronts, deep blue sky', 3, '2.6-6.0s', 'Roma,street,traffic', 5, 'static, slight pan'),
 264: ('Rome, obelisk fountain (consistent with Piazza della Rotonda; square not named on screen)', 'Crowd around a fountain, tilt up to the obelisk against blue sky and cumulus', 5, '1.5-5.5s', 'Roma,obelisk,sky,hero', 9, 'tilt up then hold'),
 275: ('Rome cafe (unconfirmed)', 'Camera upside down in a shop', 1, '', 'rotated', 0, ''),
 277: ('Rome cafe (unconfirmed)', 'Coffee shop counter with red packaging, companions paying, pastry case', 3, '13.5-19.0s', 'cafe,interior', 3, ''),
 279: ('Rome cafe (unconfirmed)', 'Selfie with companions inside a busy cafe', 1, '', 'selfie', 1, ''),
 290: ('Rome (exact street unconfirmed)', 'Low angle on a sticker-covered pole and stone street corner', 3, '1.5-5.0s', 'Roma,street,detail', 5, 'slow tilt'),
 292: ('Rome (exact street unconfirmed)', 'Crowd walking out of a street onto a wide avenue with umbrella pines, golden light', 4, '3.4-5.0s', 'Roma,pines,crowd,golden', 7, 'walking forward'),
 303: ('Osteria da Fortunata, Rome (plates printed "ROMA")', 'Pesto and ragu pasta on printed terracotta plates, companions photographing', 4, '8.0-13.4s, 15.2-20.5s', 'Roma,food,detail', 7, ''),
 305: ('Osteria da Fortunata, Rome', 'Dinner table, eating, companions', 2, '', 'food,people', 2, ''),
 318: ("Piazza Navona, Rome (hoarding reads 'Chiesa di Sant'Agnese in Agone')", "Dusk: Sant'Agnese in Agone and the Four Rivers obelisk, billboard, selfies; wide piazza at blue hour from 20 s", 5, '0.4-2.0s, 20.6-25.0s', 'Roma,Navona,dusk,hero', 9, 'pans, walking'),
 346: (U, 'Selfie eating a pizza slice indoors', 1, '', 'food,selfie', 1, ''),
 357: ('Napoli (exact street unconfirmed)', 'Street food cone and a beer in a crowded narrow street', 2, '4.0-6.5s', 'food,street', 2, ''),
 359: ('Napoli (exact street unconfirmed)', 'Selfie walking a busy street of shops and balconies', 1, '', 'selfie', 1, ''),
 370: ('Galleria Umberto I, Napoli', 'Entrance arch and glass vault of the gallery, crowd, pan right along the facade', 4, '0.2-1.5s', 'Napoli,architecture', 8, 'pan right'),
 372: ('la Sfogliatella Mary, Napoli', 'Pastry kiosk with awning, queue of customers', 3, '1.0-4.2s', 'Napoli,food,street', 5, 'static'),
 383: ('Basilica di San Francesco di Paola, Napoli (consistent with the next clip on Piazza del Plebiscito)', 'Round nave with columns, tilt up to the coffered dome and lantern, perfectly symmetric', 5, '6.0-9.2s', 'Napoli,dome,symmetry,hero', 9, 'tilt up'),
 385: ('Piazza del Plebiscito, Napoli (Palazzo Reale)', 'Locked-off wide of the piazza and royal palace under cumulus clouds', 5, '0.3-5.8s', 'Napoli,piazza,sky,hero', 8, 'static'),
 396: ('Napoli (exact street unconfirmed)', 'Narrow street of souvenir stalls, walking into the low sun with strong lens flare', 4, '1.3-4.5s', 'Napoli,flare,street', 8, 'walking forward'),
 398: (U, 'Courtyard with potted palms, companion walking', 2, '', 'courtyard', 2, ''),
 588: (U, 'Bowl of noodles with chopsticks', 2, '', 'food', 1, 'static'),
 590: ('Firenze Santa Maria Novella station', 'Station exterior and basilica bell tower, then selfie', 2, '1.0-4.0s', 'Firenze,station,selfie', 2, ''),
 601: ('Duomo di Firenze (Santa Maria del Fiore)', 'Marble flank of the cathedral and Brunelleschi dome, construction hoardings in the foreground', 5, '2.7-6.5s', 'Firenze,Duomo,hero', 9, 'walking, slow pan'),
 603: ('Firenze, leather market (exact market unconfirmed)', 'Leather bag stalls and crowd, then selfie', 3, '0.3-2.4s', 'Firenze,market', 4, 'walking'),
 614: ('Firenze (exact street unconfirmed)', 'Narrow street between rusticated stone palazzi', 3, '0.3-5.0s', 'Firenze,street', 5, 'static'),
 616: ('Ponte Vecchio, Firenze (Cellini bust in frame)', 'Walk across the bridge between jewellers, then the centre opening with the bust and the Arno', 4, '1.0-3.0s, 18.7-22.6s', 'Firenze,PonteVecchio,river', 7, 'walking'),
 627: ('Cinema Odeon, Firenze (interior)', 'Ornate cinema interior, then selfie', 2, '1.0s', 'Firenze,interior,selfie', 2, ''),
 629: ('Cinema Odeon, Firenze (lettering on facade)', 'Rusticated stone facade with ODEON lettering, passer-by', 3, '1.6-4.8s', 'Firenze,architecture', 5, 'slow tilt'),
 640: ('Capuchin museum, Rome (consistent with displays)', 'Vitrine of apothecary jars and mortars', 2, '', 'museum,interior', 2, ''),
 642: ('Capuchin museum, Rome (consistent with displays)', 'Painting of a friar holding a crucifix', 2, '', 'museum,painting', 2, ''),
 644: ('Capuchin crypt, Rome (consistent with displays)', 'Chapels decorated with bones, dim', 3, '8.0-11.7s', 'crypt,dark', 2, ''),
 655: (U, 'Shop window of trading cards', 1, '', 'shop', 1, ''),
 657: ('Piazza Venezia / Vittoriano, Rome', 'Statues over Piazza Venezia, then the Vittoriano steps and colonnade with a selfie at the right edge', 3, '0.5-1.5s, 9.5-12.4s (crop left)', 'Roma,Vittoriano', 6, ''),
 668: ('Vittoriano, Rome', 'Marble fountain and terraces with flags, umbrella in the left foreground', 4, '0.5-3.4s', 'Roma,Vittoriano,hero', 7, 'static'),
 670: (U, 'Finger over the lens', 1, '', 'unusable', 0, ''),
}
def motion_desc(r):
    ms = [m for m in r.get('motion', []) if m]
    if not ms:
        return 'static'
    dx = statistics.mean(abs(m['dx']) for m in ms); dy = statistics.mean(abs(m['dy']) for m in ms)
    sc = statistics.mean(m['scale'] for m in ms)
    if max(dx, dy) < 4 and abs(sc - 1) < 0.006:
        return 'handheld, near-static'
    parts = []
    if sc > 1.008: parts.append('moving forward')
    elif sc < 0.992: parts.append('pulling back')
    if dx > dy * 1.3: parts.append('pan ' + ('left' if statistics.mean(m['dx'] for m in ms) > 0 else 'right'))
    elif dy > dx * 1.3: parts.append('tilt ' + ('up' if statistics.mean(m['dy'] for m in ms) > 0 else 'down'))
    else: parts.append('handheld drift')
    return ', '.join(parts)
def clarity(r):
    sh = statistics.median(m['sharp'] for m in r['metrics'])
    return 5 if sh >= 500 else 4 if sh >= 300 else 3 if sh >= 180 else 2 if sh >= 100 else 1
rows = []
for k, (loc, content, comp, best, tags, use, mo) in L.items():
    name = f'DJI_{k:04d}'
    r = json.load(open(f'{S}/work/results/{name}.json')); m = r['meta']
    shot = m['creation_time'][:16].replace('T', ' ')
    fmt = f"{m['width']}x{m['height']} {m['fps']} {m['pix_fmt']}"
    rows.append(dict(file=name + '.MP4', shot=shot, duration=f"{m['duration']:.1f}", format=fmt, location=loc, content=content,
                     camera_motion=mo or motion_desc(r), composition=comp, clarity=clarity(r), best=best, tags=tags, use_score=use,
                     notes='source: GitHub release videoedit-italy-rome (SHA-256 verified)'))
with open(f'{REPO}/logs/footage_log.csv', 'a', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    for row in rows:
        w.writerow(row)
md = open(f'{REPO}/logs/footage_log.md').read().replace('191 clips.', '249 clips.', 1)
by_day = {}
for row in rows:
    by_day.setdefault(row['shot'][:10], []).append(row)
md += '\n\n# 22–28 May: Burano, Roma, Napoli, Firenze (logged from the 4K originals)\n'
for day in sorted(by_day):
    md += f'\n## {day}\n\n| File | Dur | Location | Content | Camera motion | Comp | Clarity | Best moments | Score |\n|---|---|---|---|---|---|---|---|---|\n'
    for row in by_day[day]:
        md += f"| {row['file']} | {row['duration']}s | {row['location']} | {row['content']} | {row['camera_motion']} | {row['composition']} | {row['clarity']} | {row['best']} | {row['use_score']} |\n"
open(f'{REPO}/logs/footage_log.md', 'w').write(md)
print(len(rows), 'clips appended')
