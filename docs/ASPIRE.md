# ASPIRE on the surgical instrument scene

The original five controllers now have full-stage sensor-based ASPIRE starting
skills. See [controller translations and run commands](ASPIRE_TRANSLATION.md)
for the stage mapping, per-target programs, validation status and limitations.

The current visual workflow defaults to the repo's RF-DETR detector. See
[RF-DETR setup and depth-based grasping](ASPIRE_RFDETR.md). The SAM3 instructions
below describe the optional backend; set `task.perception_backend` to `"sam3"`
explicitly to use it or reproduce earlier trials.

This branch runs [NVlabs/ASPIRE](https://github.com/NVlabs/ASPIRE) against the existing Franka and hospital scene. ASPIRE is pinned as a Git submodule in `third_party/ASPIRE`. The surgical environment/API adapter lives in `src/aspire`. The native route below calls upstream's trial, ensemble, synthesis, code extraction and regeneration functions. A small local patch parameterizes ensemble size and request timeout, guards Linux-only alarms on Windows, and permits bounded terminal stopping. Upstream prompt templates remain unchanged; tests compare them with the pinned commit.

## Native ASPIRE on scissors

The active integration uses upstream `aspire.sim.cap.envs.trial._run_single_trial` and `query_single_model_ensemble`, with the surgical API/environment attached through `NativeSurgicalExecutionEnv`. The earlier `aspire.py search` population loop is a separate custom engineering search, not the upstream trial pipeline.

```powershell
C:\isaac-sim-450\python.bat scripts/run_native_aspire.py --config configs/aspire/native-scissor-sam3.json --out logs/native_scissor_next --seed 501 --candidates 8 --revisions 3 --provider-timeout 1800 --max-output-tokens 128000 --prior-requests 2 --request-budget 22 --gui
```

Use a new output folder. The native scissors configuration records the previously tested 32/8 physics solver settings. Model-generated programs use sensor observations, public motion APIs, fixture calibration and coarse evaluator flags; private geometry stays local. The task/API instruction is retained, and the regeneration template is read verbatim from upstream's Franka configuration. Image and video differencing services and evolving skill-library extraction are disabled for this first bounded smoke test; main/wrist visual feedback is enabled.

Here K=8 means eight model proposals followed by one synthesis call, then execution of the synthesized program. T=3 is a maximum of three regenerations after the initial execution. Each generation costs up to nine requests, so initial generation plus all three repairs could require 36 requests. This continuation retains the earlier total cap of 24, including two already attempted requests: 22 remain, enough for two full generations (18 calls). The adapter stops before attempting an incomplete ensemble. Success, terminal physical failure, model FINISH, turn limits and request limits can end a trial earlier.

The credential-owning parent process relays requests through a loopback-only endpoint. Generated-code workers receive no provider credentials. The relay counts and records every external attempt and turns transport errors into non-retryable responses to prevent upstream's otherwise unbounded HTTP retry loop. `provider/request_*.request.json`, `.response.json` and `.usage.json` retain exact prompts, raw responses and reported usage before extraction. `provider/report.json` exposes request counts and remaining budget. Upstream writes its own code, ensemble and regeneration artifacts; `result.json` separately reports verified physical placement, because upstream's `success` field primarily reflects Python execution status. All artifacts remain under the selected `/logs` folder.

See [validation results and remaining limits](ASPIRE_VALIDATION.md) for the checks completed on this workstation.

See the [experiment plan](ASPIRE_EXPERIMENTS.md) for the first visual trial, bounded refinement pilot, and comparison with the current expert controller and Diffusion Policy.

The integration targets **Isaac Sim 4.5 / Python 3.10 with IsaacLab v2.1.1**. See NVIDIA's [4.5 installation instructions](https://isaac-sim.github.io/IsaacLab/v2.1.1/source/setup/installation/binaries_installation.html). The recorder's default `C:\IsaacLab\_isaac_sim\python.bat` is absent on this workstation, so this setup uses `C:\isaac-sim-450\python.bat` and downloads IsaacLab source into `.local/IsaacLab`.

## Setup and first trial

The local ASPIRE changes are saved in `patches/aspire-local.patch`. The setup
script applies this patch after initializing the pinned submodule and skips it
when already applied. Generated logs, exports, and local credentials stay outside
Git.

Run from the repo root:

```powershell
.\scripts\setup_aspire.ps1
& C:\isaac-sim-450\python.bat scripts\aspire.py preflight
& C:\isaac-sim-450\python.bat scripts\test_aspire.py
& C:\isaac-sim-450\python.bat scripts\aspire.py run --out aspire_runs\motor_smoke
```

Each output directory must be new. `--python` selects another launcher; `--gui` shows the trial window. Trials default to headless rendering with all six cameras enabled. Setup adds only missing support packages under `.local/aspire-python`, without replacing the simulator's Torch/CUDA installation. `.local` and trial outputs are ignored by Git. Full ASPIRE benchmark installation is unnecessary for this native scene; its Linux simulator/model dependencies must not be installed into Isaac Sim Python.

`motor_smoke.py` exercises reset, cameras, measured pose convergence, and gripper encoder gates. A successful smoke program has `execution_ok: true` and `success: false`: it does not pick an instrument. `success: true` always means the private evaluator verified a physical pick and placement.

## Task contract

Edit `configs/aspire/surgical.json`, or copy it to a new configuration. The default target is `scissor`, with four other instruments, an empty tray, 448-pixel cameras, and a 2,400-action budget. Supported targets are `scalpel`, `scissor`, `love_retractor`, `kelly`, and `scalpel_type2`. Tray mode can be `empty`, `random`, or `full`; extra table clutter uses the existing 4–30 distractor contract. Development seeds are 101–105; evaluation seeds are 1–5. The loader rejects overlapping seed partitions.

Reset homes the robot, restores canonical instrument link poses, samples distinct grid cells, prepares tray occupancy and extra clutter, then requires stationary objects and valid placements before motion. Geometry writes happen during reset only. Existing asset scale, mass, friction, scene layout, camera transforms, and TCP correction come from the shared recorder configuration. This adapter does not run or export the recorder FSM or produce DP demonstrations.

Three original instrument wrappers use USD crate 0.10, which the 4.5 reader cannot open. `env/aspire_usd45` contains text-format equivalents with portable references to the original geometry. The adapter verifies source and converted hashes before selecting them. It preserves all authored transforms and physics attributes. If those wrappers change, regenerate the compatibility copies with `& C:\isaac-sim-600\python.bat scripts\convert_aspire_assets.py` (or another compatible USD reader); this conversion does not launch a 6.0 simulation.

The environment implements `reset(seed=...)`, `step(action)`, `get_observation()`, `compute_reward()`, `task_completed()`, and ASPIRE rendering/capture hooks. `step` accepts eight absolute robot-base values: `[x, y, z, qw, qx, qy, qz, gripper]`, with metres, WXYZ quaternion, and +1 open / -1 close. Programs normally use the higher-level API below.

| Program API | Behavior |
| --- | --- |
| `get_observation()` | Six RGB-D cameras, calibration, measured robot state, 16-value proprioception, requested target name |
| `get_robot_state()` | Measured TCP XYZ/WXYZ and two finger encoders in robot-base coordinates |
| `goto_pose(position, quaternion_wxyz, ...)` | Smooth interpolation plus measured convergence, bounded timeout, existing corrected TCP IK |
| `open_gripper()`, `close_gripper()` | Hold measured TCP and wait for each finger's encoder stability |
| `wait(seconds)` | Step physics while holding TCP and last gripper command |
| `get_tray_slot()` | Calibrated fixed fixture goal: support center, long-axis vector, lane size, rim height |
| `segment_instrument(...)` | RF-DETR boxes + calibrated depth foreground; optional SAM3 masks |
| `mask_to_robot_points(...)` | Backproject a visual mask using metric image-plane depth and calibration |
| `estimate_grasp(...)` | PCA-based top-down starting candidate from masked sensor points |

Observations use `obs['cameras'][name]`, where `name` is `front`, `wrist`, `top`, `left`, `right`, or `tray`. Each camera contains `images.rgb` (HxWx3 uint8), `images.depth` (HxW metres), `intrinsics` (3x3), and `pose_mat` (4x4 optical camera to robot base). The optical frame is +X right, +Y down, +Z forward. Images and depth are uncropped and unrotated so pixels remain aligned with calibration. `proprio` is nine joint positions followed by TCP XYZ and WXYZ. No object pose, simulator segmentation, grid assignment, mesh, privileged grasp candidate, or recorder stage is exposed.

The evaluator privately checks lift, relative hold stability, release, open fingers, retreat, stationary support, full footprint within the designated lane, center within 8 mm, axis within 8 degrees, and preservation of preloaded instruments. Closing fingers or reaching a commanded pose does not produce reward. Dropping, slipping, invalid measured state, and displaced preloads produce failure feedback. `goto_pose` is a local IK controller; skill programs must choose appropriate collision-avoiding waypoints.

## Visual perception and refinement

Use [the RF-DETR setup](ASPIRE_RFDETR.md) with a trained five-class checkpoint.
The default configuration connects to `task.rfdetr_url` on port 8115. RF-DETR
runs in the standalone detector environment; ASPIRE derives foreground regions
from its boxes and measured depth. The existing refinement launcher uses this
backend as well.

For the optional SAM3 backend, set `task.perception_backend` to `"sam3"` and use
the [Windows SAM3 setup](SAM3_WINDOWS.md): a separate Conda Python environment
and a Transformers-based text segmentation server. That server supports text
prompts; point prompts are not implemented.

The motor setup runs without perception services or an LLM credential. SAM3
configurations additionally require `task.sam3_url`; that adapter uses `/segment`
and `/segment_point` with the upstream image/mask protocol. Services can run on
a separate GPU machine. `examples/aspire/visual_pick_place.py` remains a starting
candidate for refinement. The RF-DETR box/depth backend has contract tests but
no physical pick/place validation yet; earlier SAM3 pilot results do not
establish its performance.

Evaluate a reviewed program without an LLM:

```powershell
& C:\isaac-sim-450\python.bat scripts\aspire.py evaluate `
  --code examples\aspire\visual_pick_place.py --out aspire_runs\visual_eval
```

For automatic refinement, configure the perception endpoint and a vision-capable Chat Completions provider, then explicitly select a model:

```powershell
# Set OPENAI_API_KEY in the parent process using your normal secret-management method.
& C:\isaac-sim-450\python.bat scripts\aspire.py refine `
  --code examples\aspire\visual_pick_place.py --model <YOUR_MODEL> `
  --rounds 3 --out aspire_runs\visual_refinement
```

`--base-url` and `--api-key-env` support compatible providers. Each development round tests a candidate on every development seed and sends API documentation, outcome feedback, stage stdout, and tracebacks to the selected provider. Images come from up to two distinct failed development trials and one successful control: initial/final views and the last sampled wrist frame. Private reset diagnostics and evaluator geometry are excluded. If the protocol includes `validation_seeds`, candidates are selected on that separate partition; validation feedback is never sent for revision. Legacy protocols still select on development. The selected candidate is frozen before held-out evaluation; evaluation failures never trigger refinement. Review generated programs before reuse. The AST check catches accidental private API, file, and network access, but ordinary Python execution is not a security sandbox. Credentials are removed from simulator worker environments.

### NTHU LiteLLM gateway

The gateway API base is `https://cgv.cs.nthu.edu.tw:9128/v1`, verified against its OpenAPI schema on 2026-10-04. Store `API_KEY=your-key` in the repository-root `.env` locally. The file is ignored by Git. `refine` loads only the selected credential, supports simple single-line quoted or unquoted assignments, and preserves an existing environment-variable value. It does not evaluate shell expressions or expand variables. Provider credentials are removed from simulator worker environments.

The configured launchers now default to the gateway-listed Opus alias `claude-secondary/claude-opus-4-6`. Model listing and a synthetic red-image completion were verified on 2026-10-04. This confirms basic image transport, not manipulation-repair quality. The legacy sequential scissor launcher uses:

```powershell
.\scripts\refine_aspire.ps1 -Rounds 3 -Out logs\opus_development_01
```

It enables `--development-only`: the best candidate is frozen and a development report is saved, with no held-out trials. Three rounds test the initial program and up to two model revisions. Without this flag, the generic `refine` command still runs held-out evaluation after development. `-Model` overrides the gateway alias and `-Gui` enables the simulator window.

The earlier key authenticated for `/v1/models`, but Sonnet requests returned 403/429. After the user installed a new virtual key and selected Qwen, the model list expanded. `pro6000/Qwen/Qwen3.6-27B-FP8` and its sampling-preset alias were rejected with HTTP 400; `pro6000/qwen38-flash-next` successfully answered a synthetic image-color probe (219 total tokens, including 84 reasoning tokens). This checks image transport and a basic answer, not manipulation reasoning quality.

Refinement records non-secret provider configuration in `provider.json` and model-reported token usage/finish reason in `provider_usage_<round>.json`. The CLI and launchers default to a 128000-token output cap, matching the documented Opus 4.6 standard API output ceiling. The context window is a separate provider/model limit; `max_tokens` limits generated output. The Opus default omits `reasoning_effort`; the earlier Qwen campaign used `low`. `--max-output-tokens` supports 1024–128000; choose a value supported by the selected provider. `--reasoning-effort` selects a provider-supported effort. The provider response timeout defaults to 1800 seconds (30 minutes); search accepts `--provider-timeout` between 10 and 1800 seconds. Empty or truncated completions are rejected before execution. Trial `elapsed_s` remains simulator-process wall time; usage records do not establish monetary cost.

The first Qwen pilot completed 15 development trials: starting skill **2/5**, revision 1 **2/5**, revision 2 **0/5**. The original skill remains selected. Evidence is in `aspire_runs/qwen_development_03/pilot_summary.json`, linked to the baseline and two rejected response records. This validates the refinement pipeline, not improved placement performance. The generated revisions made mask/observation-key mistakes; see [the change report](../ASPIRE.md) for details. Held-out seeds remain reserved.

### Population search: K=8, T=3

The active search budget is eight distinct proposed programs per round and up to three revision rounds after the starting program. The initial task is scissors, with a local smoke test before live search. Use the population launcher; `refine` remains the older one-program-at-a-time loop. Preview the budget without reading credentials, contacting a model, or launching the simulator:

```powershell
.\scripts\search_aspire.ps1 -Target scissor -Plan
```

After reset reliability is repaired and experiment-data transfer is approved, run:

```powershell
.\scripts\search_aspire.ps1 -Target scissor -Iterations 3 -Out logs\scissor_opus_k8_t3
```

The launcher defaults to SAM3 and Opus 4.6. `-Candidates 8` specifies K and `-Iterations 3` specifies T. Configurations in `configs/aspire/search` provide six development, four validation, and ten reserved final scenes for every existing instrument and each supported perception backend. Model proposals condition on the top three programs ranked by development performance and their public development evidence. All eight proposals are generated before that round's executions; all eight are evaluated before a success stop. Validation selects the frozen program and never enters revision feedback. Ties retain the earlier program. Search stops upon solving all development and validation scenes, after three complete rounds, or on infrastructure/proposal errors. Duplicate or invalid proposals stop and remain logged; there are no hidden retries or early plateau stops.

At maximum, one starting program plus 24 proposals consumes 150 development and 100 validation trials: **250 trials and 24 model requests**. The default keeps final scenes unused. Explicit `-FinalEvaluation` adds one frozen ten-case evaluation, totaling **260 trials** and at most **43.33 hours of worker waiting** at the 600-second cap, excluding provider waits and cleanup. The model output cap is 128000 tokens per request; actual input/output usage is logged. Monetary cost is unknown. These remain seed-generated, evaluator-assisted engineering experiments, without exact physical scene replay or the proposed independent hold metric.

Optional `task.solver_position_iterations` and `task.solver_velocity_iterations` support a recorded numerical settling audit. They default to `null`, leaving authored physics unchanged, and apply uniformly to the five instruments when set. Solver audits use separate run configurations under `logs`; no mass, contact offset, asset, or scoring threshold is changed by those options.

`search_plan.json`, `contract.json`, `provider.json`, `report.json`, per-proposal context/source/usage/evidence, worker traces, and `frozen_program.py` are saved under the chosen `logs` directory. Infrastructure failures stop before further proposals; a failed initial reset prevents any proposal request. The six-case local pilot retained under `logs/experiments_20261004` has four such reset failures, so the larger live campaign has not been launched.

## Current visual skill and development checks

The current candidate moves the empty hand aside and associates detections from front, top, left, and right cameras by depth-derived robot-base positions within 6 cm. It requires agreement from at least two distinct views, then prefers a usable top mask, followed by side and front masks. Missing detections trigger other views through `segment_instrument(..., allow_empty=True)`; network and model errors still stop execution. For scissors, the grasp helper estimates the full visible extent center and resolves the PCA sign from the broad ring-handle end toward the narrower blade tip. It rejects insufficient-length or direction-ambiguous masks. The skill chooses the nearer equivalent parallel-finger orientation, rotates toward the fixture axis, releases, retreats, and allows settling. These heuristics have limited development evidence; they are not a trained detector or a general collision planner.

Tray axis alignment is directed: scissors blade tips should point along the calibrated lane axis. After verified terminal success, further motor API calls return measured state without moving the robot; failed episodes still stop execution. The worker reports `executing_program` after reset and saves `final_evaluation_diagnostics.json` separately for engineering review. This file contains private object measurements and is not included in policy observations or refinement feedback.

To test a frozen candidate on development seeds without consuming held-out seeds:

```powershell
& C:\isaac-sim-450\python.bat scripts\aspire.py evaluate --split dev `
  --config configs\aspire\pilot-scissor.json `
  --code examples\aspire\visual_pick_place.py --out aspire_runs\scissor_development
```

`evaluate` still defaults to `--split eval`; `refine` still evaluates held-out seeds automatically after candidate selection. Every output directory must be new.

## Evidence and troubleshooting

Every trial gets a fresh simulator process and a wall timeout (600 seconds by default, adjustable with `--wall-timeout`). `result.json` records program execution separately from task success. `worker.log`, `program.py`, `prompt.txt`, `actions.jsonl`, initial/final six-camera PNGs, depth arrays, calibration, and sampled front/wrist JPEG frames remain available on failures. `reset_diagnostics.json` contains private layout/settling evidence for engineering review only. Campaigns additionally save the frozen program hash and aggregate report. A startup crash or timeout remains a failed trial in the denominator.

If preflight fails, run setup with the correct 4.5 launcher. If a trial cannot initialize, inspect its `worker.log` and `result.json` before trying refinement. First startup can download NVIDIA base robot assets and initialize render caches. Running a second scene alongside an open Isaac Sim GUI increases GPU/RAM demand; a timeout is reported as failure rather than success. No other simulator process is terminated by the runner.

Adapter contract tests run in Isaac Sim Python without Kit. Live scene startup, motor checks, and actual grasp/placement success are distinct validation levels; passing CPU tests alone does not establish manipulation performance.
