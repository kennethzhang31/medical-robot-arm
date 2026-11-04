# ASPIRE integration report

## Full-stage controller translation (2026-10-04)

Added five standalone ASPIRE starting skills under `examples/aspire/translated`
for scalpel, scissors, Love retractor, Kelly forceps and the second scalpel.
Each translates the full approach, pick, transfer, place and settling flow,
including tight contact gates, symmetric wrist selection, grip-offset
compensation, transfer detours and stage-specific failure reporting. Target
pose and mesh queries are replaced with sensor estimates. These are sensor
adaptations of stage structure, not identical privileged expert trajectories.

Added `src/aspire/translation.py`, a shared `skill.py.in` template,
`scripts/build_aspire_skills.py`, source/program hash provenance in
`examples/aspire/translated/manifest.json`, ten target/perception protocols under
`configs/aspire/translated`, and `scripts/run_translated_aspire.ps1` for a single
trial, development evaluation or development-only refinement. The launcher
checks perception service readiness before starting the simulator. Existing
default protocols and the earlier visual candidate are preserved.

Extended the public control API with fixed table height, calibrated robot TCP
floor queries and coarse task feedback. Enabled the original Love controller's
0.25 mm contact tolerance. The new skills abort an unverified lift before
transfer and require independently verified final placement. No object pose,
target mesh, ground-truth segmentation or expert trajectory is exposed. RGB-D
observations, original controllers, environment physics and DP training/export
are unchanged.

Validation: 54 ASPIRE contract tests and 12 perception service tests passed,
including all five translations
through the real upstream executor with kinematic robot fixtures. These tests
verify API/stage execution and placement-offset calculations, not contact
physics. Two live SAM3 trials (development seeds 501 and 502) stopped during scene
reset with `reset_settle_failed` before the skill executed. Their artifacts are
retained in `aspire_runs/translated_scissor_smoke_01` and `_02`. The final saved
Kelly distractor speeds were 3.13 and 3.46 mm/s, exceeding the unchanged 3 mm/s
settling gate. These trials do not establish translated-skill performance. Sensor
direction conventions, per-instrument contact calibration and support-offset
estimates need development validation before performance claims.

See [translation details, boundaries and commands](docs/ASPIRE_TRANSLATION.md).

## RF-DETR perception update (2026-10-04)

The surgical and scissor-pilot configurations now use the repository's existing
five-class RF-DETR detector rather than SAM3 by default. `scripts/serve_rfdetr.py`
loads a matching trained checkpoint in the isolated detector environment and
exposes source-resolution boxes over HTTP. `segment_instrument` combines these
boxes with calibrated sensor depth to produce table foreground regions, rejects
boxes intersecting other detections, and preserves the existing visual program
interface and multi-camera confirmation. These regions are not learned masks.
SAM3 remains selectable through `perception_backend: "sam3"`.

Validation: 44 ASPIRE contract tests plus 15 detector transport, geometry, SAM3,
and RF-DETR pipeline tests passed; the new PowerShell launcher parsed without
errors. No instrument RF-DETR checkpoint or `.venv-rfdetr` environment was found
in this checkout, so real detector inference and physical rollouts were not
performed. Previous SAM3 pilot results do not validate this new backend.
See [setup and limitations](docs/ASPIRE_RFDETR.md).

Date: 2026-10-01 (Asia/Taipei)  
Branch: `aspire`  
Simulation runtime: Isaac Sim 4.5 / Python 3.10

## Outcome and current capability

The repository now has an ASPIRE adapter for the existing surgical-instrument scene. It uses the upstream ASPIRE Python code executor and exposes a documented sensor and motor API for reviewed skill programs. The environment can reset the scene, provide six calibrated RGB-D streams, execute measured TCP motions and gripper commands, independently evaluate manipulation outcomes, and preserve trial artifacts.

The integration infrastructure is implemented and the live motor smoke tests pass. **Autonomous physical pick-and-place has not yet been demonstrated.** The visual picking example is a starting candidate. SAM3 service operation and remote LLM refinement have not been tested because no service endpoint or provider credentials were configured.

