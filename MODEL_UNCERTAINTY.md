# MODEL_UNCERTAINTY.md - structural uncertainty in the power model

`VALIDATION.md` covers whether the model's *parameters* are defensible.
This document covers whether its *structure* is - a different question, and
the one an SME reaches faster.

It records a real defect in the shipped model, quantifies what that defect
costs, explains why the model was **not** changed to fix it, and pre-registers
the change as P9 so it can be adopted honestly rather than retrofitted.

Short version: the pre-registered cruise failure (P6, +14.2%) is mostly a
model-structure artifact rather than the optimistic calibration it was
attributed to, and the finding came out of asking what a rotorcraft engineer
would object to first.

---

## 1. The defect: one parameter doing another's job

`battery_model.py` computes induced shaft power as:

```python
induced_shaft_w = thrust_n * v_i / self.figure_of_merit      # FM = 0.65
```

Two distinct quantities are being conflated.

| Quantity | Definition | Typical value |
|---|---|---|
| **Figure of merit**, FM | ideal hover power / **actual** hover shaft power - losses already included | 0.70-0.80 |
| **Induced power factor**, kappa | actual induced power / ideal induced power; corrects for non-uniform inflow, tip loss and swirl | 1.10-1.20 |

The code applies FM as a divisor on induced power *and then adds a separate
profile-power term*. But FM's denominator already contains profile losses, so
they are counted twice. And the effective factor being applied is

```
kappa_effective = 1 / 0.65 = 1.538
```

which sits well outside the physical range for kappa.

The parameter is carrying figure of merit's **name** and figure of merit's
**value** while occupying the induced power factor's **position** in the
equation. That is the defect. It is a common one, and it is the first thing a
reviewer who knows rotorcraft will look for.

---

## 2. What it costs

Hover is unaffected, because profile power is the single fitted parameter and
absorbs the change exactly - hover power is 115.50 W in every row below. The
distortion appears only in forward flight, because **induced power falls with
airspeed while profile power rises**. Over-weighting the falling term makes the
model too optimistic in cruise.

Spec profile, hover-calibrated, cruise anchor 46.0 min and range anchor 30 km
both held out:

| FM | kappa_eff | fitted profile | cruise (min) | vs anchor | range (km) | vs anchor |
|---|---|---|---|---|---|---|
| **0.650** | 1.538 | 20.018 W | 52.548 | **+14.24%** | 38.081 | **+26.94%** |
| 0.750 | 1.333 | 28.069 W | 48.914 | +6.34% | 34.671 | +15.57% |
| 0.833 | 1.200 | 33.300 W | 46.811 | +1.76% | 32.765 | +9.22% |
| **0.870** | **1.149** | 35.266 W | **46.067** | **+0.14%** | 32.102 | +7.01% |
| 0.909 | 1.100 | 37.227 W | 45.347 | -1.42% | 31.467 | +4.89% |

At kappa = 1.15 the cruise anchor essentially lands. On the operational
profile - the actual planning product - the effect is just as large:

| | hover | cruise | vs observed 30-35 min |
|---|---|---|---|
| FM = 0.650 as shipped | 28.814 min | 37.852 min | **outside the band** |
| kappa = 1.15 | 28.814 min | 33.184 min | **inside the band** |

So the correction moves the planning figure from missing independent
measurement to matching it.

---

## 3. The deeper problem: the hover anchor cannot separate the two terms

This is the part worth understanding, because it explains why the defect
survived calibration undetected.

The hover anchor pins **total** shaft power and says nothing about its split:

```
  77 Wh / 40 min                        = 115.500 W electrical
  minus 15 W avionics, times eta 0.80   =  80.400 W of shaft power
  ideal induced power at hover          =  39.249 W
```

80.400 W is fixed by the anchor. How it divides between induced and profile is
entirely unconstrained by hover data:

| kappa | induced | profile | profile as % of shaft |
|---|---|---|---|
| 1.538 (as shipped) | 60.382 W | 20.018 W | **24.9%** |
| 1.200 | 47.100 W | 33.300 W | 41.4% |
| 1.150 | 45.134 W | 35.266 W | **43.9%** |
| 1.100 | 43.173 W | 37.227 W | 46.3% |

Profile power for a small electric multirotor is typically **20-35%** of hover
shaft power. So:

- **kappa = 1.538** gives a plausible profile share (24.9%) with an
  implausible kappa.
- **kappa = 1.15** gives a plausible kappa with an implausible profile share
  (43.9%).

**Neither configuration is physically coherent.** The model cannot satisfy a
defensible kappa, a defensible profile fraction, and the 40-minute hover anchor
simultaneously - which means some *other* parameter is absorbing the
discrepancy, and with one fitted parameter there is no way to tell which from
hover data alone.

That is a structural identifiability problem, not a tuning problem.

### What the held-out anchor is actually telling us

