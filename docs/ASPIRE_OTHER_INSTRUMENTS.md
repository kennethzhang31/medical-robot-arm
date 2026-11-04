# ASPIRE On Other Instruments

The first new campaign targets the Love retractor. It launched on October 18,
2026 at 18:06 Asia/Taipei in `logs/aspire_love_retractor_visual_20261018/` with
`configs/aspire/full-love-retractor-visual-sam3.json`. The completed scissors,
Kelly, and scalpel records remain separate historical evidence.

## Perception Changes

The pinned SAM3 model returned empty text masks for Love retractor and Kelly
prompts. The word `knife` sometimes recovered a scalpel, but covered only one
view and could not distinguish the two scalpel types. Lower thresholds,
overlapping crops, and FP32 did not resolve the previous coverage failures.

The service now exposes the installed model's visual box prompting through
`POST /segment_box`. `Sam3Client.segment` and the public
`segment_instrument(..., box=...)` API accept source-image XYXY boxes without
requiring a target text label. Model revision, FP16, and threshold 0.5 remain
unchanged. Existing saved scissors text masks were identical after restart.

`get_tabletop_candidates(camera=...)` provides an additional public sensor
primitive. It projects depth using camera calibration and the fixed table
height, then returns connected foreground regions with boxes, masks, measured
centers, and spans. It does not use instrument identities or private poses.
The generated program still has to recognize the requested target from its
appearance or shape and choose a valid grasp. Trace summaries include candidate
geometry and overlays without serializing full masks into text.

Candidates can include robot fingers, merge nearby instruments, or split an
occluded instrument. Visual box prompts can return masks of multiple similar
objects. Neither path establishes autonomous identity accuracy by itself.

## Calibration Evidence

Audit root: `logs/other_instruments_20261018/`.

- `saved_screen/`: fixed text-prompt audit on two prior scenes, with input hashes.
- `box_screen/`: depth and visual-box audit on the same saved observations.
- `fresh/`: three predetermined, motionless Love retractor scenes, seeds 1101-1103.
- `fresh_box_screen/`: candidate masks and visually inspected contact sheets.
- `perception_gate.json`: availability gate passed with target regions in 4, 3,
  and 3 views; minimum requirement was two distinct views per scene.
- `fresh_cross_view_diagnostics.json`: closest depth-center pairs agreed within
  about 2 mm in each scene; this is an offline root-proximity diagnostic proxy.

These checks used three simulator starts, zero manipulation trials, and zero
model requests. Private scene roots were used only to diagnose coverage and
were not supplied to the policy. There is no pixel-level ground-truth score or
autonomous target-selection score. Preflight scenes calibrate availability;
they are separate from development and final evaluation seeds.

## Campaign Protocol

Development uses seeds 1201-1225; final evaluation uses seeds 1301-1320.
The full workflow uses K=8, T=3, 448-pixel cameras, four distractors, an empty
tray, a 2400-step limit, and 32 position / 8 velocity solver iterations.
Private evaluator feedback is disabled for policy execution.

Five shared SAM3 skill records are frozen in the campaign's
`inherited_skills.json`. Some records overlap. This run measures adaptation
with inherited repairs, rather than zero-shot transfer or an H/A/B comparison.
The previous scissors result (18/20 repeated evaluation) is not evidence of
Love retractor manipulation success.

The model is `chatgpt1/gpt-6.1-sol` at the user-selected endpoint
`https://llm.igvi.cs.nthu.edu.tw/v1`. The supervisor owns credentials; simulator
workers use the local relay. The launch carries 108 previous attempts and allows
42 new attempts, with an initial cumulative cap of 150. On October 18 at 18:22
Asia/Taipei, the user raised the cumulative cap to **300**, allowing up to 192
attempts in this campaign including those already used. A background helper
waits for clean exhaustion of the current supervisor's original cap, then uses
the standard continuation launcher with cap 300. It preserves cached model
responses and completed trials, and refuses automatic continuation for other
errors or pending provider calls. Authorization and helper state are saved as
`budget_authorization_300.json` and `budget_continuation.json` in the campaign.
The full search may reach the cap before completion; failures and partial
responses still count as attempts.

Only one simulator runs at a time on the 11 GB GPU. Kelly and both scalpels
have promising class-agnostic regions in saved images but still need their own
fresh-scene selection and manipulation validation.

## Validation And Tracking

The main ASPIRE regression suite passed 142 tests. The subsequent focused
execution/tracing integration check passed with 2 tests and 141 deselected.
SAM3 wire, visual-box validation, and depth-component tests passed 11 tests.
Implementation/config hashes are recorded in
`logs/other_instruments_20261018/implementation_sha256.json`.

```powershell
python scripts/status_full_aspire.py logs/aspire_love_retractor_visual_20261018
```

Read the campaign's `state.json`, `supervisor.json`, provider ledgers, and
trial results for live progress. Launch stdout/stderr and helper PID are under
`logs/other_instruments_20261018/love_campaign.*.log` and `love_launch.json`.
No manipulation success rate exists at launch.
