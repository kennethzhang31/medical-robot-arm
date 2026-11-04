# ASPIRE surgical environment binding

This file binds the unmodified pinned ASPIRE Fix Loop and Evolutionary Search
runbooks to the user's surgical Isaac Sim repository. The original runbooks and
their skill references are supplied verbatim as separate messages and archived
with SHA-256 hashes. Their experiment procedure applies with the explicit
environment substitutions below. This is a port, not a Robosuite paper reproduction.

- Task, model, seed partitions and evaluation count are specified by the active
  campaign plan and launch record. Scissors was the initial source task; other
  instruments use their own fresh campaign. Use the active target, never assume scissors.
- Windows, Isaac Sim 4.5, surgical RGB-D perception and Cartesian control replace
  Linux, MuJoCo, Robosuite cameras, GraspNet, PyRoKi and Molmo. The supplied
  surgical API documentation is authoritative for signatures and units.
  Do not call Robosuite-only tools or copy their hardcoded geometry.
  The active perception binding appended to this document specifies the actual
  backend and its supported queries. Follow that binding; do not assume SAM3.
- The initial source used development seeds 101-125 and held-out seeds 1-100.
  Follow the active plan's disjoint seed partitions and declared evaluation count.
  Held-out evidence is inaccessible during program generation
  and repair. Do not encode seeds, snapshot coordinates, mask ordering or
  evaluator internals into a program.
- Stage 0: observe once, then up to five incremental, from-reset exploration
  programs. Each is chosen only after observing the previous execution. A
  motionless observation bootstrap supplies the initial scene and API docs.
- Fix Loop: replay the initial standalone program on all 25 development seeds;
  allow up to five complete repair sweeps, stopping earlier at 25 successes.
  The coordinator selects the best fully evaluated fix, preserving regressions
  and failures. No external hand-authored manipulation baseline is used.
- Evolutionary Search: K=8 separately executed candidates per round, T=3 maximum
  complete rounds. First-round A is a verbatim copy of the selected Fix Loop
  program. B–H are distinct mechanistic hypotheses. Later rounds use the top
  three development survivors and include a structurally novel candidate.
  All candidates run on the same 25 development seeds. No plateau stop.
- The host runs one simulator at a time, records every trial, and supplies
  stdout, stderr, public API traces and actor-selected sensor keyframes. It retains RGB-D arrays, calibration and motion
  frame sequences locally. No simulator XML, URDF, meshes, private geometry
  or credentials enter model context. Held-out evidence is locked until the
  post-evaluation findings phase, which cannot generate programs.
- Use only the documented surgical functions, numpy and math. Runtime reward
  queries are unavailable. Verify grasps using observed movement, RGB-D and
  robot state. Trial success is reported by an independent evaluator afterward.
- Use `inspect_evidence` to choose development replay summaries, slices of the
  primitive trace, and specific sensor images. Summaries list available images.
  Each primitive records before/after views, return values and available overlays.
  Use `submit_practice` to deliver standalone Python programs for the current
  exploration, repair or search stage; the host executes them and returns evidence.
  This native tool-loop actor replaces Claude Code CLI shell/file access. The
  upstream prompts stay verbatim; this document specifies only the surgical port.
- Read the inherited shared skill snapshot and task-local working memory before
  generation. Task notes and partially successful programs are working memory,
  not shared validated skills. Actors propose findings; only the coordinator
  can admit skills. Cite actual failed and successful debugging replays.
- Select the best program by development score (simplicity breaks ties), freeze
  its source, and run that one program once on each declared held-out seed.
  No candidate selection or repairs use held-out results. If all debug programs
  fail, mark the task unsolved and skip held-out trials (Appendix E.4).
- After evaluation, extract structured findings as in Algorithm 1 and Appendix E.1.
  Only this no-program-generation phase can inspect held-out evidence to qualify
  findings. Candidate skills include failure signature, applicability, repair,
  representative code and limitations. A separate coordinator reviews findings
  for reusability and API compliance; host checks require a cited failed-to-
  successful debugging replay with changed code on the same seed. Rejected or
  unverified observations remain in task findings. Shared skills are snapshotted
  when a future actor starts; transferring them has not yet been evaluated.

Keep diagnoses concise and evidence-based. Preserve physical task criteria.
The user retained K=8 and T=3, but removed the 6/4/10 split. Use the paper's
25-debug/100-held-out schedule unless the active plan declares a reduced evaluation,
and up to five Fix Loop repairs. Full video is
not sent to the actor; use per-primitive keyframes and traces (section 2.1). Do not claim video-model inference, tool fine-tuning, real-robot
transfer, or outcomes on untested instruments have occurred.
