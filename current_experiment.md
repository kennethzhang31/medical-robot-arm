# Current ASPIRE Experiment

<!-- love-retractor:start -->
## Love Retractor With Visual SAM3 (2026-10-18)

Launched at **18:06 Asia/Taipei** on October 18 and finished at **16:11 on
October 20** with status **unsolved / search_exhausted**. All three evolutionary
rounds finished. **756 trials** are recorded: six observation/exploration trials
and 30 complete cohorts of 25 development seeds. Every cohort scored **0/25**.
All saved results contain **zero verified target lifts or placements**.
The 20-case held-out evaluation was skipped under the protocol because no
development program succeeded. No validated shared skills were admitted.
`evo_02_G` is the frozen selection artifact, with zero development successes;
it must not be reported as a successful policy.

Final usage: **163/300** cumulative attempts, **137** remaining, no pending
calls. Automatic continuation applied the higher cap on October 19 at 14:48,
preserving the previous provider ledger. The supervisor has exited; no ASPIRE
trial or model request is active for this campaign. The separately proposed
identity repair has not been applied. Final findings:
`logs/aspire_love_retractor_visual_20261018/findings.md`.

**October 19 diagnosis:** offline inspection identifies systematic selection of
the distractor configured as `kelly`. All 298 recorded first closures in a
326-trial development audit occurred nearest Kelly, 4.7-23.7 mm from its spawn
XY, versus 190-829 mm from the requested Love retractor. In seed 1201, candidate
E's generated 10-26 mm height gate rejects the Love region (6.34 mm) and accepts
Kelly (17.41 mm). The actor's notes misidentify the raised hooked object and
then tune placement of it. Correctly available depth regions therefore do not
establish correct identity. The private evaluator correctly tracks the unmoved
Love target. Evidence and limits:
`logs/other_instruments_20261018/failure_diagnosis_20261019.md`.
This offline audit is not actor input and does not change the active campaign.
Run: `logs/aspire_love_retractor_visual_20261018/`.

Target: `love_retractor`; SAM3 now supports visual box prompts alongside text.
The new `get_tabletop_candidates` helper derives class-agnostic regions from
depth and camera calibration. Generated programs must identify the target from
appearance/shape; regions may include robot parts, merged tools, or fragments.
Three fresh perception scenes (1101-1103) passed the availability gate with
target regions in **4, 3, 3 views**. This does not establish autonomous target
selection or manipulation success. Private pose diagnostics stay outside policy input.

Development seeds: **1201-1225**. Final evaluation seeds: **1301-1320**.
Full K=8/T=3 workflow, four distractors, empty tray, original solver settings.
Five frozen shared skill records from the completed SAM3 campaigns are inherited;
this is an adaptation experiment, not a zero-shot or H/A/B comparison.
Model: `chatgpt1/gpt-6.1-sol` at `https://llm.igvi.cs.nthu.edu.tw/v1`.
Budget at launch: **108/150** cumulative attempts; **42** initially available.
At **18:22**, the user increased the cumulative cap to **300**. At 123 used,
this leaves **177** attempts. The running supervisor retains its original
in-memory cap of 150; a background helper (PID 10936) will automatically resume
the saved campaign with cap 300 if it stops on clean budget exhaustion.
No active trial is interrupted. Original launches and ledgers remain intact.
Authorization: `logs/aspire_love_retractor_visual_20261018/budget_authorization_300.json`.
Helper status: `logs/aspire_love_retractor_visual_20261018/budget_continuation.json`.
The cap can still stop search before the full workflow completes.

```powershell
python scripts/status_full_aspire.py logs/aspire_love_retractor_visual_20261018
```

Implementation, preflight evidence, and limitations: `docs/ASPIRE_OTHER_INSTRUMENTS.md`.
Gate: `logs/other_instruments_20261018/perception_gate.json`.
<!-- love-retractor:end -->

<!-- round2-continuation:start -->
## Round-2 Continuation (2026-10-18)

Latest supervisor status: **completed**. Live state: `logs/aspire_scissor_round2_finish_20261017/state.json`.
User requested completion of round 2 followed by evaluation, coordinator review, and reporting.
The completed October 7 campaign remains preserved; this branch restores its pre-evaluation development checkpoint.
Eight previously generated candidates and five completed round-2 trials are reused; 195 development trials remain at launch.
Model: `chatgpt1/gpt-6.1-sol` at `https://llm.igvi.cs.nthu.edu.tw/v1`; **108/150** cumulative attempted requests at this update.
SAM3 remains pinned, FP16, threshold 0.5. Original task/physics, debug seeds 101-125, and initial empty inherited library remain unchanged.
Select on development only, then repeat the existing 20-case evaluation on seeds 1-20. These seeds were previously evaluated; this is not a fresh independent held-out benchmark.
No round pause is configured. Read the branch state/provider ledgers for live progress.

```powershell
python scripts/status_full_aspire.py logs/aspire_scissor_round2_finish_20261017
```

Final repeated evaluation: **18/20**.
Selected program: `evo_02_G`. See the branch `report.json` and `findings.md`.
<!-- round2-continuation:end -->
## Scissors H/A/B With Window Recording (Completed; Physical Success)

All **15 paired rollouts** finished on **October 7, 2026**. Per the user's
request, primary success is now **both private lift_verified and
place_verified**, regardless of a subsequent program error. Apply this equally
to all H/A/B outcomes; keep the original error-free criterion separately.

| Condition | Physical Success (Primary) | Strict Success | Lift Verified |
| --- | --- | --- | --- |
| H: translated human baseline | **1/5 (20%)** | 1/5 | 2/5 |
| A: generated, empty library | **0/5 (0%)** | 0/5 | 5/5 |
| B: generated, three frozen skills | **2/5 (40%)** | 0/5 | 5/5 |

B's physical successes are seeds **903 and 904**; its resting-support check
raised despite the independent evaluator verifying placement. Those errors
remain in the raw results and strict metric; they do not negate physical
success under the requested definition. No policy revision or rerun occurred.

This is a **post-hoc reporting amendment after outcomes were observed**, not
a preregistered success rule or a change to the private evaluator. Evidence:
`control/physical_success_policy.json`; the original final strict report is
preserved at `control/final_report_before_physical_policy.json`. The updated
`report.json` and `physical_success_report.json` contain both metrics.
Run root: `logs/scissor_hab_source_physics_20261007/`.

Cost: **18/20 starts** including the preserved failed preflight; **2 new / 101
cumulative model attempts**. All **15 rollout videos** and both recovery
preflight videos verify; frozen setup/program hashes remain unchanged.
Reporting regression validation: **182 tests passed** in 45.49 seconds.
This remains a five-case same-object engineering pilot, not broad evidence
of skill efficacy or cross-object transfer. Kelly/scalpel stay deferred.

### Setup And Intermediate Progress History

