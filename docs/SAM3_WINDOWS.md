# Native Windows SAM3 for ASPIRE

Added 2026-10-03. This service uses Hugging Face Transformers 5.0.0's SAM3 implementation and the `facebook/sam3` weights, with native Windows PyTorch. It does not require WSL, Ubuntu, Triton, or installation into Isaac Sim Python. The pinned upstream ASPIRE checkout remains unmodified.

## Installation

From the repository root in PowerShell:

```powershell
conda create --prefix .local\sam3-python python=3.12 pip -y
& .\.local\sam3-python\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu126
& .\.local\sam3-python\python.exe -m pip install -r requirements\sam3-windows.txt
```

Only create the environment if it does not already exist. It lives under ignored `.local/`. The launcher calls its Python directly, so activation and PowerShell execution of Linux `source` commands are unnecessary.

Request access at [facebook/sam3](https://huggingface.co/facebook/sam3), then authenticate locally:

```powershell
& .\.local\sam3-python\Scripts\hf.exe auth login
```

The normal Hugging Face credential/cache configuration is used; tokens are not stored in source or task JSON. A login does not itself grant approval for gated weights.

## Start in a separate PowerShell terminal

```powershell
.\scripts\start_sam3.ps1
```

Or open a separate terminal from the repository root:

```powershell
$samLauncher = Join-Path (Get-Location) 'scripts\start_sam3.ps1'
Start-Process powershell.exe -WindowStyle Normal -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $samLauncher + '"'))
```

Keep the new terminal open. First startup downloads weights. The launcher offers local authentication when no cached token is available. The server binds to `127.0.0.1:8114` by default and becomes available only after the model loads.

```powershell
Invoke-RestMethod http://127.0.0.1:8114/health
```

The health response identifies the model revision, device, dtype, Transformers/Torch versions, and confidence threshold. CUDA uses FP16; CPU uses FP32. `scripts/start_sam3.ps1 -Device cpu` selects CPU explicitly. Speed and combined simulator memory consumption must be measured on the selected device. There is no automatic switch to CPU after a CUDA error.

## Connect ASPIRE

Set `task.sam3_url` to `http://127.0.0.1:8114` in the chosen configuration, then:

```powershell
& C:\isaac-sim-450\python.bat scripts\aspire.py run `
  --config configs\aspire\pilot-scissor.json `
  --code examples\aspire\visual_pick_place.py `
  --seed 301 --out aspire_runs\windows_sam3_visual_01
```

Use a new output directory each time. This attempts physical manipulation; a healthy model server alone does not establish successful picking.

The service implements ASPIRE's `/segment` text protocol: PNG/JPEG base64 input with `text_prompt`, and masks as base64 raw uint8 at the original image resolution, absolute XYXY boxes, confidence, and labels. `/segment_box` accepts `image_base64` and a source-image XYXY `box`, uses the pinned model's positive visual-exemplar prompt, and returns the same mask schema with label `visual`. It does not use target text or establish target identity. `GET /health` reports `box_prompts: true`. `/segment_point` returns HTTP 501 explicitly; point prompts are not implemented. The supplied `visual_pick_place.py` uses text segmentation only. This backend is an integration adaptation, not a claim of numerical equivalence to upstream SAM3's implementation.

For instruments missed by text recognition, `get_tabletop_candidates(camera=...)` returns class-agnostic connected regions from public metric depth, camera calibration, and fixture table height. A generated policy can identify a candidate by its current visible shape/appearance, pass its mask to `estimate_grasp`, or refine its box with `segment_instrument(camera=..., box=candidate['box'])`. These regions can include robot parts, split occluded tools, or merge touching tools. Neither list order, nearest image location, nor visual-box confidence identifies the requested instrument. No simulator labels or private object coordinates enter these helpers. Changes to an existing experiment's perception must use a new declared campaign; preserve earlier blocked runs.

Inference is serialized. Invalid images return HTTP 400, model failures return HTTP 500, and no detections produce an empty result list. The adapter treats empty results as failure by default; `allow_empty=True` lets a skill try another view. Startup/inference diagnostics are logged to `.local/sam3-server.log`; Uvicorn and download progress also appear in the terminal.

Contract tests use synthetic masks without weights or GPU inference:

```powershell
& .\.local\sam3-python\python.exe -m pytest tests\test_sam3_windows.py -q
```

The implementation follows [Hugging Face SAM3 documentation for Transformers 5.0.0](https://huggingface.co/docs/transformers/v5.0.0/model_doc/sam3). Real-model readiness, mask quality, latency, and physical outcomes must be checked separately.

## Workstation validation on 2026-10-03

The isolated Python 3.12 environment and CUDA Torch 2.8.0/Transformers 5.0.0 were installed. Native SAM3 imports and CUDA detection passed on the RTX 2080 Ti. Three synthetic HTTP contract tests passed, dependency validation reported no broken requirements, and the PowerShell launcher parsed successfully. A separate visible PowerShell terminal was opened for the server.

The initial startup was blocked before model loading: Hugging Face returned HTTP 403 for `facebook/sam3/processor_config.json`. The cached login authenticated as `kennethzhang`, with no token override environment variable; that credential was not authorized for the gated model at the time of the request. A valid login and model-access approval are separate requirements.

After the user obtained model access, the access check passed and the server loaded on native Windows CUDA FP16. The downloaded model revision is `3c879f39826c281e95690f02c7821c4de09afae7`. A real text-segmentation probe on `aspire_runs/smoke_450_05/initial/top.png` found one scissor mask: confidence 0.93457, 218 pixels, approximately 1.03 seconds. The mask and source image were visually inspected and matched the visible scissors. Evidence is retained under `aspire_runs/sam3_windows_probe_01`. This validates a single perception example, not instrument-wide accuracy or physical manipulation. The first server instance reported a null revision in health; source was corrected to resolve the cached model snapshot for subsequent starts.

After approval for the same account, rerun `.\scripts\start_sam3.ps1` in the server terminal. If approval belongs to another account, log in with that approved account locally using the isolated environment's `hf.exe`, then rerun the launcher. Do not send credentials through chat.

Two live ASPIRE development trials followed, using seed 301, the empty tray, and four distractors:

| Evidence directory | Outcome |
| --- | --- |
| `aspire_runs/windows_sam3_visual_01` | Original top-view candidate timed out at its first hover (18.8 mm position error, 5.9 degrees angle error), before grasping; 408 measured actions |
| `aspire_runs/windows_sam3_visual_front_01` | Front-view candidate executed successfully; lift and release verified, placement not verified; 708 measured actions, approximately 108 seconds process wall time |

The initial top image in seed 301 obscured the scissors with the home arm; SAM3 selected a different ringed instrument. Comparing saved front and top RGB-D detections showed that the front view could identify the requested scissors. `examples/aspire/visual_pick_place.py` was updated to use front segmentation and front depth/calibration. No object ground truth was added to the skill and no evaluator thresholds were weakened. The front trial proves one verified physical pick and release, not successful tray placement or reliable performance across seeds. Placement/grasp-offset alignment remains development work. Both trial programs, hashes, sensor evidence, and failures are retained.

Further development added extent-based scissor centering, handle-to-tip direction resolution, and four-camera spatial agreement. The current skill requires at least two camera confirmations and allows missing detections while preserving model/network failures. The first frozen development campaign achieved 1/5 placements; the revised campaign at `aspire_runs/windows_sam3_development_02` achieved **2/5** on seeds 301–305. Seeds 301 and 302 passed the strict placement evaluator; 303 and 305 missed the grasp, and 304 lifted then slipped during transport. All failures remain in the denominator. **36 adapter tests and 4 server/client tests passed**. Held-out seeds and automatic LLM refinement have not been exercised. See [the change report](../ASPIRE.md) for program hashes and detailed evidence.
