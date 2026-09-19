# Round 4 life-local four-task validation

## Scope and provenance

The production batch launched four existing round-4 tasks concurrently from
`instances-round4-life-local-20260907` at template commit `c3a63180`:

- `52efdaea-1808-4432-a4c9-2285a08f5de7__bid1`
- `387bef85-101a-41c6-a103-1ef39c2d219c__bid1`
- `c43673d3-3a47-4b31-a6a0-9260e7ba217d__bid1`
- `eeb26954-397b-4062-aedb-8b4fc03a21dc__bid1`

The outer Harbor job is
`jobs/production-construction-round4-life-local-20260907/production-construction-round4-life-local-20260907`.
It uses one non-retrying constructor attempt per task with four-way outer
concurrency. Fresh target and solver arms use the runner's two-attempt,
two-concurrent defaults unless the construction Agent explicitly overrides them.

All four original tasks and the corrective canary are terminal. The outer batch
completed in 4h29m44s with no constructor exceptions.

## Verified runtime state

| Task | Fresh sampling | Latest parser reading | Current state |
| --- | --- | --- | --- |
| `52efdaea` | implicit target 2 + solver 2, arms concurrent | target `0.28605`, solver `0.55225`, `R=0.93061`; 2 valid per arm; `both_fail` red flag | terminal after 2h09m31s; build collected, but reward 0 because the final task digest had no completed matching regrade |
| `387bef85` | implicit target 2 + solver 2, arms concurrent | final digest-matching regrade round 4: target `0.625`, solver `1.0`, `R=0.6`; 2 valid per arm; both score gates pass | terminal after 4h29m44s with no outer exception; reward `0.375` (the absolute solver-target gap), matching task returned |
| `c43673d3` | no current-life run | no readable current-life round | constructor ended after 3,753 seconds with reward 0 |
| `eeb26954` | explicit target 3 + solver 3, arms concurrent | digest-matching regrade round 2: target `1.0`, solver `1.0`, `R=0.0`; 3 valid per arm; `both_pass_dominates` | terminal after 3h42m38s with no outer exception; Agent emitted `incomplete`, and Harbor returned the full old-template build (407 MiB) plus trajectory |

For `387bef85`, Harbor's job aggregate includes the errored solver trial, but
`parse_scores.py` correctly excludes its `UnknownApiError` and derives the solver
mean from the valid programmatic trial. Its scored target timeout remains included
under the documented `timed_out_scored` policy. For `52efdaea`, both target trials
carry programmatic values, so both are included even though one reached the Agent
timeout.

Fresh round 3 also makes the score-source distinction concrete. Harbor's solver
aggregate headline is `0.8696` for each trial, but each trial's direct
programmatic group in `reward-details.json` is `1.0`. The remaining agent-judge
group is not part of the construction score gate; one judge timed out after 600
seconds and recorded its affected criteria as zero, which explains the lower
headline. `parse_scores.py` intentionally reads the unique direct programmatic
group, so the Agent's statement that both solver programmatic scores are `1.0`
is correct. Reporting the Harbor aggregate headline as the target/solver gate
would mix two different score semantics.

Fresh round 3 is now complete and demonstrates why that distinction matters.
The two target trials reached the unchanged 3600-second Agent timeout, then the
verifier successfully scored the workspaces at `0.7292` and `0.5208`.
`parse_scores.py` classifies both as `timed_out_scored`, includes both, and gets
`target_mean=0.625`. The two solver trials are ordinary completed samples with
direct programmatic score `1.0`, giving `solver_mean=1.0` and `R=0.6`. Both
delivery gates pass. The target Harbor headlines (`0.6341` and `0.4529`) are
again lower because they mix in the agent-judge group; they are not the values
used by the construction gate. There is no active round marker left, and the
compact evidence contains no workspace tree.

The Agent then followed the parser's post-pass red-flag branch rather than
launching another fresh sample. Across the 21 programmatic criteria, 16 are full
passes for both arms, five favor solver, none favor target, and none are equal
partial failures. The five separators include two weight-10 core criteria:
page registration fails in both target samples, while long-id preservation fails
in one and passes in the other. This makes `both_pass_dominates` a review signal,
not evidence that the passing gap is fabricated.

