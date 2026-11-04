# Scissors H/A/B comparison (2026-10-07; completed)

All 15 rollouts are complete. The user requested **verified physical pick/place
as primary success**, even if a program subsequently raises an error. Apply
`lift_verified and place_verified` equally to H/A/B. Final physical results:
**H 1/5 (20%), A 0/5 (0%), B 2/5 (40%)**. Strict error-free success remains
separate: **H 1/5, A 0/5, B 0/5**. B physically succeeds on seeds 903/904 but
its own resting-support check rejects both. A/B each verify lift in 5/5.

This is explicitly a **post-hoc reporting amendment after seeing outcomes**,
not a policy revision, rerun, threshold change or prospective evaluation rule.
Raw trials and frozen programs remain unchanged. Updated main/physical reports
and `control/physical_success_policy.json` are under
`logs/scissor_hab_source_physics_20261007/`; the original final strict report
is retained at `control/final_report_before_physical_policy.json`.

Actual cost: **18/20 starts**, including the original failed preflight;
**2 new / 101 cumulative model attempts**. All 15 rollout recordings and two
recovery preflight recordings verify. **182 offline tests passed**. N=5 per
condition, same-object ablation only; no broad efficacy/transfer conclusion.

## Preserved setup and intermediate progress history

The default-physics start remains preserved at `logs/scissor_hab_20261007/`.
All required objects were present in the final settle poll; the Kelly
distractor, not scissors, exceeded the 0.003 m/s linear-speed gate. The setup
also omitted the completed source campaign's explicit solver iterations.
The declared recovery at `logs/scissor_hab_source_physics_20261007/` restores
source **32 position / 8 velocity** iterations identically for H/A/B before
generation. Same observation/evaluation seeds and unchanged settling gates,
distractors, perception and recording. Count the failed start: **18 planned
total starts**, at most **20**. The same seed's reset now passes in **181 steps**,
replay error is **1.7881e-7** (tolerance 1e-6), all **four** SAM3 views find
target candidates, and both rendered-window MP4s verify. This establishes
readiness on seed 801, not manipulation efficacy. **173 offline tests passed**.
The recorded background pilot launched at **18:21 Asia/Taipei**, October 7,
2026: two one-time A/B generations, then 15 rollouts. At launch, three starts
including the preserved failure and no manipulation outcomes; read the new
run's state/report/provider ledger for current progress and model cost.

Both original A/B submissions are now frozen (**2 new / 101 cumulative model
attempts**). The gateway's complete native B tool block used `end_turn`; an
explicit saved-stream recovery corrects only the transport finish label,
without another model call, code changes or policy revision. Originals stay
preserved; truncated/unclosed streams are still rejected. The recorded
evaluation resumed at **18:39 Asia/Taipei**, October 7, 2026, with **H_s901**
first. At 18:39:58, four total starts including the original failure and no
completed manipulation outcomes. **179 offline tests passed**; actual live
state/report, not these launch snapshots, determines subsequent progress.

At **18:43 Asia/Taipei**, the first completed rollout H_s901 verifies lift but
not placement (`program_error`, held/not_released); its 139-second recorded
Isaac-window MP4 verifies. A_s901 is running with verified scene pairing.
One of 15 rollouts has completed, five total starts including the original
failure, and 101 cumulative model attempts. No policy revision follows this
outcome; final five-case-per-condition success rates are not available yet.

## Original preserved preflight scope

The user deferred Kelly and scalpel and requested a fresh **scissors H/A/B**
comparison with Isaac-window recording. This tests **same-object frozen skill
reuse**, not cross-object transfer. H retains the translated scissors baseline
apart from private scoring gates; A generates once with an empty library;
B generates once with exactly three admitted source scissors repairs. Freeze
both before manipulation; no revisions, Evo search or new skill admissions.

Motionless seed **801**, paired final seeds **901-905**, **15 manipulation
rollouts**, **17 planned simulator starts**, hard cap **20** including failures.
Carry **99** model attempts from completed Kelly; up to two new generations
reach 101. Use unchanged SAM3 scissor/FP16/0.5 and task settings; no knife,
threshold reduction or cropping. Record each rendered Isaac app window as a
4-fps per-trial MP4, without desktop or audio. Recording, replay and perception
must validate before generation. Preserve every previous run and source skill.
See `docs/ASPIRE_SCISSOR_COMPARISON.md` and `logs/scissor_hab_20261007/`.

