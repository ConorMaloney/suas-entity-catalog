# START HERE

A **simulation entity catalog** for small UAS: a schema with enforced
requirement classes, an agent-directed research pipeline, an automated
validation suite, and a readiness gate that refuses to produce a number from an
incomplete record.

The catalog feeds a physics-based endurance model built against Cosys-AirSim
3.4.1 / Unreal Engine 5. **The model is the consumer. The catalog and the
process that keeps it honest are the subject.**

**This page is seven minutes. Everything else is optional.**

---

## The four findings

### 1. The catalog reports its own gaps, and refuses to model what it cannot

```
  UAS-QUAD-DJI-MAVIC3     16/16  100%   P20 D1 L8 E4   R3 VALIDATED
  UAS-QUAD-SKYDIO-X2D      8/16   50%   P8  D0 L5 E0   R0 STUB
  UAS-QUAD-DJI-MINI4PRO    6/16   38%   P2  D0 L4 E0   R0 STUB

  Modelable (R1 or better) : 1 of 3
  Segment coverage         : 3 of 12 planned entities, across 4 segments
```

Every entity carries a readiness tier **computed from its record**, not
asserted by it - and `test_catalog.py` fails the build if a file claims a tier
higher than it earns. Below R1 the tooling raises rather than returning a
hedged number:

```
$ python test_3a_hover.py --entity UAS-QUAD-SKYDIO-X2D
ERROR: ... it is R0 STUB. Missing required parameters: physical.mass_kg,
physical.propeller_diameter_m, battery.capacity_wh (+7 more...). Refusing to
produce a number from an incomplete record.
```

The board reports gaps against **declared intent**, not just against what
exists - `coverage_plan.json` names 12 planned entities across 4 segments, two
of which contain nothing at all. A catalog that only reports what it contains
cannot report a hole in itself.

No stub was filled with a plausible value. [STANDARDS.md](STANDARDS.md) is the
governing document, written to be followed by a person or an AI agent.

### 2. Agent-directed production, with a gate a human actually has to walk through

Entities are built by an AI agent through four stages:

```
   DIRECT  ->  RESEARCH  ->  VALIDATE  ->  PROMOTE
   binding     research      frozen        human review
   rules       log           test suite    of every gap
```

The Skydio X2D went through all four. What came out:

- **A research log** (`drafts/*.research.md`, 5.3k words) recording, per field,
  the searches run, the sources rejected and why, and the decision taken.
- **A record** where every value carries `value_as_published`, `confidence`,
  `source`, `source_url` and a **verbatim `source_quote`** - and where
  conflicting sources are preserved side by side rather than averaged.
- **A frozen validation suite** (`catalog/tests/*.yaml`, 77 tests) run by
  `run_validation.py`, which reads only the record, the schema and the suite -
  no network, no other record.
- **A human review** ([catalog/reviews/](catalog/reviews/)) adjudicating all
  **9 gaps** the suite declared not automatable.

The suite's most important output is not its 55 passes. It is the 9 **gaps** -
tests that explicitly say *a machine cannot decide this, a person must*. They
cover whether a quote is authentic, whether a value came from the declared
configuration, whether tooling silently infers a field. Of the 9: four closed on
evidence, one settled by decision, two deferred, one split, and **one -
XF-014 - still blocks promotion**.

**The X2D was not promoted.** It remains R0.

### 3. A failure was predicted in advance, failed on cue, and was then diagnosed

Predictions are frozen in `PREDICTIONS.md` before any test runs - twelve
registered to date, P1 through P10c. **P6 was
registered as an expected FAIL**: the model, calibrated on the hover anchor
only, should overshoot DJI's published 46-minute cruise figure by 10 to 25%.

It came in at **+14.2%**. Max range also fails, at +26.9%. Both ship that way.

The fitted anchor reports `CALIBRATED`, never `PASS`, because an anchor that
cannot fail is not worth scoring.

**The miss was then traced to its cause.** The model's `figure_of_merit`
occupies the position of the induced power factor kappa while carrying figure
of merit's name and value. Correcting it brings cruise to +0.14% - and the
correction was **deliberately not applied**, because retuning a parameter to
turn a pre-registered failure into a pass is exactly what the register exists
to prevent. It is pre-registered instead, as P9.
[MODEL_UNCERTAINTY.md](MODEL_UNCERTAINTY.md) has the analysis, including a
claim it retracts.

### 4. The same discipline, applied to the physics

The catalog feeds a model, and the model was held to the same standard.

**The simulated aircraft is not a Mavic 3.** `VehicleType: SimpleFlight` routes
to `setupFrameGenericQuad` - a 1.0 kg F450-class quad on Phantom 2 propellers.
Mass, drag and rotor geometry are C++ compile-time constants no setting can
reach. So no simulator figure is a figure about a Mavic 3, and every number
carries a layer tag (L1 aircraft / L2 model / L3 simulator).

**A coefficient recovered from behaviour matched one read from source.**
Reading `MultiRotorPhysicsBody.hpp` gives an effective CdA_y of 0.011676 m2,
written down before any test existed. A wind sweep then fitted it from observed
tilt alone: **0.011476 m2, error -1.71%, r2 = 1.0000**. Nothing was tuned to
make those agree, and a negative control confirms the test can fail - feed it a
drag law 1.6x off and it goes red at +60%.