The review did find one concrete over-strictness/duplication risk in a shared
criterion. `saved_village_id_reaches_the_room_request` simultaneously required
the POST method/URL/id handoff, village name/address inheritance, and a successful
validation string even though the latter two facts already have their own
criteria. The Agent reduced it to the one transport-layer obligation and added
no criterion. This is a verifier-quality repair, not a score-maximizing change:
its offline replay predicted no delta across all four round-3 workspaces, and
the final mechanical check remained nop `0/48`, oracle `48/48`, with 21 criteria
and the allowed weight ratio of 10.

For the formal confirmation it correctly used regrade. Compact
`round-0004/round.json` records `kind: regrade` and
`source_round: round-0003`; each arm has one `source_jobs` entry, no agent/model
configuration, no attempts field, and `n_concurrent_trials: 1`. The four replay
scores are byte-for-byte unchanged: target `0.7292/0.5208`, solver `1.0/1.0`, so
the final digest-matching result remains target `0.625`, solver `1.0`, `R=0.6`.
This is a clean demonstration of the intended “post-pass quality review →
tests-only repair → nop/oracle → regrade” loop. It also exposes a remaining
latency cost: because each trial's full verifier includes a 600-second agent
judge and each arm regrades its two trials serially, this no-rollout replay took
about 22 minutes rather than a few minutes.

The outer constructor then ended cleanly. Its authoritative `gap.json` names
round 4, reports `task_matches_final: true`, both gates true, zero faults, and
reward `0.375`. That reward is the absolute programmatic gap
`1.0 - 0.625`, not a binary pass indicator; the separate `clears_all_gates` field
is true. Harbor returned a 100 MiB task result directory containing an 80 MiB
build and a 4.4 MiB constructor trajectory. The final resume is 256 lines, and
no workspace directory leaked into compact evidence.

## Findings from Agent behavior

### The two-attempt default is real

Both `52efdaea` and `387bef85` called `run-two-models.sh both` without sampling
flags. Each created exactly two target and two solver trial directories, and the
two Harbor arms overlapped. This validates the runner default on real Daytona
work rather than only in unit tests.

`eeb26954` explicitly supplied `--attempts 3 --concurrency 3`. The runner therefore
honored six trials. This is not a defaulting bug; it showed that the SOP did not
yet tell the Agent when the default should remain authoritative.

All six trials eventually produced valid programmatic readings. One target trial
recorded `AgentTimeoutError` but still scored `1.0`, and the parser correctly
included it under the scored-timeout policy. Both arm means are `1.0`, so the
round is saturated (`R=0.0`) and requests verifier iteration rather than delivery.
The compact current-life evidence added about 42 MiB of retained trajectories;
the returned build is about 238 MiB, of which about 181 MiB is still the earlier
misplaced nop/oracle job trees created under the old template.

`387bef85` provides the first live positive check of the intended light loop. The
Agent changed only `tests/**`, reran mechanical nop/oracle successfully, checked
that the rollout-input identity was unchanged, and invoked
`run-two-models.sh regrade`. Runtime `round-0002` contains two Harbor regrade job
configs with `source_jobs` and no agent model configuration, one per arm; both use
the regrade default `n_concurrent_trials: 1`. It completed and compact-published
without another model call. The two target workspaces regraded to a mean of
`0.67705`; the two solver workspaces regraded to `1.0` and `0.0`. Runtime retention
then removed the derived regrade round and kept only the original real source,
while collected evidence grew from about 42.3 to 42.5 MiB and still contains no
workspace tree.

The same run exposed a lineage correctness bug. Harbor's actual CLI contract is
to regrade every recorded trial in a source job. Solver source trial `nozEKNM`
was excluded from round 1 because its model call ended with `UnknownApiError`
(`Upstream response stream was interrupted`), but it still had an archived
workspace. Regrade trial `wXcnmom` names `nozEKNM` as `source_trial`, reports no
new exception, and scores that incomplete workspace `0.0`. The current parser
only sees the regrade result's null exception and would therefore include it as a
new completed solver sample, while the genuinely completed solver source regrades
to `1.0`. This turns an infrastructure-invalid rollout into a model failure and
would change solver mean from `1.0` to `0.5`.