This is a custom surgical-scene integration, not a reproduction of ASPIRE's published benchmark results.

## Initial gaps addressed

- Robot motion and scene preparation were embedded in large recorder scripts rather than exposed through an ASPIRE environment interface.
- ASPIRE needed `reset`, `step`, observations, reward, termination, rendering, and callable motor helpers for this scene.
- The repository's default IsaacLab launcher was absent. The installed standalone Isaac Sim 4.5 runtime needed a matching IsaacLab source checkout and additional Python support packages.
- Three existing instrument wrappers used USD crate 0.10, which the 4.5 reader could not open.
- Trials needed bounded execution, retained failure evidence, and separate development/evaluation seeds.

## Upstream and runtime dependencies

Added `third_party/ASPIRE` as a Git submodule and added `.gitmodules`.

| Component | Version or revision | Location |
| --- | --- | --- |
| ASPIRE | `f4c8939aab0af9b97690c561bd80e282940f7886` | `third_party/ASPIRE` |
| IsaacLab | v2.1.1, `90b79bb2d44feb8d833f260f2bf37da3487180ba` | `.local/IsaacLab` |
| Isaac Sim | 4.5, bundled Python 3.10.15 | `C:\isaac-sim-450\python.bat` |
| Additional Python packages | Listed in `requirements/aspire-isaac45.txt` | `.local/aspire-python` |

The ASPIRE submodule is unmodified. Its full benchmark dependency stack was not installed into Isaac Sim. The setup uses source paths and local support packages so the simulator's existing Torch/CUDA installation is preserved.

The local installation added OmegaConf, ANTLR runtime, cloudpickle, flatdict, Hydra, h5py, prettytable, wcwidth, trimesh, einops, and pytest support packages. The dependency manifests also provide a smaller CPU/core dependency set for separate environments.

## Added source modules

| File | Responsibility |
| --- | --- |
| `src/aspire/__init__.py` | Package entry without starting the simulator |
| `src/aspire/bootstrap.py` | Configure repository, compatibility-shim, ASPIRE, local dependency, and IsaacLab source paths; resolve the ASPIRE revision |
| `src/aspire/config.py` | Validate task settings and disjoint development/evaluation seed partitions |
| `src/aspire/assets.py` | Verify compatibility-copy hashes and select text-format instrument wrappers |
| `src/aspire/runtime.py` | Private IsaacLab backend: create the shared scene, reset and settle objects, advance physics, read sensors, expose fixture calibration, and measure evaluator state |
| `src/aspire/environment.py` | ASPIRE `BaseEnv` adapter with Gym spaces, reset/step lifecycle, reward, completion, rendering, budgets, and capture hooks |
| `src/aspire/control.py` | Register the surgical sensor/motor API and document its callable functions |
| `src/aspire/geometry.py` | Quaternion/frame transforms, calibrated depth backprojection, and sensor-mask grasp estimation |
| `src/aspire/evaluator.py` | Private physical lift, hold, release, retreat, and supported placement verification |
| `src/aspire/execution.py` | Bind the API into the genuine upstream code executor; check program ASTs and report task failure alongside execution results |
| `src/aspire/perception.py` | Lightweight HTTP client for the pinned upstream SAM3 segmentation protocol |
| `src/aspire/artifacts.py` | Save sensor images, depth, calibration, action journals, sampled frames, and atomic JSON reports |
| `src/aspire/worker.py` | Run one simulator trial, capture exceptions, save results before teardown, and close its simulator |
| `src/aspire/campaign.py` | Launch isolated bounded trials, freeze evaluated programs, aggregate results, and optionally refine programs using a Chat Completions provider |

## Environment and scene behavior

The backend builds one environment from `Isaac-Lift-Cube-Franka-IK-Abs-v0`, then applies the existing authoritative surgical scene and camera configuration. It reuses the repository's compatibility imports, TCP correction, bounded IK controller, geometry utilities, reset helpers, cell placement, tray slots, clutter preparation, and optional lighting randomization.