On **October 7, 2026**, the user approved continuing the recorded scissors
pilot. The failed start remains in `logs/scissor_hab_20261007/`. Its final
settling poll has all five objects present: scissors speed is **0.0001325 m/s**,
but the Kelly distractor is **0.0032170 m/s**, above the **0.003 m/s** gate.
Poll history was not saved, so this identifies the final blocker, not every
poll's cause. Actor/COM velocities both exceed the gate for Kelly.

The failed pilot also omitted the source campaign's explicit **32 position /
8 velocity** solver iterations. The declared, pre-generation recovery uses
those existing source settings for all H/A/B, not tune thresholds on outcomes:
`logs/scissor_hab_source_physics_20261007/`. Carry the failed start forward;
same seed **801**, final **901-905**, **17 new / 18 total planned starts**,
hard cap **20**. Keep all distractors, settling gates, SAM3 and recording.
The same seed's new reset passed in **181 steps**. Motionless replay verified
asset state within **1.7881e-7** (tolerance 1e-6); unchanged SAM3 found target
candidates in **all four** views. Both app-window MP4s decoded successfully
(28 seconds each), and original frame inspection confirms Isaac GUI/scene.
This supports recovery of seed 801, not a general causal claim or manipulation
success. **173 offline tests passed** in 45.53 seconds. The background H/A/B
runner launched at **18:21 on October 7, 2026 (Asia/Taipei)**, helper PID 26240;
read its state/report/provider ledger for current generation and rollout cost.
At launch: **3 total starts** including the original failure, zero manipulation
outcomes and zero new model attempts; two one-time A/B generations come next.
Diagnosis: `logs/scissor_hab_checks_20261007/reset_diagnosis.json`.

The first generation runner stopped at a completion-label guard: B's saved
native stream contained one complete, closed `submit_program` tool block,
valid JSON and terminal `message_stop`, but used native `end_turn`. The relay
incorrectly labeled this as chat `stop`. An explicit offline recovery fixes
only that transport label, preserving original responses/SSE and identical
program code; no extra model request or policy revision. The normalized B
sidecar and recovery evidence are hashed into the frozen program manifest.
Truncated, unclosed or malformed tool streams remain rejected.

Both original A/B submissions are now frozen: **2 new / 101 cumulative model
attempts**. The recorded evaluation resumed at **18:39 Asia/Taipei**, October
7, 2026, helper PID **22824**, supervisor PID **7564**, starting **H_s901**.
At the 18:39:58 check, **4 total starts** including the original failure and
zero completed manipulation outcomes. No success rates exist yet; read the
live state/report rather than interpreting an in-progress trial as a failure.
Final recovery/recorder regression validation: **179 tests passed** in 45.10 s.
Logs: `logs/scissor_hab_checks_20261007/saved-native-evaluation.stdout.log`.

At **18:43 Asia/Taipei**, H_s901 is the first completed rollout: private
scoring verifies **lift**, but not placement; final phase **held**, reason
**not_released**, status `program_error`.
The controller stopped at `SCISSOR_MOVE_TO_TARGET` with `pose_timeout`
(measured position error 0.1691 m, orientation error 36.1 degrees), not a
segmentation failure. Its actual Isaac-window video is
complete/verified (**139 seconds**, 1280x800 at 4 fps):
`trials/H_s901/screen.mp4`. **A_s901 is running** with verified scene pairing
(maximum error 1.1921e-7). **1/15 rollouts completed**, **5 total starts**
including the original failed preflight, **101 cumulative model attempts**.
These are intermediate outcomes, not final H/A/B rates. Continue the frozen
protocol without outcome-driven program changes or additional generation.

Latest check at **18:46 Asia/Taipei**: **B_s901 is running**, **2/15 rollouts
completed**, **6 total starts** including the original failure. A_s901 finished
execution normally and verified lift, but not placement (released,
placement_not_verified). Its app-window recording is complete/verified at
**144.75 seconds**. H/A on seed 901 therefore both verify lift but not full
success; no final five-case rates yet. Model attempts remain **101 cumulative**.

### Preserved Default-Physics Preflight

On **October 7, 2026**, the user deferred Kelly/scalpel and requested scissors
H/A/B, then asked to record Isaac Sim. A fresh same-object skill-library
ablation uses `logs/scissor_hab_20261007/`; all earlier runs stay preserved.

- H: unchanged translated scissors controller, except two private evaluator
  gates deferred to scoring. A: one fresh empty-library program. B: one fresh
  program with exactly three frozen admitted scissors repairs, no revision.
- Motionless seed **801**; paired final seeds **901-905**, outside source
  development 101-125 and planned held-out 1-100. **15 manipulation rollouts**,
  **17 planned starts** including two motionless preflights, hard cap **20**.
- Carry **99** cumulative model attempts from completed Kelly; at most two
  fresh generations reach 101. Source skills remain the completed scissors
  campaign's records; do not reuse the source winner as B's program.
- Original SAM3 **scissor** prompt, FP16/threshold **0.5**, no knife mapping,
  crops or new target practice. Replay/perception checks precede generation.
- Every GUI trial will save its rendered Isaac-window video as `screen.mp4`
  and metadata/PNGs in its trial directory, **4 fps**, no desktop/audio capture.
  Recorder failure preserves the session and stops before an unrecorded retry.
- Pilot and recorder regression validation: **168 offline tests passed** in
  45.45 seconds. The first seed-801 motionless capture stopped during reset:
  `reset_settle_failed: settle_timeout_or_missing_object`, after 750 settling
  steps. Replay and perception readiness have not run; this is an initial
  physics/setup failure, not a SAM3 miss or H/A/B manipulation outcome.
- **Recording is verified working:** `trials/observe/screen.mp4`, **79.25 s**,
  **1280x800 at 4 fps**, 257 captured PNG frames. Decoding and visual preview
  confirm the actual rendered Isaac GUI/scene, not a camera-only substitute.
- Actual cost: **1 simulator start**, **0 manipulation rollouts**, **0 new
  model calls**, **99 cumulative attempts**. No retry, seed replacement or
  relaxed settling criterion was applied. The supervisor is stopped.

See `docs/ASPIRE_SCISSOR_COMPARISON.md`. This is same-object skill reuse,
not cross-object transfer. Read the new run's state/report for actual progress.

## Fixed Crop Check (Completed; No New Target Views)

On **October 7, 2026**, the user requested a quick fixed-crop test. **32 SAM3
calls completed in 10.8 seconds**: four identical overlapping tiles for each
of the eight saved views from scalpel seeds **551/552**, unchanged `knife`
text, FP16 and threshold **0.5**. Artifacts:
`logs/scalpel_knife_crop_check_20261007/README.md` and `report.json`.

- Cropped target-proxy views remain **left/right for 551**, **left only for
  552**. No new view is recovered; top/front and seed 552's right remain empty.
- Seed 552's left target score improves **0.5728 -> 0.7080**, but a partial
  Kelly mask also appears at **0.5386**. Some seed-551 target masks meet crop
  boundaries; the right-view crop truncates the scalpel. Overlay review and
  private root-XY checks are diagnostics, not policy identity filtering.
- All **83** frozen input/artifact hashes match; no live service restart or
  configuration change. Coverage, mask/box mapping and edge checks passed.