The completed parser output demonstrates the decision impact: it reports target
`0.67705`, solver `0.5`, and `R=-0.26150`, with two supposedly valid trials per
arm. If the original provider-failed solver source remains excluded as it was in
the fresh round, the solver mean is `1.0` and the same verifier produces
`R=0.476996`; both delivery gates (`target < 0.7`, `R > 0.2`) pass. The lineage
bug therefore reverses a passing task into an apparent failure rather than merely
changing a diagnostic count. The construction Agent also noticed the nop-shaped
solver replay and traced it back to `UnknownApiError`, but only after the official
parser had already emitted the false aggregate.

This is not hypothetical and not an Agent misuse: the runner intentionally passes
the whole source job, and `harbor job regrade --help` confirms that every recorded
source trial is replayed. Regrade parsing must preserve the source trial's
eligibility state (or the runner must construct a valid-trials-only source) before
this round can be used for a fair gap decision. The verifier replay itself remains
useful; the bug is in which replayed rows are eligible for aggregation.

An independent parser review classifies this as a P1 truthfulness defect and
recommends the smaller parser-local correction rather than changing Harbor source
jobs. The compact regrade trial already preserves its `source_trial.path`, while
the compact source round preserves the source trial's lock, result, and verifier
detail. The parser can therefore validate the regrade path against
`round.json.source_round`, map its `round-NNNN/<arm>/run-NNNN/jobs/.../task__...`
suffix into the same evidence root, and derive source eligibility without the
runtime workspace. Missing, ambiguous, cross-arm, or source-round-mismatched
lineage must fail closed instead of silently treating the regrade row as a
completed model attempt. Eligibility must preserve source *rollout* validity,
not blindly copy the old verifier's `included` bit. Harbor's `SingleStepTrial`
runs the Agent, uploads its log, and collects the workspace before calling the
verifier; `RewardFileNotFoundError` is raised only inside that later verifier
phase when neither reward file exists. A successful regrade must therefore be
allowed to repair this verifier-only source failure. Provider/environment/
cancelled failures and unscored Agent timeouts remain ineligible; scored Agent
timeouts retain the existing eligible policy. Unknown or malformed lineage
fails closed.

The full batch contains 14 compact regrade-to-source lineage edges. Every edge's
recorded source trial id matches the `id` in the mapped compact source result and
uses the same `round/arm/run/jobs/job/trial` suffix: nine sources completed
normally, four are scored `AgentTimeoutError` trials, and the one
`UnknownApiError` source is the misclassified case above. This means the repair
can use evidence already retained by the current format; it does not require a
new manifest, full workspace retention, or a Harbor invocation change.

An isolated parser prototype was then exercised against the retained production
artifacts. On the defective round it changed the aggregate from solver `0.5`,
`R=-0.261502` to solver `1.0`, `R=0.476996`, while keeping both target samples,
including the scored source timeout. The same prototype left the final 387
regrade at target `0.625`, solver `1.0`, and the eeb regrade at `1.0/1.0`, with
all of their valid source trials retained. This is implementation-feasibility
evidence only; the production parser and its synthetic edge-case tests remain
unchanged pending approval.

After tracing the nop-shaped solver replay, the Agent did not keep iterating from
the false round-2 aggregate. It rechecked nop/oracle (`0/48` and `48/48`) and
started a new fresh `round-0003` without sampling flags. The runtime now contains
an active target and solver Harbor process for that round. This heavy step is
defensible in this instance because one of the two original solver rollouts is an
infrastructure-invalid source that regrade cannot turn into a second valid solver
sample; the new fresh round is gathering replacement model evidence rather than
merely retesting the same two valid workspaces.

The new round's two job configs each record `n_attempts: 2` and
`n_concurrent_trials: 2`. Daytona independently lists four nested sandboxes—two
with the target trial ids and two with the solver trial ids—all in `STARTED`
state. Each contains a growing Claude stream log (about 0.9–1.6 MiB at the first
live check) and a live `claude` process. This rules out a stale outer job counter:
the intended four-way inner model concurrency is actually running.

The constructor then used the active-run wait to pursue a contingency from its
resume note: it read the page criteria and existing probe helper, wrote a new
`/tmp/pagefacts.py`, and compared archived round-1 workspaces in case the new
target mean remains above the gate. It did not change `/app/build/task`—the
1119-file `477c...` digest remains exact—but this is a second real example of the
scratch-probe exception expanding attention during a blocking run. The work is
contract-oriented and read-only with respect to the task, yet it is not needed to
monitor or attribute the four current trials. This supports deleting the
exception rather than trying to enumerate acceptable forms of concurrent
verifier research.