The target is exposed internally as `scene.object`; the other four canonical instrument bodies retain their named scene entries. The adapter owns reset, termination, and success checks. The inherited cube reward and privileged observation vector are not used as the program's observation or task reward.

Reset performs the following preparation before a skill runs:

1. Reset the robot to its default home joints, zero velocities, and clear previous action state.
2. Resolve instrument rigid-link geometry and build canonical flat templates using the measured thin body axis.
3. Sample distinct grid cells and bounded jitter, with randomized yaw or an explicitly configured target cell/yaw.
4. Restore instrument poses and zero their velocities.
5. Prepare the requested tray occupancy and any additional table clutter.
6. Apply optional training lighting randomization.
7. Require stationary objects using the existing settling gates and one bounded continuation.
8. Validate cell footprints, optionally recenter during preparation, and validate preloaded tray instruments and extra clutter.
9. Warm and check all six RGB streams before returning observations.

Object pose writes and recentering are confined to reset preparation. Skill motion advances physics through robot actions. The adapter applies the recorder's FXAA and disabled DLSS frame-generation settings before Kit startup, avoiding the shader initialization stall observed during the first live attempt. Debug command and end-effector markers are disabled.

## Observation and action contract

`reset(seed=..., options=...)` returns observations and trial information. Omitting the seed selects and reports a concrete seed. `step(action)` returns the Gym-style observation, reward, termination, truncation, and feedback tuple.

Low-level actions contain eight absolute robot-base values:

```text
[x, y, z, qw, qx, qy, qz, gripper]
```

XYZ is in metres, orientation is WXYZ, and the gripper command is `+1` to open or `-1` to close. Invalid/nonfinite commands, zero quaternions, and commands outside the broad workspace envelope are rejected.

Program observations contain:

- `cameras`: `front`, `wrist`, `top`, `left`, `right`, and `tray`.
- Per-camera `images.rgb`, metric `images.depth`, `intrinsics`, and `pose_mat`.
- Measured robot-base TCP XYZ/WXYZ and two finger encoders under `robot`.
- A 16-value `proprio` vector: nine joint positions, TCP XYZ, and WXYZ.
- `task_target`, the operator-requested instrument name.

Camera data is uncropped and unrotated. `pose_mat` maps the optical camera frame (+X right, +Y down, +Z forward) into the robot base. Public observations exclude object poses, simulator segmentation, mesh geometry, sampled grid assignments, and expert recorder stages.

## Added program API

| Function | Behavior |
| --- | --- |
| `get_observation()` | Read the public camera and robot observation dictionary |
| `get_robot_state()` | Read measured TCP pose and finger positions |
| `goto_pose(...)` | Interpolate an absolute TCP pose and require measured position/orientation convergence within a bounded simulation-time budget |
| `open_gripper(...)` | Hold the measured TCP while opening; require finger encoder stability |
| `close_gripper(...)` | Hold the measured TCP while closing; require finger encoder stability |
| `wait(seconds)` | Advance physics while holding the measured TCP and last gripper command |
| `get_tray_slot()` | Return calibrated fixture support center, lane size, long-axis vector, rim height, and slot ID |
| `segment_instrument(...)` | Send live RGB to a configured SAM3 text- or point-prompt endpoint |
| `mask_to_robot_points(...)` | Backproject a visual mask using current depth and camera calibration |
| `estimate_grasp(...)` | Estimate a top-down starting candidate from a masked point cloud |

Pose commands use the existing corrected TCP IK and pick/place precision modes. A measured finger/table clearance can raise a low requested pose. These commands do not provide global collision-free planning; skill programs must select suitable waypoints.

The grasp helper aligns the Panda finger closing axis across the estimated instrument axis. Its PCA orientation and centroid are starting estimates, not proof of a graspable handle or correct blade/handle direction.

## Reward and outcome verification

Success is measured independently of a program's printed output or requested robot poses. The private evaluator checks:

- The target was lifted clear of its initial table placement while the gripper was commanded closed.
- Relative target/TCP hold geometry remained sufficiently stable during transport.
- The fingers were commanded open and the robot retreated after release.
- The target became stationary and supported at the tray floor.
- Its full footprint fits inside its class-designated lane, with center error at most 8 mm and axis error at most 8 degrees.
- Preloaded instruments remain valid in their lanes.