Cruise discriminates where hover cannot, because the two terms scale
differently with airspeed. And cruise says kappa = 1.15 (+0.14%) over
kappa = 1.538 (+14.24%).

This is a more interesting result than a pass would have been: **the held-out
anchor is informative about model structure, not merely about accuracy.** The
+14.2% miss was not the model being uniformly optimistic - it was the
induced/profile split being wrong, in a way only forward flight could reveal.

### The most likely resolution

If avionics power is the term absorbing the error, both quantities become
plausible at once:

| avionics | shaft total | profile at kappa=1.15 | profile % of shaft |
|---|---|---|---|
| 15 W (current estimate) | 80.400 W | 35.266 W | 43.9% |
| 25 W | 72.400 W | 27.266 W | 37.7% |
| **30 W** | 68.400 W | 23.266 W | **34.0%** |

At roughly 30 W of avionics load, kappa = 1.15 and a 34% profile share are both
inside their expected ranges and the hover anchor is still met exactly.

Avionics power is recorded in the entity file as `confidence: "estimated"`, and
the sensitivity table shows hover endurance moving -2.5% per +20% on it. It is
the weakest load-bearing parameter in the record, and this analysis says it is
probably too low by a factor of two.

**The next measurement worth taking is hover current draw.** The Mini 4 Pro
stub's `avionics_power_w` todo already says so, for a different reason.

---

## 4. Why the shipped model was not changed

Changing FM from 0.65 to 0.87 would move P6 from a +14.2% FAIL to a +0.1%
PASS.

**That change was deliberately not made.**

P6 was pre-registered before any test ran, published, and pushed. Retuning a
parameter after seeing the result, in order to turn a recorded failure into a
pass, is precisely the behaviour `PREDICTIONS.md` exists to prevent - rule 1,
and the reason the fitted anchor reports `CALIBRATED` rather than `PASS`. A
register that can be satisfied after the fact is not a register.

The correct route is to pre-register the change and then make it, which is
section 5. Until that resolves:

- **P6 stands at +14.2% FAIL**, as recorded.
- Every published figure stays pinned in `test_regression_pinned.py`. This
  analysis moved nothing; all 36 pins hold.
- The shipped model keeps FM = 0.65, and `battery_model.py` now carries a
  pointer to this document at the line in question.

---

## 5. P9, pre-registered

See `PREDICTIONS.md`. In summary: adopting an explicit `induced_power_factor`
of 1.15, *together with* a measured avionics load, should bring the held-out
cruise anchor within +/-5% while keeping hover exact and the implied profile
share inside 20-35%.

P9 **cannot be resolved yet.** It depends on a hover current-draw measurement
that does not exist. That is the honest state: the fix is identified, its
expected effect is written down in advance, and it is blocked on data rather
than on effort.

---

## 6. Two smaller items, quantified

Both are minor. They are recorded because "minor" should be a measured claim.

**Parasitic power is divided by a propulsive efficiency of 0.70.** That is a
fixed-wing propeller idiom; on a multirotor the tilted rotor already produces
the force that overcomes airframe drag. At 9 m/s it inflates the parasitic term
from 4.465 W to 6.379 W, **+42.9%** - but parasitic is only 7.26% of the 87.92 W
cruise total, so removing it would change total cruise power by **2.18%**.
Left in place pending P9 rather than changed piecemeal.

**Induced power uses the tilted thrust while parasitic is added separately.**
Strictly a double-count: the standard rotorcraft decomposition computes induced
power from the *lift* component and adds `D*V` separately. At 9 m/s, weight is
8.7770 N and tilted thrust is 8.7910 N, an overstatement of **0.160%**.
Negligible, and quantified here so the answer exists if asked.

---

## 7. What would settle all of this

One measurement and one bench test, in priority order:

1. **Hover current draw** at a known battery voltage. Resolves avionics power,
   which this analysis fingers as the parameter absorbing the structural error,
   and unblocks P9.
2. **Static thrust and torque against RPM** for the propeller. Yields C_T and
   C_P directly, and with them the profile power at hover - which would remove
   the fitted parameter entirely and make every anchor held out.

The second one is what turns this from a calibrated model into a predictive
one. It is also the point at which `calibration="none"` would become the
default rather than a comparison mode.

---

## Appendix: a claim this analysis retracts

`VALIDATION.md` previously reported that with `calibration="none"` - nothing
fitted - the model predicts 40.04 min hover against a published 40, and offered
this as evidence that "the momentum-theory parameter set is independently
reasonable."

**That claim is withdrawn.** At kappa = 1.15 the same unfitted mode gives
51.313 min, an error of **+28.3%**. The agreement at FM = 0.65 was the inflated
kappa cancelling against the `0.33 * ideal_induced` profile-power heuristic -
two errors of opposite sign, not independent corroboration.

A result that good from a model with no free parameters should have prompted
more suspicion at the time than it did. Two compensating errors are the usual
explanation for an unexpectedly exact fit, and that is what this was.
