# ASPIRE method audit - 2026-10-05

Authority: user-supplied 2607.00272v1.pdf, sections 2.1-2.3, Algorithm 1,
section 3.3 and Appendix E.1/E.4. Extracted text is retained under
logs/aspire_setup_paper_20261005/paper.txt.

The user removed the 6/4/10 pilot split. Active SAM3 configuration uses the
Robosuite schedule: 25 debugging seeds (101-125), 100 held-out seeds (1-100).
K=8 and T=3 remain user overrides. Surgical Isaac Sim is a new domain,
not a reproduction of the paper's benchmark scores.

| Paper requirement | Implementation |
| --- | --- |
| Actor chooses primitive evidence, section 2.1 | inspect_evidence exposes trace slices and selected sensor images in a multi-turn tool conversation. |
| Before/after evidence, section 2.1 | Three camera views before/after every API call, upstream perception overlays, inputs, outputs, errors and timing. |
| Validated shared repairs, section 2.2 / E.1 | Actor reports structured findings; separate coordinator context audits reusability and API compliance. Host verifies changed-code failure/success replays on the same debug seed. |
| Evolutionary history, section 2.3 | K candidates per complete generation; top-three parents and all search history available for inspection; stop at success or T rounds, not plateau. |
| Algorithm 1 lines 16-18 | Select on debugging results, freeze program, evaluate once on held-out seeds, then extract/review patterns. |
| Held-out lockout, section 3.3 | No held-out evidence during generation/repair. Findings may inspect it after evaluation; this phase accepts no programs. |
| All attempts fail, E.4 | Save unsolved findings, skip held-out rollout and admit no skills. |

Explicit implementation substitutions and evidence limits:

- Native Opus tool-loop actor and separate coordinator review replace Claude Code
  CLI. Gateway 1M context support is unverified; 128000 is an output ceiling.
- Surgical RGB-D/SAM3 and Cartesian control replace Robosuite's robot, grasp
  and planning APIs. SAM3 point prompts are unavailable.
- Seed resets do not prove bitwise-identical physical state snapshots.
- Admission establishes debugging evidence and coordinator judgment, not
  demonstrated cross-task transfer. Transfer and ablations have not run.
- Fake-physics/model tests check the protocol; actual manipulation success
  must be established by simulator outcomes.

Old campaigns are preserved and cannot be resumed under protocol v3.
Original upstream prompts remain unchanged. The separate surgical binding
records environment and tool substitutions. Admitted repairs persist under
logs/aspire_shared_skills/sam3 with evidence and transfer status. Local notes
and partially successful whole programs are not labeled validated skills.
