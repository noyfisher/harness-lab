# Decision log

- [2026-09-03] **Direction: benchmarked self-improving harness, then OSS PRs.** Rationale:
  breadth of demos exists; measured proof does not. Employers ask how you know it worked,
  what it cost, what happened when it failed.
- [2026-09-03] **Compute: subscription-first, measured.** Max 20x is the default. Week 1
  spike records usage-window consumption per run; a pre-written rule (heaviest week <= 50%
  of weekly capacity) decides whether a $600-capped API key is created for overflow only.
  Terms: individual use of the official binary on the owner's own account; judged low risk,
  not zero.
- [2026-09-03] **Grading: swebench 5.0.2 test-spec + grading functions inside Epoch arm64
  images.** `run_evaluation`'s namespace flag cannot target Epoch's registry. Import paths
  verified against the pinned version before grade.py is written. sb-cli is the fallback.
- [2026-09-03] **Never `--bare`.** It skips custom agents/commands and does not read
  subscription tokens, silently.
- [2026-09-03] **Harness copy is a `cp`, never a symlink.** The improver may only mutate
  `harness-lab/harness/`.
- [2026-09-03] **All seeded agents on Sonnet.** C1 vs C0 isolates structure from model tier.
  Opus-lead (C1o) is an optional sensitivity variant.
- [2026-09-03] **Epoch arm64 images are publicly readable** (anonymous manifest fetch
  returned HTTP 200); no `docker login ghcr.io` required.
