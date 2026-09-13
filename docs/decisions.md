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
- [2026-09-05] **Docker VM freeze, not a harness bug.** The first candidate screen produced
  sessions that ended at turn 1 with "Unknown skill: swe-fix" and zero cost. Root cause: the
  Docker Desktop VM had frozen (no VM log lines for an hour; API 500s; containers unkillable);
  a forceful restart fixed it, and both the seed and candidate exports load the command in a
  healthy container. `run.py` now classifies any one-turn zero-cost session as `error`
  (infrastructure) so it can never count as a failure of the agent.
- [2026-09-05] **Loop wedged after 4 consecutive rejects; owner decision: revise the improver
  prompt, 2 more iterations, then write up.** All four hypotheses added process (broader tests,
  root-layer localization, forced specialists, both combined); none flipped an always-fail train
  instance at k=3 and the one confirmed candidate regressed a held-out task at 1.3x the seed's
  cost. `improve.md` now tells the improver what the archive shows and restricts this iteration
  to subtraction, budget reallocation, or handoff quality. Cap raised to 7 for this run only.
- [2026-09-05] **Usage-wall handling tightened.** Iteration 5's train screen had 6 zero-cost,
  zero-turn timeouts (the CLI waited on the exhausted 5-hour window until the wall clock fired)
  and iteration 6's improver session failed with "You've hit your limit". Both are
  infrastructure: `run.py` now classifies a timeout with no result event and no spend as
  `paused` (the batch re-queues it), and `loop.py` pauses 30 min and retries the improver
  session on rate-limit text. The 6 runs are superseded as `paused`; the candidate is
  re-screened. Lesson for the protocol: daytime screens compete with the owner's own usage.
- [2026-09-04] **Credential exposure incident (recorded for completeness).** A diagnostic probe
  during the Docker VM freeze raised a Python exception whose traceback included the container's
  subscription token in the command arguments, printing it into the local Claude Code session
  log on the owner's machine. It never entered the repo, git, or any remote. The owner was
  advised to regenerate the token with `claude setup-token`. Probes now catch exceptions and
  redact the credential before printing.
- [2026-09-11] **C1o sensitivity variant started (owner decision, over phase B).** Tag
  `harness-c1o` (d7bc81f) = seed harness with `lead.md` on `claude-opus-5` and the five
  specialists pinned to `claude-sonnet-5` by explicit id (the Lead is the top-level session, so
  the run passes `--model claude-opus-5`; specialists must not inherit it). Budget stays at
  $4.00 per run for parity with C1: a one-turn container call showed claude-opus-5 and
  claude-sonnet-5 priced within 2% of each other per cache-creation token in the CLI's estimate,
  so the cap is not model-tier-biased. Batch: `--condition C1o --harness-sha harness-c1o
  --split all --k 3 --workers 2`, workers reduced from 3 because Opus runs draw on the scoped
  weekly cap that the owner's own Opus/Fable sessions share.
- [2026-09-12] **C0o added post hoc** (single agent on claude-opus-5, same config as C0). C1o came
  in at 0.900 [0.808, 0.975] vs C1 0.750 (5 flips, 0 regressions, p=0.018), but it mixes a stronger
  model into the harness, so the effect is confounded with model tier. C0o de-confounds it. Not
  pre-registered; labeled as an extension in every table. Weekly cap at 40% before the run.
- [2026-09-12] **C0o result closes the model-tier question.** Single agent on Opus 5: 0.875
  [0.775, 0.975], $0.62/solve, 0 flaky. Paired C0o -> C1o: 0 flips, 1 regression, p=0.28. The
  Opus-lead harness's gain over the Sonnet harness was the model, not the orchestration. At both
  tiers the single agent is the cheaper condition with equal or better pass rate.
- [2026-09-12] **Verified-study images removed from Docker to make room for SWE-bench-Live.**
  The 43 `harness-lab/agent.arm64.*` agent images and the Epoch arm64 base images are deleted
  locally; both are reproducible from `bench/docker/Dockerfile` and the public registry, and
  every Verified result is already committed. The owner's own old containers are untouched.
  Live candidate count set to 60 (not 90): the spike's 5-of-6 gold keep rate makes 60 enough
  for a 40-instance subset, and Live images are 1.7 to 3.7 GB each.
- [2026-09-12] **Disk incident during Live gold validation.** Pulling all 60 candidate images
  filled the host: Docker's disk image grew from 107 GB to ~291 GB and the host hit ENOSPC (the
  gold run then failed writing its results file and the daemon degraded). Cause: Live images
  expand to roughly 4x their Hub download size on disk, and 60 of them exceeded the 176 GB that
  was free. Recovery: restart Docker Desktop, remove all Live images, prune. Corrected plan:
  gold-validate in waves of 12 with a per-wave cleanup of images that fail gold, keep only the
  40 selected images plus their agent images, and gate every pull on 60 GB of host headroom.
- [2026-09-12] **Docker credential helper bypassed for pulls.** After the disk incident, every
  `docker pull` hung before any network activity while the daemon itself answered; the cause was
  `docker-credential-desktop` (invoked on each pull) hanging against a wedged Docker Desktop
  backend, which also idle-restarted the VM. `~/.docker/config.json` had no stored logins, so
  `credsStore` was set to empty (backup at `config.json.bak-20260912`); public pulls need no
  helper. Restore the original file to re-enable Docker Hub login through Desktop.
