# Scissors H/A/B with Isaac-window recording

The user deferred Kelly and scalpel on October 7, 2026 and requested scissors
H/A/B instead, with screen recording. This is a fresh **same-object frozen
skill-library ablation**, not cross-object transfer or another source campaign.
Preserve the completed source/Kelly runs and both blocked scalpel plans.

## Final results and success definition

All **15 paired rollouts** completed on October 7, 2026. The user requested
physical pick/place as the primary outcome: **lift_verified and place_verified**
from the existing independent private evaluator. A post-placement program
exception does not cancel this physical outcome. Apply the criterion equally
to every H/A/B case; keep raw status, execution_ok and strict success visible.

| Condition | Physical Success (Primary) | Strict Success | Verified Lift |
| --- | --- | --- | --- |
| H | **1/5 (20%)** | 1/5 | 2/5 |
| A | **0/5 (0%)** | 0/5 | 5/5 |
| B | **2/5 (40%)** | 0/5 | 5/5 |

B succeeds physically on seeds 903/904 but raises its own resting-support
verification error. Strict success retains the original
`result.success and execution_ok` criterion. The new primary metric is an
explicit **post-hoc reporting amendment**, requested after intermediate
outcomes were observed; the recorded amendment was saved after all 15 finished.
Neither the private evaluator nor frozen policies, cases, seeds or raw results
are changed. This small engineering pilot does not establish broad efficacy.

Evidence under `logs/scissor_hab_source_physics_20261007/`:

- `report.json` and `physical_success_report.json`: primary physical and
  secondary strict metrics, with per-seed outcomes and policy provenance.
- `control/physical_success_policy.json`: explicit scope, timestamp, formulas,
  post-hoc marker and hashes of frozen manifests/pre-amendment snapshots.
- `control/final_report_before_physical_policy.json`: original final strict report.
- `trials/<identifier>/result.json`: unchanged raw evaluator/program outcomes.

All 15 rollout videos and both recovery preflight videos verify. Cost is
**18/20 starts**, including the original failure, and **2 new / 101 cumulative
model attempts**. Frozen setup/program hashes are unchanged. **182 offline
tests passed** in 45.49 seconds, including rejection of lift-only success,
uniform scoring across conditions, raw-evidence preservation and avoiding
report overwrites while a supervisor is active.

Reporting-only refresh (no simulator, segmentation or model call):

```powershell
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scissor_hab_source_physics_20261007 --stage report
```

The live report stage writes a separate physical summary. `--follow-report`
refreshes it and updates the canonical final report only after the evaluation
supervisor exits and its lock is acquired; it first archives the strict report.

## Preserved setup: declared source-physics recovery

The original run below is preserved unchanged. Its final settling poll shows
all five objects present and only the Kelly distractor above the linear-speed
gate: **0.0032170 m/s**, versus **0.003 m/s**; scissors is **0.0001325 m/s**.
Actor and COM velocity audits both fail Kelly's gate. Pose deltas are small.
There is no saved poll history, so this is a final-poll diagnosis, not proof
of the entire timeout's cause. SAM3 and policy motion were not reached.

The source task contract used explicit solver **32 position / 8 velocity**
iterations; the new default task omitted them. Before any model generation,
the declared recovery matches these existing source settings for **all H/A/B**
in `logs/scissor_hab_source_physics_20261007/`. It does not relax gates, remove
distractors, replace seeds or tune based on manipulation outcomes. Capture
and replay must still validate; solver matching is a hypothesis until tested.

Preparation with `--session-parent` carries the failed start forward and
hashes its state, contract and plan. A stopped initial reset is eligible only
before generation/manipulation. Nested carry-in counts accumulate rather than
reset. **17 new / 18 total starts** are planned, still capped at **20**; model
accounting remains **99**, with at most two fresh A/B attempts. Original eight
setup hashes are verified unchanged. Private diagnosis is saved separately at
`logs/scissor_hab_checks_20261007/reset_diagnosis.json`, not in model context.

Live verification on October 7, 2026: the same seed's reset passed in **181
steps**, replay maximum error **1.7881e-7** is within 1e-6, and unchanged SAM3
returns target candidates in **top, front, left and right**. Both rendered
app-window MP4s decode (28 seconds each); an original frame was visually
verified to show Isaac GUI/scene. This establishes readiness on seed 801, not
manipulation efficacy or a general causal claim. The **173-test** offline suite
passed in 45.53 seconds. The background `--stage run` supervisor launched at
**18:21 Asia/Taipei**: generate A/B once, then execute the 15 paired trials.
At launch, three total simulator starts including the original failure and
zero manipulation outcomes. Read state/report/ledger for current progress.

The initial generation runner subsequently stopped at B's completion guard.
The preserved native stream has a complete closed tool block, valid original
JSON and terminal `message_stop`, but native `end_turn` was mislabeled chat
`stop`. Explicit `--recover-native-tool-finish` reparses the same saved bytes:
only the finish label changes. Original responses/SSE remain unchanged, the
normalized sidecar/control/stream hashes join the frozen manifest, and no new
model call or code revision occurs. Missing terminal events, unclosed blocks,
malformed JSON and token-limit truncations remain rejected.

