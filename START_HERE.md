# START HERE

A simulation entity catalog for small UAS, built against Cosys-AirSim 3.4.1 /
Unreal Engine 5: a physics-based endurance model, a coverage tracker that
reports its own gaps, and a test suite built so that its tests can fail.

**This page is six minutes. Everything else is optional.**

---

## The four findings

### 1. The catalog reports its own gaps, and refuses to model what it cannot

```
  UAS-QUAD-DJI-MAVIC3     16/16  100%   R3 VALIDATED
  UAS-QUAD-DJI-MINI4PRO    6/16   38%   R0 STUB
  UAS-QUAD-SKYDIO-X2D      6/16   38%   R0 STUB

  Modelable (R1 or better) : 1
  THIS CATALOG IS THIN. 2 of 3 entities cannot produce any number at all.
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

The two stubs were deliberately **not** filled with plausible values. A board
reading "3 of 3" on invented data could not be acted on; this one can.
[STANDARDS.md](STANDARDS.md) is the governing document, written to be followed
by a person or an AI agent.

### 2. The simulated aircraft is not a Mavic 3

`settings.json` declares `"VehicleType": "SimpleFlight"`, which routes to
`setupFrameGenericQuad` - a **1.0 kg F450-class quad on Phantom 2 propellers**,
against the Mavic 3's 0.895 kg and 0.2388 m. Mass, drag, rotor count and
propeller geometry are **C++ compile-time constants**; `AirSimSettings.hpp`
has no key for any of them.

So no endurance figure from the simulator is a figure about a Mavic 3. The
project is built around that: the parametric model does the energy physics and
is validated against published aircraft data, while the simulator supplies a
trustworthy timebase, attitude and an independently computed air density - and
is tested on those. Every number carries a layer tag (L1 aircraft / L2 model /
L3 simulator) so the two can never be confused.

### 3. A failure was predicted in advance, failed on cue, and was then diagnosed

Eight predictions were frozen in `PREDICTIONS.md` before any test ran. **P6 was
registered as an expected FAIL**: the model, calibrated on the hover anchor
only, should overshoot DJI's published 46-minute cruise figure by 10 to 25%.

It came in at **+14.2%** (52.55 min). Max range also fails, at +26.9%. Both
ship that way.

Predicting the direction and size of your own model's error before measuring it
is stronger evidence of understanding than a green board - so the fitted anchor
reports `CALIBRATED`, never `PASS`, because an anchor that cannot fail is not
worth scoring.

**The miss was then traced to its cause.** The model's `figure_of_merit`
occupies the position of the induced power factor kappa while carrying figure
of merit's name and value, giving an effective kappa of 1.538 against a
physical 1.10-1.20. Correcting it brings cruise to +0.14% - and the correction
was **deliberately not applied**, because retuning a parameter to turn a
pre-registered failure into a pass is exactly what the register exists to
prevent. It is pre-registered instead, as P9, blocked on a measurement.
[MODEL_UNCERTAINTY.md](MODEL_UNCERTAINTY.md) has the analysis, including a
claim it retracts.

### 4. A coefficient recovered from behaviour matched one read from source

The simulator exposes no drag model through its API. But the C++ is readable:
matching `MultiRotorPhysicsBody.hpp` against `F = 0.5 rho CdA v^2` gives an
effective **CdA_y = 0.011676 m2**, derived and written down before any test
existed.

Test 3.b then flew a wind sweep, read the tilt the aircraft held at each speed,
and fitted the coefficient from observed behaviour alone:

```
  fitted CdA_y  0.011476 m2      error -1.71%      fit r2 = 1.0000
```

Nothing was tuned to make those agree, and the fit is constrained through the
origin so it has no free intercept to absorb an error with. A negative control
confirms the test can fail: feed it a drag law 1.6x off and it goes red at +60%.

---

## Run it in one minute

No simulator, no install, standard library plus numpy. On the machine this was
built on, Python 3.14 is **not on PATH** - substitute your own interpreter:

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
| The VV&A case: layer model, calibration discipline, defects, limitations | [VALIDATION.md](VALIDATION.md) | 18 min |
| Where the model's *structure* is weak, and the defect I found in it | [MODEL_UNCERTAINTY.md](MODEL_UNCERTAINTY.md) | 7 min |
| The pre-registration and all eight results | [PREDICTIONS.md](PREDICTIONS.md) | 13 min |
| How to add an entity - the tradecraft, written for a person or an AI agent | [STANDARDS.md](STANDARDS.md) | 9 min |
| How this was built with an AI agent, and four times the agent was wrong | [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) | 8 min |
| Environment, file map, run instructions | [README.md](README.md) | 11 min |

**Reviewing in 15 minutes?** This page, then `VALIDATION.md` sections 1-3 -
the defect analysis of the prior iteration, with the evidence preserved in
`prior_work/` so the claims can be checked.

**Reviewing as an engineer?** [MODEL_UNCERTAINTY.md](MODEL_UNCERTAINTY.md).
It is where the model is picked apart, including the finding that the hover
anchor cannot separate induced from profile power at all.

---

## Results, in full

| ID | Prediction | Result |
|---|---|---|
| P1 | Sim CdA_y = 0.011676 m2 | **PASS** -1.71%, r2 = 1.0000 |
| P2 | Tilt 1.044 / 5.995 deg at 5 / 12 m/s | **PASS** -1.3%, -1.8% |
| P3 | Wind energy penalty below 0.5% | **PASS** 0.0162% |
| P4 | No translational lift in AirSim | **PASS** +2.51% |
| P5 | Sim air density 1.225 kg/m3 | **PASS** -0.02% |
| P6 | Model overshoots cruise by 10-25% | **FAIL +14.2% - as pre-registered** |
| P7 | Sim T/W 1.705, hover throttle 58.7% | **PASS** |
| P8 | Station-keeping breaks down at 29.7 m/s | **PASS** - observed bracket 25-30 m/s |
| P9 | kappa = 1.15 plus a measured avionics load brings cruise within +/-5% | **PENDING** - blocked on a measurement, not on effort |

P8's prediction was committed and pushed to GitHub **before** the test that
resolves it was ever run, so its ordering is witnessed by the remote rather
than asserted by the document. P1-P7 are self-attested; `PREDICTIONS.md` draws
that distinction explicitly rather than claiming all eight are proven.

---

## What is not done

- **The catalog is thin.** The tooling generalises; the content does not yet.
  Two entities are stubs. Every gap in them carries a `todo` naming what would
  close it, so `python catalog.py --entity <id>` is the work queue.
- **The simulator still flies the wrong airframe.** Fixing it means adding
  `setupFrameMavic3()` to the plugin and rebuilding - the only route to a
  simulator that actually flies a Mavic 3, and out of scope here.
- **Fixed-wing segments cannot be populated at all** until there is a second
  energy model. Momentum theory has no fixed-wing equivalent. Listed as a gap
  in `coverage_plan.json` rather than quietly omitted.
- **`max_wind_resistance_ms`** is a declared held-out anchor with no predictor,
  so it reports `UNSCORED`. Inventing one to fill the row would be a new
  falsifiable claim requiring pre-registration first.