That scratch branch did at least terminate cleanly: the Agent found that every
page-layer difference was downstream of the already-known missing page
registration, found no independent discriminator, and wrote that negative result
into `resume.md` before returning to a read-only wait. This is a positive example
of a richer note preventing the same hypothesis from being reopened, but it does
not change the conclusion that the work should have waited until the formal round
ended.

### `c43673d3` spent the life before the measurement gate

The outer Agent completed successfully at the transport layer and returned a
40 MiB build artifact, but it never created `/app/runtime/harbor-evidence` and
never produced a current-life round. Its trajectory contains 199 tool calls:
133 Bash, 27 Write, 18 Edit, 18 Read, two subagent calls, and one subagent-list
call. Thirty-five calls targeted previous-life material and 30 targeted new
design helpers. The only runner mention was its initial help lookup.

The Agent delegated detailed time-distribution and error-cycle reviews of the
previous target and solver trajectories, then continued reopening the same
history in the main context. It used the resulting batch-level model profile to
redesign the task contract before taking a current-life reading. At the end it
explicitly corrected a long sequence of actions that it had narrated but not
executed, acknowledged that no mechanical gate or formal measurement existed,
and nevertheless returned a successful final response with a next-action note.

The root cause is an ordering loophole, not lack of a generic persistence
sentence: the old SOP said only that the *first formal measurement* must be fresh
and that rollout input freezes after the first fresh in *this life*. That left
unbounded history analysis and contract redesign legal before the measurement.

### Mechanical checks can bypass compact retention

`eeb26954` placed complete nop and oracle Harbor jobs below
`/app/build/evidence/checks`. The directory contains 1,426 files and 180,976,496
bytes, including both
`checks/nop-0005/.../artifacts/workspace` and
`checks/oracle-0005/.../artifacts/workspace`. The formal runner remains compact;
the leak came from ad-hoc mechanical checks whose output path the SOP had not
specified.

### Text guidance alone did not protect the light loop

After its first fresh round, `52efdaea` changed verifier fixtures and synchronized
the solution. It then invoked `run-two-models.sh both --attempts 2 --concurrency 2`
instead of `run-two-models.sh regrade`. The two runtime locks prove that this was
not a rollout-input change: round 1 and round 2 both record
`sha256:3f32266d308c320f31d06006aed31fb69bf99cb2dfbc386105121d95af7ef63d`
as `rollout_input_digest`, while only the full task digest changed. A compatible
current-life real source therefore existed and the second 2+2 model run was
unnecessary.

The Agent then found another verifier/contract contradiction after the fresh
jobs had started and sent `kill -9` to the runner. Round 2 ended with four
errored trials, no complete job aggregates, and no readable score. This avoided
waiting the full model hour but still spent allocation and startup work, and it
left another incomplete round for recovery. A pre-allocation refusal would have
prevented both the unnecessary run and this cleanup path.

This is a real failure of the intended cheap-first behavior, not a runner
defaulting bug: the runner faithfully honored the Agent's explicit fresh command.
The parser and SOP already recommended regrade, but that recommendation was lost
after a long attribution loop. A follow-up guard should make a compatible-source
fresh run opt-in rather than the default.

The outer constructor then ended normally rather than timing out or losing its
sandbox. Its result ran from `2026-09-06T17:27:49.021382Z` to
`2026-09-06T19:37:20.086031Z` (2h09m31s), recorded no exception, and successfully
collected a 56 MiB build before Daytona cleanup. The Agent explicitly said that
its context was nearly exhausted, wrote a resume note, and returned a final
message instead of executing the five planned fixture edits, nop/oracle, and
regrade. It had consumed 112,874 output tokens and 27,283,541 input tokens
(26,013,713 cached). The terminal verifier fault is therefore precise: final task
digest `sha256:75a62070d1abce13741b6777aaffb8d4b79b9b7d1635dccc4083f352b3e1bb76`
does not match the only complete round lock
`sha256:23a529077da826697ce3ae3565b7404ec04713ae60ec0d65700e4a19dfac0822`.
This is a premature-successful-exit failure caused by attention/context exhaustion,
not an infrastructure deletion or Harbor timeout.

## Corrective change and canary

Commit `de705e22` makes four bounded corrections:

1. the first current-life fresh run is an explicit gate before attribution or
   task-content changes, except for a mechanical defect that blocks nop/oracle or
   Harbor wiring;
2. a previous-life index carries the rollout-input freeze across the life
   boundary; only round numbering and regrade source reset;
3. task-local trajectory review must answer one named verifier decision, while
   batch-level timing and model profiling move to batch recovery; and
4. full nop/oracle jobs go to `/app/runtime/harbor-checks`; the parser flags any
   `artifacts/workspace` under compact evidence and tells the Agent to clean it
   without rerunning models or checks.

The parser change was written from a failing behavioral test. Two follow-up tests
prove that detection prunes traversal at the first full workspace and that cleanup
takes precedence over score iteration. The focused parser and template suite
passes 52 tests. A reviewer found the traversal and priority defects in the first
implementation; both were fixed and the reviewer then approved it.

A controlled corrective canary reused the original `c43673d3` seed and changed
only the outer template to `de705e22`. It ran under
`jobs/round4-life-local-canary-c436-20260907` to test whether the Agent kept the
incoming task frozen, wrote full mechanical jobs outside `/app/build`, and reached
an implicit-default `2+2` fresh measurement.

The canary crossed the pre-fresh gate. The incoming seed task and the
live `/app/build/task` both hash to
`sha256:a791c2eeebe7150dbda2875da76207239ac2484019d7c411a760d9c73582435c`
over 230 packaged files. Its local mechanical checks reported nop `0.0` over all
34 criteria and oracle `1.0` over all 34 criteria. The Agent then invoked
`run-two-models.sh both` without `--attempts` or `--concurrency`. Both live job
configs resolve `n_attempts: 2` and `n_concurrent_trials: 2`, and the runtime
contains exactly four trial directories (two per arm). The fresh round is now
complete: target `1.0` over two valid trials, solver `1.0` over two valid trials,
`R=0.0`, and `both_pass_dominates`. The final task returned to the exact incoming
230-file `a791...` digest before publication. Collected evidence is about 58.5
MiB, compared with about 304.7 MiB retained in the current-life runtime source,
and no `artifacts/workspace` exists below `/app/build/evidence`.

While the fresh run was active, the Agent initially considered changing the
shipped implementation to reduce target wall-clock pressure. It then checked
the four explicit unfreeze conditions against the task and rejected that plan:
the instruction disclosed the relevant duties, oracle proved a solution, and
Harbor wiring worked. Its recorded conclusion was “rollout input stays frozen,”
followed by a contract-local tests-only hypothesis. The live task digest remained
unchanged. This is direct behavioral evidence that the new cross-life freeze
language corrected the original canary's pre-measurement redesign tendency.

That positive result is qualified by a later checkpoint violation. After both
solver trials finished but while both target trials were still running, the Agent
wrote `tests/__lib/mutation.py` into the formal task. The task grew from 230 to
231 packaged files and its digest changed from
`sha256:a791c2eeebe7150dbda2875da76207239ac2484019d7c411a760d9c73582435c`
to `sha256:399e10a4491343c8398df35e05e2c0d49e6bf6d162a212b3129ccc73c4b2edb9`.
The file is a verifier-side mutation module, not a scratch probe, and therefore
contradicts the explicit instruction that `/app/build/task/` remain unchanged
until the formal fresh run ends and is parsed. The source rollout remains usable
for a later regrade because rollout input itself did not change, but the behavior
shows that prose alone does not reliably enforce the blocking checkpoint during
a long-running arm.

The violation was temporary and the same Agent corrected it without outside
intervention. After a context compaction, its resume text quoted the blocking
checkpoint, noticed that a target verifier image was being built from the live
`tests/` tree, moved `mutation.py` back out of the task, and restored the exact
230-file `a791...` digest. The added module was not registered in the reward
configuration, so it did not affect criterion scoring. This is evidence that the
resume/SOP reminder can recover attention after compaction, but it also suggests
that allowing verifier-oriented scratch work during a formal run creates an
avoidable boundary: the safer simplification is to keep formal-run time to
monitoring and infrastructure attribution only, then begin verifier exploration
after both arms finish and parse.

