#!/usr/bin/env python3
"""Render the EDL as an edit table (剪輯表) in Markdown.  python3 -I edl_table.py <edl.json> <shots.json> <out.md>"""
import json, sys
edl = json.load(open(sys.argv[1])); shots = {s['id']: s for s in json.load(open(sys.argv[2]))}
BEAT = 60 / 165.0
FX_NAMES = {'flash_pop': 'Flash Pop In', 'zoom_out': 'Zoom Out', 'glass': 'Glass Text', 'bw': 'B&W', 'shutter': 'Shutter Clip',
            'bw_invert': 'B&W Inverted', 'overexpose': 'Flash Effect', 'white': 'white flash', 'clone': 'Clone Effect',
            'text': 'Text Exclusion', 'roto_text': 'Rotoscope text', 'hud': 'HUD tracking', 'letterbox': 'red letterbox bounce',
            'red_inset': 'red-frame inset -> pop back', 'title_top': 'full-width red headline', 'duotone': 'red/white duotone flash',
            'red_invert': 'red inverted flash', 'whip': 'whip pan', 'scanlines': 'CRT texture', 'black': 'black', 'red': 'full red',
            'chroma': 'RGB split'}
def fx_desc(seg):
    out = []
    for fx in seg.get('fx', []):
        n = FX_NAMES.get(fx['type'], fx['type'])
        if fx['type'] in ('title_top', 'glass', 'roto_text', 'text'):
            n += f" '{fx['text']}'"
        if fx['type'] == 'whip':
            n += ' out' if fx.get('out') else ' in'
        out.append(n)
    if seg['type'] == 'split':
        out.append(f"red split card '{seg['text']}'")
    if seg['type'] == 'card':
        out.append({'roma': "red card 'ROMA'", 'red': 'full red frame', 'end': 'end card (wine red + ITALIA)'}.get(seg['card'], seg['card']))
    if seg['type'] == 'intro':
        out.append("'postcards from ITALIA' intro: 6 strips -> band -> decode -> band opens")
    if seg.get('wipe_in'):
        out.append('Background Wipe in')
    sh = shots.get(seg.get('shot'), {})
    sp = sh.get('speed', 1.0)
    if isinstance(sp, list):
        out.append('speed ramp ' + '->'.join(f'{v:g}x' for _, v in sp))
    z = seg.get('zoom')
    if z and abs(z[-1][1] - z[0][1]) > 0.01:
        out.append(f'camera move zoom {z[0][1]:.2f}->{z[-1][1]:.2f}')
    return ', '.join(out)
au = edl['audio']
sfx = edl['sfx']
lines = ['| Time (s) | Beat | Frames | Shot (file @ source s) | Graphics / effects | Sound |', '|---|---|---|---|---|---|']
for seg in edl['segments']:
    t0 = seg['f0'] / 60; t1 = seg['f1'] / 60
    sh = shots.get(seg.get('shot'), {})
    src = f"{sh.get('clip','')} @ {sh.get('src_in', 0) + seg.get('cache_offset', 0)/60:.1f}" if sh else ''
    snd = ', '.join(f"{e['type']}" for e in sfx if t0 - 0.001 <= e['t'] < t1 - 0.001)
    lines.append(f"| {t0:6.2f}–{t1:6.2f} | {t0/BEAT:5.1f} | {seg['f1']-seg['f0']} | {src} | {fx_desc(seg)} | {snd} |")
filt = ['', '**Music / filters**', '',
        f"- Song segment from {au['song_start']:.3f} s (bar downbeat on the fitted 165 BPM grid), length {au['dur']:.2f} s.",
        f"- Intro low-pass dive {au['lpf_intro'][0]:.2f}–{au['lpf_intro'][1]:.2f} s to {au['lpf_intro'][4]} Hz, held through the ITALIA decode, reopens to full range by {au['lpf_intro'][3]:.2f} s.",
        f"- Buildup high-pass sweep {au['hpf_build'][0]:.2f}–{au['hpf_build'][1]:.2f} s ({au['hpf_build'][2]}→{au['hpf_build'][3]} Hz) + riser; full range returns on the drop.",
        f"- Silence gaps (2 frames): " + ', '.join(f'{a:.3f}–{b:.3f} s' for a, b in au['gaps']) + '.',
        f"- Low-end dip before the final hit {au['lowdip'][0]:.2f}–{au['lowdip'][1]:.2f} s (HPF to {au['lowdip'][2]} Hz); outro low-pass close + fade.",
        f"- Sidechain: music below 150 Hz ducks up to {au['sc_depth']} dB under booms/impacts; master {au['lufs']} LUFS, true peak ≤ {au['tp']} dBTP before AAC."]
open(sys.argv[3], 'w').write('\n'.join(lines + filt) + '\n')
print('rows', len(edl['segments']))