- Added cost: **0 simulator starts, 0 manipulation, 0 LLM calls**. Attempts
  stay **99**, scalpel starts **4**. No crop frontend was selected or applied;
  H/A/B remains unstarted under the unchanged seed-552 perception failure.

## Knife Threshold Check (Completed; No Improvement)

On **October 7, 2026**, the user approved a saved-image-only comparison of
`knife` at confidence **0.5 vs 0.3** on the eight top/front/left/right images
from motionless scalpel seeds **551 and 552**. Artifacts:
`logs/scalpel_knife_threshold_check_20261007/README.md` and `report.json`.

- Intended-target proxy views remain **left/right for 551**, **left only for
  552**, at both thresholds. Top/front stay empty, as does seed 552's right
  view. **0.3 does not recover any missing target view.**
- The additional 0.3 masks are distractors: **scalpel_type2** in seed 551's
  left view (0.4348) and **Kelly** in seed 552's left view (0.3101). Overlay
  review supports the private nearest-root XY diagnostic, not mask ground truth.
- Live/direct FP16 threshold-0.5 masks, boxes and scores agree exactly on
  **8/8** pairs. All **79** frozen input/code/campaign artifact hashes match.
- SAM3 was restored at **16:39:25 Asia/Taipei**, PID **23228**, with unchanged
  checkpoint/FP16/threshold **0.5**. No live threshold change was selected.
- Added cost: **0 simulator starts, 0 manipulation, 0 ASPIRE/LLM calls**.
  Cumulative model attempts remain **99**, total scalpel starts **4**. The
  mapped H/A/B pilot remains blocked; neither A nor B has been generated.

## Calibrated Scalpel H/A/B (Current; Perception Blocked)

On **October 7, 2026**, the user approved the shared **scalpel -> knife**
mapping at threshold **0.5** for H/A/B. The separately frozen pilot is
`logs/scalpel_hab_knife_20261007/`; the original scalpel and Kelly records
remain unchanged. This is zero-shot manipulation transfer with calibrated
perception, not zero-shot object recognition.

- H retains the translated scalpel controller; A is planned as one fresh
  empty-library program; B as one fresh program using exactly three frozen
  scissors repairs. **B does not get outcome-driven revision.** Any adaptation
  comparison needs a separate label and matched A/B refinement budgets.
- Fresh motionless observation/replay seed **552** precedes final paired
  seeds **701-705**. Fifteen planned manipulation rollouts plus two fresh
  motionless starts and two carried original scalpel starts would total
  **19**, within the unchanged hard cap of **20**.
- Preflight stopped at **16:20:09 Asia/Taipei**. State replay passed
  (maximum error **1.192e-7**, tolerance 1e-6). `knife` returned one left-view
  mask: score **0.5728**, **446** valid foreground points, median XY **8.17 mm**
  from the private target-root proxy. Top/front/right returned no masks.
- Only **one of four views** establishes target candidates, below the frozen
  two-view gate. State is `stopped / perception_blocked`. This does not erase
  the prior seed-551 audit's two-view detections, but demonstrates that its
  readiness did not generalize to the independently checked seed-552 scene.
- Actual cost: **2 new motionless starts**, **4 scalpel starts including
  carry-in**, **0 manipulation rollouts**, **0 new model attempts**, **99
  cumulative attempts**. A/B programs were not generated; no H/A/B success
  rate exists. No retry, seed selection, threshold reduction or gate bypass
  is authorized by this stopped run.
- Mapping/cap regression validation: **162 offline tests passed** in 45.13 s.
  All eight frozen setup hashes match after the stop. Read `state.json`,
  `report.json`, `scene_replay_preflight.json` and
  `control/perception_preflight.json` inside the calibrated pilot for evidence.

## SAM3 Saved-Image Audit (Completed)

Completed on **October 7, 2026**, with SAM3 restored at **15:44:12 Asia/Taipei**
and final integrity verification at **15:48:47**. Artifacts:
`logs/sam3_saved_image_audit_20261007/README.md` and `report.json`.

- Tested **26 fixed image/prompt pairs** from two saved scenes, not robot
  trials: scalpel seed 551, Kelly seed 601, four views and three descriptions
  each, plus two scissors controls. Thresholds 0.05/0.1/0.3/0.5; same weights.
- Live wire PNG pixels and direct FP16 masks match exactly (**26/26** pairs,
  including 22 empty pairs). Official HF v5.0.0-style FP32 inference has the
  same counts at 0.5 and does not resolve named-label misses. No wrapper or
  FP16-related explanation for the original empty named detections was found.
- **New diagnostic finding:** fixed `knife` text at the existing threshold
  **0.5** detects the actual scalpel in left/right. Scores **0.6953/0.5713**;
  valid table-foreground clouds **398/643** points; median XY difference
  **9.91 mm**. The right view also detects `scalpel_type2` at **0.6021**, so
  selecting the highest score alone would choose the wrong target.
- Lower thresholds recover named scalpel masks but also other instruments.
  Kelly descriptions (`kelly`, `hemostat`, `surgical clamp`) remain unusable
  in the saved scene; the one low-threshold hemostat detection masks the robot.
  Scissors positive controls work. This points to concept/view recognition
  and instance ambiguity, not a globally dead segmentation service.
- **No operational change during the audit:** SAM3 remained FP16, threshold 0.5, same pinned
  revision and port. No new simulator sessions, manipulation or ASPIRE calls;
  cumulative attempts stay **99**. All Kelly/scalpel frozen setup hashes pass.
  The original scalpel `scalpel`-prompt plan remains blocked and unmodified.
- The subsequent calibrated pilot declared a shared `scalpel -> knife` prompt mapping
  at 0.5 and independently tested sensor-only seed 552, outside final seeds
  701-705. It returns all candidates, preserving each H/A/B policy's
  instance-association logic, without shared learned fusion or private pose
  exposure. The original blocked plan remains preserved.

## Original Scalpel H/A/B Preflight (Previous; Perception Blocked)

On **October 7, 2026**, the user proposed scalpel instead of a scissors sanity
check, retaining cross-object transfer on the same robot. Preparation uses a
fresh `logs/scalpel_hab_20261007/`; the completed source and Kelly runs stay
frozen. No scissors H/A/B sanity-check run was started.

- Plan: H is the translated scalpel baseline with only oracle gates removed;
  A is one new program without a library; B is one new program with exactly
  three admitted scissors repairs. No target manipulation practice or Evo
  search. Both A/B must be frozen before any manipulation result.
- Predetermined observation seed **551**, paired evaluation seeds **701-705**:
  15 manipulation rollouts plus two motionless sessions, hard cap 20 starts.
  Keep Kelly's task/physics settings except target and declared seeds.
- Model accounting carries **99** from completed Kelly; skill origin stays
  the completed scissors campaign. Two new attempts would reach 101, not 98.
  Offline regression validation: **153 tests passed** in 43.95 seconds.
