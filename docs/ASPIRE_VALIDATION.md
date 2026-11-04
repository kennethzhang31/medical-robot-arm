# ASPIRE adapter validation on Isaac Sim 4.5

Validated on 2026-10-01 using `C:\isaac-sim-450\python.bat`, IsaacLab v2.1.1, and an RTX 2080 Ti. ASPIRE is pinned at `f4c8939aab0af9b97690c561bd80e282940f7886`; IsaacLab source is pinned at `90b79bb2d44feb8d833f260f2bf37da3487180ba`.

| Check | Result |
| --- | --- |
| Dependency and asset preflight | Passed |
| Adapter contract tests, without Kit | 30 passed |
| Scissor target, seed 101, empty tray, four other instruments | Live motor smoke passed; 84 measured actions |
| Scalpel type 2 target, seed 102, four preloaded tray lanes | Live motor smoke passed; preloads preserved across 84 actions |
| Same full-tray case with two extra table distractors | Reset rejected by the stationary-object gate; retained as a failed trial |
| Vision-based physical pick/place | Not yet validated; requires visual mask/perception service and skill development |
| Remote LLM refinement / live SAM3 service | Not exercised; no provider credentials or model service configured |

The successful smoke checks cover scene creation, geometry-aware reset, settling, six calibrated RGB-D streams, measured TCP convergence, finger encoder gates, and artifact capture. Initial top/front/wrist images were visually reviewed. Both smoke trials correctly report `execution_ok: true` and `success: false`, because the program performs no pick/place.

The extra-clutter trial reached the bounded 750-step reset limit. `clutter_00` reported approximately 3.58 mm/s, exceeding the unchanged 3 mm/s gate. The adapter rejected the trial and saved sensor images and private diagnostics. Four canonical distractors remain the validated starting configuration; dense-clutter reliability needs additional development trials.

Two runtime issues were resolved during integration: Kit startup required the recorder's FXAA setting before shader initialization, and three USD crate 0.10 wrappers required text equivalents for the 4.5 reader. Reset also seats each measured thin body axis flat before settling, rather than caching an upright pre-settle pose. Original USD assets are unchanged.

Local evidence is under `aspire_runs/smoke_450_05`, `aspire_runs/full_tray_450_01`, and `aspire_runs/populated_450_01`. Those generated directories are ignored by Git. CPU tests additionally verify metric backprojection, frame transforms, grasp finger-axis alignment, Gym observation shapes, independent success/failure checks, bounded controls, upstream execution and traceback capture, episode namespace reset, seed partition separation, frozen evaluation programs, credential isolation, and failure preservation.

## Native Windows follow-up, 2026-10-03

SAM3 now runs on native Windows CUDA FP16 through the Transformers server at `http://127.0.0.1:8114`. Weights revision: `3c879f39826c281e95690f02c7821c4de09afae7`. The current checks pass **36 adapter tests and 4 server/client contract tests**. The server tests use synthetic masks, separately from live inference and physics trials.

Development seed 301 achieved verified lift, release, supported stationary placement, full footprint containment, 7.98 mm center error, and 0.73-degree directed-axis error. The earlier post-success motor exception was corrected without relaxing evaluation gates. The first frozen five-seed development campaign (`windows_sam3_development_01`) finished at **1/5 verified placements**; missing detections and wrong-object selection remained failures. Subsequent development uses four-camera agreement and an opt-in empty-detection fallback. See [the change report](../ASPIRE.md) for the latest campaign results. Reserved seeds 401–405 remain unused, and automatic LLM refinement and baseline comparisons have not run.

## Qwen refinement validation, 2026-10-04

Automatic refinement now ran through the NTHU LiteLLM alias `pro6000/qwen38-flash-next`, authenticated with the local `.env` credential. A synthetic image probe returned the correct color. The bounded pilot completed 15 development trials across the initial skill and two valid model revisions: **2/5, 2/5, and 0/5**, respectively. The original skill remains selected; no improvement is claimed. Two additional truncated provider responses were rejected before execution. The provider pipeline's empty/truncated-response, image transport, reasoning-effort, usage, and private-feedback checks passed as part of **41 adapter tests**.

Detailed retained evidence is in `aspire_runs/qwen_development_03/pilot_summary.json`, with the baseline trials in `qwen_development_01` and the rejected retry in `qwen_development_02`. Revision requests reported 39,658 tokens in total, including truncations; currency cost is unknown. Generated semantic mistakes in mask/RGB access prevented intended grasp/hold changes. Public API documentation now gives explicit access examples. Held-out seeds remain unused and expert/DP comparisons remain unimplemented.
