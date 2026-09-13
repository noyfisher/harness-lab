#!/usr/bin/env bash
# After gold validation: draw the 40-instance Live subset, pull its 40 base images, and build the
# 40 amd64 agent images, with a host headroom gate before each pull.
#   bench/live_prepare_subset.sh [N=40] [SEED=20260912] [MIN_FREE_GB=60]
set -euo pipefail
cd "$(dirname "$0")/.."
N="${1:-40}"; SEED="${2:-20260912}"; MIN_FREE_GB="${3:-60}"
PY=.venv/bin/python

echo "=== select N=$N seed=$SEED from gold-passing candidates ==="
$PY -m bench.select_live --n "$N" --seed "$SEED" --gold-results bench/live-gold-results.json --out bench/live-subset.json
$PY - <<'EOF'
import json
s = json.load(open("bench/live-subset.json"))
ids = sorted(s["train"] + s["heldout"])
open("bench/.cache/live-subset-ids.txt", "w").write("\n".join(ids) + "\n")
print(f"subset: {len(ids)} ids, train {len(s['train'])}, heldout {len(s['heldout'])}, strata {s.get('strata')}")
EOF

free_gb() { df -g / | tail -1 | awk '{print $4}'; }
echo "=== pull + build agent images (gate: ${MIN_FREE_GB} GB free) ==="
i=0
while read -r iid; do
  i=$((i+1))
  if [ "$(free_gb)" -lt "$MIN_FREE_GB" ]; then echo "STOP: host free $(free_gb) GB < $MIN_FREE_GB before $iid"; exit 2; fi
  if docker image inspect "harness-lab/agent.amd64.$iid" >/dev/null 2>&1; then echo "[$i] $iid: agent image present"; continue; fi
  $PY -c "from bench import live; import sys; sys.exit(0 if live.ensure_image('$iid') else 1)" || { echo "[$i] $iid: PULL FAILED"; continue; }
  bench/docker/build-live.sh "$iid" >"results/batches/build-live-$iid.log" 2>&1 && echo "[$i] $iid: built ($(free_gb) GB free)" || echo "[$i] $iid: BUILD FAILED (see results/batches/build-live-$iid.log)"
done < bench/.cache/live-subset-ids.txt

echo "=== summary ==="
missing=0; while read -r iid; do docker image inspect "harness-lab/agent.amd64.$iid" >/dev/null 2>&1 || { echo "missing: $iid"; missing=$((missing+1)); }; done < bench/.cache/live-subset-ids.txt
echo "agent images missing: $missing / $(wc -l < bench/.cache/live-subset-ids.txt | tr -d ' ')"
docker system df | sed -n 2p; echo "host free: $(free_gb) GB"
