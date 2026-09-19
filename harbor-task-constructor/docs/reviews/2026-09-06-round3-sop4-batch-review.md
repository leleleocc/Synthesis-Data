# Round 3 SOP4 resumed batch review

Evidence root: `jobs/production-construction-round3-sop4-resumed-20260905/`.

This review uses each outer `result.json`, outer-verifier `gap.json`, the constructor
trajectory, retained `round-NNNN` evidence, and `resume.md`. Scores below are accepted
only when the outer parser found a readable two-arm round whose task digest matches the
final task. Notes are used to explain a raw result, not to replace it.

## Outcome

- 21/21 outer jobs reached a terminal state.
- 12/21 ended with an outer exception: 4 Daytona startup S3 failures, 7 upstream/API
  interruptions, and 1 eight-hour constructor timeout.
- 7/21 ended with a readable, comparable latest round.
- 3/21 cleared both construction gates: `26117e32`, `87d51bdf`, and `a3e92222`.
- Among the 9 jobs that exited without an outer exception, 5 still left an invalid
  latest state: `453cbac9`, `7d289736`, `84204b2d`, `8a9ab226`, and `95713311`.

| Task | Latest comparable reading | Result |
| --- | --- | --- |
| `26117e32` | target `0.5040`, solver `0.8862`, R `0.7582` | clears |
| `387bef85` | target `0.8696`, solver `0.7826`, R `-0.1000` | reverse gap |
| `49bb6e22` | target `0.9734`, solver `0.9945`, R `0.0218` | saturated |
| `87d51bdf` | target `0.6424`, solver `1.0000`, R `0.5567` | clears |
| `8818d381` | target `1.0000`, solver `1.0000`, R `0` | saturated |
| `a3e92222` | target `0.2671`, solver `0.7843`, R `1.9358` | clears |
| `c43673d3` | target `1.0000`, solver `1.0000`, R `0` | saturated |

Invalid latest states split into: three final-task digest mismatches (`453cbac9`,
`667b8927`, `95713311`), one mixed-digest round (`7d289736`), four allocated or
otherwise unreadable latest rounds (`84204b2d`, `8a9ab226`, `ade66e4d`, `b4f12661`),
one round with no qualifying job config (`52efdaea`), one job with no numbered round
(`22ca05d3`), and the four startup failures.

## Did the agents use the SOP?

Yes at discovery time, but not reliably at lifecycle boundaries.

All 17 jobs that produced an agent trajectory read `/app/method/sop.md`, read
`/app/build/evidence/resume.md`, and invoked `run-two-models.sh --help`. The verifier
quadrant and light-loop guidance visibly influenced the successful work in `26117e32`,
`87d51bdf`, and the defect-falsification work in `c43673d3`.

The weak point was closing the loop:

- `453cbac9` made a tests-only fix after round 2, then voluntarily returned a handoff
  with regrade still listed as the next action. Its final task therefore did not match
  the last round.
- `84204b2d` and `8a9ab226` returned while a detached fresh round was still in flight.
  Their latest round had no resolved model and was not deliverable.
- `7d289736` left target and solver locks with different task digests.
- `95713311` honestly retracted an invented round-5 score and several invented checks,
  but still exited with an unverified, modified task. The parser correctly rejected it.
- `ade66e4d` had a valid round-7 numerical gap, opened round 8 to remove a demonstrated
  scaffolding confound, and then hit the outer eight-hour limit before round 8 became
  readable. Continuing was substantively defensible; starting a round without enough
  remaining lifecycle budget was not.

Several empty or corrupted tool-channel episodes were genuine infrastructure failures:
`387bef85`, `7d289736`, `84204b2d`, and `8a9ab226` explicitly probed the channel and
stopped rather than continue blind. SOP wording cannot restore those tools, but a disk
parser gate can prevent inferred state from being treated as evidence.

No constructor used a subagent: 0 subagent calls in 17 readable trajectories, although
the tool was available and the SOP mentioned it. This is evidence that the current
preamble is not an effective trigger. It is not evidence by itself that subagents would
have improved scores.

## Regrade audit

Regrade was useful. Four tasks produced six complete regrade rounds:

| Task | Regrade effect | Value |
| --- | --- | --- |
| `26117e32` | round 3 `0.3089 / 0.7886` -> round 4 `0.5040 / 0.8862` | removed a command-line gate that falsely controlled the scale suite, retained a real gap without rerunning agents |
| `87d51bdf` | round 2 `0.6978 / 0.6978` -> round 3 `0.6978 / 1.0` -> round 4 `0.6424 / 1.0` | two fast verifier-only iterations turned an undifferentiated real rollout into a valid final verifier |
| `c43673d3` | rounds 4 and 6 both ended at `1.0 / 1.0` after fixing false negatives | cheaply proved that the repaired criteria were not a real separation axis |
| `ade66e4d` | round 4 regraded an otherwise unusable round-3 rollout to `0 / 0.9277` | recovered diagnostic signal from existing workspaces, although the task later moved to fresh rounds |

`a3e92222` also exercised the preflight. It first received the actionable requirement
for `[verifier].environment_mode = "separate"`, then the actionable error that no
`rollout.lock` source existed. It correctly moved to a fresh rollout instead of silently
falling back.

The pre-fix cross-life packer conflicted with this mechanism. Regrade rounds deliberately
do not contain `rollout.lock`; repeated regrades reuse the latest real rollout. It had
retained only the numerically greatest round. For example,
`26117e32` needs real round 3 to regrade again while final round 4 is a regrade, and
`87d51bdf` needs real round 2 while rounds 3 and 4 are regrades. Packing only round 4
removes the proven regrade source. The packer now retains the latest formal round plus
the latest real-rollout round when they differ and records both roles. It does not
permit regrade chaining or parser fallback.

## Minimal SOP changes supported by this batch

Keep the six-step structure, the verifier quadrant, the `tests/**`/`solution/**` light
loop, the <=50 criterion cap, and the current timeout. The batch validates those choices.
Do not add more construction heuristics to the main SOP.

Make only these lifecycle rules more executable:

1. A fresh/regrade command is synchronous. If the tool backgrounds it, poll that exact
   process/session until exit. Do not return, modify `task/`, or launch another round
   while it is active.
2. Admit another round only for one reproduced scoring defect or one named capability
   axis supported by criterion evidence and a targeted mutation/probe, with enough
   remaining time to modify, run poles, complete the round, parse it, and hand off.
   Otherwise preserve the latest valid state.
3. Before the final response, run the existing parser against `--last` and
   `--final-task`, require matching digest and valid two-arm means, and confirm that no
   nested runner remains active. Empty, corrupted, inferred, or remembered output is
   not evidence.
4. Move the existing subagent sentence from the preamble into Step 4 and make the
   trigger concrete: when target/solver trials or two independent criterion clusters
   must be inspected, delegate read-only analysis and receive only findings plus paths.
   This should replace text, not lengthen the SOP.

The already-approved
`docs/superpowers/specs/2026-09-04-minimal-construction-lifecycle-clarification-design.md`
implements items 1-3 without a new state machine. This batch strengthens its evidence.
The subagent relocation is lower priority and should be tested separately.

## Next-run recommendations

1. Do not rerun the three cleared tasks. Requeue the other 18.
2. Retry the four Daytona startup failures from their last usable build, but stagger
   sandbox creation. All four failed in the first synchronized four-slot wave with the
   same S3 PUT failure; this supports a startup-burst hypothesis, not a task/SOP cause.
3. Route readable saturated/reverse tasks by evidence: repair reverse/false-negative
   verifier behavior first; if both arms remain saturated after regrade, stop regrading
   that surface and use one new independently scored capability axis plus a fresh run.
4. For digest-mismatched or in-flight tasks, close or discard the invalid latest state
   before any design edit. Do not let the highest directory number alone decide what is
   reusable.
5. Use the corrected seed packer for the next cross-life regrade. It retains at most
   two full rounds: the latest formal round and, only when different, the latest real
   rollout source; `seed-packaging.json` records both roles.
6. Keep four active constructors if desired, but separate orchestration retries from
   task reasoning. Startup S3 failures and upstream stream interruptions should be
   retried/resumed by the batch runner; they should not consume a constructor's SOP
   iterations or trigger task changes.

One useful construction pattern remains a batch-specific tip rather than an SOP rule:
`a3e92222` succeeded after four saturated depth-oriented rounds by switching to a set of
independent, consistently shaped work units whose completion was scored separately. It
is a strong candidate for saturated tasks, but one current-batch success is not enough
to universalize it.
