"""Gold-validate SWE-bench-Live candidates in waves, removing each wave's images afterwards.

Why: Live images are ~3 GB each on disk and a candidate list of 60 exceeded the host's free
space when pulled all at once (docs/decisions.md, 2026-09-12). Gold validation needs an image
only transiently, so this pulls and grades a wave, merges the results into the gold JSON, and
deletes the wave's images before the next one. A headroom gate refuses to start a wave with
less than --min-free-gb free on the host.

    python -m bench.live_gold_waves --ids-file bench/live-candidates.json \
        --out bench/live-gold-results.json --wave 10 --workers 2 --min-free-gb 60
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from bench import live

ROOT = Path(__file__).resolve().parents[1]


def free_gb(path: str = "/") -> float:
    return shutil.disk_usage(path).free / 1e9


def load_ids(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    ids = data["candidates"] if isinstance(data, dict) else data
    return [x["instance_id"] if isinstance(x, dict) else x for x in ids]


def remove_images(ids: list[str]) -> None:
    refs = [live.image_ref(i) for i in ids]
    subprocess.run(["docker", "rmi", "-f", *refs], capture_output=True, text=True, timeout=600)
    subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, text=True, timeout=600)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--wave", type=int, default=10)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--min-free-gb", type=float, default=60.0)
    ap.add_argument("--keep", action="store_true", help="do not remove images after each wave")
    a = ap.parse_args(argv)

    ids = load_ids(Path(a.ids_file))
    out = Path(a.out)
    done = json.loads(out.read_text()) if out.exists() else {}
    todo = [i for i in ids if i not in done]
    print(f"[waves] {len(ids)} candidates, {len(done)} already graded, {len(todo)} to do, wave={a.wave}", flush=True)
    t0 = time.time()
    for w in range(0, len(todo), a.wave):
        chunk = todo[w:w + a.wave]
        fg = free_gb()
        if fg < a.min_free_gb:
            print(f"[waves] STOP: only {fg:.0f} GB free on the host (< {a.min_free_gb:.0f}); not starting wave {w // a.wave + 1}", flush=True)
            return 2
        print(f"[waves] wave {w // a.wave + 1}: {len(chunk)} instance(s), host free {fg:.0f} GB, {time.strftime('%H:%M:%SZ', time.gmtime())}", flush=True)
        try:
            live.gold_validate(chunk, str(out), workers=a.workers, timeout=a.timeout)
        finally:
            if not a.keep:
                remove_images(chunk)
        res = json.loads(out.read_text()) if out.exists() else {}
        got = [i for i in chunk if i in res]
        passed = sum(1 for i in got if res[i])
        print(f"[waves]   graded {len(got)}/{len(chunk)}, resolved {passed}; cumulative {sum(res.values())}/{len(res)}; host free {free_gb():.0f} GB; elapsed {(time.time() - t0) / 60:.0f} min", flush=True)
    res = json.loads(out.read_text()) if out.exists() else {}
    print(f"[waves] done: {sum(res.values())}/{len(res)} resolved; failed: {sorted(k for k, v in res.items() if not v)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
