# Starting ASPIRE and comparing controllers

Prepared 2026-10-02. This is an experiment plan, not a performance report. No live perception/refinement campaign or controller comparison has been completed.

## First objective

Demonstrate a physically verified scissor pick-and-place, then determine whether feedback-driven code refinement improves the starting visual program. Start with an empty tray, four canonical distractors, and lighting randomization off. Those scene settings have passed motor validation. Extra clutter has already exposed a settling failure and should be a later experiment.

The implemented integration uses upstream ASPIRE's code executor and a custom development-feedback loop. It does not reproduce the complete upstream evolutionary search or published benchmark protocol. See [ASPIRE](https://github.com/NVlabs/ASPIRE) and the [integration report](../ASPIRE.md).

## 1. Connect perception and inspect one development trial

Two external inputs are still needed: a running ASPIRE-compatible SAM3 endpoint, and a vision-capable Chat Completions provider/model for automatic refinement. Keep credentials in the parent process environment. A trained DP checkpoint is not needed for this first stage.

Set `task.sam3_url` in `configs/aspire/pilot-scissor.json` to the service's base URL. The native Windows follow-up now points this pilot to `http://127.0.0.1:8114`; the server must actually be running before visual picking. See [native Windows setup](SAM3_WINDOWS.md), or the [upstream Linux simulation/service instructions](https://github.com/NVlabs/ASPIRE/tree/main/aspire/sim) for a remote service. Do not install the full upstream Linux simulator stack into Isaac Sim 4.5 Python.

Run from the repository root, using a new output directory for each command:

```powershell
& C:\isaac-sim-450\python.bat scripts\aspire.py preflight `
  --config configs\aspire\pilot-scissor.json

& C:\isaac-sim-450\python.bat scripts\aspire.py run `
  --config configs\aspire\pilot-scissor.json `
  --code examples\aspire\visual_pick_place.py `
  --seed 301 --wall-timeout 600 --out aspire_runs\pilot_scissor_first
```

Inspect `result.json`, `worker.log`, initial/final images, and the sampled motion frames. `execution_ok: true` means the program executed; only `success: true` means verified manipulation. Diagnose segmentation, grasp position, approach, slip, release, and retreat separately. A failed reset should be fixed before spending model requests on motion refinement. The PCA grasp example is an unvalidated starting candidate; ringed scissors may need handle selection or a different grasp offset.

Preflight checks dependencies and assets; it does not test the SAM3 endpoint, provider credentials, or physical grasp success. The existing motor smoke program does not attempt a pick, so explicitly pass the visual program with `--code`.

## 2. Run a bounded refinement pilot

The new pilot configuration uses development seeds 301-305 and held-out pilot seeds 401-405. These are separate from the integration's earlier motor trials and are not intended as the final scientific test set.

After the first trial reaches perception and control successfully, select a provider/model and set its credential through your normal environment configuration:

```powershell
$aspireModel = 'YOUR_VISION_MODEL'
$aspireProvider = 'https://YOUR_PROVIDER/v1'

& C:\isaac-sim-450\python.bat scripts\aspire.py refine `
  --config configs\aspire\pilot-scissor.json `
  --code examples\aspire\visual_pick_place.py `
  --model $aspireModel --base-url $aspireProvider `
  --api-key-env ASPIRE_API_KEY --rounds 3 --wall-timeout 600 `
  --out aspire_runs\pilot_scissor_refinement
