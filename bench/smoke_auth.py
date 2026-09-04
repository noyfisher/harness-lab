"""One minimal real call inside the agent container to verify auth and the result shape.

Costs a few cents at most (budget-capped). Prints the result event's field names, cost, model,
and the reply text. Never prints the credential.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from bench.run import C0_CONFIG, PERMISSION_FLAG, read_credentials

IMAGE = "harness-lab/agent.arm64.django__django-11099"


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
    name, value = read_credentials()
    tmp = Path(tempfile.mkdtemp(prefix="hl-smoke-"))
    cmd = [
        "claude", "-p", "--output-format", "json", PERMISSION_FLAG, "--no-session-persistence",
        "--model", model, "--effort", "low", "--max-budget-usd", "0.10",
        "Reply with exactly the word OK and nothing else.",
    ]
    quoted = " ".join("'" + c.replace("'", "'\"'\"'") + "'" for c in cmd)
    inner = f"mkdir -p /harness && cp -a /harness-src/. /harness/ && cd /testbed && {quoted}"
    r = subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/arm64",
         "-v", f"{C0_CONFIG}:/harness-src:ro",
         "-e", f"{name}={value}", "-e", "CLAUDE_CONFIG_DIR=/harness", "-e", "IS_SANDBOX=1",
         "-e", "DISABLE_AUTOUPDATER=1", "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1", "-e", "HOME=/root",
         IMAGE, "/bin/bash", "-lc", inner],
        capture_output=True, text=True, timeout=300,
    )
    print("exit code:", r.returncode)
    err = r.stderr.replace(value, "<redacted>")
    if err.strip():
        print("stderr tail:", err[-800:])
    out = r.stdout.replace(value, "<redacted>").strip()
    try:
        ev = json.loads(out)
    except json.JSONDecodeError:
        print("non-JSON stdout tail:", out[-800:])
        return 1
    print("result keys:", sorted(ev.keys()))
    for k in ("type", "subtype", "is_error", "num_turns", "duration_ms", "total_cost_usd", "session_id"):
        print(f"  {k}: {ev.get(k)}")
    print("  usage:", json.dumps(ev.get("usage"))[:300])
    print("  modelUsage:", json.dumps(ev.get("modelUsage"))[:300])
    print("  result text:", str(ev.get("result"))[:120])
    return 0 if not ev.get("is_error") else 2


if __name__ == "__main__":
    sys.exit(main())