Dropping below the table, transport slip, remaining attached after opening, displaced preloads, and nonfinite measured state produce failure. Stable fingers alone do not establish a grasp. The task reward is `1` only after verified pick/place; otherwise it is `0`.

## Execution, refinement, and artifacts

Programs run through upstream ASPIRE's `CodeExecutionEnvBase` with the surgical API registered. Upstream stdout and traceback capture are preserved. Episode reset clears the execution namespace. AST checks restrict imports to NumPy and math and reject common private simulator, file, and network access patterns. **This is ordinary trusted Python execution, not an adversarial security sandbox.**

Each trial runs in a fresh simulator process. The runner enforces a simulation-step budget and an outer wall timeout. It can terminate only the process tree it created for that trial. Provider credential environment variables are removed from simulator workers.

Optional refinement uses a vision-capable Chat Completions provider. It evaluates candidates on development seeds, sends public API documentation, outcome feedback, tracebacks, and initial/final RGB, and selects the best development candidate. Private reset geometry is excluded from model feedback. The selected program is frozen before held-out evaluation; evaluation failures do not trigger tuning. Missing refinement credentials are checked before expensive multi-round trials, and refinement errors retain the selected program and development evidence.

Trial output includes:

- `result.json`: execution status, physical task success, feedback, timing, and program hash when available.
- `program.py`, `prompt.txt`, and `contract.json`.
- `worker.log` and `actions.jsonl`.
- Initial/final six-camera PNGs, metric depth arrays, and calibration/proprioception JSON when initialization permits capture.
- Sampled front/wrist JPEG frames.
- `reset_diagnostics.json`, containing private engineering evidence for reset and settling.

Campaign output additionally includes the frozen program and aggregate reports. Startup crashes and timeouts remain failed trials in the denominator.

## Other added files

| File | Purpose |
| --- | --- |
| `configs/aspire/surgical.json` | Default surgical task: scissor, empty tray, four canonical distractors, 448-pixel cameras, 2,400-action budget, development seeds 101–105, evaluation seeds 1–5 |
| `examples/aspire/motor_smoke.py` | Exercise six-camera observations, open/close gates, measured pose convergence, and waiting; deliberately performs no pick/place |
| `examples/aspire/visual_pick_place.py` | Sensor-only picking/placement starting candidate requiring SAM3; intended for development refinement |
| `requirements/aspire-core.txt` | Minimal ASPIRE adapter dependencies for a separate CPU/core environment |
| `requirements/aspire-isaac45.txt` | Additional local support packages for the installed 4.5 runtime |
| `scripts/setup_aspire.ps1` | Initialize ASPIRE, download pinned IsaacLab source, install local support packages, and run preflight |
| `scripts/aspire.py` | CLI commands: `preflight`, `run`, `evaluate`, and `refine` |
| `scripts/aspire_worker.py` | Simulator-worker entry point |
| `scripts/convert_aspire_assets.py` | Export newer binary wrappers to portable text USD without launching simulation or modifying originals |
| `scripts/test_aspire.py` | Run adapter tests in Isaac Sim Python without Kit |
| `tests/test_aspire.py` | Contract tests using genuine upstream execution and a deterministic fake robot; optional dependencies are skipped in unrelated test environments |
| `docs/ASPIRE.md` | Setup, usage, interfaces, perception/refinement configuration, and troubleshooting |
| `docs/ASPIRE_VALIDATION.md` | Workstation validation results and remaining limits |

## USD compatibility additions

Added these files under `env/aspire_usd45`:

- `love_centered_root_at_center.usda`
- `kelly_root_at_center.usda`
- `scalpel_type2_root.usda`
- `manifest.json`

The text copies preserve the original wrappers' authored transforms and physics attributes and use portable relative references to original geometry under `assets`. The manifest records hashes for both source and converted files; the adapter rejects stale copies.

Conversion used the installed Isaac Sim 6 USD reader without starting a 6.0 simulation. The simulation target remains 4.5. Original asset files were verified unmodified.

