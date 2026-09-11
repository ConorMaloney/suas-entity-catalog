# AGENT_WORKFLOW.md - How this catalog is built with an AI agent

Most of the code, records and prose in this repository were written by an AI
agent under direction. That is stated plainly at the top because it is the
method, not a disclaimer, and because a reader is entitled to know it before
deciding how much to trust anything below it.

Three documents divide the job:

| | |
|---|---|
| `STANDARDS.md` s12 | The **guardrails** - rules an agent must follow when touching the catalog |
| **This document** | The **pipeline**, the **prompt patterns**, and the **review loop** |
| `catalog/reviews/` | The **gate**, walked - what a human actually adjudicated |

It is short on purpose. A workflow document nobody reads is a workflow nobody
follows.

---

## 1. The division of labour

| Agent | Human |
|---|---|
| Read 40k+ lines of C++ plugin source, extract the governing equations | Decided which equations mattered |
| Draft the model, the tooling, the tests, the documentation | Set scope, refused scope creep |
| Grind through parameter-by-parameter sourcing across dozens of documents | Adjudicated contested sources |
| Propose the numbers | **Challenged the numbers** |
| Escalate what it could not decide | **Answered the escalation** |

The last two rows are the ones that matter. Section 5 is the evidence.

The agent is fast at reading source and producing structure, and it is
simultaneously the most likely origin of a confident, well-formatted, wrong
number. Every practice below exists because of that asymmetry.

---

## 2. The pipeline

An entity is built in four stages. Each produces an artifact that outlives it,
and each hands the next stage something auditable.

```
   DIRECT    ->    RESEARCH    ->    VALIDATE    ->    PROMOTE
   binding         research          frozen            human review
   rules           log               test suite        of every gap
```

### DIRECT - binding rules, written before the agent starts

The prompt is a contract, not a request. The rules that carry the most weight:

- **Coverage.** Every schema parameter appears as a key. A field you could not
  source is `status: "missing"` with a `todo` naming what would close it. An
  absent key is a failure of the task, not a gap.
- **No inference.** No estimating, interpolating, scaling from a sibling model,
  or back-computing. **Returning a gap is a correct outcome.**
- **Conflicts are preserved, never averaged.** Both values, both sources,
  `conflicting: true`, and a note saying which you would use and why.
- **Quote what you read.** Every non-null value carries a verbatim
  `source_quote`. *If you cannot quote it, you did not read it.* This is the
  single strongest anti-fabrication measure available.
- **Units and precision.** Record `value_as_published` alongside the SI value.
  Convert once, from the original. **Never add significant figures the source
  does not have.**
- **Stay in your lane.** Do not research the `REQUIRED_MODELING` constants -
  those are modelling choices, not facts about the aircraft.
- **Stop and ask.** Named thresholds, not "use judgement": three or more values
  for the calibration anchor, sources disagreeing by more than 20% on a
  `REQUIRED_MEASURED` field, or an undeterminable variant.

### RESEARCH - the log is the deliverable, not just the record

`drafts/UAS-QUAD-SKYDIO-X2D.research.md` is 5,300 words recording, per field:
the searches run, every source examined **including the rejected ones and
why**, the decision taken, and the confidence assigned.

The log is what makes the work auditable without redoing it. A record alone
tells you what was concluded; the log tells you what was considered and
discarded. Negative results are recorded too - the next person must not repeat
a dead end.

The record is written to `drafts/`, never straight to `catalog/entities/`.

### VALIDATE - a frozen suite, and the gaps it refuses to decide

`run_validation.py` runs a per-entity suite (`catalog/tests/*.yaml`,
**77 tests** for the X2D) and writes a machine-readable report. The runner
reads only the record, the schema and the suite - verified: no `urllib`, no
`requests`, no `socket`, no other entity record.

The X2D outcome: **55 pass, 8 skipped, 4 fail, 1 warn, 9 gaps.**

**The gaps are the point.** A gap is a test that declares itself *not
automatable* - `target: human` or `target: tooling`. It states what a machine
cannot determine from the artifact and parks it for a person:

> *"Whether a source_quote is authentic, or actually supports the value it sits
> beside, cannot be determined from the artifact."*

A suite that reports only pass and fail is claiming to have checked things it
has not. Naming them keeps the board honest.

### PROMOTE - a human walks every gap, in writing

`catalog/reviews/REVIEW-UAS-QUAD-SKYDIO-X2D-2026-09-11.md` adjudicates all
nine: four closed on evidence, one settled by decision, two deferred, one
split between the two, and one - XF-014 - still blocking.

**The X2D was not promoted.** It remains R0, and the gate still refuses it.

Two principles the review enforces:

- **Caveats must be structural, not editorial.** A caveat in a note field gets
  lost the first time someone copies a number onto a slide. A caveat the
  tooling reads - the `provisional` banner, the readiness tier - cannot be.
- **Hard blocks are not overridable in tooling.** An unadjudicated conflict on
  the calibration anchor blocks promotion outright, because that is the field
  the entire model is fitted to.