- First saved-image check: fixed text **scalpel** returned **zero masks in all
  four Kelly views** (top/front/left/right). No simulator or LLM request was
  used. Fresh scalpel motionless perception/replay checks must precede any
  generation or manipulation; distinguish `scalpel_type2` as well.
- Fresh seed-551 capture/replay finished on October 7, before **15:22:51
  Asia/Taipei**. State replay passed (maximum error **1.788e-7**, gate 1e-6).
  Fixed **scalpel** text again returned **zero masks in top/front/left/right**.
  Per the user's condition (run H/A/B only if detected), stop at this gate:
  **2 simulator sessions, 0 manipulation rollouts, 0 new model requests**.
  Cumulative model attempts stay **99**. No H/A/B success rate exists.
  `control/perception_preflight.json` records the diagnostic; an explicit
  negative gate blocks model generation even if the runner is resumed.
- Scalpel is a different task target but an existing asset, potentially seen
  as a source-scene distractor. This tests cross-object source-skill reuse,
  not an unseen visual category or broad domain-transfer claim.

See `docs/ASPIRE_SCALPEL_COMPARISON.md`. Read its `state.json` and `report.json`
for actual starts/outcomes; no scalpel success rate is available yet.

## Kelly H/A/B Pilot (Completed; Deferred For Further Work)

Prepared on **October 7, 2026, Asia/Taipei** in `logs/kelly_hab_20261007/`.

- Completed at **13:48:59 Asia/Taipei**: all 15 manipulation rollouts ended
  in localization-related `program_error`. H **0/5**, A **0/5**, B **0/5**;
  zero verified lifts or placements. The supervisor exited, with 18 total
  simulator sessions and **99 cumulative model attempts**, none pending.
- All ten A/B initial-state replay checks passed (maximum errors 1.192e-7
  or 1.788e-7, tolerance 1e-6); setup and frozen artifact hashes were verified.
  Original results remain frozen, including all localization failures.
- Diagnostic trace review: all **60** `kelly` segment calls returned zero
  masks, no service errors, and no backprojection calls. A saved-image probe
  returned scissors masks in the left view, but none for `kelly` or `hemostat`.
  This isolates empty text-segmentation output, not a demonstrated controller
  failure or a globally broken SAM3 service. Prompt/domain/view limitations
  remain possible; the diagnostics do not establish an internal SAM3 bug.
- The user requested Kelly first, H/A/B, with at most 20 trials/sessions.
  Five predeclared matched cases (601-605) give **15 manipulation rollouts**.
  A motionless seed-501 sensor capture and replay preflight precede generation.
  Every started simulator session, including infrastructure failures, counts
  toward the hard **20-session** cap; there is no automatic retry or expansion.
- **H:** frozen translated human Kelly baseline. Only the private lift/place
  assertions are deferred to independent scoring; expert motion/profile code
  is unchanged. **A:** one generated program with an empty source library.
  **B:** one generated program with the three frozen admitted scissors skills.
  A/B receive the same permitted initial sensor context, no Kelly outcomes,
  H code, source programs, or task-local scissors notes. No target refinement.
- Source library/program hashes and baseline provenance are frozen. A/B must
  both be generated and frozen before any H/A/B manipulation outcome. Each
  case's measured initial asset state is saved by H, restored by A/B, and
  checked before motion. PhysX contact caches are not replayed; this is not
  a claim of identical future trajectories or images.
- Setup validation: **150 offline tests passed** after the infrastructure and
  bounded transport-recovery fixes.
  SAM3 is ready, GUI simulation is retained, model is `chatgpt1/gpt-6.1-sol`
  at IGVI. Cumulative accounting carries in **96 attempts** (cap 150), with
  one generated program per A/B. No Kelly model request or manipulation
  had occurred at the initial setup snapshot.
- The initial motionless capture passed. The first replay preflight failed
  on an Isaac/PyTorch inference-mode write, before manipulation. Its result
  remains preserved and counted. The tested inference-mode fix and explicit
  retry passed with maximum absolute state error **1.788e-7** (gate 1e-6).
  Three motionless session attempts plus 15 planned rollouts give **18 total**,
  below 20. The retry is recorded under `control/`; evaluation/generation
  retries are not enabled. Read live `state.json`/`report.json` for later status.
- One chat-route attempt was rejected by IGVI with HTTP 400 (unsupported
  `tool_choice`), before any model completion. The failed attempt remains
  counted in `provider_000`. The explicit recovery uses the source campaign's
  working native `/messages` envelope and the identical frozen A request;
  there is no prompt repair or target outcome feedback. The original plan
  remains unchanged; `control/transport_recovery.json` records one extra
  compatibility-attempt allowance. At most **three new transport attempts**
  (99 cumulative), still **two generated programs**; no general retry loop.
- Scoring remains the existing independent `lift_verified`/`place_verified`
  metrics, with execution success separately reported. The proposed two-second
  stable-hold/rotation metric is not implemented. This is an engineering pilot,
  not a broad cross-object transfer claim. See `docs/ASPIRE_KELLY_COMPARISON.md`.

## Completed Scissors Evaluation And Skill Admission

Completed at **October 7, 2026, 11:30:27 Asia/Taipei**; verified at
**11:40:21 Asia/Taipei**.

- Campaign status: **completed**, with no recorded error. The supervisor exited
  after evaluation, actor consolidation, coordinator review, and final reporting.
- Final held-out result: **18/20 successes (90%)** on the fixed seed prefix 1-20.
  Failed seeds: **5 and 8**. This is the user-requested reduced evaluation, not
  the original 100-seed benchmark; the limit history preserves 100 -> 30 -> 20.
- Frozen winner: `evo_01_B`, selected using development results only,
  **24/25 development successes (96%)**. Program SHA-256 remains
  `229beef6c9d36d9c967bcb29b33cb9be4ef42e5525c56c3659e2b370f58b1725`.
  No held-out repairs or reselection occurred. Round 2 remains excluded from
  selection, so this is not a completed T=3 search.
- Coordinator review **did run**: saved request at 11:30:13 and response at
  11:30:27 under `model/coordinator_review.request.json` and
  `model/coordinator_review.response.json`. All three consolidated candidates
  passed the host's eligibility gates and received explicit approval with reasons.
- **Three shared skills were admitted**, each saved as hashed JSON and Markdown
  under `logs/aspire_shared_skills/sam3/`:
  1. High-outward hover with diagonal descent instead of a stalling low inward
     approach. Controller/scissors-specific routing gates; separate sensor-based
     capture verification is still required. ID:
     `f635f6e8c3863eeab1d856077d00551afa93e5aebd7aa6e00365025224f3744e`.
  2. Per-view invalid-depth/backprojection handling, allowing another usable
     RGB-D view to be checked without swallowing motion/service/episode errors.
     This helper alone does not establish capture or placement. ID:
     `3b987927f3e66aba0508abf955261db5dd7fd4e1716efd5ca2486cae0841e7c6`.
  3. Directed cross-view agreement and cloud fusion with single-view fallback.
     Scissors-specific gates, correlated-view bias, and a consensus regression
     remain explicit limitations; it is not universally better localization. ID:
     `e3e632cf74058b5173e5d4419540f06285006e6b4c64ef61847c26658243a0d5`.
