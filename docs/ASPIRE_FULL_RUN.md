# Surgical ASPIRE setup

Run scripts/run_full_aspire.py. Default: SAM3, scissors, Opus 4.6 at
https://cgv.cs.nthu.edu.tw:9128/v1 with TLS verification. No RF-DETR training
is required. Original upstream prompts are preserved byte-for-byte.
See [method audit](ASPIRE_FIDELITY.md) and [binding](ASPIRE_SURGICAL_BINDING.md).

## Active protocol

- Debug seeds 101-125; held-out seeds 1-100. The 6/4/10 split is retired.
- Motionless observation, up to five exploration blocks, initial debug sweep,
  then up to five Fix Loop repair sweeps.
- K=8 candidates, at most T=3 evolutionary rounds. First candidate A is the
  selected Fix Loop program verbatim. Every candidate uses the same debug seeds.
- Actor selects trace slices and sensor images. Each primitive has pre/post
  camera evidence. Fixed CaP visual-difference summaries do not replace inspection.
- Select the best debug program, freeze it, then run one held-out cohort.
  No held-out feedback repairs code. All-debug-failure skips held-out trials.
- After evaluation, the actor reports findings; a separate coordinator audits
  reusable repairs. Only debug-validated, approved patterns enter shared memory.
- Maximum 856 simulator trials; early success reduces this. At the 600-second
  watchdog the theoretical ceiling is about 143 hours plus model time.
- Request timeout 1800 seconds; output ceiling 128000 tokens. Context capacity
  is unverified. Every inspection/review request counts toward the explicit
  provider cap, which may stop a campaign before all stages finish.

## Checks and launch

Use Isaac Sim Python: C:/isaac-sim-450/python.bat.

```powershell
& C:/isaac-sim-450/python.bat scripts/test_aspire.py
& C:/isaac-sim-450/python.bat scripts/run_full_aspire.py --out logs/full-preflight --preflight
& C:/isaac-sim-450/python.bat scripts/check_aspire_gateway.py --out logs/full-preflight/gateway.json
```

Launch with a fresh --out under logs, explicit --prior-requests,
--request-budget and --max-total-requests. Never reset cumulative usage.
--smoke executes one actor exploration block; --prepare-only runs the
motionless bootstrap without inference. GUI is enabled unless --headless.
--resume continues an immutable campaign; old protocols require a fresh run.

For a bounded continuation, use the saved model, endpoint, simulator and display
settings through the wrapper. Rounds are zero-based; this completes round 1 and
pauses before round 2, program freezing, or held-out evaluation, without changing T=3:

```powershell
& scripts/continue_full_aspire.ps1 `
  -Out logs/aspire_codex61_scissor_sam3_igvi_20261005_run04 `
  -MaxTotalRequests 150 -PauseAfterRound 1 -RecoverInterrupted -Background
```

`-RecoverInterrupted` requires a verified inactive previous supervisor. The new
supervisor owns an exclusive campaign lock and records recovery metadata under
`recoveries/`; historical pending attempts and raw streams remain untouched and
count toward the cumulative cap. Previously acknowledged historical pending
attempts do not require another recovery flag. Never clear a ledger to regain budget.

Complete cached model turns and their saved inspection outputs are reused. A
partial streamed response is not executable. Completed physics trials, including
successful retry attempts, are reused with their corresponding trace/image directory.
Reusing the same pause boundary on a paused campaign performs no further work;
omit the pause flag only when the remaining search and evaluation are authorized.

If the user explicitly requests skipping the remaining search, stop the current
supervisor and its trial workers first, preserving all checkpoints and ledgers.
Then use `-EvaluateAfterRound 1` instead of `-PauseAfterRound 1` to select from
the completed Fix Loop and rounds 0-1 and run the 100 held-out trials directly.
The matching Python flag is `--evaluate-after-round 1 --resume`. Later-round
trials remain saved but are excluded from selection. `evaluation_plan.json`
records the user-requested truncation without changing the original T=3 plan.
This is an early evaluation, not a completed three-round search. Resumes retain
the evaluation boundary and frozen code/memory, even if the flag is omitted;
they never resume development search or reselect using held-out feedback.

For an explicitly requested shorter evaluation of an already frozen program,
resume with `-HeldoutTrials 30` (Python: `--heldout-trials 30 --resume`). Stop any
active supervisor and trial workers first. This changes only that campaign:
`evaluation_limit.json` records the original count, first 30 planned seeds,
frozen program hash, and outcomes completed before the change. Completed trials
are reused, and neither the original contract nor global defaults are changed.
Resumes retain the cap even when the flag is omitted. A different cap, a cap
that would exclude a completed outcome, or truncating a finished evaluation
is rejected. Reports explicitly label the reduced evaluation rather than
claiming the full 100-seed benchmark. Coordinator review still follows it.

If the user explicitly asks for a further reduction before evaluation finishes,
stop the active supervisor and workers, then use `-HeldoutTrials 20 -ReviseHeldoutLimit`
(Python: `--heldout-trials 20 --revise-heldout-limit`).
The revision must reduce the existing count, never exclude any completed result
(including uncheckpointed or retry results), and retain the frozen program.
The old limit is archived byte-for-byte under `control/evaluation_limits/`;
the new limit records its archive path and hash, so the final report retains
the user-requested stopping history. Ordinary resumes cannot change a saved cap.

## Durable artifacts under /logs

- Campaign state, contract, plan, upstream hashes, provider ledgers, raw model
  requests/responses, chosen inspections, replay sources, traces and images.
- skills/: task-local notes and evaluated programs, not validated shared skills.
- inherited_skills.json: shared library snapshot at actor dispatch.
- selection.json, frozen_program.py, frozen_skills.json: pre-evaluation selection.
- proposals/consolidation.json and skill_admission.json: findings, decisions,
  rejected patterns and admitted IDs.
- logs/aspire_shared_skills/sam3/: coordinator-admitted JSON/Markdown repairs.
- report.json and findings.md: results after evaluation and review. Unsolved
  searches save failure findings without claiming completed evaluation.

Check status with scripts/status_full_aspire.py followed by the campaign path.