---

## 3. Prompt patterns that produced usable work

**Point at the source, not at the question.** "How does AirSim compute rotor
thrust?" invites a plausible answer from training data. "Read
`RotorParams.hpp` and quote the thrust equation with line numbers" produces
`thrust = C_T * rho * n^2 * D^4` at `RotorParams.hpp:21-62`, which can be
opened and checked.

**Require file:line on every factual claim.** A claim with no citation was not
looked up. Several assertions in `VALIDATION.md` were wrong until the citation
was demanded.

**Pre-register the prediction before the agent is allowed to measure.** An
agent asked to "check whether the model matches" will find a way to make it
match. An agent asked to commit to a number first, then measure, cannot.

**Ask for the negative control explicitly.** "Show me this test failing when
the physics is wrong" produced the synthetic-drag check: feed the
identification a drag law 1.6x off and confirm it goes red. Without that
prompt the test would have been trusted on the strength of passing, which is
no evidence at all.

**Require the agent to say what it did NOT verify.** This surfaced the
`getRotorStates()` problem - a Python client promising rotor thrust in a
docstring while declaring neither - and produced
`probe_sim_capabilities.py`, which discovers the contract at runtime.

**Ask what it would refuse.** "Flag anything you think is scope creep and say
so rather than designing it" produced nine refusals in the catalog plan: a
taxonomy engine for three quadcopters, a JSON Schema interpreter, a wind
predictor invented to fill an empty row. An agent left unprompted builds all of
them, because building is what it is for.

**One question per agent, with its own scope.** Subagents were used to map the
model's coupling to a single entity, and to design the catalog against those
findings. Neither was asked to do both.

---

## 4. The review loop

Six checkpoints. Each exists because it caught something.

| Before | Check |
|---|---|
| Accepting a factual claim | Is there a file:line? Open it. |
| Accepting a number | Was it *measured* at the precision quoted, or extended? |
| Trusting a source read | Is there a runtime check that would catch it being wrong? |
| Any refactor | Is the existing behaviour pinned first? |
| Believing a green board | Has anyone watched this test fail? |
| Accepting a summary | Does the underlying output actually say that? |

Two deserve expanding.

**Pin before you refactor.** `test_regression_pinned.py` was written and
passing against untouched code as its own commit, before the catalog inversion
was allowed to start. It pins 36 published figures at 1e-8. The inversion moved
34 by nothing at all; the two that changed were a deliberate shape change,
edited by hand with the reason recorded. Without that commit, "I refactored and
I think nothing moved" would have been an opinion.

**Watch the test fail.** `test_catalog.py` check 7 asserts the readiness gate
*refuses* every R0 record. A gate nobody has observed refusing anything is not
known to work. The check was deliberately vacuous for one commit - "no R0
entity present to refuse" - and only began to bite when the stubs landed.

---

## 5. Seven times the agent was caught being wrong

These are the reason to trust anything else here. All seven are recorded in the
artifacts themselves, not only in this document.

### 5.1 A confident claim, asserted twice, backwards

The agent stated - twice, across five files - that AirSim's `FastPhysicsEngine`
"uses a fixed-step integrator", inherited from a planning document without
verification. A human question - *"wouldn't a higher ClockSpeed just run faster
without affecting accuracy?"* - forced it to check.

The truth was close to the opposite: the physics thread runs on a fixed
**wall-clock** 3 ms cadence while the integration step is whatever *simulation*
time elapsed, so `dt_sim ~= 3 ms * ClockSpeed`. Raising ClockSpeed does not run
more steps; it makes each step cover more simulated time.

The conclusion survived - a high ClockSpeed does damage results - but for the
opposite mechanical reason. `VALIDATION.md` carries the correction explicitly
rather than overwriting the wrong claim quietly.

**Lesson: an agent's confidence is uncorrelated with its correctness, and it
will restate an unverified claim as often as you let it.**

### 5.2 Fabricated precision, caught by a tool

Writing the regression pins, the agent typed expected values to ten decimal
places having only ever measured four. Twelve of thirty-six pins reported
CHANGED on the first run - against code nobody had modified.

The deltas were around 1e-5, small enough to wave away as floating point. They
were not floating point. They were invented digits.

Recorded in `test_regression_pinned.py:91-102` rather than quietly fixed.

**Lesson: build the check that catches the agent before you need it. This one
earned its place on its first execution, against its own author.**

### 5.3 A human intuition that was half right

A human challenged whether `simSetWind()` could work at runtime, believing wind
had to come from `settings.json` and required a restart.

Half right. `settings.json` wind genuinely does require a restart - and
`simSetWind()` writes the same variable the settings loader seeds. The agent
traced the full RPC chain to answer it, then settled it empirically: the
aircraft tilted, saturated, and was carried 290 m downwind with no restart.

**Lesson: a wrong challenge is still valuable. It converted an assertion into a
traced chain plus a measurement.**

### 5.4 A green table that meant nothing

