# AGENT_WORKFLOW.md - How this catalog was built with an AI agent

Most of the code and prose in this repository was written by an AI agent under
direction. That is stated plainly at the top because it is the method, not a
disclaimer, and because a reader is entitled to know it before deciding how
much to trust anything below it.

`STANDARDS.md` section 12 is the **guardrails** - the rules an agent must
follow when touching the catalog. This document is the other two thirds: the
**prompt patterns** that produced usable work, and the **review loop** that
caught the work that was not usable.

It is short on purpose. A workflow document nobody reads is a workflow nobody
follows.

---

## 1. The division of labour

| Agent | Human |
|---|---|
| Read 40k+ lines of C++ plugin source and extract the governing equations | Decided which equations mattered |
| Draft the model, the tooling, the tests, the documentation | Set scope, refused scope creep |
| Grind through parameter-by-parameter sourcing | Adjudicated contested sources |
| Propose the numbers | **Challenged the numbers** |

The last row is the one that matters, and section 4 is the evidence for it.

The agent is fast at reading source and producing structure, and it is
simultaneously the most likely origin of a confident, well-formatted, wrong
number. Every practice below exists because of that asymmetry.

---

## 2. Prompt patterns that produced usable work

**Point at the source, not at the question.** "How does AirSim compute rotor
thrust?" invites a plausible answer from training data. "Read
`RotorParams.hpp` and quote the thrust equation with line numbers" produces
`thrust = C_T * rho * n^2 * D^4` at `RotorParams.hpp:21-62`, which can be
opened and checked.

**Require file:line on every factual claim.** Not as bureaucracy - as a
forcing function. A claim with no citation was not looked up. Nearly every
assertion in `VALIDATION.md` carries one for this reason, and several were
wrong until the citation was demanded.

**Pre-register the prediction before the agent is allowed to measure.**
`PREDICTIONS.md` exists because an agent asked to "check whether the model
matches" will find a way to make it match. An agent asked to commit to a
number first, then measure, cannot.

**Ask for the negative control explicitly.** "Show me this test failing when
the physics is wrong" produced the synthetic-drag check in `PREDICTIONS.md`:
feed the identification a drag law 1.6x off and confirm P1 and P2 both go red.
Without that prompt the test would have been trusted on the strength of
passing, which is no evidence at all.

**Require the agent to say what it did NOT verify.** This surfaced the
`getRotorStates()` problem: the Python client promises rotor speed and thrust
in a docstring while declaring neither, so the key names were an unverified
server contract. The result was `probe_sim_capabilities.py`, which discovers
them at runtime rather than assuming.

**Ask what it would refuse.** "Flag anything you think is scope creep and say
so rather than designing it" produced a list of nine refusals in the catalog
plan - a taxonomy engine for three quadcopters, a JSON Schema interpreter, a
wind predictor invented to fill an empty row. An agent left unprompted builds
all of them, because building is what it is for.

**One question per agent, with its own scope.** Two subagents were used here:
one to map every place the model was coupled to a single entity, one to design
the catalog layer against those findings. Neither was asked to do both.

---

## 3. The review loop

Six checkpoints. Each one exists because it caught something.

| Before | Check |
|---|---|
| Accepting a factual claim | Is there a file:line? Open it. |
| Accepting a number | Was it *measured* at the precision quoted, or extended? |
| Trusting a source read | Is there a runtime check that would catch it being wrong? |
| Any refactor | Is the existing behaviour pinned first? |
| Believing a green board | Has anyone watched this test fail? |
| Accepting a summary | Does the underlying output actually say that? |

Two of those deserve expanding.

**Pin before you refactor.** `test_regression_pinned.py` was written and
passing against untouched code as its own commit, before the catalog inversion
was allowed to start. It pins 36 published figures at 1e-8. The inversion then
moved 34 of them by nothing at all, and the two that changed were a deliberate
shape change edited by hand with the reason recorded in the file. Without that
commit, "I refactored and I think nothing moved" would have been an opinion.

**Watch the test fail.** `test_catalog.py` check 7 asserts that the readiness
gate *refuses* every R0 record. A gate nobody has observed refusing anything is
not known to work. The check was deliberately vacuous for one commit - "no R0
entity present to refuse" - and only began to bite when the stub entities
landed.

---

## 4. Four times the agent was caught being wrong

These are the reason to trust anything else in this repository. All four are
recorded in the artifacts themselves, not just here.

### 4.1 A confident claim, asserted twice, backwards

