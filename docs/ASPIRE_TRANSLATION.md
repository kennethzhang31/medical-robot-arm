# Full-stage translations for ASPIRE

The five original instrument controllers now have standalone, sensor-based
ASPIRE starting skills in [examples/aspire/translated](../examples/aspire/translated).
Each contains the complete approach, pick, transfer and place sequence. They
are executable candidates for refinement, not trained Diffusion Policies.

The robot, tables, tray, cameras, assets, physics, original recorder controllers,
and DP training pipeline are unchanged. No downloaded collection instruments
have been registered by this change. The shared corrected TCP controller and
bounded place servo remain in use.

## Source and translation boundaries

| Target | Original source | Standalone ASPIRE program |
| --- | --- | --- |
| Scalpel | [scalpel recorder](../backends/phase3_grid_split_scalpel_recorder.py) | [scalpel.py](../examples/aspire/translated/scalpel.py) |
| Scissors | [scissor recorder](../backends/phase3_grid_split_scissor_recorder.py) | [scissor.py](../examples/aspire/translated/scissor.py) |
| Love retractor | [Love recorder](../backends/phase3_grid_split_love_retractor_recorder.py) | [love_retractor.py](../examples/aspire/translated/love_retractor.py) |
| Kelly forceps | [Kelly recorder](../backends/phase3_grid_split_kelly_recorder.py) | [kelly.py](../examples/aspire/translated/kelly.py) |
| Second scalpel | [type-2 recorder](../backends/phase3_grid_split_scalpel_type2_recorder.py) | [scalpel_type2.py](../examples/aspire/translated/scalpel_type2.py) |

The original `pick_and_place_object` function alone does not describe the
effective controller. [Phase 4 feedback](../src/recorder/phase4_feedback.py)
replaces pose and finger gates, selects a symmetric wrist branch using eventual
placement, aligns the instrument, compensates object-to-hand offsets, computes
release clearance, and routes far-side transfers around the robot base.

The translations preserve this stage structure and nominal vertical clearances:
hover 230 mm, pre-grasp 60 mm, lift 160 mm, above-tray 180 mm and retreat 220 mm.
These distances are relative to the estimated grasp or calibrated tray, not
seed-specific target locations. Transfer height is also raised to preserve
clearance; transfer timing accounts for translation and wrist rotation.