---

## Run it in one minute

No simulator, no install, standard library plus numpy:

```bash
PY="C:/Users/black/AppData/Local/Python/pythoncore-3.14-64/python.exe"

"$PY" catalog.py                  # the coverage board above
"$PY" test_catalog.py             # 9 structural checks, including that the gate refuses
"$PY" test_regression_pinned.py   # 36 published figures, unmoved
"$PY" battery_model.py            # the model's own self-test
```

All four exit 0 and need nothing running.

---

## Where to go next

| If you want | Read | Time |
|---|---|---|
| **How an entity gets built and reviewed** - prompt patterns, the review loop, seven times the agent was wrong | [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) | 11 min |
| **How to add an entity** - the tradecraft, written for a person or an AI agent | [STANDARDS.md](STANDARDS.md) | 9 min |
| **A gate being walked** - 9 gaps adjudicated, with what blocked promotion | [catalog/reviews/](catalog/reviews/) | 9 min |
| The VV&A case: layer model, calibration discipline, defects, limitations | [VALIDATION.md](VALIDATION.md) | 18 min |
| Where the model's *structure* is weak, and the defect found in it | [MODEL_UNCERTAINTY.md](MODEL_UNCERTAINTY.md) | 7 min |
| The pre-registration, every result, and two recorded corrections | [PREDICTIONS.md](PREDICTIONS.md) | 14 min |
| Environment, file map, run instructions | [README.md](README.md) | 11 min |

**Reviewing in 15 minutes?** This page, then `AGENT_WORKFLOW.md` sections 2-4 -
the pipeline, the review loop, and the seven recorded times the agent was caught
being wrong.

**Reviewing as an engineer?** [MODEL_UNCERTAINTY.md](MODEL_UNCERTAINTY.md),
where the model is picked apart - including the finding that the hover anchor
cannot separate induced from profile power at all.

---

## Why there are simulation scripts in a catalog repository

Because a catalog of entity parameters is only worth something if the
parameters do something, and the only way to find out whether a record is any
good is to run it through a model and compare against reality.

`battery_model.py` is that model. `test_3a_hover.py`, `test_3b_wind.py`,
`wind_demo.py` and `probe_sim_capabilities.py` are how its claims were tested
against a simulator rather than asserted. They produced findings 3 and 4 above,
and they are the reason the catalog's requirement classes are drawn where they
are: the sensitivity analysis showing mass and rotor diameter dominate is why
those two are `REQUIRED_MEASURED` and may not be estimated, while figure of
merit is `REQUIRED_MODELING` and may.

The scripts are evidence, not the subject. If you are short on time, they are
the part to skip.

---

## Results, in full

| ID | Prediction | Result |
|---|---|---|
| P1 | Sim CdA_y = 0.011676 m2 | **PASS** -1.71%, r2 = 1.0000 |
| P2 | Tilt 1.044 / 5.995 deg at 5 / 12 m/s | **PASS** -1.3%, -1.8% |
| P3 | Wind energy penalty below 0.5% | **PASS** 0.0162% |
| P4 | No translational lift in AirSim | **PASS** +2.84% |
| P5 | Sim air density 1.225 kg/m3 | **PASS** -0.02% |
| P6 | Model overshoots cruise by 10-25% | **FAIL +14.2% - as pre-registered** |
| P7 | Sim T/W 1.705, hover throttle 58.7% | **PASS** |
| P8 | Station-keeping breaks down at 29.7 m/s | **PASS** - observed bracket 25-30 m/s |
| P9 | kappa = 1.15 plus a measured avionics load brings cruise within +/-5% | **PENDING** - blocked on a measurement, not on effort |

P8's prediction was committed and pushed to GitHub **before** the test that
resolves it was ever run, so its ordering is witnessed by the remote rather
than asserted by the document. P1-P7 are self-attested; `PREDICTIONS.md` draws
that distinction explicitly rather than claiming all nine are proven.

---

## What is not done

- **The catalog is thin.** The tooling and the process generalise; the content
  does not yet. Every gap carries a `todo` naming what would close it, so
  `python catalog.py --entity <id>` is the work queue.
- **One gap still blocks the X2D.** The record passed through a wrong variant
  twice (see the escalation in the record). Until every value is re-confirmed
  against an X2D source, no figure from it may be quoted.
- **The X2D may be permanently unpromotable.** Skydio publishes no hover
  endurance figure, and that field is the calibration anchor - a
  `REQUIRED_MEASURED` field, which may not be estimated. Whether the catalog
  accepts a `derived` anchor or accepts that some platforms stay R0 is an open
  policy question, not a research task.
- **Two schema defects are logged, not fixed** - the R3 staleness limit is
  referenced but never defined, and the `range` value shape is undeclared.
  Neither affects a current record.
- **Fixed-wing segments cannot be populated at all** until a second energy
  model exists. Listed as a gap in `coverage_plan.json` rather than omitted.
- **The simulator still flies the wrong airframe**, and fixing it means
  rebuilding the plugin. Out of scope here.
