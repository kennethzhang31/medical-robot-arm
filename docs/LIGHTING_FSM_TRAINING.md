# P4 lighting / FSM revision — 2026-09-14

Current material tuning is documented in [Simulation material realism](SIMULATION_REALISM.md).
The material-preservation notes below describe the earlier lighting revision.

## Implemented, P4 only

`scene_layout.json` owns lighting and the FSM feature switch. All five backend
entrypoints receive the same P4 runtime hooks. P3 files and instrument materials,
physics, grasp offsets/yaw, success criteria, stage IDs, camera dimensions and H5
schema are unchanged. Backup: `archive/before_lighting_fsm_20260914`.

| Shared light | Before | Current candidate |
|---|---:|---:|
| Ambient | 1800 | 1000 |
| Key | 45000 | 18000 |
| Fill | 22000 | 8800 |

These are renderer intensity parameters, not calibrated room lux measurements.
Imported hospital lights remain unchanged. No global Isaac preferences changed.
Keep metallic appearance: first reduce illumination, then inspect actual saved
camera crops. Roughness controls highlight spread, not simply overall brightness.
Only adjust roughness later if an asset's finish is demonstrably wrong; do not
turn real steel into plastic just to make recognition easier.

Read-only source-material audit found an additional issue: `my_scissor_clean.usd`
has a mesh with no bound material or authored displayColor; love retractor's
bound shader has metallic=0, roughness=1. In contrast scalpel has metallic=1
and roughness about0.24-0.31; Kelly/type2 metal is about0.83 and roughness0.26.
Thus a white instrument is not automatically a metallic highlight. The shared
asset configuration now supplies the scissor with a visual-only brushed-steel
fallback (`diffuse=(0.48, 0.50, 0.52)`, `metallic=0.78`, `roughness=0.36`).
It applies to the target, base object, and duplicate table distractors because
they all use the same `rigid_cfg` factory. Existing authored material bindings
on the other four instruments are preserved. The fallback does not alter mesh,
scale, collision, mass, semantic class, instance masks, or grasp behavior.

### Motion candidate (DISABLED by default after a release failure)

| Stage family | Change |
|---|---|
| Smooth CLOSE | 32 -> 24 steps, remove initial repeated-open commands |
| Smooth OPEN | 24 -> 18 steps, remove initial repeated-closed commands |
| Constant CLOSE (object-specific branch) | unchanged, normally 32 steps |
| LOWER_PRE / LOWER_GRASP / LOWER_PLACE | original limits, target tolerances and stall tests retained |
| HOVER / LIFT_CLEAR / MOVE_TO_TARGET / RETREAT | original interpolation, early-stop and limits retained |
| Type-2 transfer | original special 16-step interpolation retained |

The new smooth ramp is exactly the tail of the old command sequence; its slope
and endpoint are unchanged. Removing the initial wait can still affect grip
success, so it requires multi-seed physical validation before a production run.
Set `fsm.remove_smooth_grip_initial_idle=false` to restore the original ramp.
No micro-lift or hold-after-close has been reintroduced.

The active setting is now **false**: original32-step smooth close and24-step
smooth open are retained. One reduced-ramp trial passed; a second picked and
transferred successfully but failed release (object followed retreat). That
does not isolate the cause, so shorter ramps are not approved for production.

Legacy camera sample collection repeatedly traversed the entire USD stage to
hide debug markers during the same sample. P4 now performs that cleanup once
per sample, not once for each alias/append. Calls outside collection still run
normally, and every subsequent sample gets a fresh scan. No camera streams or
physics steps are dropped. `observation_collection_wall_s` measures collection
time separately from the whole stage.

`stage_metrics.jsonl` is append-only per output folder. It includes stage name,
actual samples, control_dt_s, simulation_s, wall_s, final EE position error,
orientation error, and exceptions. It includes failed attempts too. A
REVIEW_STALL_OR_TIMEOUT flag means position is outside the requested tolerance;
it does NOT distinguish collision/contact from timeout or prove grasp failure.
Original object-specific lift/placement checks still decide success. These
stage metrics do not include startup, settling or H5 compression: inspect the
run metrics/log for those. Stage simulation duration = steps * env.step_dt,
not wall-clock runtime. No claim that all five objects should take equal time.

## Training guidance (not a new trainer implementation)

1. **Detection:** use recorded RGB as input, canonical semantic masks as labels.
   Convert visible per-class mask extents to 2D boxes if the selected detector
   needs boxes. Background/robot/tray are not instrument classes. Remap semantic
   IDs 3..7 to contiguous detector class IDs 0..4 and record that mapping.
   One class mask cannot separate two same-class instances; add instance labels
   before supporting multiple copies. Empty masks mean not visible in that view,
   not necessarily absent from the whole scene. Crop-edge objects are truncated.