## Existing files changed and local additions

- `.gitignore`: ignore `.local/` integration dependencies and `aspire_runs/` generated trial output.
- `README.md`: add a link to the ASPIRE usage guide.
- `.gitmodules`: added for the pinned ASPIRE checkout.

Local, ignored additions include `.local/IsaacLab`, `.local/aspire-python`, temporary validation configurations under `.local/aspire-checks`, and trial evidence under `aspire_runs`. Existing recorder source, original asset geometry, recordings, and DP training/inference implementations were not edited by this integration.

## Validation completed

| Check | Result |
| --- | --- |
| Dependency and compatibility-asset preflight | Passed in Isaac Sim 4.5 Python |
| Adapter contract tests | **30 passed**, without launching Kit |
| Scissor, development seed 101, empty tray, four other instruments | Live motor smoke passed; 84 measured actions |
| Scalpel type 2, development seed 102, four preloaded tray lanes | Live motor smoke passed; preloads preserved across 84 actions |
| Full-tray case with two extra table distractors | Reset rejected by the stationary-object gate; failure evidence retained |
| PowerShell setup syntax | Passed parser check |
| Tracked diff whitespace | Passed `git diff --check` |
| ASPIRE checkout | Verified unmodified |
| Original assets | Verified no Git diff |

The successful live checks exercised scene creation, flat-body reset, settling, all six cameras, TCP convergence, gripper encoder gates, and artifact capture. Initial top/front/wrist images were visually reviewed. Both motor checks correctly report `execution_ok: true` and `success: false` because no picking was attempted.

The extra-clutter case reached the bounded 750-step settling limit. One extra body reported approximately 3.58 mm/s against the unchanged 3 mm/s gate. It was rejected rather than counted as a usable trial.

Local evidence:

- `aspire_runs/smoke_450_05`
- `aspire_runs/full_tray_450_01`
- `aspire_runs/populated_450_01`

Earlier unsuccessful attempts also remain under `aspire_runs`, including startup, unsupported-wrapper, and initial-reset failures encountered while diagnosing the runtime.

## Running the integration

From the repository root:

```powershell
.\scripts\setup_aspire.ps1
& C:\isaac-sim-450\python.bat scripts\aspire.py preflight
& C:\isaac-sim-450\python.bat scripts\test_aspire.py
& C:\isaac-sim-450\python.bat scripts\aspire.py run --out aspire_runs\my_smoke
```

Use a new output directory for every run. `--gui` shows the trial window; `--python` selects another compatible simulator launcher. The default trial is headless with cameras enabled.

For visual picking, configure `task.sam3_url` and select `examples/aspire/visual_pick_place.py` using `--code`. Automatic refinement additionally requires an explicitly selected model and its parent-process provider credential. Detailed commands are in [the usage guide](docs/ASPIRE.md).

## Remaining work

### Qwen refinement campaign, 2026-10-04

The user replaced the local virtual key and selected Qwen. The key authenticated and exposed three Qwen aliases. The two `pro6000/Qwen/Qwen3.6-27B-FP8` aliases returned HTTP 400; the preset alias's response explicitly reported an invalid model name. `pro6000/qwen38-flash-next` accepted image input and correctly answered a synthetic red-image probe, using 219 reported total tokens including 84 reasoning tokens. SAM3 health was ready on CUDA FP16.

`scripts/refine_aspire.ps1` now defaults to that working Qwen alias and output `aspire_runs/qwen_development_01`. `src/aspire/campaign.py` records provider configuration without the key and saves provider token usage/finish reason per revision, bounds output to 8192 tokens, uses a 180-second request timeout, and rejects empty/truncated completions before validation/execution. Three new provider-contract tests cover normal, empty, and truncated responses, image payloads, private-feedback exclusion, and credential-free usage records: **41 adapter tests passed**.

A three-round development-only campaign was started on seeds 301–305, retaining the starting skill plus up to two Qwen revisions and every trial failure. The starting program repeated **2/5** placements in `aspire_runs/qwen_development_01`. The first revision response consumed all 8192 output tokens in reasoning and was rejected as truncated. A `reasoning_effort=low` retry in `qwen_development_02` also truncated (7566 reasoning tokens plus 626 remaining output tokens). Neither response was executed.

