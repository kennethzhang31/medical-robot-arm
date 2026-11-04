# ASPIRE with the existing RF-DETR detector

The surgical and scissor-pilot configurations now select `perception_backend:
"rfdetr"`. ASPIRE uses the same five-class detector and checkpoint format as
the standalone training pipeline. Camera observations, robot motion helpers,
multi-view confirmation, evaluator, and development/evaluation partitions are
shared with the existing ASPIRE workflow.

## Start the detector

Use a checkpoint trained on this repo's exported instrument dataset. Generic
COCO weights are not a substitute: the server checks that the checkpoint class
names and order match `scalpel`, `scissor`, `love_retractor`, `kelly`,
`scalpel_type2`. Select the model size used during training.

```powershell
# If the isolated detector environment does not already exist:
.\RUNME.ps1 -Mode rfdetr-setup
# Add the HTTP server dependencies in that environment:
& .\.venv-rfdetr\Scripts\python.exe -m pip install -r requirements\aspire-rfdetr.txt
.\scripts\start_rfdetr.ps1 -Checkpoint '<RFDETR_RUN>\checkpoint_best_total.pth' -Model small
```

The server uses port 8115 by default. `GET /health` reports the model variant,
class order, confidence threshold, package version, and checkpoint SHA256.
`POST /detect` accepts base64 PNG RGB and returns source-resolution XYXY boxes,
scores and instrument labels. Keep this service outside Isaac Sim's Python
environment. `-Device cpu`, `-Port`, and `-Threshold` override defaults.

In another terminal, run a development trial:

```powershell
& C:\isaac-sim-450\python.bat scripts\aspire.py run `
  --config configs\aspire\pilot-scissor.json `
  --code examples\aspire\visual_pick_place.py --seed 301 `
  --out aspire_runs\rfdetr_visual_dev_01
```

The existing `scripts/refine_aspire.ps1` also uses this pilot configuration and
therefore now requires the RF-DETR service. Start with a frozen development
trial before spending provider tokens on refinement.

## Boxes and depth for grasping

`segment_instrument` keeps the existing program interface. With RF-DETR it
filters detections by the requested trained class and returns a boolean region
formed from measured depth inside each box, between 0.5 mm and 45 mm above the
calibrated table. The returned `mask_source` is `box_depth_foreground`.
This is **not a learned segmentation mask** and does not use simulator object
poses or semantic labels.

Boxes that intersect another detected instrument are excluded. Missing or
unusable candidates allow the visual skill to try another camera; transport
and detector failures stop the trial. The example still requires agreement
from two cameras and enough shape information to resolve scissors' handle and
blade direction. Undetected clutter inside a box can contaminate depth regions;
occlusion, thin geometry, depth noise and similar tools remain failure modes.
Tray regions need different foreground logic; this table-height helper is
intended for the initial table pick.

These contract tests establish interface and geometry behavior, not detection
accuracy or manipulation success. A trained checkpoint, live image checks and
development rollouts are required before reporting performance.

## Optional SAM3 backend

To reproduce earlier SAM3 trials, copy the configuration and explicitly set
`task.perception_backend` to `"sam3"` and `task.sam3_url` to the SAM3 service URL
(usually `http://127.0.0.1:8114`). SAM3 supports text/point prompts according to
the selected server; RF-DETR accepts only the five trained class names and no
point prompts. Old configurations without `perception_backend` now default to
RF-DETR and must select SAM3 explicitly when reusing that service.