The first seed-801 motionless start failed the scene-settling check after 750
steps: `reset_settle_failed: settle_timeout_or_missing_object`. No replay,
perception gate, A/B generation or manipulation occurred. Preserve the failed
start; do not silently retry or replace the seed. Recording succeeded and was
decoded/visually verified: `trials/observe/screen.mp4`, 79.25 seconds,
1280x800, 4 fps. Cost is one simulator start and zero new model calls (99
cumulative). Pilot/recording regression validation passed 168 offline tests.

# Deferred calibrated scalpel comparison (2026-10-07; blocked)

The fixed-crop follow-up is also complete: four predeclared overlapping
tiles per saved view, **32 calls in 10.8 seconds**, unchanged knife/FP16/0.5.
It adds no target-proxy camera view: 551 stays left/right and 552 left only.
Seed 552's left score rises to 0.7080 but a Kelly mask appears at 0.5386;
some crops truncate seed-551 target masks. All 83 frozen hashes and the live
fingerprint match. No crop frontend was applied, and no simulator/LLM cost
was added. See `logs/scalpel_knife_crop_check_20261007/README.md`.

The subsequent saved-image **knife 0.5 vs 0.3** check is complete. Across the
eight views from motionless seeds 551/552, 0.3 adds no target-proxy view:
551 remains left/right, 552 remains left only. Added masks are scalpel_type2
and Kelly distractors. Exact live/direct FP16 parity passes 8/8; all 79 frozen
artifact hashes match. SAM3 was restored unchanged at threshold 0.5, with no
simulator or LLM requests. Do not treat 0.3 as a demonstrated fix or start the
blocked pilot under it. See `logs/scalpel_knife_threshold_check_20261007/README.md`.

The user approved a shared **scalpel -> knife** mapping at the unchanged
**0.5** threshold for H/A/B. A separately frozen calibrated pilot is prepared
at `logs/scalpel_hab_knife_20261007/`, preserving the original blocked plan.
H uses the existing translated scalpel controller; A gets one fresh program
with an empty library; B gets one fresh program with the three frozen scissors
repairs. **B gets no outcome-driven revision.** A refinement experiment must
be separately labeled and give A/B matched budgets.

Independent motionless seed **552** capture/replay passed (maximum replay
error **1.192e-7**). At **16:20:09 Asia/Taipei**, the mapped perception check
stopped: one left-view mask, score **0.5728**, **446** foreground points and
**8.17 mm** median XY distance to the private target-root proxy; zero masks in
top/front/right. It fails the frozen two-view readiness gate. Private state
is used only for this diagnostic, not policy filtering or generation input.

Five matched cases **701-705** and **15 manipulation rollouts** remain planned
but unstarted. The budget carries two original scalpel starts: **19 planned
total starts**, hard cap **20**. Actual cost is **2 new motionless starts**,
**4 total scalpel starts**, **0 manipulation**, **0 new model attempts** and
**99 cumulative attempts**. Neither A nor B was generated. Do not report
0/5 success rates or bypass the recorded failure on resume. This calibrated
setup is not zero-shot object recognition. Mapping/cap validation passed
**162 offline tests**; all eight frozen setup hashes remain intact.
See `current_experiment.md` and `docs/ASPIRE_SCALPEL_COMPARISON.md`.

# Previous scalpel preflight and saved-image audit (2026-10-07)

The requested saved-image perception audit has completed. Live FP16 and direct
FP16 masks agree on all 26 image/prompt pairs; FP32 does not fix the named-label
misses at 0.5. In the scalpel seed-551 scene, the broad text **knife** detects
the actual scalpel in both side views at 0.5, but also matches scalpel_type2.
This is promising diagnostic evidence, not independent readiness validation
or a manipulation result. The audit changed no live settings or frozen plans.
The original comparison stays blocked. A shared, declared prompt-calibrated
setup may be validated next without using final seeds or altering the source
library. Keep all candidates and each H/A/B policy's own association logic;
do not give H/A the ASPIRE-learned fusion as a shared perception repair.
See `logs/sam3_saved_image_audit_20261007/README.md` for complete findings.

The user proposed **scissors-to-scalpel** transfer rather than returning to a
same-object scissors sanity check. Prepare a fresh H/A/B pilot with the existing
translated scalpel baseline, an empty-library generated program, and a program
generated using the three frozen scissors repairs. Use five matched cases
(701-705), observation seed 551, 15 manipulation rollouts, two motionless
sessions and a hard cap of 20 simulator starts. Carry 99 model attempts from
completed Kelly; the source skill library still originates from scissors.
Keep Kelly task/physics settings except target and seeds. No target practice,
Fix Loop, Evo search, prompt repairs or library updates in the frozen comparison.

