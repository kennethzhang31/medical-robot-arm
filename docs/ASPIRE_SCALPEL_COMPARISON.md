# Scissors-to-scalpel H/A/B pilot

## Current calibrated pilot: stopped before generation

The subsequent fixed-crop check is complete:
`logs/scalpel_knife_crop_check_20261007/README.md`. Four fixed overlapping
tiles per saved view (32 calls, 10.8 seconds) at unchanged knife/FP16/0.5
recover no missing target view. Seed 552's left confidence improves to
0.7080, but its right view stays empty and a Kelly distractor appears.
Some seed-551 masks are crop-truncated. All 83 hashes and service settings
match, with no simulator or LLM cost. This does not resolve the frozen gate;
no crop frontend was selected or inserted into H/A/B.

The user-approved saved-image threshold check is now complete:
`logs/scalpel_knife_threshold_check_20261007/README.md`. At both **0.5 and
0.3**, target-proxy views are left/right in scene 551 and left only in scene
552. Lowering to 0.3 adds scalpel_type2/Kelly masks, not a missing target view.
Live/direct FP16 parity is exact for 8/8 pairs, and all 79 frozen artifact
hashes match. SAM3 is restored unchanged at threshold 0.5; no new simulation
or model-generation cost was incurred. This does not resolve the gate below.

The user approved the shared **scalpel -> knife** mapping on October 7, 2026.
The fresh frozen directory is `logs/scalpel_hab_knife_20261007/`. The target,
scoring identity and baseline instrument profile remain scalpel; only the
shared canonical SAM3 text is knife. Threshold 0.5, FP16, model revision,
task physics and all-candidate returns are unchanged. Each H/A/B policy owns
instance association; no private pose filtering or learned fusion is added
to the shared policy-facing perception API.

The calibrated pilot uses motionless seed **552** and final matched seeds
**701-705**. Two fresh capture/replay starts plus 15 planned manipulation
rollouts and two original scalpel starts would total **19**, under the hard
cap **20**. Model accounting carries **99** from completed Kelly; up to two
fresh A/B generations would reach 101. The source library remains scissors.

The independent preflight stopped at **16:20:09 Asia/Taipei**:

- Capture/replay passed: maximum error **1.192e-7**, tolerance 1e-6.
- Left: one knife mask, score **0.5728**, **446** foreground depth points,
  median XY **8.17 mm** from the private target-root diagnostic proxy.
- Top/front/right: zero masks. Only one distinct view establishes a target
  candidate; the predeclared two-view gate fails.
- State is `stopped / perception_blocked`. A/B were not generated; no H/A/B
  manipulation or success-rate measurement occurred.
- Cost: **2 new motionless starts**, **4 scalpel starts with carry-in**,
  **0 new model attempts**, **99 cumulative attempts**. Do not silently retry,
  select a different scene, lower thresholds or weaken the readiness gate.

Evidence is in the calibrated directory's `state.json`, `report.json`,
`scene_replay_preflight.json` and `control/perception_preflight.json`. All
eight frozen setup hashes match. Mapping/cap validation passed **162 tests**.
The earlier seed-551 audit detected knife in two views, but that diagnostic
did not establish independent seed-552 readiness. This is a declared
prompt-calibrated manipulation-transfer pilot, not zero-shot object recognition.

**B should not get revision in H/A/B.** Its planned fresh generation may
use the three admitted source repairs, but no scalpel outcome feedback.
Any outcome-driven adaptation belongs in a separate comparison with matched
A/B refinement budgets; do not amend this pilot's programs or results.

## Shared comparison scope

This is a new cross-object, sensor-only comparison on the same robot, not a
restart of the completed Kelly experiment. Scissors source skills stay frozen.
Scalpel is a different task target, but is an existing simulator asset and can
have appeared as a distractor in source scenes. Do not describe this as an
unseen visual category, new robot, or broad domain-transfer benchmark.

