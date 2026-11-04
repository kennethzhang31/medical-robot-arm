# Kelly H/A/B Pilot

This is a separate, small zero-shot comparison, not another full ASPIRE campaign.
The completed scissors campaign and its admitted library are not modified.

| Condition | Program source | Kelly practice | Shared source skills |
| --- | --- | --- | --- |
| H | Frozen translated Kelly controller | None | None |
| A | One new model-generated program | None | Empty |
| B | One new model-generated program | None | Three admitted scissors repairs |

H's two private evaluator assertions are deferred to the independent scorer in
a versioned copy. All expert motion/profile/localization code is preserved.
This boundary change is recorded explicitly; H is not the original privileged
controller and does not acquire ASPIRE motion improvements. The API disables
evaluator feedback for all three conditions.

Default: five cases (seeds 601-605), 15 manipulation rollouts total. One initial
motionless sensor capture on seed 501 and one motionless saved-state replay
preflight precede generation, for 17 simulator sessions. The hard session cap
is 20, including failed starts; no automatic retries. Up to six cases may be
declared before any run (18 rollouts plus the two preflight sessions).

A/B receive identical initial RGB images, measured robot state, fixture
calibration, API documentation, model and generation instructions. Only B's
frozen repair-library message differs. Neither receives H code, target-object
outcomes, source programs, raw simulator states, or task-local scissors notes.
Exactly one complete response is accepted per condition, with no correction
request, tool execution, or feedback-driven program revision. Both programs
are frozen before H, A, or B has a manipulation outcome.

Model: `chatgpt1/gpt-6.1-sol`; IGVI provider; SAM3; normal Isaac Sim GUI. The
provider relay preserves cumulative attempted-request accounting from the
completed scissors campaign (96 at setup), with a two-new-request pilot cap
inside the existing authorization of 150. Credentials are never sent to workers.
The runner uses the source campaign's native `/messages` gateway envelope.
One initial chat-route HTTP 400 compatibility rejection occurred before a
model completion. `--recover-transport` can explicitly record this exact
unsupported-parameter failure and permit one replacement transport attempt.
The rejected call stays counted: at most three new attempts (99 cumulative),
still only two generated programs, with no prompt changes, outcome feedback,
or candidate selection. The original plan remains intact; the one-attempt
supplement is auditable in `control/transport_recovery.json`. No general
provider retry or schema-correction loop is enabled.

H captures each measured initial asset state before its program runs. A/B
restore that state after an ordinary reset and must match asset poses,
velocities, and robot joint state to an absolute tolerance of 1e-6 before
execution. Snapshot hashes and private replay diagnostics are recorded.
PhysX contact/solver caches and renderer history are not saved: this establishes
measured initial-state pairing, not identical future trajectories or bitwise
identical images. The motionless replay preflight must pass before generation.

Use the existing independent scorer. Report `lift_verified`, `place_verified`,
`execution_ok`, and joint execution/placement success separately for each case.
The proposed two-second stable-hold/rotation contract is not implemented here.
Infrastructure failures stop the pilot rather than becoming hidden retries.
Before any model request or manipulation, `--stage observe --retry-preflight`
may explicitly retry a failed motionless replay after an infrastructure repair.
The old result remains intact, the repair/retry is recorded under `control/`,
and failed sessions still count toward 20. No evaluation or generation retries
are enabled by this flag.
An interrupted provider attempt requires offline reconciliation; the runner
does not resend an interrupted request. Preserved final trial outcomes are
reused on resume without re-execution or reselection.

```powershell
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/kelly_hab_20261007 --stage prepare
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/kelly_hab_20261007 --stage observe
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/kelly_hab_20261007 --stage generate
& C:/isaac-sim-450/python.bat scripts/run_kelly_comparison.py --out logs/kelly_hab_20261007 --stage evaluate
```

`--stage run` combines generation and evaluation. Preparation performs no
model requests or simulator sessions. Read `state.json`, `report.json`, and
`provider_*/report.json` for live progress. `plan.json`, `setup_hashes.json`,
`baseline_provenance.json`, `programs/*/library.json`, and
`frozen_programs.json` define the auditable comparison boundary. This is one
engineering pilot, not sufficient evidence for a broad transfer claim.