An agent-produced sensitivity table showed a 20% change in every parameter
moving hover endurance by exactly 0.0%. It looked like robustness. It was the
calibration silently re-fitting and absorbing each perturbation, so the table
could only ever print zeros.

Caught by reading the output, not the code.

**Lesson: a plausible-looking table is the easiest thing for an agent to
produce and the hardest thing to eyeball. Ask what result would be impossible,
then check whether you are looking at it.**

### 5.5 The escalation rule caught an error in the brief itself

The research agent was directed to compile *"Skydio X2D, Enterprise variant"*.
**No such configuration exists.** Skydio's X2 line splits into the X2D
(**defense**) and the X2E (**enterprise**) - separate products, separate
datasheets, different radios, different encryption.

The agent did not pick one and proceed. It stopped under the stop-and-ask rule
(*"cannot determine which variant a source describes"*) and escalated. The
record preserves the whole thing as `ESC-1`, including that the owner answered
it **twice** - first X2E, then corrected to X2D - and why both turns are on the
record.

It mattered: max speed is **11.2 m/s on the X2D against 13.9 on the X2E, 24%
apart**. Every other airframe figure is common to both, which is exactly what
makes the discrepancy easy to miss. The X2E readings survive in
`conflicting_values` as the rejected alternative rather than being deleted.

**Lesson: escalation rules do not only catch the agent's errors. This one
caught the director's. An agent that had "used judgement" here would have
produced a clean, confident, 24%-wrong record.**

### 5.6 A report written into the wrong directory turned the board red

`run_validation.py` defaulted its output to
`catalog/entities/validation_report.json`. But `catalog.list_entity_ids()`
globs `*.json` in that directory, so the report was loaded as a fourth entity,
failed on `schema_version`, and turned `test_catalog.py` check 2 red.

A directory whose contract is *one entity record per file* had a non-entity put
in it. Caught by running the battery, not by reading the diff.

**Lesson: namespaces have contracts, and an agent will violate one while
satisfying every explicit instruction. The test battery is what notices.**

### 5.7 A published figure that broke the project's own stated rule

The worst of the seven, because nothing caught it for a day.

`PREDICTIONS.md` and `README.md` both stated that test 3.a "should be re-run at
ClockSpeed 1.0 before its energy figures are quoted" - the project's own
conclusion from catch 5.1. The 1.0x re-run was then performed, produced 597
samples against the original run's 41, and was written to `results/`.

**And the documents went on quoting the 14.54x run anyway.** P4's published
`+2.51%` came from a 41-sample run that this repository disavows in writing, in
two files. The correct figure, `+2.84%`, sat uncited on disk for a day while
three documents published the other one.

Found during a cleanup audit, by cross-referencing which `results/` file each
published figure actually came from - a question nobody had asked, because
`results/` had no index and two of its sixteen files were cited by name.

Corrected in `PREDICTIONS.md` as a recorded correction rather than a silent
swap, and `results/README.md` now names the authoritative run for every
prediction.

**Lesson: a rule written in a document checks nothing. The repository stated
the right rule, derived it correctly, wrote it down twice - and then violated
it in its own headline table, because no test compared the published figures
against the runs they came from. Stating a standard and enforcing a standard
are different pieces of work.**

---

## 6. What the agent was not permitted to do

- **Invent a parameter value.** `STANDARDS.md` s5 forbids it; the schema makes
  a declared gap structurally distinct from a present value; two of three
  entities are consequently stubs the tooling refuses to model.
- **Widen a tolerance to turn a row green.** The cruise anchor misses by +14.2%
  and ships that way.
- **Invent a predictor to fill an empty row.** `max_wind_resistance_ms` reads
  UNSCORED, because a predictor is a new falsifiable claim requiring
  pre-registration.
- **Raise a readiness claim to make a test pass.** Computed versus declared
  tier is asserted by `test_catalog.py`.
- **Resolve a source conflict by averaging.** Both values are retained.
- **Promote its own record.** Promotion is a human step with a written review.
- **Auto-update a regression pin.** `--update-pins-dry-run` prints, never
  writes.

---

## 7. Honest limits of this account

Written from a single project by the people who ran it, which is the weakest
possible evidence base. Four things it does not establish:

1. **It is not a controlled comparison.** Nobody built this by hand alongside,
   so "the agent was faster" is an impression, not a measurement.
2. **The catches in section 5 are the ones that were found.** An unknown number
   were not. Five of the seven were caught by a tool, a direct challenge or an
   audit rather
   than by reading output carefully - which suggests careful reading is the
   *weakest* link in the loop, not the strongest.
3. **The practices are not validated at scale.** One entity with a complete
   record, one researched to R0, one stub. Whether they survive fifty entities
   and several contributors is untested.
4. **The pipeline has been run end to end exactly once.** The X2D is a single
   trial. Its most useful output was a blocked promotion, which is encouraging,
   but one trial is one trial.

The one claim worth making: **every number in this repository can be traced to
a citation, a measurement, or an explicit statement that it is an estimate** -
and where that failed, in 5.2, a check caught it and the failure is on the
record rather than quietly repaired.