- Each shared record is marked `debug_validated_repair` with
  `cross_task_transfer: not_yet_evaluated`. Approval does not establish transfer
  to another object or isolated causal benefits for every accompanying code change.
  The three JSON/Markdown pairs, content-derived IDs, approvals, and 20-trial
  provenance were verified. All 16 pre-revision protected artifacts remain unchanged.
- Task-local memory remains **17 notes and 20 saved programs**, separate from
  the three coordinator-admitted shared skills. Frozen memory remains unchanged.
- Final accounting: **96 cumulative attempted model requests**, **54 remaining**
  under cap **150**. Ledger `provider_009` completed all five post-evaluation
  requests; zero live requests are pending. The historical interrupted marker
  remains counted and acknowledged, not another live request.
- Final artifacts in the campaign: `report.json`, `findings.md`,
  `skill_admission.json`, `proposals/consolidation.json`, `selection.json`,
  `frozen_program.py`, `frozen_skills.json`, `evaluation_plan.json`, and
  `evaluation_limit.json`. Previous validation: 132 adapter tests passed.
- The next object has not been selected or launched. Start a fresh campaign
  and task config on the same robot, preserving this scissors contract/results.
  Its initial shared-memory snapshot can now inherit the three approved SAM3
  repairs; respect their applicability and measure cross-object transfer explicitly.

```powershell
python scripts/status_full_aspire.py logs/aspire_codex61_scissor_sam3_igvi_20261005_run04
```

## 20-Trial Held-Out Evaluation (Historical)

Verified at **October 7, 2026, 10:57:57 Asia/Taipei**.

- The user explicitly requested reducing this instance from 30 to **20 held-out
  trials**, to move on to ASPIRE on the same robot with a different object.
  No next object has been selected or launched yet.
- The previous supervisor and its workers were stopped at 10:53:13, preserving
  all nine completed outcomes. Resumed at 10:57:33 with `-EvaluateAfterRound 1
  -HeldoutTrials 20 -ReviseHeldoutLimit`. Seeds 1-9 are reused; interrupted
  seed 10 is an infrastructure retry of identical frozen code, not a repair.
- Live supervisor PID: `3348`; wrapper PID: `11872`; ledger: `provider_009`.
  Phase: `heldout_evaluation`; active: `heldout_s10:retry001`;
  progress: **9/20 completed** at the snapshot. No recorded infrastructure error.
- Frozen winner remains `evo_01_B`, with 24/25 development successes. All
  16 protected artifacts (selection, frozen code/memory, contract, plan,
  inherited skills, and nine prior ledger reports) remain byte-for-byte unchanged.
- `evaluation_limit.json` now records the first 20 planned seeds (1-20), the
  original 100-trial plan, nine completed seeds before revision, and the previous
  cap of 30. The prior cap is archived byte-for-byte under
  `control/evaluation_limits/`, linked by path and SHA-256. Stop checkpoint:
  campaign `control/heldout_20_20261007_105313_001/`.
- Ordinary resumes retain the cap. Further user-requested reductions require
  an explicit revision flag and cannot discard any completed outcome, including
  uncheckpointed or retry results. Completed evaluations cannot be truncated.
  Final reporting must identify **20/100 planned trials** and the stopping history,
  not present this as the full original benchmark or a complete T=3 search.
- Accounting remains **91 attempted requests**, **59 remaining**, cap **150**.
  GUI mode and SAM3 are unchanged. Coordinator skill review still follows the
  20-trial evaluation; no shared skill has been admitted at the snapshot.
- Validation: **132 adapter tests passed in 40.44 seconds**, including explicit
  cap revision, preserved limit history, and rejection of discarded outcomes.
  Offline actual-campaign validation used zero model requests or physics trials.
  Artifacts: `logs/aspire_heldout20_checks_20261007/`.
- Current logs: campaign `supervisor_20261007_105730_954.stdout.log` and
  `supervisor_20261007_105730_954.stderr.log`; settings: `launches/launch_009.json`.
- The remaining 11 outcomes project to about 30 minutes, around 11:30 Taipei
  time, assuming normal runtime and no interruptions. Review adds time afterward.
- The next object requires a fresh campaign and its own config/seed contract;
  preserve this scissors campaign. Snapshot coordinator-approved reusable skills
  after review for the new campaign, and evaluate transfer rather than assuming
  that scissors-specific code or notes generalize to a different object.

```powershell
python scripts/status_full_aspire.py logs/aspire_codex61_scissor_sam3_igvi_20261005_run04
```

## 30-Trial Held-Out Evaluation (Historical)

Verified at **October 7, 2026, 10:42:52 Asia/Taipei**.

- The user explicitly requested **30 held-out trials for this instance**.
  Only this campaign is capped; global configuration and future campaign
  defaults remain at 100 held-out seeds.
- The previous supervisor and its trial workers were stopped at 10:35:34.
  Completed outcomes for seeds 1-6 are preserved and reused. The interrupted
  seed 7 is retried with identical frozen code and separate retry evidence;
  this is infrastructure recovery, not a program repair.
- Resumed at 10:42:28 with `-EvaluateAfterRound 1 -HeldoutTrials 30`.
  Live supervisor PID: `23604`; background wrapper PID: `14800`;
  ledger: `provider_008`. Phase: `heldout_evaluation`;
  active: `heldout_s7:retry001`; progress: **6/30 completed** at this snapshot.
- Winner remains `evo_01_B`, selected from development rounds 0-1, with 24/25
  development successes. Frozen program, selection, memory, original contract,
  original plan, inherited skills, and all eight prior ledger reports were
  verified byte-for-byte unchanged: 15 protected artifacts in total.
- `evaluation_limit.json` records the original 100-trial plan, first 30 planned
  seeds (1-30), selected program hash, completed seeds before the change, and
  request timestamp. Resumes retain this limit even when the flag is omitted.
  Changing the saved cap, discarding a completed outcome, or truncating an
  already completed evaluation is rejected.
- The final report and findings explicitly identify **30/100 planned trials**,
  not the full original benchmark. No held-out repairs or reselection occur.
  Round 2 remains excluded; coordinator skill review follows the 30 outcomes.
- Accounting is unchanged: **91 attempted requests**, **59 remaining**, cap
  **150**. The new ledger has zero requests at the verification snapshot.
  GUI mode and the independent SAM3 CUDA service remain unchanged.
- Validation: **128 adapter tests passed in 40.20 seconds**. Offline validation
  checked the actual frozen program, six saved outcomes, 30-seed prefix, and
  historical ledgers with zero model requests or simulator trials.
  Artifacts: `logs/aspire_heldout30_checks_20261007/`.
- Current supervisor logs: campaign `supervisor_20261007_104225_302.stdout.log`
  and `supervisor_20261007_104225_302.stderr.log`; launch settings:
  `launches/launch_008.json`. Protected stop checkpoint:
  campaign `control/heldout_30_20261007_103534_777/`.