Original A/B programs are frozen at **2 new / 101 cumulative model attempts**.
Recorded `--stage evaluate` resumed at **18:39 Asia/Taipei**, October 7, 2026;
H_s901 runs first. At 18:39:58, four total starts including the original failed
preflight and no completed manipulation outcomes. All **179** offline tests
passed in 45.10 seconds. Read the live state/report for later outcomes.

## Preserved original: recorded reset failure

The first seed-801 motionless start failed during scene reset, before initial
capture, replay or SAM3 readiness: `reset_settle_failed:
settle_timeout_or_missing_object`, after 750 settling steps. The supervisor
stopped and preserved the failed start. Actual cost is **one simulator start**,
**zero manipulation**, **zero new model calls**, **99 cumulative attempts**.
Neither A nor B was generated; there is no H/A/B success rate. No automatic
retry, seed substitution or changed physics/settling criterion was applied.

Native app-window recording worked: `trials/observe/screen.mp4` is a decoded
and visually verified **79.25-second, 1280x800, 4-fps MP4**, with 257 captured
PNG frames. `screen_preview.png` shows the actual Isaac GUI and surgical scene.
All **168** offline pilot/recording tests passed before this live preflight.
Diagnose the reset failure and explicitly account for any recovery before
attempting another startup or spending A/B generation calls.

## Frozen conditions and budget

- H: translated `examples/aspire/translated/scissor.py`, with only private
  require_lift/require_place assertions deferred to the independent scorer.
  All localization, motion and instrument-profile stages remain unchanged.
- A: one fresh generated program, empty source library.
- B: one fresh generated program, exactly the three admitted scissors repairs.
  No source winner/controller, task-local notes or previous pilot outcomes.
- Freeze A and B before any manipulation result. No refinement, Evo search,
  program selection, revisions or library admission during this pilot.
- Fresh motionless capture/replay seed **801**, final paired seeds **901-905**.
  These do not overlap the source campaign's development 101-125 or planned
  held-out 1-100. Fifteen manipulation rollouts plus two motionless starts:
  **17 planned simulator starts**, hard cap **20**, including failed starts.
- Model accounting carries **99** from completed Kelly; two fresh A/B
  attempts would reach **101**, under the cumulative authorization of 150.
  Skill origin remains the completed scissors source campaign.

Run root: `logs/scissor_hab_20261007/`. Same Kelly/scalpel task settings except
target and declared seeds: SAM3 text **scissor**, threshold 0.5, pinned FP16,
448-pixel RGB-D cameras, empty tray, four distractors, randomization off,
2400 simulation steps, 8-second motor timeout and no solver overrides.
No knife mapping, threshold reduction or crop frontend is carried over.

Motionless initial-state replay and two-camera perception readiness precede
generation. Private saved root XY is used only to diagnose target candidates,
never policy filtering or model input. H records each evaluation initial state;
A/B restore and verify it before motion. PhysX contact caches are not replayed.
Report execution, lift, placement and full success independently; five cases
and one program per condition provide engineering evidence, not broad efficacy.

## Recording

Preparation freezes `--record-screen` in the plan. Every started GUI trial,
including the two motionless preflights, captures the **rendered Isaac app
window** through `omni.kit.renderer.capture` swapchain capture, not Windows
desktop capture or just the robot's sensor cameras. No other app or audio is
recorded. Sampling is **4 fps**, with repeated frames preserving wall-clock
gaps; output is resized to at most 1280 pixels wide.

Each trial writes:

- `screen.mp4`: verified, decodable MP4 of the simulator window.
- `screen_recording.json`: scope, timings, capture count, dimensions and SHA256.
- `screen_frames/`: original PNGs and timestamp index retained as evidence.

Paths include `trials/H_s901/screen.mp4`, `trials/A_s901/screen.mp4` and
`trials/B_s901/screen.mp4`. Loading/scene-building frames can precede motion.
GPU capture and CPU encoding add wall-clock overhead equally to all conditions,
without adding physics steps or changing task tolerances. Requested recording
failure stops the run, preserving the consumed session rather than silently
continuing unrecorded or retrying. No generated program can access recorder
internals, private diagnostic state or other conditions' videos.

## Launch and status

Declared recovery (prepare once; never overwrite or resume the original
failed observation as though it succeeded):

```powershell
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scissor_hab_source_physics_20261007 --stage prepare --target scissor --accounting-parent logs/kelly_hab_20261007 --session-parent logs/scissor_hab_20261007 --match-source-physics --record-screen
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scissor_hab_source_physics_20261007 --stage run
```

Original launch, retained only as provenance; do not repeat:

```powershell
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scissor_hab_20261007 --stage prepare --target scissor --accounting-parent logs/kelly_hab_20261007 --record-screen
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scissor_hab_20261007 --stage run
```

Do not repeat preparation or launch a second supervisor. Read `state.json`,
`report.json`, `supervisor.json` and the checks directory's background logs for
actual status. A stopped preflight does not represent a 0/5 manipulation rate.
