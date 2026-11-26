#!/bin/bash
# Wait politely for Drive to serve the Rome clips again: one 1 MB probe every 20 minutes. When a probe succeeds,
# start the gentle keyframe-only ingest (it has its own quota back-off) unless it is already running.
S=/tmp/claude-0/-home-user-VideoEdit/8531dbc8-a772-580f-8538-3f205e4051d8/scratchpad
ID=1ZC2Nv2XuU7tKV2eb4-0K5b4gqr4DAZS9      # DJI_0275 copy
LOG=$S/logs/quota_probe.log; TMPF=$S/probe/p.bin
while true; do
  code=$(curl -sS -L -r 0-1048575 -o "$TMPF" -w "%{http_code}" "https://drive.usercontent.google.com/download?id=$ID&export=download&confirm=t" 2>/dev/null)
  sz=$(stat -c %s "$TMPF" 2>/dev/null || echo 0)
  if grep -q "Quota exceeded" "$TMPF" 2>/dev/null; then st=QUOTA; elif [ "$code" = "206" ]; then st=OPEN; else st="OTHER"; fi
  echo "$(date -u +%H:%M:%S) $st code=$code size=$sz (copy probe)" >> "$LOG"
  rm -f "$TMPF"
  if [ "$st" = OPEN ] && ! pgrep -f ingest_sparse.py > /dev/null; then
    echo "$(date -u +%H:%M:%S) starting keyframe ingest of the Rome clips" >> "$LOG"
    setsid nohup python3 -I $S/tools/ingest_sparse.py $S/rome_all.tsv $S/work > $S/work/ingest_sparse_rome.out 2>&1 < /dev/null &
  fi
  sleep 1200
done