- At the snapshot, mean runtime is about 2.57 minutes/trial; the remaining
  24 outcomes project to about 62 minutes, around 11:45 Asia/Taipei, assuming
  normal runtime and no further interruptions. Skill review adds time afterward.

```powershell
python scripts/status_full_aspire.py logs/aspire_codex61_scissor_sam3_igvi_20261005_run04
```

## Direct Held-Out Evaluation (Round 2 Skipped, Historical)

Verified at **October 7, 2026, 10:19:31 Asia/Taipei**.

- The user explicitly requested skipping round 2 and evaluating directly.
  The round-2 supervisor and its simulator children were stopped at 10:12:24;
  the separate SAM3 CUDA service remains running. Five completed round-2 trials
  and the interrupted sixth trial remain preserved, but are excluded from selection.
- The existing campaign resumed with `-EvaluateAfterRound 1` at 10:19:24.
  Live supervisor PID: `21896`; background wrapper PID: `6476`;
  provider ledger: `provider_007`. Phase: `heldout_evaluation`;
  active trial: `heldout_s1`, with 0/100 held-out outcomes complete at this snapshot.
- Selection uses only the 22 complete development cohorts from the Fix Loop
  and rounds 0-1. Frozen winner: `evo_01_B`, **24/25 (96%) development success**,
  SHA-256 `229beef6c9d36d9c967bcb29b33cb9be4ef42e5525c56c3659e2b370f58b1725`.
  This is not a held-out success estimate.
- `selection.json`, `frozen_program.py`, and `frozen_skills.json` are saved
  before held-out trials. Seeds 1-100 use that same program, without repairs
  or reselection. Coordinator skill review follows the completed evaluation;
  no reusable shared skill has yet been admitted.
- `evaluation_plan.json` records the user-requested early stop and excluded
  round-2 evidence. The original K=8, T=3 plan and seed contract are unchanged;
  the eventual report must identify this as a shortened search, not a completed T=3 run.
  Resumes retain the evaluation boundary and frozen artifacts even without
  repeating the flag, and cannot resume round-2 search.
- Accounting remains **91 cumulative attempted requests**, **59 remaining**,
  under the unchanged authorized cap **150**. Evaluation itself needs no
  model requests; post-evaluation diagnosis/review may consume remaining budget.
  All seven previous provider report hashes were verified unchanged.
- Memory at freeze contains 17 local notes and 20 saved programs. Two notes
  came from the now-abandoned round-2 proposal; they do not change the frozen
  executable or provide held-out feedback. Shared admission is still separate.
- Validation: **117 adapter tests passed in 40.30 seconds**, including direct
  evaluation, later-round exclusion, immutable freeze/resume, recovery, and
  launcher forwarding. Offline validation checked the actual winner's saved
  seed results and ledgers with zero model requests or simulator trials.
  Artifacts: `logs/aspire_skip_round2_checks_20261007/`.
- Stop checkpoint and ledger hashes:
  `logs/aspire_codex61_scissor_sam3_igvi_20261005_run04/control/skip_round2_20261007_101224_659/`.
  Current logs: campaign `supervisor_20261007_101921_617.stdout.log` and
  `supervisor_20261007_101921_617.stderr.log`; launcher settings: `launches/launch_007.json`.

Check live progress rather than treating this dated snapshot as current:

```powershell
python scripts/status_full_aspire.py logs/aspire_codex61_scissor_sam3_igvi_20261005_run04
```

## Final-Evaluation Continuation (Historical)

Verified at **October 7, 2026, 09:50:37 Asia/Taipei**.

- Round 1 finished all eight candidates and 200 development trials, and paused
  successfully at 09:19:22. Best: `evo_01_B`, 24/25 (96%); runner-up:
  `evo_01_H`, 23/25 (92%). These are development scores, not final evaluation.
- The user has now requested the remaining workflow. The original campaign was
  resumed at approximately 09:50 with **no pause-after-round flag**, preserving
  K=8, T=3, the seed partitions, the model/endpoint, and normal GUI trial mode.
- Live supervisor PID: `7508`; new ledger: `provider_006`.
  Current phase is `evolutionary_search`, active model turn `evo_02_3`.
- Launch accounting: **83 prior attempts**, **67 available new attempts**,
  unchanged cumulative cap **150**. At the verification snapshot, four new
  attempts have started: **87 cumulative**, **63 remaining**, one live pending
  request. The original crash marker remains historical and counted.
- Expected sequence: finish the eight-candidate round 2; select the best program
  using development results only; freeze that program and actor memory; run the
  100 held-out seeds once each without repairs or reselection; then consolidate
  findings and perform coordinator review of eligible reusable repairs.
- There are up to 300 remaining simulator trials before completion, excluding
  infrastructure retries: 200 round-2 development trials plus 100 held-out trials.
  Final evaluation has **not started yet** at this snapshot.
- SAM3 was verified healthy on CUDA. Physical disk-space verification showed
  approximately 152.57 GB free before launch. No simulator/perception settings
  or dependencies were changed.
- All six previous provider reports were verified unchanged after restart.
  The paused round-1 state and supervisor metadata were preserved under
  `logs/aspire_final_resume_20261007_094903_267/` together with the preflight
  accounting snapshot and new background-launch record.
- Existing working memory contains 15 notes and 20 saved programs. No shared
  skill has been admitted; admission remains a post-evaluation step and does
  not establish cross-instrument transfer.

Use the status command for live progress; counts above are a dated snapshot:

```powershell
python scripts/status_full_aspire.py logs/aspire_codex61_scissor_sam3_igvi_20261005_run04
```

## Round-1 Resume (Historical)

Observed at **2026-10-06 16:07:38 UTC / October 7, 2026, 00:07:38 Asia/Taipei**.

- The same campaign has been resumed in the background, not replaced by a new run.
- Live supervisor PID: `4468`; SAM3 service PID: `23384`, healthy on `cuda:0`.
- Current phase: `evolutionary_search`; active turn: `model:evo_01_3`.
  The replacement request is in flight; no round-1 candidate cohort is complete yet.
- New ledger: `provider_005`, starting with **82 prior attempts** and **68 new
  attempts available**, under the unchanged authorized cumulative cap of **150**.
  At this observation, one new request is pending: **83 total attempted**, **67 remaining**.
- The original interrupted attempt remains counted and its saved ledger/stream
  are untouched. The old pending marker is historical, not a second live request.
- Actual launch settings preserve `chatgpt1/gpt-6.1-sol`, the IGVI endpoint,
  the existing config, and non-headless simulator mode. GUI trials start after
  the round-1 candidate programs have been generated.
- `--pause-after-round 1` is now implemented and enabled. Finish the complete
  eight-candidate round 1, then durably pause before round 2, program freezing,
  or held-out evaluation. K=8 and T=3 are unchanged.
- Recovery now requires an inactive previous supervisor and exclusive campaign
  ownership. Metadata is saved under the campaign's `recoveries/` directory;
  no historical request counts are reset or historical reports rewritten.
