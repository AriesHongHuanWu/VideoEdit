# Footage-log brief (素材日誌) — Italy travel montage

You are logging raw DJI action-camera clips (Osmo Action, 4K60, Normal colour, no GPS) from a May 2026 trip.
The trip is "mainly Rome" but also includes Milan and possibly other places. The goal is to pick the
**best-composed, sharp, layered shots** for a ~28 s beat-synced travel montage (red magazine style).
Your log is the only thing the editor will see for these clips, so be accurate and concrete.

## Inputs (all paths absolute)
- Root: `/tmp/claude-0/-home-user-VideoEdit/8531dbc8-a772-580f-8538-3f205e4051d8/scratchpad`
- Your clip list: `log/batches/<BATCH>` (one stem per line, e.g. `DJI_0048`)
- Metric summaries for your clips: `log/batches/<BATCH>_summary.txt`
  - Header: name | duration | resolution fps pixfmt bitdepth | shot time (camera clock) | white balance K | ISO | shutter | mean luma | sharpness median
  - Then per ~3 s segment: camera motion estimated from keyframes 0.5 s apart, on a 480-px-wide frame:
    `pan-L(26)` = camera pans left at 26 px/s; `pan-R`, `tilt-up`, `tilt-down`; `push-in(+3%/s)` = moving forward / zooming in;
    `pull-out` = moving backward; `roll`; `static`; `shaky(N)` = jitter. `sharp x1.2` = sharpness relative to the clip median
    (low values like x0.4 often mean motion blur or a transition); `luma` 0–255 brightness.
  - Motion numbers are approximate. Trust what you see in the frames when they disagree.
- Compact sheet per clip (≤18 frames, timestamps in seconds, `sh` = relative sharpness):
  `work/logsheets/<stem>.jpg` — view it with the Read tool.
- Detailed sheet (≤30 frames, larger): `work/sheets/<stem>.jpg`. Open it ONLY for clips you rate
  use_score ≥ 7, to pin down the best moment more precisely.

## What to write
Append one JSON object per clip (one line each, JSONL) to `log/<BATCH>.jsonl` with exactly these keys:

```json
{"file":"DJI_0048.MP4","duration":34.6,"shot":"2026-05-20T09:21",
 "content":"Milano Centrale main hall: low-angle walk under the arched skylight vault, travellers with suitcases",
 "location":"Milano Centrale station, Milan","location_confidence":"high",
 "camera_motion":"forward walk (push-in) with slight tilts; ends tilting down to the floor",
 "composition":4,"composition_notes":"strong symmetry and depth, leading lines to vanishing point",
 "clarity":4,"exposure_notes":"skylight slightly clipped, otherwise clean",
 "best_moments":[{"start":12.0,"end":15.0,"why":"centred symmetric vault, people crossing"}],
 "tags":["architecture","interior","symmetry","people","walk"],
 "fx":{"hud_track":"walking traveller centre-left 18–20 s","rotoscope":null,"clone":null,"fg_wipe":"green jacket passes lens ~21.5 s","whip":null},
 "use_score":7,
 "notes":"Milan, not Rome"}
```

Field rules:
- `content`: what is actually visible: subject, setting, light (golden hour / night / overcast / harsh noon), people, notable details. Be specific.
- `location`: name a place ONLY if you can confirm it from the frames (famous landmark clearly visible, or readable signage).
  Candidates include Rome (Colosseum, Roman Forum, Palatine, Arch of Constantine, Trevi Fountain, Pantheon, Piazza Navona,
  Spanish Steps, Vittoriano/Altare della Patria, St Peter's Basilica/Square, Vatican Museums, Sistine Chapel, Castel Sant'Angelo,
  Tiber bridges, Trastevere), Milan (Duomo, Galleria Vittorio Emanuele II, Milano Centrale), Florence, Venice, Pisa, etc.
  The trip might include places outside Italy; if signage or landmarks show another country, say so. Otherwise write
  `"unknown"` (optionally "generic Italian street" in content, but keep `location` = "unknown"). Never guess.
  `location_confidence`: high / medium / low.
- `camera_motion`: direction words (pan left/right, tilt up/down, push in / pull out, static, orbit, handheld walk) and when it changes.
- `composition` (1–5): 5 = striking, layered (foreground/midground/background), clean subject, strong lines/symmetry, good light;
  3 = ordinary snapshot; 1 = unusable (pointing at the ground, pocket footage, accidental recording, heavily obstructed).
- `clarity` (1–5): 5 = crisp, steady, well exposed; lower for motion blur, heavy noise, focus/exposure problems, big shake.
- `best_moments`: 1–3 windows (start/end seconds, 0.5–4 s long) that would make the best montage shots, using the
  frame timestamps. Empty list if the clip is unusable.
- `tags`: from landmark, architecture, street, people, portrait, food, detail, night, golden-hour, interior, crowd, water,
  sky, transport, walk, symmetry, texture, sign, art, nature, selfie, pov, other.
- `fx`: describe concrete opportunities (with times) or null:
  - `hud_track`: a clear subject a computer-vision HUD could track (a person walking, a dome, a statue) and when.
  - `rotoscope`: a person/statue cleanly separable from the background, big enough to place giant text behind them.
  - `clone`: locked-off/static camera with a person moving through the frame (needed for a clone effect).
  - `fg_wipe`: a foreground object (pillar, passer-by, wall edge) sweeping across the lens, usable as a wipe transition.
  - `whip`: a fast pan/whip moment usable as a transition.
- `use_score` (1–10): overall value for a high-end travel montage. 8–10 only for genuinely great shots.
- `notes`: anything else (duplicate of another clip, vertical framing, faces too close, people blocking, etc.).

## Process
1. Read your clip list and summary file.
2. For each clip: Read its compact sheet, combine with the summary, write the JSON line. Open the detailed sheet only for use_score ≥ 7.
3. Write the JSONL with a small Python or shell heredoc as you go (append), so partial progress survives. Ensure valid JSON (double quotes).
4. When done, reply with ONLY a short summary: number of clips logged, the 5–8 best clips (file, best window, one-line why, location),
   and any clips outside Italy or with D-Log/odd formats. No other commentary.

Do not modify or delete anything under `work/`. Do not download anything.

## Addendum (client preference, added later)
The client wants FEWER shots of themselves. Any clip where the camera operator films themselves
(selfie / vlog to camera / face filling the frame / arm-held self shot) must get the tag `selfie` and
its `use_score` lowered by 2 (unless the selfie is truly exceptional). Prefer places, streets, people
in context, architecture, light. Shots with the traveller seen from behind or small in a wide frame are fine.