```

`ASPIRE_API_KEY` must already be set in the parent process. The command tests the initial candidate on all five development seeds, requests an improved program between rounds, selects the best development candidate, freezes it, and automatically evaluates the five held-out pilot seeds. Three rounds allow at most 15 development trials, five evaluation trials, and two model requests; the loop can finish earlier. The 600-second per-worker cap permits up to 200 minutes of worker waiting, plus provider requests and process cleanup. There is no configured monetary spending cap.

Review `development.json`, `frozen_program.py`, and `evaluation/report.json`. The report includes the frozen program hash. Model feedback includes outcomes and stage logs from all development trials. Images now prioritize two distinct failed trials and one successful control, including the last sampled wrist frame. Protocols can include disjoint `validation_seeds` for candidate selection; this older five/five pilot configuration still selects on development. Provider token usage is recorded in `provider_usage_<round>.json`; monetary cost is not calculated automatically. Add `--development-only` to freeze without held-out evaluation. The configured Windows Qwen launcher uses that flag; see [the usage guide](ASPIRE.md#nthu-litellm-gateway).

First aim for one verified placement, then reliable performance across the development scenes. If pilot evaluation inspires further changes, those pilot seeds become development evidence: reserve fresh seeds for the final comparison. Never refine from final held-out outcomes and continue calling the same set held out.

## 3. Establish comparable baselines

| Method | Role | Work still needed |
| --- | --- | --- |
| Starting visual program, without refinement | Measures the gain from refinement | Evaluate the unchanged source on the same held-out scenes |
| Refined ASPIRE program | Main experimental method | Live perception/refinement validation, then freeze source |
| Current expert recorder/controller | Reference for geometric control | Wrap the existing approach/pick/transfer/place logic in a common rollout harness; label its object ground-truth access as an oracle advantage |
| Current Diffusion Policy | Learned sensor-policy comparison | Provide non-smoke pick/place checkpoints and connect the runtime's observe/predict interface to skill handoffs and robot actions |

No trained `.pt`, `.pth`, or `.ckpt` files were found in this checkout during planning. Checkpoints elsewhere can be used after verifying their sensor/controller contract. `training/runtime.py` is a prediction interface, not a complete end-to-end robot application. The current workflow combines controller approach/transfer with learned pick/place phases; its handoffs must be represented in the comparison.

Build a common rollout harness before claiming a fair method comparison:

- Save each case's initial object poses, tray occupancy, target, lighting, robot state, and relevant physics/reset settings; replay the same validated case for every method. Equal integer seeds alone do not guarantee equal layouts across different reset implementations.
- Use the same robot/TCP configuration, action budget, private physical evaluator, and fixture goal. Prevent ASPIRE or DP from receiving object ground truth or expert stages.
- Report sensor differences: the present ASPIRE candidate uses RGB-D and calibration, while DP consumes six RGB images and proprioception. This is a system comparison with different inputs; a claim about algorithm quality alone requires a matched-input experiment.
- Keep source/checkpoint hashes, protocol, model/provider identity, perception version, and training/refinement budget with results. Freeze the skill before final evaluation.
- Retain every scheduled attempt, including crashes and timeouts. Report reset/infrastructure failures separately as well as end-to-end success. Define invalid-case handling before running comparisons; do not silently discard failures or repeatedly retry until success.

This common harness and the expert/DP rollout adapters are proposed next work; they have not been implemented by adding this plan.

## 4. Expand experiments after the scissor pilot

Start the formal comparison with 50 fresh paired cases per instrument, five instruments, empty tray, four distractors, and fixed lighting: 250 cases per method. Check coverage of table cells and instrument orientations rather than relying only on seed count. Fifty cases is an initial practical budget, not a statistical power guarantee. Three methods would require 750 rollouts for this condition alone; the starting-program ablation adds another 250 if included.

Then change one condition at a time:

| Experiment | Question |
| --- | --- |
| Starting program versus refined program | Does development feedback improve held-out success? |
| Empty versus preloaded tray | Can the method place without disturbing existing instruments? |
| Additional clutter, after reset reliability is resolved | How does crowding affect target selection and collision avoidance? |
| Lighting randomization off versus the existing `train` preset | How sensitive is perception/control to visual variation? |
| Small versus larger refinement budgets | How much success is gained per model request and development rollout? |

For each method report verified first-attempt placement rate, lift rate, slip/drop rate, preloaded-instrument disturbance, failure phase, and infrastructure failure rate. Report execution time separately from simulator startup; the current `elapsed_s` is process wall time. Add stage timing and provider usage accounting before making speed or cost claims. Use paired cases for success differences and confidence intervals. If assessing the refinement procedure rather than one frozen skill, repeat independent refinement campaigns and report variation between the learned programs.

## Recommended order

Connect SAM3; inspect one development trial; achieve a verified scissor placement; run the bounded refinement pilot; implement the shared baseline harness; freeze methods and run a fresh paired comparison. Expand to all instruments and difficult conditions after this sequence works.