The next live actions reinforce that simplification. With one target trial still
running, the Agent resumed contract-gap exploration and opened previous-life
rounds 7 through 10 plus the long resume history. This did not mutate the task,
but it was not needed to observe the outstanding current-life trial and moved
attention away from the formal checkpoint. The present wording says both “only
monitor” and “or execute the one scratch probe”; in practice the latter clause
expanded from a bounded `/tmp` probe into formal verifier code and multi-round
history review. Removing that exception is a smaller and clearer control than
adding more rules about which exploratory files may be touched while a run is
active.

The corrective canary's outer Agent eventually ended normally after 2h30m06s.
Harbor returned an 82 MiB outer result directory containing a 60 MiB build and a
3.8 MiB constructor trajectory. The returned task still has the exact incoming
230-file `a791...` digest, and compact evidence contains no nested workspace.
The final status is correctly `incomplete` because the formal round remains
target `1.0`, solver `1.0`, `R=0.0`. It nevertheless continued into increasingly
broad cross-workspace experiments after nine candidate axes saturated. This is
useful stop-policy evidence: the new pre-fresh gate fixed ordering and artifact
placement, but it does not by itself bound post-saturation exploration.

A next-life packaging rehearsal found one additional layout defect. The Agent
saved about 104 KiB of probe scripts and logs at `evidence/round-0001/probes/`.
`pack-seed.py` correctly rejected that directory because formal `round-*` paths
are a closed, tool-owned compact schema. The other three latest builds packed
directly into 7.5--13 MiB archives. A staging-only repair that moved the canary's
probe directory to `evidence/analysis/` allowed it to pack into a 4.9 MiB archive
without changing the original returned build, and the analysis directory was not
carried into the new life. The root cause is the SOP's vague instruction to put
other process material in an evidence subdirectory; it never says that formal
round directories are runner-owned. The fix belongs in that instruction, not in
the packer allowlist, because allowing arbitrary probe trees would reopen
cross-life artifact growth.

Its tenth measured axis was a useful overfitting check: each delivery's tests
were cross-run against the oracle implementation. After excluding one whitespace
assertion that depends on behavior the contract leaves undefined, three of four
suites were contract-portable. The only remaining coupling was a single target
trial's reference to its private `RESULT_ORDER` constant, with no second-target
reproduction. The Agent correctly refused to promote that one-sample
implementation detail into a criterion. This strongly supports the
contract/replication guard, while ten post-saturation axes remain too expensive
for a routine loop.

Its eleventh axis reached the same disciplined conclusion on a stronger probe.
The Agent generated four portable mutations for the published `evaluateAll`
ordering contract and ran every mutation against each delivery's own tests. All
20 mutation anchors matched exactly once. The two solver trials and one target
trial caught three of four mutations; the other target trial caught all four.
The sole difference was removal of the `rSquared` tie-break: it survived in both
solver trials and one target trial, but was caught by only the second target.
Because the difference did not reproduce across both target samples and pointed
in the reverse direction, the Agent rejected it instead of expanding the formal
verifier. The final task remains the exact incoming `a791...` digest. This is
direct evidence that multi-sample replication and direction checks prevent a
real but unsuitable one-trial observation from becoming a manufactured score
gap.

The canary then spent another full axis on a 576-case adversarial trend corpus.
All four deliveries and the oracle completed all 576 cases. A literal line diff
reported 364 differences per delivery, but every sampled difference was only the
free-form `trendDescription` wording: the contract requires a readable summary
containing the sample-day count, not oracle-identical prose. After normalizing
that field, all four deliveries have **zero** structured-field differences from
the oracle across the entire corpus. This again proves saturation, but it also
shows why post-saturation exploration needs a stop predicate: an exhaustive
corpus can generate hundreds of textual differences that look informative until
the contract is applied, while yielding no usable verifier change.

The canary also exposed a cross-life authority conflict. Its inherited
`resume.md` says that recorded saturation permits returning to step 1 and
changing rollout input, and recommends shipping a defective implementation or
rewriting the capability axis. The current SOP says the opposite: a new life
inherits the rollout freeze, and lack of separation is not an unfreeze condition.
The Agent noticed the conflict and reread the current freeze clauses before
acting; its task digest remains unchanged. The template currently calls
previous-life material “background reference” but never states the precedence
rule directly. The smallest follow-up is one sentence near the first evidence
read: historical `resume.md` supplies facts and hypotheses, while the current SOP
governs workflow and wins any conflict. Do not solve this by truncating the
retained evidence or adding another decision loop.

