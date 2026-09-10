# START HERE

A simulation entity catalog for small UAS, built against Cosys-AirSim 3.4.1 /
Unreal Engine 5: a physics-based endurance model, a coverage tracker that
reports its own gaps, and a test suite built so that its tests can fail.

**This page is four minutes. Everything else is optional.**

---

## The three findings

### 1. The simulated aircraft is not a Mavic 3

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

### 2. A failure was predicted in advance, and it failed on cue

Eight predictions were frozen in `PREDICTIONS.md` before any test ran. **P6 was
registered as an expected FAIL**: the model, calibrated on the hover anchor
only, should overshoot DJI's published 46-minute cruise figure by 10 to 25%.

It came in at **+14.2%** (52.55 min). Max range also fails, at +26.9%. Both
ship that way.

Predicting the direction and size of your own model's error before measuring it
is stronger evidence of understanding than a green board - so the fitted anchor
reports `CALIBRATED`, never `PASS`, because an anchor that cannot fail is not
worth scoring.

### 3. A coefficient recovered from behaviour matched one read from source

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

## Run it in 60 seconds

No simulator, no install, standard library plus numpy:

```bash
python catalog.py                  # coverage board - what exists and what does not
python test_regression_pinned.py   # 36 published figures, unmoved
python battery_model.py            # the model's own self-test
```

The first one prints the honest state of the catalog:

```
  UAS-QUAD-DJI-MAVIC3     16/16  100%   R3 VALIDATED
  UAS-QUAD-DJI-MINI4PRO    6/16   38%   R0 STUB
  UAS-QUAD-SKYDIO-X2D      6/16   38%   R0 STUB

  Modelable (R1 or better) : 1
  THIS CATALOG IS THIN. 2 of 3 entities cannot produce any number at all.
```

Two entities hold no sourced aircraft data, the tooling refuses to model them,
and they were deliberately **not** filled with plausible values. A board
reading "3 of 3" on invented data would be worth nothing, because nothing on it
could be acted on. Point a test at one and it refuses rather than hedging:

```
$ python test_3a_hover.py --entity UAS-QUAD-SKYDIO-X2D
ERROR: ... it is R0 STUB. Missing required parameters: physical.mass_kg,
physical.propeller_diameter_m, battery.capacity_wh (+7 more...). Refusing to
produce a number from an incomplete record.
```

---

## Where to go next

| If you want | Read | Time |
|---|---|---|
| The VV&A case: layer model, calibration discipline, defects, limitations | [VALIDATION.md](VALIDATION.md) | 18 min |
| The pre-registration and all eight results | [PREDICTIONS.md](PREDICTIONS.md) | 13 min |
| How to add an entity - the tradecraft, written for a person or an AI agent | [STANDARDS.md](STANDARDS.md) | 9 min |
| How this was built with an AI agent, and four times the agent was wrong | [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) | 8 min |
| Environment, file map, run instructions | [README.md](README.md) | 11 min |

**Reviewing in 15 minutes?** This page, then `VALIDATION.md` sections 1-3.
Section 3 is the defect analysis of the prior iteration of this work and is the
part I would want read.

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