- Complete inspection turns reuse their saved outputs. Successful infrastructure
  retries reuse the corresponding trace/image directory, including recovery of
  a completed retry whose canonical checkpoint was interrupted.
- Validation: **105 adapter tests passed in 36.55 seconds**. An offline replay
  of the actual campaign reused all three cached round-1 responses/inspections
  and verified identical interrupted-turn input, with zero provider calls or
  physics trials. All 13 protected historical artifacts remained unchanged.
- Optional SAM3/RF-DETR test suites could not collect in Isaac Python because
  `httpx` is absent; no dependencies were changed. The actual SAM3 CUDA health
  endpoint was checked independently.
- Verification artifacts: `logs/aspire_resume_checks_20261006/`, including
  `tests-adapter.log`, `cache-replay-check.log`, `pre_resume_snapshot.json`,
  `checkpoint_before_resume.json`, and the service/campaign launch records.

Monitor current progress without model requests:

```powershell
python scripts/status_full_aspire.py logs/aspire_codex61_scissor_sam3_igvi_20261005_run04
```

**The remainder is the preserved pre-resume handoff.** Its stale live-status
warnings and pending implementation/restart steps describe the earlier snapshot,
not the resumed supervisor. Round 1 and later evaluation results remain pending.

## Pre-Resume Snapshot

Snapshot: October 6, 2026, approximately 23:03, Asia/Taipei (UTC+08:00).

This summarizes our discussion and the saved repository artifacts. Completed
work is distinguished from requested work that has not yet been executed.

## Current Status

**Round 0 is complete. The campaign was interrupted during round-1 model
 generation, before any round-1 candidate was evaluated.**

- Active campaign: `logs/aspire_codex61_scissor_sam3_igvi_20261005_run04/`.
- Best development program: **`evo_00_B`, 22/25 successes (88%)**.
- Best Fix Loop program: **`fix_04`, 20/25 successes (80%)**.
- Completed: observation, five exploration blocks, the initial debugging sweep,
  five repair sweeps, and all eight round-0 candidates.
- Saved evidence: 356 entries, including six observation/exploration entries and
  350 seed-results in 14 completed development cohorts. Retry attempts are separate.
- Pending: round 1, round 2, final program selection/freezing, 100-seed held-out
  evaluation, and coordinator-reviewed skill admission.
- Requested stopping point: **finish round 1, then pause before round 2**, keeping
  the campaign resumable for another day.

Latest saved checkpoint:

```text
status:         running
phase:          evolutionary_search
active:         model:evo_01_3
last update:    2026-10-06 18:59:45 Asia/Taipei
```

The saved `running` status is stale relative to the shutdown, not proof of a live
supervisor. Earlier checks found no campaign worker or SAM3 service after the
reboot. Fresh process/listener queries during this summary returned `Access
denied`, so live status was not independently reverified at this snapshot.

No resumed launch or new provider ledger is visible in the artifacts. Writing
this document does not restart the experiment or spend model requests.

## Experiment Setup

| Setting | Current choice |
| --- | --- |
| Task | Scissors pick-and-place only |
| Simulator | Isaac Sim 4.5 on Windows |
| Display | Normal GUI, non-headless |
| Perception | SAM3 on CUDA; local service at `http://127.0.0.1:8114` |
| Model alias | `chatgpt1/gpt-6.1-sol` |
| Provider endpoint | `https://llm.igvi.cs.nthu.edu.tw/v1` |
| Configuration | `configs/aspire/full-scissor-sam3.json` |
| Development seeds | 101-125: 25 trials per candidate |
| Held-out seeds | 1-100: one frozen program, once per seed |
| Population | K=8 candidates per round |
| Maximum rounds | T=3, numbered 0, 1, and 2 |
| Immediate stopping point | Complete round 1, then pause |
| Authorized cumulative request cap | 150 attempted model requests |
| Artifacts | Repository `logs/` directory |

The earlier 6/4/10 engineering-pilot split was retired. Select the program using
only development results, freeze it, then evaluate on held-out seeds without
repairs or reselection. K=8 and T=3 remain user-selected limits.

The configured full-workflow maximum is 856 simulator trials, excluding extra
infrastructure retries. Early success or the request cap can shorten execution.
Stopping after round 1 is a checkpoint, not completion of the full experiment.

## What We Have Done

### Protocol and implementation

- Reviewed the supplied ASPIRE paper; extracted text is saved in
  `logs/aspire_setup_paper_20261005/paper.txt`.
- Ported the Fix Loop and Evolutionary Search workflow to the surgical simulator,
  retaining upstream runbooks and a separate surgical environment/API binding.
- Changed the active seed schedule to 25 development and 100 held-out seeds.
- Added actor-selected trace/image inspection, before/after primitive camera
  views, and available perception overlays.
- Separated task-local working memory from persistent, coordinator-admitted skills.
- Added structured findings, debugging repair replay checks, and a separate
  coordinator review for reusability and API compliance.
- Added cached model responses, saved programs/cohorts, provider-attempt ledgers,
  frozen-program checks, and preservation of infrastructure retry artifacts.
- Documented the procedure, deviations, API binding, and launch instructions.

### Model and runtime setup

- Investigated Codex login, custom-provider configuration, and transport/API
  compatibility rather than treating Responses and Chat Completions as interchangeable.
- Moved the active experiment to the IGVI endpoint and `chatgpt1/gpt-6.1-sol`.
  Saved artifacts contain completed requests through this combination.
- Set up SAM3 locally and used normal GUI execution after earlier headless camera
  and Isaac renderer/reset problems.
- Increased the request cap when authorized, retaining usage across restarts.
- Preserved older campaigns separately instead of merging their results into this run.

### Tests and shutdown inspection

- Last saved test result: **88 passed in 34.86 seconds**, in
  `logs/aspire_setup_paper_20261005/tests-final.log`.
- Tests cover workflow/cache behavior, held-out boundaries, interrupted streams,
  native tool conversations, trace/image inspection, and skill admission.
- Fake model/physics tests establish protocol behavior, not manipulation success
  or cross-task transfer. Manipulation results come from simulator task evaluation.
- Inspected the checkpoint, completed cohorts, model caches, partial stream, and
  request ledgers after the shutdown without changing their history.
- Confirmed that automatic pause-after-round support is **not yet implemented**.
  The restart, pause implementation, and new recovery tests are still pending.

## Development Results

Each row contains 25 development seed-results. Task success is determined by the
independent evaluator, not merely by successful Python execution.

| Program | Successes | Rate |
| --- | ---: | ---: |
| `fix_initial` | 1/25 | 4% |
| `fix_00` | 0/25 | 0% |
| `fix_01` | 11/25 | 44% |
| `fix_02` | 12/25 | 48% |
| `fix_03` | 18/25 | 72% |
| `fix_04` | 20/25 | 80% |
| `evo_00_A` | 20/25 | 80% |
| **`evo_00_B`** | **22/25** | **88%** |
| `evo_00_C` | 20/25 | 80% |
| `evo_00_D` | 21/25 | 84% |
| `evo_00_E` | 19/25 | 76% |
| `evo_00_F` | 16/25 | 64% |
| `evo_00_G` | 21/25 | 84% |
| `evo_00_H` | 19/25 | 76% |