| Condition | Frozen program source | Target manipulation practice |
| --- | --- | --- |
| H | Existing translated scalpel controller; only private scoring gates removed | None |
| A | One model-generated program, empty source library | None |
| B | One model-generated program, three admitted scissors repairs | None |

H's motion, localization and instrument profile are unchanged. A/B do not see
H's code, source programs, Kelly outcomes, task-local notes or private state.
Both receive the same public API and motionless scalpel sensor context. B alone
receives the three source repair records. Freeze both generated programs before
any manipulation outcome; no Fix Loop, Evo search, candidate selection or
target-driven revision is allowed in this comparison.

## Original unmapped bounded plan (preserved)

- Fresh directory: `logs/scalpel_hab_20261007`.
- Observation seed 551; five paired evaluation seeds 701-705.
- Fifteen manipulation rollouts, plus two motionless capture/replay sessions.
- Hard cap: 20 started simulator sessions, including failed starts.
- Same translated task settings as Kelly except target and declared seeds:
  SAM3, 448-pixel cameras, empty tray, four distractors, randomization off,
  2400-step limit, 8-second motor timeout, no solver overrides.
- Accounting parent: completed Kelly pilot, carrying 99 cumulative attempts.
  Library origin remains the completed scissors campaign, not Kelly.
- At most two new generation attempts, 101 cumulative if both are spent,
  inside the existing cumulative cap of 150. Native IGVI transport is retained.

Use the independent lift/place scorer and report execution separately. Initial
asset-state replay must pass before generation; contact caches are not replayed.
See `docs/ASPIRE_KELLY_COMPARISON.md` for unchanged pairing and isolation rules.

## Original unmapped perception gate (preserved)

The subsequent saved-image audit found that `knife`, unlike `scalpel`, detects
the actual scalpel in both side views at the unchanged 0.5 threshold. It also
matches scalpel_type2, which scores higher in the right view. No operational
prompt mapping, threshold or frozen contract was changed by that audit.
See `logs/sam3_saved_image_audit_20261007/README.md`. Any prompt-calibrated
comparison must be separately declared and checked on sensor-only scenes;
keep candidate association in H/A/B rather than adding B's learned fusion
to their shared perception front end. The original blocked plan stays intact.

Fresh seed-551 capture/replay completed on October 7, 2026. Replay passed at
maximum error 1.788e-7, but the unchanged `scalpel` prompt returned zero masks
in all four fresh views. The pilot is stopped at `perception_blocked`, with
two simulator sessions, no manipulation rollouts and no new model requests.
`control/perception_preflight.json` records the negative gate, and generation
rejects the recorded failure before any model call. Do not execute the later
generation/evaluation commands under the current failed perception setup.

The fixed text `scalpel` returned zero masks in all four saved Kelly views
(top/front/left/right). This is a diagnostic on a different saved scene, not
a scalpel manipulation failure or proof that all scalpel views will fail.
The scene also contains `scalpel_type2`; a nonempty mask alone does not verify
the intended identity, usable depth, or cross-view localization.

First run only the motionless observation/replay preflight and inspect its
saved images with the unchanged `scalpel` prompt. Do not launch generation or
15 rollouts if localization is unusable. No alternative prompt, threshold,
point cue or perception backend is selected in this plan. If perception needs
calibration, record a separate shared-perception setup for H/A/B and disclose
it; do not silently repair the frozen zero-shot programs or Kelly results.

```powershell
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scalpel_hab_20261007 --stage prepare --target scalpel --accounting-parent logs/kelly_hab_20261007
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scalpel_hab_20261007 --stage observe
```

The original recorded gate failed; the following commands document the
remaining stages only, not instructions to bypass that stop:

```powershell
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scalpel_hab_20261007 --stage generate
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/scalpel_hab_20261007 --stage evaluate
```

The legacy runner filename is retained for compatibility; `--target` and
`--accounting-parent` apply only to a fresh preparation. Existing Kelly
contracts, libraries, frozen programs and results are never reinterpreted.
This single five-case pilot can test feasibility and a paired library effect,
but cannot establish general transferability.