First verify fresh scalpel sensor-only localization. The fixed `scalpel` label
returned no masks in four saved Kelly views; do not assume visual distinctness
means SAM3 recognition. `scalpel_type2` is a distractor. Stop before generation
and manipulation if perception is unusable. Any shared perception calibration
must be separately recorded and disclosed. Existing scalpel assets may have
appeared as source distractors; this is cross-object skill reuse, not an unseen
visual-category test. See `docs/ASPIRE_SCALPEL_COMPARISON.md`.

Fresh seed-551 motionless capture and replay have now passed, but the fixed
`scalpel` label again produced zero masks in all four views. Stop before H/A/B
as requested: two simulator sessions, zero manipulation rollouts and zero new
model attempts (99 cumulative). Generation is blocked by the recorded negative
perception gate. This is a setup diagnostic, not a 0/5 manipulation result.

# Completed Kelly comparison (2026-10-07)

Kelly finished with H 0/5, A 0/5, B 0/5: all 15 rollouts failed localization;
all 60 text `kelly` segment calls returned no masks before backprojection.
Eighteen simulator sessions and 99 cumulative model attempts are preserved.
All ten paired state-replay checks passed. Defer Kelly for future work; do not
overwrite or retry its frozen outcomes as if those failures never happened.

The scissors source campaign has completed. The user approved a separate small
Kelly H/A/B zero-shot pilot, capped at 20 started simulator sessions. Default:
five matched cases per condition (15 manipulation rollouts), with motionless
initial-context and measured-state replay checks before A/B generation. H is
the boundary-sanitized translated baseline; A has no library; B has exactly the
three frozen coordinator-admitted scissors repairs. Generate and freeze both
A/B before any Kelly manipulation outcome. No Kelly refinement or library
updates. See `docs/ASPIRE_KELLY_COMPARISON.md` and `current_experiment.md`.
This bounded pilot does not change the completed source campaign's contract.

# Scissors source execution protocol (2026-10-05)

The user requested the paper protocol and removed 6/4/10. Use SAM3 with
25 debugging seeds (101-125), 100 held-out seeds (1-100), K=8, T=3.
Select on debugging results, evaluate one frozen program once per held-out
seed, then review validated reusable repairs for shared-skill admission.
See [the active run guide](docs/ASPIRE_FULL_RUN.md) and
[method audit](docs/ASPIRE_FIDELITY.md). Maximum 856 simulator trials.
All artifacts are under /logs. The earlier 196/260-trial schedules and
validation-based candidate selection below are historical proposals, not
instructions for the current runner.

---

## Historical experiment proposals

Current execution protocol (2026-10-05): use the [full surgical ASPIRE workflow](docs/ASPIRE_FULL_RUN.md)
via `scripts/run_full_aspire.py`, starting with scissors. It includes exploration,
Fix Loop, persistent skill learning/reuse, K=8/T=3 Evolutionary Search, and frozen
validation/final evaluation. Its maximum is 196 simulator trials and 40 new
provider attempts including visual diagnosis and response corrections. These
counts supersede the older custom-search schedule in section 6 below. Existing
provider approvals remain enforced separately; see each run's ledger. Logs and
learned skills are saved under the repository `/logs`.

I recommend the following experiment.
1. Establish reliable source skills on existing instruments.
Start with scissors to stabilize the experimental infrastructure, then cover the five existing instruments.
For each instrument, compare the translated starting script against its ASPIRE-refined version on identical saved scenes. Keep the original privileged controller as a separate feasibility reference; it has access to object geometry that the generated programs do not.
During development, give ASPIRE evidence around the actual failed stage: detection, approach, closure, lift, and transport. The current refinement loop supplies images only from the first development trial, which can be successful while other cases fail. Fixing this is more useful than immediately increasing the revision budget.
Keep development, candidate-selection validation, and final evaluation separate. Select the program on validation, freeze it, then evaluate it once on reserved cases.
2. Collect both programs and reusable findings.
For each validated skill, preserve:
Artifact	What it contributes
Complete executable program	Reproduction and direct reuse
Failure signature	Recognizing when the skill is relevant
Validated repair and code excerpt	Guidance for generating a new program
Applicability and limitations	Avoiding inappropriate transfer
Evidence and provenance	Objects, conditions, successes, failures, and source version


For example, “slow the initial lift when this grasp repeatedly slips” is a candidate transferable finding only after testing supports it. “Scissors succeeded once at these coordinates” is weak library material.
Keep human-authored starting knowledge distinguishable from ASPIRE-discovered changes. Otherwise, improved transfer could reflect the original expert knowledge alone.
This emphasis on storing reusable fixes follows ASPIRE’s published method.
3. Make library transfer the central comparison.
On each new object, use this small experimental matrix:
Condition	Source library	Feedback-driven revision on new object
A: direct generation	No	None
B: library-assisted generation	Yes	None
C: generation and refinement	No	Fixed budget
D: library-assisted refinement	Yes	Same fixed budget