Round-0 candidate A is the selected Fix Loop program copied verbatim. Candidate
B improves on it by two development successes. These are adaptation/debugging
scores, **not held-out performance**.

## Shutdown and Resume Point

The previously verified reboot time was **October 6, 2026, 19:03:22 Asia/Taipei**,
shortly after the last checkpoint. Round 0 had already finished.

- Round-1 turns `evo_01_0`, `evo_01_1`, and `evo_01_2` have complete cached
  responses and inspection artifacts.
- `model/evo_01_3.request.json` exists, but its complete response does not.
- `provider_004/request_004.stream.sse` contains only `message_start`, with no
  completed program or usable tool result.
- The saved provider report retains one pending attempt. That is crash evidence,
  not evidence that the request is still live.
- No `iter_01_summary.json` or round-1 cohort is saved yet.

Resume should reuse complete cached turns and completed trials, then retry the
unfinished model turn in a new ledger. Keep the interrupted attempt counted;
never execute partial streamed output or fabricate a completed response.

## Request Budget

| Ledger | Attempts | Completed responses | Pending in saved report |
| --- | ---: | ---: | ---: |
| `provider_000` | 15 | 15 | 0 |
| `provider_001` | 0 | 0 | 0 |
| `provider_002` | 0 | 0 | 0 |
| `provider_003` | 21 | 21 | 0 |
| `provider_004` | 4 | 3 | 1 |
| **Campaign subtotal** | **40** | **39** | **1** |

- Usage carried into the campaign: **42 attempts**.
- Cumulative attempted usage: **42 + 40 = 82**.
- Latest authorized cap: **150**, after adding 42 to the previous cap of 108.
- Remaining allowance: **68 attempts**.
- The interrupted request counts: do not reduce cumulative usage to 81.
- Inspection, generation, and coordinator-review requests all consume the budget.

The original `launch.json` still records a cap of 68; the latest saved provider
report records 108. Neither represents a newly launched 150-cap supervisor.
The next launch must explicitly use the updated cap and all 82 prior attempts.

## Paper Alignment and Codex Clarification

This is a **paper-aligned surgical port**, not an identical reproduction of the
paper's robot stack or benchmark numbers.

| Aspect | Paper workflow in our retained audit | This experiment |
| --- | --- | --- |
| Environment | Robosuite/MuJoCo setup | Surgical Isaac Sim on Windows |
| Coding-agent interface | Claude Code workflow | Project-managed native tool-loop actor |
| Current model | Not an identical model comparison | Gateway alias `chatgpt1/gpt-6.1-sol` |
| Perception/planning | GraspNet, PyRoKi, Molmo interfaces | SAM3, RGB-D, Cartesian motor APIs |
| Search | Iterative repairs and evolutionary candidates | Fix Loop, K=8, up to T=3 |
| Evaluation | Select before held-out evaluation | Development selection, freeze, 100 held-out seeds |
| Persistent knowledge | Reusable validated repairs | Coordinator-admitted shared library |

Our API exposes functions including `get_observation`, `get_robot_state`,
`goto_pose`, `open_gripper`, `close_gripper`, `estimate_grasp`, and
`get_tray_slot`. They are not interchangeable with the paper's robot APIs.

We discussed and configured Codex, but the saved experiment does **not** launch
Codex CLI as its task actor. The supervisor calls the gateway model through the
project's own evidence/submission tool loop. This distinction matters for fidelity.

Some saved plans/docs still say "Opus" or show the original gateway defaults.
The active campaign's explicit model and launch artifacts show the IGVI endpoint
and GPT model alias listed here. Provider context capacity is unverified; an
output-token ceiling is not a verified context-window size.

Seed resets do not prove exact saved physical scene replay. We have not established
paper-score reproduction, real-robot transfer, model fine-tuning, or zero-shot
cross-instrument performance.

## Saved Skills and Transfer

- Task-local memory exists: `skills/index.json` contains 12 notes and 12 program entries.
- The inherited shared-skill snapshot is empty: `inherited_skills.json` is `[]`.
- This campaign has not reached consolidation/admission; `skill_admission.json` is absent.
- Final `selection.json`, `frozen_program.py`, `report.json`, and `findings.md` are absent.

Local notes and successful programs are useful artifacts, but are not automatically
validated shared skills. The planned shared library is
`logs/aspire_shared_skills/sam3/`; admission requires debugging repair evidence and
coordinator approval after evaluation. Skills can be supplied to future actors,
but useful zero-shot transfer must be tested separately and is not yet demonstrated.

## Remaining Work

1. Implement/test a durable pause after round 1, before round 2 or final evaluation,
   without changing the frozen T=3 protocol.
2. Preserve the interrupted request and add recovery metadata without resetting
   counts or overwriting crash evidence.
3. Verify cached inspection reuse and that completed physics trials are not repeated.
4. Restart SAM3 on CUDA, check health, and restore normal GUI execution.
5. Resume this exact campaign with 82 prior attempts, up to 68 new attempts,
   cap 150, and the explicit current model/endpoint. Next ledger: `provider_005`.
6. Complete round 1 and pause. Continue round 2 later only when requested.
7. After search, select/freeze one program, run all 100 held-out trials, write
   findings, and review eligible repairs for shared admission.

The proposed `--pause-after-round 1` option does **not** exist in the current runner.
Do not launch an unrestricted resume expecting an automatic round-1 pause. The
existing continuation wrapper also rejects saved pending requests, so interruption
recovery must be handled explicitly.

Earlier issues included authentication/provider access, request-budget stops,
headless camera output, and renderer/reset failures. This latest interruption was
specifically a shutdown during model generation, not a newly observed simulator
failure. A retry-evidence-path issue noted in the handoff should also be checked
if infrastructure retries are needed.

## Important Files

- Campaign: `logs/aspire_codex61_scissor_sam3_igvi_20261005_run04/`.
- Progress/results: `state.json`, `iter_00_summary.json`, `fix_result.json`.
- Actor history: `model/`, `proposals/`, `skills/`, `task_analysis.md`.
- Physics evidence: `trials/`, including preserved retry attempt directories.
- Accounting: `provider_*/report.json` and raw request/stream files.
- Supervisor/workflow: `scripts/run_full_aspire.py`, `src/aspire/full.py`.
- Config: `configs/aspire/full-scissor-sam3.json`.
- Method audit: [docs/ASPIRE_FIDELITY.md](docs/ASPIRE_FIDELITY.md).
- API binding: [docs/ASPIRE_SURGICAL_BINDING.md](docs/ASPIRE_SURGICAL_BINDING.md).
- Run guide: [docs/ASPIRE_FULL_RUN.md](docs/ASPIRE_FULL_RUN.md).

Preserve earlier campaigns and cumulative request counts. Do not merge unrelated
runs, expose credentials, or interpret stale `running` metadata as a live process.