The old-template `eeb26954` run provides the stronger negative comparison. At
about 2h39m of sandbox life it had made 310 tool calls, downloaded additional
dependencies, and built more differential harnesses while repeatedly rejecting
performance, private implementation choices, and other out-of-contract axes. Its
task remains mechanically stable, but the build is about 238 MiB and compact
evidence about 236 MiB because the old template retained about 181 MiB of nested
check workspaces. This is attention and artifact cost without a formal second
round yet.

The exploration eventually became more disciplined. After 252 contract-pinned
differential observations were byte-identical across all six deliveries, the
Agent stopped inventing runtime edge cases, reread the frozen instruction, and
identified four concrete surfaces that the verifier appears not to exercise:
the service-level dedup-plan accessor, all ten enumerated endpoints, all seven
configuration keys, and menu/button permission DDL. It then measured those facts
across the six archived workspaces before proposing criteria. This is the right
evidence order—contract obligation, current coverage gap, then cross-arm
variation—but it arrived only after 329 tool calls. A concise post-saturation
route should point to this static contract-coverage comparison earlier, rather
than merely adding a general instruction to “explore more.”

Those four static candidates, the SDK-discovery candidate, and a performance
candidate all subsequently failed the Agent's own evidence gate. All six
deliveries satisfied the static obligations; SDK selection was already covered;
and the shipped dump contained only 26 lines, so a “tens of thousands” timing
criterion would rely on narrative scale rather than the actual task and would be
flaky. The Agent explicitly rejected that move and returned to the official
per-trial parser output. This is good correctness discipline, but it took 335
tool calls to prove saturation rather than reaching a new formal verifier round.

The late full-contract scan found one genuinely stronger candidate in the
previously unread concurrency section: the whole folded search result must come
from one snapshot, and per-pair validity alone is explicitly insufficient. A
six-workspace stress probe exercised roughly 1.25–2.91 million reads per
delivery, 4,000 concurrent adds, 400 competing removals, 300 concurrent replaces,
and 3,200 rejected writes. Every target and solver delivery reported zero
throws, duplicates, cap/order violations, phantom pairs, lost adds, mixed or
vanished replaces, and counting errors. The strongest omitted contract surface
therefore also saturates. This validates the proposed coverage-scan ordering as
an efficiency improvement, not as a promise that every frozen task can be made
separating.

The same full-contract scan exposed a different SOP loophole. The degraded
engine probe showed that all six deliveries already raise `ServiceException` for
the previously unobserved `verify` and `search` calls, and all six expose the same
`FaceMatch` bean behavior. The only gap-probe divergence was the unreadable-image
exception type: all three targets used `IllegalArgumentException`, while two of
three solvers used `ServiceException`, which is the wrong direction for a
separator. The Agent nevertheless added six observations to the formal harness
and extended the existing engine criterion, explicitly describing the change as
closing coverage “without changing any score.” This keeps the criterion count at
50 but enlarges verifier cost and surface with no expected delta. The current
both-pass row says to keep a few core floors, yet does not forbid this use of
“contract completeness” as an expansion license. A tighter rule should reject
both-pass test additions or expansions unless current arm evidence predicts a
useful delta or the change repairs a demonstrated verifier false positive/
negative; core-floor language should preserve a small existing floor, not grow
one merely because another contract clause can be enumerated.

After a context compaction, `eeb26954` resumed at the correct light-loop boundary
rather than repeating discovery or launching another fresh sample. Its compacted
state preserved the local oracle result, named the required full Harbor nop and
oracle jobs, quoted the parser's “regrade before fresh” action hint, and specified
`run-two-models.sh regrade` as the next scoring action. The Agent then started one
real oracle and one real nop job concurrently. This is positive evidence that
the resume plus tool hint can preserve the light-versus-heavy decision across
context loss. Because this task still runs the old template, however, those jobs
again target `/app/build/evidence/checks`; the observed file count immediately
began increasing there. In under three minutes, the returned build grew from
about 238 MiB to 419 MiB and `evidence/checks` from about 181 MiB to 362 MiB.
The new runtime-only check location remains necessary even though the Agent chose
the right evaluation loop.