The runner now exposes `--reasoning-effort` and `--max-output-tokens` (1024–32768). The Qwen launcher defaults to low effort and 16384 output tokens. The ignored engineering helper `.local/continue_qwen.py` resumes from the five completed baseline trials, checks their program hashes, preserves the original candidate in best-program selection, and runs up to two revisions without held-out evaluation. A complete revision was returned in `aspire_runs/qwen_development_03`, using 7765 total tokens including 2246 reasoning tokens, and began development trials. Its proposed handle-offset calculation accesses a missing `grasp['mask']` field and catches the resulting `KeyError`, so that part falls back to the original grasp; the candidate is evaluated as generated. Other changes include a higher lift, slower transport, and settling after closure. **41 adapter tests still passed**, including reasoning-effort request forwarding; launcher syntax passed.

The campaign completed all **15 scheduled development trials**:

| Candidate | Verified placements | Result |
| --- | --- | --- |
| Starting four-camera skill | 2/5 | Seeds 301/302 passed; 303/305 missed grasp; 304 slipped |
| Qwen revision 1 | 2/5 | Seeds 301/302 passed; 303/304/305 had no verified lift |
| Qwen revision 2 | 0/5 | 301 fell off table; 302/305 placement unverified; 303 no lift; 304 slipped |

The starting skill remains selected because revision 1 only tied its score and revision 2 was worse. Its SHA256 is `d8cbcc92065a804cc024e0ee8c6d8ab9940a63856452607d3d39d99df407358f`. The selected source is `aspire_runs/qwen_development_03/frozen_program.py`; the runnable example was not replaced by a generated revision. This demonstrates a working Qwen refinement/execution pipeline, **not improved manipulation performance**.

The final revision retained the missing `grasp['mask']` access and added wrist RGB indexing as `camera['rgb']` rather than `camera['images']['rgb']`. Its broad exception handlers suppressed these errors, so the proposed hold check could not work as intended. It also reopened the fingers after a negative check, losing held objects. Candidates were evaluated as generated; no manual fixes were inserted into their trials. The public API docstrings in `src/aspire/control.py` now explicitly demonstrate RGB/depth indexing and state that the grasp result does not include the input mask. These are documentation changes for future generation, not changed motor behavior.

The ignored helper `.local/summarize_qwen.py` assembles the retained trial outcomes and usage into `aspire_runs/qwen_development_03/pilot_summary.json`. Four revision requests (two truncated, two complete) reported **39,658 total tokens**; the separate image readiness probe reported 219. Monetary cost is not calculated. All aborted requests remain recorded. Held-out seeds 401–405 remain untouched; this five-seed development pilot is not a held-out benchmark or a comparison with the existing expert/DP controller.

Next development should validate generated accesses against concrete observation/API schemas, retain masks separately, verify holds through working sensor/proprioception checks, and include failure-case images rather than only images from the first successful development trial. The current model receives all trial outcomes but images only from the first trial. SAM3 remains running locally.

### LiteLLM refinement setup, 2026-10-04

- Verified the supplied NTHU gateway's OpenAPI schema exposes `/v1/chat/completions` and `/v1/models`; configured API base `https://cgv.cs.nthu.edu.tw:9128/v1`.
- Added `src/aspire/provider.py` to load only the requested credential from a simple local `.env` assignment, preserving existing environment values without evaluating or interpolating file contents. `scripts/aspire.py` adds `--env-file`, defaulting to the repository-root `.env`, for refinement. `.env` remains ignored and credentials remain excluded from simulator worker environments.
- Added `--development-only` to refinement and `src/aspire/campaign.py`; it saves the selected frozen program and development report without touching held-out seeds. Existing default refinement behavior remains development followed by held-out evaluation.
- Added `scripts/refine_aspire.ps1`, configured for `API_KEY`, the supplied gateway, and Sonnet 4.5 through its listed alias `claude-secondary/claude-sonnet-4-5`, with development-only operation. Model, round count, output directory and GUI can be selected through launcher parameters.
- Expanded `tests/test_aspire.py` to verify development-only seed isolation and selective credential loading/worker exclusion. **38 adapter tests passed**; launcher syntax passed. Updated `docs/ASPIRE.md` with gateway setup and command semantics.

