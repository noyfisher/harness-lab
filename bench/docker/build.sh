#!/usr/bin/env bash
# Build the agent image for one instance. Usage: bench/docker/build.sh <instance_id>
set -euo pipefail
iid="$1"
cd "$(dirname "$0")/../.."
docker build --build-arg "INSTANCE_ID=${iid}" -t "harness-lab/agent.arm64.${iid}" -f bench/docker/Dockerfile bench/docker
