#!/bin/bash
# Probe Drive download quota every 10 minutes with a 1 MB range request; log result.
LOG="$1"; ID="${2:-1ckk4iORpkws8VmCQgFdOrJmsCzSk2TrG}"; TMPF="$3"
while true; do
  code=$(curl -sS -L -r 0-1048575 -o "$TMPF" -w "%{http_code}" "https://drive.usercontent.google.com/download?id=$ID&export=download&confirm=t" 2>/dev/null)
  sz=$(stat -c %s "$TMPF" 2>/dev/null || echo 0)
  if grep -q "Quota exceeded" "$TMPF" 2>/dev/null; then st=QUOTA; elif [ "$code" = "206" ]; then st=OPEN; else st="OTHER"; fi
  echo "$(date -u +%H:%M:%S) $st code=$code size=$sz" >> "$LOG"
  rm -f "$TMPF"
  sleep 600
done