Both mechanical jobs then completed without an exception at exactly the expected
scores: nop `{ut: 0.0, reward: 0.0}` and oracle
`{ut: 1.0, reward: 1.0}`. The Agent read those results, stated “Regrading now,”
and invoked `run-two-models.sh regrade`; runtime `round-0002/.active` and one
Harbor regrade process per arm were subsequently observed. No new target or
solver model configuration is present. This is the second real task to use the
regrade loop and the first to demonstrate that the decision survives a context
compaction.

That regrade completed successfully. Compact `round-0002/round.json` records
`kind: regrade` and `source_round: round-0001`; each arm's job config has one
`source_jobs` entry, `n_concurrent_trials: 1`, no `n_attempts`, and no agent/model
section. All three target and all three solver replays scored `1.0`, so the
digest-matching result remains target `1.0`, solver `1.0`, `R=0.0`. The derived
runtime round was removed after publication, the fresh source round was retained,
and compact round 2 contains no workspace directory. This is a complete positive
mechanical validation of regrade and a negative product result for the added
both-pass tests: they consumed check/regrade resources without changing any
score or revealing a discriminator.

The final resume update preserves the useful conclusion rather than only the
headline score. It records zero delta for all 14 new dedup/regroup criteria,
byte-identical values for all 44 new observations across six deliveries, the
per-trial Agent durations including one scored 3600-second target timeout, the
nop/oracle and digest invariants, and an explicit statement that the current
life's both-pass branch is exhausted. This is enough for the next life to inherit
the decision without reopening full trajectories. It demonstrates the intended
cross-life compounding behavior even though this particular verifier direction
did not create separation.

The outer eeb job then ended normally with no exception and reward `0`, as
expected for an honest `incomplete` construction. Its downloaded directory is
433 MiB, including a 407 MiB returned build and a 6.3 MiB constructor trajectory.
This confirms that the final resume and both compact rounds survived outer
cleanup; it also quantifies the old check-workspace retention penalty rather than
leaving artifact collection as an assumption.

After the final SOP/parser wording correction, the complete repository unit-test
suite passes: 170 tests in 104.713 seconds.

## Overall conclusion and remaining gate

The run validates four parts of the design with real Harbor/Daytona evidence:

- fresh `target` and `solver` sampling defaults to two attempts per arm and runs
  the two arms concurrently;
- compact publication retains the useful result, trajectory, and resume evidence
  without retaining a workspace tree under the corrected template;
- tests/solution-only changes can reuse current-life rollouts through regrade, and
  two Agents independently selected that path instead of another model rollout;
- the corrected pre-fresh gate kept the canary's incoming rollout input frozen and
  produced an honest `incomplete` result when no separating axis survived.

It does **not** yet prove the full objective that four tasks completed under the
latest design. The original four-way batch used template commit `c3a63180`; only
the corrective canary used `de705e22`. One original task (`387bef85`) reached a
valid final separator, but its earlier regrade exposed a real eligibility bug:
the parser can count a replay of a provider-failed source rollout as a completed
zero and reverse a passing gap into a failure. That defect must be fixed before a
new four-task batch can be treated as an authoritative validation of regrade.

The smallest production gate before that rerun is:

1. make regrade aggregation inherit rollout eligibility from the compact source
   trial and fail closed on missing or inconsistent lineage;
2. remove the active-run scratch exception so a formal run permits only monitoring
   and infrastructure attribution;
3. state that the current SOP overrides historical resume workflow advice;
4. reject both-pass test additions or expansions unless current evidence predicts
   useful separation or demonstrates a verifier false positive/negative; and
5. reserve `evidence/round-*` for the runner and place disposable process material
   under `evidence/analysis/`, which is intentionally not inherited by the next
   life.

Four behavioral parser tests are sufficient for that correctness change: the
real 387 regression; a source-state table that keeps completed and scored-timeout
rollouts, excludes provider/environment/cancelled and unscored-timeout rollouts,
and permits a successful replay to repair `RewardFileNotFoundError`; a malformed
lineage table covering missing marker/path/id, cross-arm and digest mismatch; and
an ordinary fresh-round regression proving its existing eligibility behavior is
unchanged. The SOP edits are prose-only and should be pressure-checked in the new
four-task run rather than protected by source-text assertions.

The roughly 22-minute regrade observed on `387bef85` is a separate efficiency
issue, caused by the full 600-second agent judge and serial replay within each arm.
It does not invalidate score reuse, so changing regrade concurrency or introducing
a programmatic-only tuning mode should be evaluated separately rather than folded
into the correctness fix.