The existing `.env` credential authenticated for model listing. The user corrected the requested model from Opus to Sonnet 4.5. The only listed Claude alias was `claude-secondary/claude-sonnet-4-5`; a small synthetic-image request to the requested `anthropic/claude-sonnet-4-5` returned HTTP 403, and the listed alias returned HTTP 429. No completion was returned, so image capability remains unverified and the gateway rejection remains unresolved. No automatic refinement or new simulator campaign ran in this setup step. The credential itself was not printed or copied into artifacts.

On the user's subsequent request to start ASPIRE, SAM3 health again reported ready on CUDA FP16. The Sonnet probes repeated the 403/429 responses. The 429 response identified a rate-limit error and provided no `Retry-After` header; a further probe of the listed alias after a 30-second pause also returned 429. No simulator refinement campaign was started because the model could not return a completion. The next external requirement is to resolve the gateway rate limit or obtain another authorized Sonnet deployment; its exact quota/capacity cause has not been established.

### Continued sensor-based skill development, 2026-10-03

The worker now reports `executing_program` after reset and records private final measurements in `final_evaluation_diagnostics.json`, outside model feedback and observations. Extending retreat and settling alone did not fix placement: `windows_sam3_place_diag_01` showed a stable, supported object with a 31.55 mm center error and 179.54-degree direction error. Moving the hand aside alone also failed (`windows_sam3_full_mask_01`), because the top detector still selected another ringed instrument.

The current visual example associates front, top, left, and right detections in sensor-derived robot coordinates and requires agreement from at least two distinct cameras. It prefers a usable top mask, then side views, then front. `src/aspire/perception.py` and `src/aspire/control.py` add opt-in `allow_empty=True` so missing detections can trigger another view; transport/model failures still raise. The scissor grasp helper in `src/aspire/geometry.py` uses visible extent centering instead of density-biased median centering and distinguishes the wider ring-handle end from the blade tip to resolve the PCA sign. `src/aspire/control.py` enables this shape rule only for the requested scissor class. No per-seed coordinates, simulator object pose, or mesh is exposed to the program. The program chooses the nearer equivalent wrist orientation independently of the directed instrument axis.

`windows_sam3_multiview_01` achieved a verified placement at 644 measured actions, with final private center error 7.98 mm, direction error 0.73 degrees, supported/stationary contact, and full slot containment. That run also exposed a post-success API exception when the program requested another motion after terminal success. The motor API was corrected to stop moving and return measured state after verified completion; failed episodes still raise. Regression coverage now includes rotated synthetic scissor clouds, density-independent centering, ambiguous masks, terminal-success calls, and preserved failure behavior: **36 adapter tests passed**.

`scripts/aspire.py evaluate` now accepts `--split dev` to test the development partition explicitly. The first frozen five-seed campaign, `aspire_runs/windows_sam3_development_01`, finished at **1/5 verified placements**. Seed 301 had both `success: true` and `execution_ok: true`, in about 102 seconds. Seeds 302, 304, and 305 stopped on missing detections; seed 303 executed but did not lift the requested target. Program hash: `e5e76862698d32672abf4d89469a095e2f4eb30dd8f441984ef0da5792b884cb`. An offline engineering audit of saved views motivated the four-camera version; private target measurements were used only to diagnose errors, never provided to the skill. Held-out seeds have not been used for this development work, and no LLM refinement request has been made.

### Native Windows validation follow-up, 2026-10-03

The revised frozen four-camera campaign at `aspire_runs/windows_sam3_development_02` completed at **2/5 verified placements**, with all five scheduled development attempts retained. Program SHA256: `d8cbcc92065a804cc024e0ee8c6d8ab9940a63856452607d3d39d99df407358f`. Both successful cases passed execution and the unchanged physical evaluator.

