#!/usr/bin/env bash
# Disk guard for a running bench.batch: interrupt the batch cleanly if host free space falls
# below a floor. Why: SWE-bench-Live images unpack ~6 GB each on first container start and the
# host has already been filled once (docs/decisions.md, 2026-09-12); an ENOSPC mid-batch corrupts
# grading state, while a SIGINT to the batch process lets the in-flight runs drain and records
# the batch as interrupted, so it can be resumed with the same command.
#   bench/disk_guard.sh <condition> [MIN_FREE_GB=8] [INTERVAL_S=120]
# Exits 0 when the batch process is gone (finished or interrupted).
set -uo pipefail
COND="${1:?condition, e.g. C1o}"; MIN_FREE_GB="${2:-8}"; INTERVAL="${3:-120}"
# Anchored on the interpreter so the pattern never matches this script or a shell wrapper
# (a plain `pgrep -f bench.batch` matches the grep's own command line; decisions.md 2026-09-13).
PAT="^\.venv/bin/python -m bench\.batch --bench live --condition ${COND}( |$)"
batch_pid() { ps -Ao pid,args | awk -v pat="$PAT" '{pid=$1; $1=""; sub(/^ /,""); if ($0 ~ pat) print pid}' | head -1; }
free_gb() { df -g / | tail -1 | awk '{print $4}'; }
raw=~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw
while :; do
  pid="$(batch_pid)"
  if [ -z "$pid" ]; then echo "$(date -u +%FT%TZ) batch ${COND} not running; guard exiting"; exit 0; fi
  fg="$(free_gb)"; blocks="$(stat -f %b "$raw" 2>/dev/null || echo '?')"
  echo "$(date -u +%FT%TZ) pid $pid host free ${fg} GB Docker.raw blocks ${blocks}"
  if [ "$fg" -lt "$MIN_FREE_GB" ]; then
    echo "$(date -u +%FT%TZ) LOW DISK: ${fg} GB < ${MIN_FREE_GB} GB; sending SIGINT to batch pid $pid"
    kill -INT "$pid"
    sleep 30
    # A second SIGINT is still a clean interrupt for bench.batch; never escalate to SIGKILL here.
    [ -n "$(batch_pid)" ] && kill -INT "$pid"
    echo "$(date -u +%FT%TZ) interrupt sent; resume the batch with its original command once space is freed"
    exit 3
  fi
  sleep "$INTERVAL"
done