They are **sensor adaptations, not trajectory-equivalent ports**. The original
controllers query target poses and mesh geometry. The new programs use camera
detections, metric depth, robot state and fixed fixture calibration. Raw root
offsets cannot be added to a surface point from depth, and root-frame yaw offsets
(including type-2's 90-degree correction) are not added again to an already
estimated physical long axis.

Contact-height starting calibrations above the table are 4 mm (scalpel), 3 mm
(scissors), 3 mm (Love), 8 mm (Kelly), and 5 mm (type-2), clamped by the existing
orientation-dependent robot finger floor. They are hypotheses requiring live
validation. Kelly's 8 mm starts from its original 18+4-14 mm adjustment, with
the root location replaced by the table calibration. The scalpel's former extra
descent is folded into its 4 mm minimum contact height. Love retains the original
0.25 mm contact tolerance; the others request 1 mm. Other convergence timing and
gates continue to use the adapter's bounded controller.

## Stages available to ASPIRE

| Stage | Translation |
| --- | --- |
| Prepare / clear view | Open fingers and park the hand relative to measured home |
| Perceive / grasp pose | Confirm target in two views; derive center and axis from masked depth |
| `OPEN_HOVER` | Move to the estimated grasp plus hover clearance |
| `LOWER_PRE` | Descend to the pre-grasp waypoint |
| `LOWER_GRASP` | Reach calibrated contact height with tight pose convergence |
| `LOWER_EXTRA` | Optional, floor-clamped descent; disabled in all five initial profiles |
| `CLOSE` | Close immediately while holding measured TCP, with encoder stability |
| `LIFT_CLEAR` / verify | Lift and require the independent evaluator's verified-lift flag |
| `MOVE_TO_TARGET` | Rotate toward tray axis, compensate estimated grip offset, and use a base detour when needed |
| Verify hold | Require held state before lowering into the tray |
| `LOWER_PLACE` | Lower using estimated support offset and calibrated finger/rim clearance |
| `OPEN` | Release while holding measured TCP |
| `RETREAT` | Clear the released instrument vertically |
| Return / settle / verify | Return toward home, allow settling, require verified placement |

The active originals omit or merge `LOWER_EXTRA` for the requested target. An
optional branch is retained for future refinement; an additional descent is not
forced just to emit a stage name. Setup and transfer remain separate from the
original DP recording windows (`LOWER_PRE..LIFT_CLEAR` and
`LOWER_PLACE..RETREAT`). These skills do not currently export DP-compatible H5.

Every stage prints `STAGE_BEGIN` and `STAGE_END`. Exceptions include the target
and stage name and propagate to the worker. The independent evaluator still
decides physical success, including existing footprint, center, directed axis,
stable support, retreat and preload-preservation checks. Finishing a script
does not certify manipulation success; inspect `result.json`.

## Public API additions

- `get_table_height()`: fixed support-plane calibration in robot-base metres.
- `get_tcp_floor(quaternion_wxyz, surface="table" | "tray")`: motionless query
  of known robot finger geometry and fixed table/tray calibration. Tray floor
  reserves the existing P4 4.5 mm servo margin above the lip.
- `get_task_feedback()`: coarse outcome flags and reason already used in trial
  feedback. This exposes verified lift/placement booleans, not target coordinates,
  mesh or expert trajectories. The flags are evaluator-derived, not perception.
- `goto_pose` accepts the original Love controller's 0.25 mm contact tolerance;
  a tighter request can still time out.

The RGB-D observation schema is unchanged. All comparison methods using these
skills should receive the same coarse feedback API and fixture calibration.

## Run and refine

Ten matching protocols are in [configs/aspire/translated](../configs/aspire/translated):
one RF-DETR and one SAM3 protocol per target. Default detector setup is documented
in [ASPIRE_RFDETR.md](ASPIRE_RFDETR.md); it requires a trained surgical checkpoint.
SAM3 is an explicit alternative documented in [SAM3_WINDOWS.md](SAM3_WINDOWS.md).
Neither service is started by a skill or the launcher.

From the repo root, with the selected perception service already running:

```powershell
# One development trial with a visible simulator; no LLM call.
.\scripts\run_translated_aspire.ps1 -Target scissor -Perception sam3 `
  -Seed 501 -Gui -Out aspire_runs\translated_scissor_watch_01

# Initial translated skill across development seeds, using trained RF-DETR.
.\scripts\run_translated_aspire.ps1 -Target kelly -Command evaluate `
  -Split dev -Out aspire_runs\translated_kelly_baseline_01

# Initial candidate plus up to two Qwen revisions on development cases only.
.\scripts\run_translated_aspire.ps1 -Target scissor -Perception sam3 `
  -Command refine -Rounds 3 -Out aspire_runs\translated_scissor_qwen_01
```

Select any of the five target identifiers in the table above. Use a new output
directory for every run. The launcher checks service health before starting
Isaac Sim. A healthy service does not establish perception accuracy. The
refinement launcher reads `API_KEY` from `.env`, uses the current working Qwen
alias, and preserves candidate files and trial evidence. It does not touch
evaluation seeds. Three rounds means the initial script plus up to two revisions;
the campaign may stop early if all development cases succeed.

These protocols reserve development seeds 501..505 and evaluation seeds 601..605.
They are the same across targets to facilitate paired trials; identical seeds
alone do not establish identical complete scenes across target classes.

After freezing a candidate, evaluate **that file**, not the initial translation:

```powershell
& C:\isaac-sim-450\python.bat scripts\aspire.py evaluate `
  --config configs\aspire\translated\scissor-sam3.json `
  --code aspire_runs\translated_scissor_qwen_01\frozen_program.py `
  --split eval --out aspire_runs\translated_scissor_final_01
```

Review stage logs in `result.json` (`stdout`/`stderr`) and `worker.log`, and inspect
saved frames and `actions.jsonl`. Campaign `candidate_0.py` is a copy of the
translated initial script; later candidates are LLM revisions. Preserve all
trials, including failures, when calculating success rates.

## Generation and validation

The shared [template](../examples/aspire/translated/skill.py.in) expands into
five self-contained Python files. ASPIRE receives the full expanded program,
so it can revise perception, grasp selection and every motion stage. There is
no hidden package helper executing an expert controller on its behalf.

```powershell
& C:\isaac-sim-450\python.bat scripts\build_aspire_skills.py --check
& C:\isaac-sim-450\python.bat scripts\test_aspire.py
```

Edit the template or [profiles](../src/aspire/translation.py), then run the builder
without `--check` to regenerate starting skills. Regeneration overwrites those
five files and their ten protocols, so make experimental revisions in campaign
copies. [manifest.json](../examples/aspire/translated/manifest.json) records source
controller, shared Phase 4, template and translated-program hashes. `--check`
also detects source provenance drift.

Contract tests execute all five programs through the real upstream ASPIRE
executor with a kinematic robot fixture. They verify the complete stage flow,
grasp-offset compensation and tray alignment, fixture height handling, and
aborting a missed lift or mismatched target. They do not simulate contact physics
or establish success on real instrument meshes.

Two live SAM3 trials (development seeds 501 and 502) failed scene reset with
`reset_settle_failed: settle_timeout_or_missing_object`, before any skill stage.
They are retained under `aspire_runs/translated_scissor_smoke_01` and `_02` and
do not establish translation or grasp performance. In the final saved reset
reports, Kelly's linear speeds were 3.13 and 3.46 mm/s against the 3 mm/s gate;
all required objects must settle, including distractors. RF-DETR was not running
during validation. No settling criteria or environment physics were changed.

Sensor masks may be partial or
include table pixels. PCA's sign is resolved by visible end widths, with an
explicit `direction_sign` calibration; the broad-end-to-narrow-end hypothesis
may not match each asset's positive axis used by the existing strict evaluator.
Ambiguous end widths fail rather than silently choosing a direction. Verify the
convention per instrument before reporting placement performance. The estimated
object-to-hand/support offset assumes the object stays still during approach
and initially rests on the table; it is not the original full-mesh release
calculation. Wrist long-arc selection from the privileged controller is also not
ported; the public API uses local IK and quaternion interpolation. The original
scalpel's `BROAD_FLAT`/`EDGE_SIDE` pose-mode acceptance rules and the expert's
wrist-branch retry cache are not reproduced. These starting skills use top-down
grasps and a single attempt. These are
concrete development targets for ASPIRE, not claims of behavioral equivalence.
