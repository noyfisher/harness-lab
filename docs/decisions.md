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
- [2026-09-03] **arm64 coverage gap accepted as a stated limitation.** Epoch has arm64 images
  for 420/500 Verified instances; xarray 0/22, matplotlib 7/34, scikit-learn 7/32. The
  subset tilts toward pure-Python repos. x86_64 images exist for all 500; an amd64
  sensitivity run under emulation is a possible later addition, not part of the study.
- [2026-09-03] **Only the `latest` tag exists on Epoch images.** Runs record the image digest
  so a re-tag cannot silently change the environment.
- [2026-09-03] **Root inside the container with `IS_SANDBOX=1`.** The permission-bypass flag
  is refused for root unless the sandbox marker is set; the container is throwaway.
- [2026-09-03] **Network egress is NOT restricted in v1 benchmark runs.** The SWE-bench repos
  are pinned 2019-2023 commits of well-known projects; exfiltration risk from repo content is
  judged negligible for phase A. Phase B (arbitrary OSS repos) must add egress restriction
  before any run. Tracked as an open item.
- [2026-09-03] **Config dir is copied to a writable path inside the container.** Claude Code
  writes `.claude.json` and backups into its config dir; the harness checkout is mounted
  read-only and copied, so runs never dirty the harness git tree.
- [2026-09-03] **Model pinned by explicit id, agents inherit.** In CLI 2.1.76 `--model sonnet`
  resolved to claude-sonnet-4-6 (seen in the smoke call's modelUsage). Runs pass
  `--model claude-sonnet-5`; all six harness agents use `model: inherit` so the Lead and every
  specialist run the same model. Manifests record the actual model ids from modelUsage.
- [2026-09-03] **Auth verified inside the container** with the subscription token: one call,
  subtype success, $0.02 at list price. Root + `IS_SANDBOX=1` + permission bypass works.
- [2026-09-04] **Spike manifests live in `results/spike-runs.jsonl`, not `runs.jsonl`.** The spike
  predates the protocol freeze, used k=1 on three hand-picked instances, and includes one
  duplicate C0 run caused by a grading infra retry. `runs.jsonl` holds protocol runs only.
- [2026-09-04] **Grading infra failures are regraded, not re-run.** `bench/regrade.py` rescores an
  existing patch and appends a superseding manifest; the agent's cost and trace are kept.
- [2026-09-04] **Compute: subscription only; no API key.** Spike: ~$7.9 list-equivalent moved
  the 5-hour window 3 points and the weekly cap < 0.5 points. Projected study ~$760 over ~4
  weeks; heaviest week <= 20% of weekly capacity. Re-check after the C0 baseline batch.
- [2026-09-04] **Protocol frozen v1.** N=40 (24/16), k=3, claude-sonnet-5 medium, $4.00 budget,
  2400 s wall, 3 workers, batches overnight. Harness seed = tag `harness-seed` (9ec1540).
- [2026-09-04] **Post-C0 re-check: weekly cap ~= $1,600 list-equivalent; subscription decision
  stands.** Weekly moved 7 points on ~$111 of mixed usage (batch + orchestration), one point over
  the literal threshold; attribution puts the batch at ~6 points. See `spike.md`.
- [2026-09-04] **Improver loop judgment calls (improver/loop.py).** (a) Candidate branches start
  at HEAD with only `harness/` reset to the base sha, so the driver and `/improve` stay current
  while what is measured (`harness/` at the sha) is unchanged; asserted with
  `git diff --quiet <base> HEAD -- harness`. (b) `results/` and `improver/state/` are exempt
  from the clean-tree precondition (a batch may be appending). (c) Rejected candidates are
  still committed on their branch so evidence survives and `main` ends clean. (d) The leak
  check scans added lines only; `HYPOTHESIS.json` is exempt from the instance-id check because
  `expected_flips` must name train ids, and `run.py` now strips that file from the export so
  it never enters the agent container. (e) The k=1 screens are cheap filters; only the k=3
  confirmation applies the accept rule. (f) `batch.py` default budget corrected to $4.00 to
  match protocol v1 (both baselines already ran at $4.00).
- [2026-09-04] **Unattended improver = a long-running host process, not a scheduled Claude
  session.** `python -m improver.loop --iterations K` keeps disk state (`archive.json` with
  `.bak`, `best.json`, `owner-decisions.md`) and resumes from it; background processes survive
  on this machine, so the team-auto scheduled-task shim is unnecessary here.
- [2026-09-04] **Improver host session authenticates with the long-lived token**, not the CLI
  login. First real iteration failed at turn 1 with a 401 (host OAuth access token expired;
  a plain `claude -p` then hung on re-auth). `loop.py` now injects the credentials-file token
  into the improver's environment, the same credential the containers use.
- [2026-09-04] **Leak check scoped to container-bound files.** The first real candidate was
  rejected because its HYPOTHESIS.json rationale quoted a hidden test name. That file never
  enters a container (run.py strips it), so it is exempt; every other harness file is still
  checked for test names and instance ids. Added `--reuse-candidate REF` so an existing
  candidate can be re-screened after an infra stop or a rule change without a new proposal.
- [2026-09-04] **Batch preflight retries a failed image inspect.** A re-screen stopped at
  preflight on an image that both baselines had used and that `docker images` listed; a single
  transient Docker Desktop error under load. Persistent misses still fail the batch.
