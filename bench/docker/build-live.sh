#!/usr/bin/env bash
# Build the agent image for one SWE-bench-Live instance.
# Usage: bench/docker/build-live.sh <instance_id>
#
# The Live base image name is the instance id with "__" -> "_1776_", lowercased.
# Ask bench.live for it so there is one source of truth; fall back to an inline
# transform if the study venv is not where we expect it.
set -euo pipefail
iid="$1"
cd "$(dirname "$0")/../.."
py="${PYTHON:-.venv/bin/python}"
base=""
if [ -x "$py" ]; then
  base="$("$py" -m bench.live image-ref "$iid")"
fi
if [ -z "$base" ]; then
  base="starryzhang/sweb.eval.x86_64.$(printf '%s' "$iid" | sed 's/__/_1776_/g' | tr '[:upper:]' '[:lower:]')"
fi
echo "base: $base"
docker build --platform linux/amd64 \
  --build-arg "BASE=${base}" \
  -t "harness-lab/agent.amd64.${iid}" \
  -f bench/docker/Dockerfile.live bench/docker