- [2026-09-13] **Live grading timeout raised to 3600 s (infra parameter, post-freeze).** The
  first C0o Live runs on conan hit the grader's 1800 s cap: its ~4,000-test suite under emulation
  with two concurrent gradings exceeds 30 minutes. This is the grader's wall clock, not the
  agent's budget or timeout, so it does not touch the pre-registered comparison; affected runs
  were `error` (uncounted) and are re-run by resume. Container-start timeout raised 300 -> 900 s
  for the same contention. `bench.batch` now takes `--grade-timeout`.
- [2026-09-13] **Live traces before this fix landed in `results/traces/` (the Verified directory)**
  because one path in `run.py` still used the Verified constant; manifests record the real path,
  so nothing is lost. Fixed for subsequent runs; the C0o Live runs graded before the fix keep their
  recorded paths.
- [2026-09-13] **Live image footprint is ~2x the pulled size after first use.** During the C0o
  Live batch, Docker's disk image grew ~110 GB beyond the pulled images while no container or
  image accounted for it, then stopped growing once every instance had run once; sampling over
  ten minutes and three runs showed zero growth. Reading: layers are unpacked into snapshots on
  first container start, so budget ~6 GB per Live instance, not 3. A disk guard interrupts the
  batch cleanly below 8 GB free.
- [2026-09-13] **C0o Live batch complete (22:05Z).** 120 counted runs (40 instances x k=3):
  pass rate 0.492 [0.350, 0.633], 16 solid-pass / 7 flaky / 17 solid-fail, $1.77 per solve,
  mean wall 853 s; train 0.472, held-out 0.521; $104.71 at list price. Three `error` runs are
  uncounted: two grader timeouts at the old 1800 s cap (re-run by the resume) and one agent
  container that never started under the old 300 s start cap (no trace, no patch). No counted
  run hit the agent's 3600 s timeout or the $4 budget. Roughly half the Verified rate for the
  same agent: Live lite is harder for it, as the spike suggested. `results/live/c0o-stats.json`.
- [2026-09-13] **All C0o Live traces live in `results/traces/`, not only the pre-fix ones.**
  `bench.batch` imports `bench.run` in-process, so the resumed batch (started 09:23Z) kept the
  old trace directory for its whole life; the fix landed at 17:53Z. Every manifest records the
  real path and nothing is lost. The C1o batch starts a fresh process and writes to
  `results/live/traces/`. Not moving the files: the manifest is append-only.
- [2026-09-13] **The Live harness leaks its container when killed on timeout.** Found after the
  batch: two `git-launch-<id>-*` containers from the C0o batch's 1800 s grader timeouts still
  running 15 hours later, and four from the gold-validation waves running 19 to 22 hours, each
  pinning a base image that the wave cleanup had untagged (the four "dangling" images, 10.7 GB).
  All six, plus the never-started agent container, are removed, and the four images with them.
  Fix: `grade_live` and `gold_validate` now remove any leftover `git-launch-<id>-*` container in
  a `finally` (tests added). **Consequence for the numbers:** those six emulated containers were
  burning CPU for the entire C0o batch, so C0o's Live wall times are inflated by contention that
  C1o will not see. The pre-registered primary metric (pass rate) and cost per solve (token
  based) are unaffected; wall time is reported as a secondary metric and this confound is stated
  wherever the two conditions' wall times are compared.
- [2026-09-13] **C1o launch task: disk gate lowered 40 -> 15 GB, disk guard made a script.**
  Docker's disk image stopped growing once every Live instance had run once and stayed flat
  for the last ~80 runs at ~20 GB host free; a 40 GB gate would have refused a launch that is
  safe. `bench/disk_guard.sh <condition> [floor GB] [interval]` sends SIGINT to the batch's
  Python process below the floor (8 GB) and exits when the batch is gone; the scheduled task
  starts it alongside the batch. Host free after cleanup: 22 GB; Docker images 261 GB.
- [2026-09-13] **CI was red from 06:38Z on every commit; cause was float noise, not code.** The
  site-drift step regenerates `results/site` on the Linux runner and diffs it byte for byte;
  three Wilcoxon p-values differed from this arm64 Mac in the 17th digit (libm). The 213 tests
  passed throughout. Fix: the site serialiser rounds floats to 10 decimals (test added) and the
  site was regenerated. Lesson kept: a byte-for-byte gate needs platform-stable output.
- [2026-09-13] **C1o Live batch started 23:01Z, ahead of the planned Monday reset.** Owner's
  call on the strength of remaining weekly usage headroom (the deferral to after the reset was
  usage management, not protocol; conditions and parameters are exactly those frozen in
  `docs/protocol-v2.md`). Batch id `live-C1o`, harness tag `harness-c1o`, two workers, disk
  guard armed at 8 GB, host free 27 GB at start. The one-time launch task for Monday is
  disabled so it cannot start a second copy. The owner's day-trader scheduled tasks stay paused
  through Monday so the batch has the usage bucket to itself.