2. **DP:** RGB + measured robot proprioception + requested object/skill condition
   -> sequence of absolute robot-base actions (xyz, quaternion wxyz, gripper).
   Keep saved224x224 input, normalization, camera calibration and control period
   identical during inference. Depth can stay recorded without being fed in.
   Exclude simulator object/tray pose and perfect semantic masks from inference
   inputs. Simulator GT is legitimate for expert generation and training labels.
3. **One checkpoint:** a shared visual encoder with optional recognition/mask
   auxiliary head and diffusion action head is a possible custom architecture.
   Standard DP is visual action learning, not automatically an explicit detector.
   This revision does not implement or train those heads.
4. **Closed loop:** predict an action chunk, execute only part, read fresh RGB and
   robot state, replan. Select observation/action horizons by validation at the
   actual control period, not by borrowing a paper's step count blindly.
5. **Coverage:** include approach from varied robot starts if inference must find
   the instrument from those starts. Hover-only data cannot establish that skill.
   A bbox center is not a verified grasp point for scissors or bent retractors.
6. **Splits / diversity:** split by episode/seed, not adjacent frames. Validate
   new object positions/yaws and lighting conditions separately. Later add modest
   per-episode lighting variation (not frame flicker), occlusions, and absent
   target cases for recognition. Do not enable large randomization before base
   renderer/physics is reliable. Balance object/skill sampling; do not flood
   detection training with almost identical stationary video frames.

There is no universal best stage-step count or guarantee of successful training.
Compare multiple seeds per object, first-attempt success, failure categories,
grasp retention, place error, RGB visibility and elapsed time per saved success.
Do not optimize only the shortest successful episode.

## References

- Diffusion Policy authors: visual conditioning and receding-horizon action
  sequence control, not a guaranteed perception detector:
  https://diffusion-policy.cs.columbia.edu/
- NVIDIA OmniPBR reflectivity: metallic, roughness and specular material behavior:
  https://docs.omniverse.nvidia.com/materials-and-rendering/latest/templates/parameters/OmniPBR_Reflectivity.html
- NVIDIA lighting properties:
  https://docs.omniverse.nvidia.com/materials-and-rendering/latest/lighting.html
- NVIDIA Isaac Sim synthetic object data: RGB, segmentation and bounding-box
  annotations with scene randomization:
  https://docs.isaacsim.omniverse.nvidia.com/5.0.0/action_and_event_data_generation/tutorial_replicator_object.html

Numerical light levels and step adjustments above are project engineering
choices, not values prescribed by those papers/documentation.

## Commands

```powershell
cd C:\IsaacLab\scripts\custom\i4h_project\p4
.\scripts\launchers\view_env.ps1 -Cameras
# One episode per object, GUI and the runner's default GIF outputs:
.\scripts\launchers\run_all_v2_test.ps1 -Episodes 1 -Gui
# Read-only same-pose old/current light comparison:
C:\IsaacLab\_isaac_sim\python.bat .\scripts\p4.py tool preview_env --headless --frames 5 --lighting-compare --capture-dir .\debug\validation\lighting_compare
```

The main viewport is not the recording crop. Inspect the six224x224 sensor
panels. Whole-frame constant white/black RGB can be a renderer readiness issue,
which is different from localized metallic glare. The normal recorder's RGB
readiness guard remains enabled; preview-only diagnostics may warn and continue.

## Validation so far

- CPU contract tests pass for all5 backend bindings, exact ramp tails, unchanged
  dynamic/constant-close functions, and once-per-sample cleanup.
- Migration audit passes: P3 hashes unchanged, copied backend files unchanged
  except the original asset-path migration; P4 wraps them at runtime.
- First bounded scalpel physical diagnostic with reduced lighting/ramp passed:
  240steps, 4.80simulationseconds at50Hz, tray XY error2.27mm, all6RGB ready.
  This run preceded the once-per-sample cleanup optimization.
- This is not a production H5 validation or a multi-seed five-object benchmark.
- Second diagnostic with cleanup optimization:279steps; pick/transfer passed,
  release failed, final object Z0.2208m. No training episode saved. Candidate
  ramp shortening was disabled afterward; cleanup optimization remains active.
  Observation cleanup reduced observed per-step time from about0.99s to0.50s
  on these runs, but these were not matched-seed performance benchmarks.
- Final lighting-only same-pose A/B completed with RGB ready and six224x224
  crops, in `validation/lighting_comparison`. Mean RGB intensity fell in all6
  views; tray126.3->104.5 and top169.5->142.3. Whole-crop near-white pixels
  (all RGB channels>=245) fell, but include the white robot and are NOT a
  measurement of instrument-only glare or recognition accuracy. Material
  deficiencies remain. `old_lighting_*.png` is the former light configuration;
  `baseline_*.png` is the active reduced-light configuration.
- Both motion tests were preview diagnostics, not saved training episodes.
  Final active original-grip timing was checked structurally for all5 backends;
  no full five-object physical regression has been run after this revision.