| Development seed | Outcome |
| --- | --- |
| 301 | Verified placement; top mask confirmed across four cameras; 7.98 mm center error, 0.73-degree axis error |
| 302 | Verified placement; right mask confirmed across two cameras; 2.97 mm center error, 0.99-degree axis error |
| 303 | Program completed but no verified lift; wrist frames show a missed grasp |
| 304 | Verified lift, then `target_slipped_during_transport`; evaluator stopped execution |
| 305 | Program completed but no verified lift |

Four-view association resolved missing-view aborts in this campaign, but grasp contact and stable transport remain unresolved. These reused development seeds establish feasibility, not held-out performance. The server/client suite now has **4 passing tests**, including opt-in empty detections versus the default error. Recommended next development work is sensor-based grasp/contact verification and more stable transport before freezing a candidate for evaluation. SAM3 remains running locally; automatic LLM refinement still requires a selected provider/model. No original-controller or Diffusion Policy comparison has run.

The separate Windows SAM3 environment installed successfully. CUDA and native Transformers SAM3 imports passed, the three HTTP contract tests passed, and dependency validation reported no broken requirements. After the user obtained gated-model access, the server loaded `facebook/sam3` revision `3c879f39826c281e95690f02c7821c4de09afae7` on the RTX 2080 Ti using FP16. A real saved-image probe found the visible scissors in about 1.03 seconds (confidence 0.93457, 218 mask pixels); the image and mask were visually reviewed. Evidence is in `aspire_runs/sam3_windows_probe_01`.

The original top-camera skill on development seed 301 selected a different ringed instrument while the scissors were obscured by the home arm, then timed out at the first hover. That attempt remains in `aspire_runs/windows_sam3_visual_01`. A subsequent front-camera RGB-D candidate, without ground-truth inputs, completed without program errors and verified a physical scissors lift and release over 708 actions in `aspire_runs/windows_sam3_visual_front_01`. It still reported `success: false`, `place_verified: false`, and `placement_not_verified`; process wall time was about 108 seconds. Later verified placements are documented above; no model-driven refinement campaign or controller comparison is claimed.

Native Windows perception support was added on 2026-10-03: `scripts/serve_sam3_windows.py` implements the ASPIRE text-mask HTTP contract using Transformers SAM3; `scripts/start_sam3.ps1` launches it in a separate local Python environment; `requirements/sam3-windows.txt` specifies server dependencies; `tests/test_sam3_windows.py` checks mask encoding, invalid images, unsupported point prompts, and inference failures. [Windows setup instructions](docs/SAM3_WINDOWS.md) document installation and operation. This backend uses FP16 on CUDA and FP32 on CPU and leaves the upstream checkout unchanged. Point prompting remains unsupported. These additions alone do not establish live perception or manipulation success.

The follow-up [experiment plan](docs/ASPIRE_EXPERIMENTS.md), added 2026-10-02, describes the first visual trial, a bounded refinement pilot, baseline integration gaps, and a shared-scene comparison protocol. `configs/aspire/pilot-scissor.json` adds separate development seeds 301-305 and held-out pilot seeds 401-405. The 2026-10-03 Windows setup configures its SAM3 endpoint as `http://127.0.0.1:8114`; a ready server is still required. These additions prepare experiments; they do not add manipulation results or an expert/DP comparison runner.

1. Extend the now-working native Windows SAM3 perception checks across instruments and occluded views; text segmentation is validated on limited development images, while point prompts remain unsupported.
2. Validate depth-derived grasp candidates, handle selection, approach waypoints, and release offsets through development trials.
3. Demonstrate and measure physical pick/place success for each instrument class.
4. Configure a vision-capable model provider and exercise the live refinement loop.
5. Freeze the selected skill and evaluate it on the reserved seeds without further tuning.
6. Improve and characterize dense-clutter reset reliability without weakening outcome or settling checks.

The implemented setup provides the environment, controls, evaluation, and trial infrastructure needed for those stages. Current validation establishes working sensor/motor integration, not reliable autonomous manipulation performance.