These comparisons answer different questions:
- B versus A: Does the library improve transfer without target-object practice?
- C versus A: Does execution feedback improve generated skills?
- D versus C: Does the library improve adaptation or reduce its cost?
For A and B, generate one program per target object from the same permitted task information and initial sensor context, then freeze it across evaluation scenes. No target-object trial outcomes may influence generation. This is zero-shot program generation, rather than necessarily running an old script unchanged.
For C and D, allow target-object development trials, but use separate validation and final scenes. Call these results adaptation, not zero-shot transfer.
Freeze the source library throughout this comparison. Give each target an isolated campaign so discoveries on one target do not silently help another.
A useful later ablation compares original-script knowledge only against original knowledge plus ASPIRE-discovered repairs. That establishes what ASPIRE itself added.
4. Choose new objects that isolate the difficulty.
I would use three groups:
Group	Controlled change	Question
Thin tools	Thickness, with declared mass/density treatment	Can the method adapt contact height and grasp selection?
Uneven mass	Same appearance and collider, different physical mass distribution	Can it remain stable or adapt from interaction?
New instrument geometries	Held-out rigid meshes	Does knowledge transfer beyond source identities?


Use several levels of thickness and mass offset. Reserve particular variants or ranges before development. One successful new object is a feasibility demonstration; multiple identities are needed for a broader transfer claim.
For the mass experiment, a visually identical heavy-ended object does not reveal its true center of mass through RGB-D alone. Measure robustness and feedback-based adaptation; do not claim visual inference of hidden mass.
Also audit the effective contact geometry. The current canonical configuration applies an 8 mm contact offset and 0.10 kg mass. Those settings deserve particular scrutiny when the experimental difference is only a few millimeters of thickness.
5. Measure grasping before requiring tray placement.
Make the first task:
Locate → grasp → lift → hold for two seconds → short transfer.

Use an independent physical evaluator to check lift, clearance, drift, rotation, and drops. Your proposed hold thresholds are reasonable starting hypotheses, but validate them against known successful and failed grasps before freezing them.
Report tray placement separately afterward. Otherwise, a good grasp can receive the same failure score as an empty grasp because the final orientation misses a tray tolerance.
There is one information-boundary issue to resolve: the translated scripts currently query evaluator-derived lift/hold feedback during execution. Those booleans are privileged feedback even though they contain no coordinates. For the main sensor-only condition, replace them with sensor-based checks and keep physical scoring private. Alternatively, retain them in a clearly labeled evaluator-assisted condition shared by all methods.
6. Use a bounded pilot, then size the main study.
Use six development, four validation, and ten reserved final cases for the engineering pilot. The current requested budget is K=8 distinct candidates per revision round and up to T=3 revision rounds, starting with scissors and a local smoke test. T was reduced from five to three to limit model usage. After evaluating the starting program, this permits at most 25 programs, 150 development trials, 100 validation trials, and 24 Opus proposal requests. Final evaluation of the frozen selected program adds ten trials, for at most 260 trials. Four validation cases and ten final cases remain engineering-pilot samples, too small for strong performance conclusions. Repair reset reliability before starting population search; increasing the proposal budget cannot repair failures before program execution. The population runner and budget-only preview are available through scripts/search_aspire.ps1; logs default to the repository's logs directory. Exact physical scene replay remains prerequisite work for the matched-scene comparison.
For the subsequent study:
- Repeat independent generation campaigns—three is a practical starting point.
- Replay the same saved scenes across methods.
- Match model, perception, API, action limits, and development budgets.
- Report per-object success and paired differences with uncertainty.
- Count unsuccessful campaigns, crashes, and reset failures.
- Measure simulator trials, tokens, elapsed time, and manual intervention.
- Report source-library construction cost separately from marginal cost per new object.
Use the same perception backend across transfer conditions. The five-class RF-DETR setup cannot simply recognize arbitrary imported classes; SAM3 is a candidate for broader descriptions, but its accuracy still needs validation.
My recommendation is to proceed with your sequence, with library-assisted transfer as the main research result. First make the source experiments trustworthy; then demonstrate that accumulated knowledge produces better new-object skills or reaches comparable reliability with fewer trials. Keep demonstration collection and Diffusion Policy training as a later extension so they do not obscure that central question.