The agent stated - twice, in five files - that AirSim's `FastPhysicsEngine`
"uses a fixed-step integrator", inherited from a planning document without
verification. A human question ("wouldn't a higher ClockSpeed just run faster
without affecting accuracy?") forced it to actually check.

The truth was close to the opposite: the physics thread is scheduled on a fixed
**wall-clock** 3 ms cadence, while the integration step is whatever
*simulation* time has elapsed, so `dt_sim ~= 3 ms * ClockSpeed`. Raising
ClockSpeed does not run more steps; it makes each step cover more simulated
time.

The conclusion happened to survive - a high ClockSpeed does damage results -
but for the opposite mechanical reason to the one given. Corrected across five
files, and `VALIDATION.md` carries the correction explicitly rather than
overwriting the wrong claim quietly:

> **Correction to an earlier claim in this document.** It previously said
> FastPhysics uses a fixed-step integrator. That is wrong, and the truth is
> close to the opposite.

**Lesson: an agent's confidence is uncorrelated with its correctness, and it
will restate an unverified claim as often as you let it.**

### 4.2 Fabricated precision, caught by a tool

Writing the regression pins, the agent typed expected values to ten decimal
places having only ever measured four. Twelve of thirty-six pins reported
CHANGED on the first run - against code nobody had modified.

The deltas were around 1e-5, small enough to have been waved away as floating
point. They were not floating point. They were invented digits.

Recorded in `test_regression_pinned.py:91-102` rather than quietly fixed:

> That is the failure mode this whole project exists to name: a number quoted
> to more precision than its source supports.

**Lesson: build the check that catches the agent before you need it. This one
earned its place on its first execution, against its own author.**

### 4.3 A human intuition that was half right

A human challenged whether `simSetWind()` could work at runtime, believing wind
had to come from `settings.json` and required a simulator restart.

Half right. `settings.json` wind genuinely does require a restart - and
`simSetWind()` writes the same variable the settings loader seeds
(`SimModeWorldBase.cpp:76` and `:137` both route to
`physics_engine->setWind()`). The agent traced the full RPC chain to answer it.

Then it was settled empirically anyway: in `wind_demo.py` the aircraft tilted,
saturated and was carried 290 m downwind with no restart. `PREDICTIONS.md`
records both the source reading and the measurement, because "source reading is
evidence, not proof, and the installed server binary is what actually answers."

**Lesson: a wrong challenge is still valuable. It converted an assertion into a
traced chain plus a measurement.**

### 4.4 A green table that meant nothing

An agent-produced sensitivity table showed a 20 percent change in every
parameter moving hover endurance by exactly 0.0 percent. It looked like
robustness. It was the calibration silently re-fitting and absorbing each
perturbation, so the table could only ever print zeros.

Caught by reading the output rather than the code. The fix runs it with nothing
fitted, and the self-test now explains that the all-zeros version was the fit
hiding the sensitivity.

**Lesson: a plausible-looking table is the easiest thing for an agent to
produce and the hardest thing to eyeball. Ask what result would be impossible,
then check whether you are looking at it.**

---

## 5. What the agent was not permitted to do

- **Invent a parameter value.** `STANDARDS.md` section 5 forbids it, the
  schema makes a declared gap structurally distinct from a present value, and
  two of three catalog entities are consequently stubs the tooling refuses to
  model. The board reads "1 of 3 modelable" and that is the honest number.
- **Widen a tolerance to turn a row green.** The cruise anchor misses by
  +14.2% and ships that way.
- **Invent a predictor to fill an empty row.** `max_wind_resistance_ms` reads
  UNSCORED, because a predictor is a new falsifiable claim and must be
  pre-registered before it is run.
- **Raise a readiness claim to make a test pass.** Computed tier versus
  declared tier is asserted by `test_catalog.py`.
- **Auto-update a regression pin.** `--update-pins-dry-run` prints and never
  writes.

---

## 6. Honest limits of this account

This document is written from a single project by the people who ran it, which
is the weakest possible evidence base. Three things it does not establish:

1. **It is not a controlled comparison.** Nobody built this repository by hand
   alongside, so "the agent was faster" is an impression, not a measurement.
2. **The catches in section 4 are the ones that were found.** An unknown number
   were not. Three of the four were caught by a tool or a direct challenge, not
   by reading the agent's output carefully - which suggests reading carefully is
   the weakest link in the loop, not the strongest.
3. **The practices are not validated at scale.** They were exercised on one
   entity with a complete record and two stubs. Whether they survive fifty
   entities and several contributors is untested.

The one claim worth making: **every number in this repository can be traced to
either a citation, a measurement, or an explicit statement that it is an
estimate** - and where that failed, in section 4.2, a check caught it and the
failure is on the record rather than quietly repaired.
