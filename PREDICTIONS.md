# PREDICTIONS.md - Pre-registration

**Frozen 2026-09-09, before any simulator run.**

Every number below was derived either from the Cosys-AirSim C++ source or
from published Mavic 3 specification, and written down **before** the
corresponding test was executed. Acceptance bands were set at the same time.

## Why this file exists

The briefed tests, as originally structured, could not fail.

`battery_model.py` is a pure function of time and velocity, and AirSim
simulates no battery at all - a case-insensitive search of the whole
`cosysairsim` package returns zero matches for `battery`, `power`, `mass` or
`drag`. So "hover energy" is `P_hover * t`, and checking that the pack empties
at the specification endurance is checking that `77 / 115.5 = 0.667 h`. That is
arithmetic wearing a lab coat, and it will report PASS forever regardless of
what the simulator does.

The defence against that is not a better tolerance. It is committing to the
number in advance, in writing, and then letting the measurement disagree.

## Provenance of this register - what is checkable and what is not

Pre-registration is only worth something if the ordering can be verified. A
document asserting its own priority is the document vouching for itself, and a
reader is entitled to ask how they would tell the difference between a
prediction and a postdiction. So this register states plainly which of its rows
are independently checkable and which rest on the author's word.

**P1 through P7** were written on 2026-09-09 and resolved on 2026-09-10. That
ordering is attested by file modification times and by the working record, but
NOT by this repository: version control was initialised after those runs had
already happened. Committing them now in an order that implied otherwise would
be manufacturing the very evidence this method exists to make unnecessary, so
it has not been done. Treat P1-P7 as self-attested.

**P8** is different. It was committed to version control **before
`wind_demo.py` had ever been run**, in a repository state that contains the
prediction and no corresponding result. The commit history therefore witnesses
the ordering independently of anything asserted here.

That distinction is the honest one, and it is drawn deliberately. A register
that claimed every row was proven would be making exactly the kind of
unverifiable assertion the register exists to prevent.

## Rules

1. Predictions are frozen before the run. This file is append-only for
   results; the prediction rows are never edited after the fact.
2. Bands are set from the physics, not from the observed spread.
3. A fitted anchor is reported `CALIBRATED`, never `PASS`. It cannot fail by
   construction, so scoring it would be dishonest.
4. **P6 is pre-registered as an expected FAIL.** Predicting the direction and
   magnitude of your own model's error before measuring it is stronger
   evidence of understanding than a green board.
5. Failures ship. A red result is a finding.

---

## The predictions

| ID | Prediction | Band | Source | Can fail? |
|---|---|---|---|---|
| **P1** | Simulator effective `CdA_y` identified from a tilt-vs-wind sweep = **0.011676 m2** | +/-15% | `MultiRotorPhysicsBody.hpp:190-217`, `FastPhysicsEngine.hpp:269-308` | yes |
| **P2** | Station-keeping tilt = **1.044 deg** at 5 m/s, **5.995 deg** at 12 m/s (y axis) | +/-20% | `tan(theta) = D/mg` | yes |
| **P3** | Thrust (hence energy) penalty between 0 and 5 m/s wind is **below 0.5%** (predicted 0.017%) | < 0.5% | thrust ratio `1/cos(theta)` = 1.000166 | yes |
| **P4** | Simulator rotor shaft power at 9 m/s is within **10%** of hover (predicted +0.22%) | +/-10% | `RotorParams.hpp:21-62` | yes |
| **P5** | `EnvironmentState.air_density` = **1.225 kg/m3** at sea level | +/-2% | ISA | yes |
| **P6** | L2 model calibrated on hover **only** predicts cruise endurance of **50-58 min** against DJI's 46 - an expected **+10 to +25% FAIL** | +10..+25% | momentum theory | yes |
| **P7** | Simulator thrust-to-weight = **1.705**; hover throttle **58.7%** | +/-5% | `calculateMaxThrust()`, `RotorActuator.hpp:125` | yes |

### Added 2026-09-10, before `wind_demo.py` was first run

Registered later than P1-P7 and labelled as such, because a register that
quietly absorbs new rows is not a register. P8 was written before the demo
executed.

| ID | Prediction | Band | Source | Can fail? |
|---|---|---|---|---|
| **P8** | Station-keeping breaks down at **29.7 m/s** (y axis) / **30.9 m/s** (x axis): below it the aircraft holds position, above it the controller saturates and it is blown downwind | observed transition brackets the prediction | `simple_flight/firmware/Params.hpp:80` | yes |

**Derivation.** simple_flight caps commanded roll and pitch in angle-level
mode at `Axis4r max_limit = Axis4r(pi/5.5f, pi/5.5f, pi, 1.0f)` - **32.73
degrees**. The comment on the line above says why: past roughly that angle the
vertical thrust component can no longer hold the vehicle up at control
extremities.

Station-keeping needs `tan(theta) = drag_factor * rho * v^2 / (m*g)`. Setting
`theta = 32.73 deg` and solving:

```
y axis: v = sqrt(tan(32.73 deg) / (0.005838 * 1.225 / 9.8067)) = 29.7 m/s
x axis: v = sqrt(tan(32.73 deg) / (0.005383 * 1.225 / 9.8067)) = 30.9 m/s
```

This is the only prediction in the set that is **visible to the naked eye**.
Below the threshold the aircraft sits still and tilts about a degree; above it,
it is carried away on screen.

### Added 2026-09-10, after diagnosing the induced-power formulation

Registered after P8 and labelled as such. P9 arises from
`MODEL_UNCERTAINTY.md`, which found that the model's `figure_of_merit`
parameter occupies the position of the induced power factor kappa while
carrying figure of merit's name and value, giving an effective kappa of 1.538
against a physical range of 1.10-1.20.

| ID | Prediction | Band | Source | Can fail? |
|---|---|---|---|---|
| **P9** | Adopting an explicit `induced_power_factor` of **1.15**, together with a **measured** avionics load, brings the held-out cruise anchor within **+/-5%** while hover stays exact and the implied profile-power share falls inside **20-35%** of hover shaft power | all three clauses must hold | Leishman, momentum theory; `MODEL_UNCERTAINTY.md` | yes |

**Why it is stated with three clauses.** Setting kappa = 1.15 alone already
brings cruise to +0.14%, so a single-clause version would be trivially
satisfiable and would prove nothing. The demanding part is the third clause:
at kappa = 1.15 with the *current* 15 W avionics estimate, the fitted profile
power implies a 43.9% profile share, which is outside the plausible range. Both
have to be true at once, and that requires the avionics figure to be wrong in
the direction this analysis predicts.

**P9 cannot be resolved yet, and is not pending on effort.** It needs a hover
current-draw measurement that does not exist. If that measurement comes back
near 15 W, P9 fails and the structural explanation in `MODEL_UNCERTAINTY.md`
is wrong - which is the point of writing it down before measuring.

**The shipped model was not changed to anticipate this.** FM stays at 0.65 and
P6 stands at +14.2% FAIL. Retuning a parameter after seeing a result, to turn a
pre-registered failure into a pass, is what rule 1 exists to prevent.

### Added 2026-09-10, BEFORE any DJI Mini 4 Pro specification was looked up

P10 is registered before the research it concerns. No Mini 4 Pro figure has
been read at the time of writing, and the commit containing this section
precedes the commit containing the entity record - so the ordering is witnessed
by the repository, as P8's was.

The purpose is to test whether the model **generalises to an airframe it was
never calibrated against**. Everything to date has been fitted and validated on
one aircraft. A sub-250 g quadcopter is roughly a quarter of the Mavic 3's mass
and the point where the induced/profile balance diagnosed in
`MODEL_UNCERTAINTY.md` should behave differently.

| ID | Prediction | Band | Can fail? |
|---|---|---|---|
| **P10a** | At the published flight-time test speed, the model predicts `P_hover / P_cruise` **below 1.0** for a sub-250 g quad - the translational-lift benefit **reverses sign** relative to the Mavic 3's 1.314 | 0.85 to 1.00 | yes |
| **P10b** | Consequently the held-out cruise anchor error is **NEGATIVE**, opposite in sign to the Mavic 3's +14.2% | -10% to -30% | yes |
| **P10c** | The completed record reaches **R2 MODELED**, not R3 | exact tier | yes |

**Derivation, from stated assumptions only.** With one parameter fitted to the
entity's own hover anchor:

```
  cruise_predicted = hover_published * (P_hover / P_cruise)
  cruise_error     = (hover_pub / cruise_pub) * (P_hover / P_cruise) - 1
```

Pack capacity cancels, so the prediction needs no battery data. Checked against
the Mavic 3: `P_hover/P_cruise = 1.3137`, and `(40/46) * 1.3137 - 1 = +14.24%`,
which reproduces the recorded P6 exactly.

Assumed airframe - **every value here is an assumption, not a looked-up spec**:
mass 0.249 kg (the regulatory class ceiling, definitional to the sub-250 g
category), four rotors of 0.1524 m, CdA 0.0035 m2, avionics 8 W, class-typical
efficiencies.

```
  hover induced velocity  3.696 m/s   (Mavic 3: 4.472)
  disk loading            33.5 N/m2   (Mavic 3: 49.0)

  cruise speed   P_h/P_c    error if published ratio is 40:46
      6.0 m/s     0.9881              -14.1%
      9.0 m/s     0.9193              -20.1%
     12.0 m/s     0.8161              -29.0%
```

**Why the sign reverses.** Hover power falls steeply with mass, but the
speed-dependent costs do not fall as fast. A smaller propeller has a lower tip
speed, so at the same airspeed the advance ratio is higher and profile power
grows faster; parasitic power still scales with the cube of speed; and the
fixed avionics load is a much larger share of a small aircraft's total. Past
some scale, cruising costs more than hovering, and the Mavic 3's
flight-time-exceeds-hover-time relationship should not hold.

**The main risk to this prediction is the propeller diameter**, which is
assumed. Sensitivity at 9 m/s: a 5 in propeller gives -15.8%, 6 in gives
-20.1%, 7 in gives -24.7%. CdA and avionics power barely matter (under 1.5%
across plausible ranges). The published test speed matters comparably.

**What would falsify it.** A positive cruise error, or a `P_hover/P_cruise`
above 1.0, means the sign does not reverse at this scale and the scaling
argument above is wrong. That is a live possibility: if DJI publishes the
flight-time figure at a low speed, say 6 m/s or below, the effect shrinks
towards zero and could stay positive.

**Interaction with P9.** The kappa conflation over-weights induced power, which
falls with airspeed, so it biases cruise predictions *upward*. On the Mavic 3
that produced the +14.2% overshoot. If P10b resolves negative, correcting kappa
would make it **more** negative, not less - so P9 and P10 are not independent,
and a future kappa correction has to be re-scored against both entities rather
than against the Mavic alone.

---

## Derivations

### P1 - effective CdA from the source

`MultiRotorPhysicsBody.hpp:190-217` builds per-axis drag factors;
`FastPhysicsEngine.hpp:269-308` applies
`drag_force = normal * (-drag_factor * air_density * v^2)`.

```
propeller_xsection = pi * D * h                = 0.007182 m2
left_right_area    = 0.180 * 0.040             = 0.007200 m2
linear_drag_coeff  = 1.3 / 4                   = 0.325
drag_factor_y = (0.007200 + 4 * 0.007182) * 0.325 / 2 = 0.005838
```

Since `drag_factor * rho * v^2` must equal `0.5 * rho * CdA * v^2`, the
effective `CdA = 2 * drag_factor`:

- **CdA_x = 0.010766 m2**
- **CdA_y = 0.011676 m2**

An independent literature estimate for a Mavic-class airframe gives
**0.010 m2**. Two unrelated derivations landing within 8-17% is corroboration,
not a fit.

### P2 - tilt required to hold station

```
drag(5 m/s)  = 0.005838 * 1.225 * 25  = 0.1788 N  ->  atan(0.1788/9.8067) = 1.044 deg
drag(12 m/s) = 0.005838 * 1.225 * 144 = 1.0299 N  ->  atan(1.0299/9.8067) = 5.995 deg
```

Mass is the simulator's 1.0 kg generic quad, not the Mavic's 0.895 kg.

### P3 - why wind cannot move the energy number

Thrust to hold station is `weight / cos(theta)`. At 5 m/s, `theta = 1.044 deg`,
so the thrust ratio is `1/cos(1.044 deg) = 1.000166` - an increase of
**0.017%**.

This makes briefed constraint #4 a quantified certainty rather than a
limitation to investigate: no experiment in this simulator can show wind
affecting endurance, because the effect is four orders of magnitude below
anything measurable. Any test that appears to show one is reporting an
artifact of its own model.

### P4 - AirSim has no translational lift

`RotorParams.hpp:21-62` computes `thrust = C_T * rho * n^2 * D^4`. Thrust
depends **only** on rotor speed. There is no airspeed term and no
induced-velocity term anywhere in the rotor model.

`RotorActuator.hpp:124-126` then gives `thrust = c * max_thrust`,
`speed = sqrt(c) * max_speed`, `torque = c * max_torque`, so shaft power
`P = torque * omega` scales as `c^1.5`, i.e. as `T^1.5`, with no airspeed
dependence at all.

At 9 m/s the aircraft tilts 3.12 deg to overcome 0.534 N of drag, raising
thrust from 9.807 N to 9.821 N and shaft power by **+0.22%**.

A real Mavic 3 goes the *other way*: DJI publishes 46 min of flight time
against 40 min of hover, because forward airspeed reduces induced velocity.
AirSim cannot reproduce that sign, let alone the magnitude. **Sim-derived
power therefore can never validate cruise endurance** - that physics must live
in the parametric model.

### P6 - the expected failure

The L2 model is calibrated on the hover anchor only; cruise is held out. Under
momentum theory, forward flight reduces induced power substantially, so the
model predicts a longer cruise endurance than DJI publishes. DJI's 46 min is
measured at a constant 9 m/s under ideal conditions, and includes real losses
the model does not carry.

The prediction is that the model overshoots by 10-25%. A result inside that
band confirms the model's structure is right and its absolute calibration is
optimistic. A result *outside* it - in either direction - is more interesting
than a pass.

### P7 - thrust-to-weight and hover throttle

```
max_thrust per rotor = 4.179446 N   ->   4 rotors = 16.7178 N
weight = 1.0 kg * 9.80665           =     9.8067 N
T/W = 1.7047
```

`RotorActuator.hpp:125` makes thrust **linear** in the control signal
(`output.thrust = control_signal_filtered * max_thrust`), so hover throttle is
`9.8067 / 16.7178 = 0.587`, i.e. **58.7%**.

---

## Results

Appended after runs. Prediction rows above are never edited.

### Resolved offline (no simulator required)

Run 2026-09-09 via `python battery_model.py`.

| ID | Predicted | Measured | Error | Status |
|---|---|---|---|---|
| **P6** | 50-58 min (+10..+25% FAIL) | **52.55 min** vs DJI 46 | **+14.2%** | **FAIL as predicted** |
| **P7** | T/W 1.705, throttle 58.7% | T/W **1.7047**, throttle **58.7%** | 0.0% | **PASS** (source-derived) |

P6 landed at +14.2%, inside the pre-registered +10 to +25% band. The model
overshoots DJI's cruise figure by the predicted amount and in the predicted
direction.

A further offline result worth recording, though it was not pre-registered:
with `calibration="none"` - every parameter from literature and specification,
nothing fitted at all - the model predicts **40.04 min** hover against DJI's
published 40. That agreement is not evidence of a good fit, because there is
no fit; it is evidence that the momentum-theory parameter set is independently
reasonable.

> **RETRACTED.** The claim in the paragraph above - that 40.04 min with nothing
> fitted shows the parameter set is independently reasonable - does not hold.
> `calibration="none"` still routes induced power through `figure_of_merit`
> standing in for kappa, so the agreement reflects two compensating errors
> rather than an unfitted model landing on the right answer. The paragraph is
> left as written because this register is append-only. See
> `VALIDATION.md` "The zero-free-parameter result - RETRACTED" and
> `MODEL_UNCERTAINTY.md` "Appendix: a claim this analysis retracts".

### Resolved against the running simulator - 2026-09-10

Executed by the operator. Probe at 00:22, tests 3.a and 3.b following.

| ID | Predicted | Measured | Error | Status |
|---|---|---|---|---|
| **P1** | CdA_y = 0.011676 m2 | **0.011476 m2** | **-1.71%** | **PASS** (band +/-15%) |
| **P2@5** | 1.0443 deg | **1.0306 deg** | **-1.3%** | **PASS** (band +/-20%) |
| **P2@12** | 5.9939 deg | **5.8877 deg** | **-1.8%** | **PASS** (band +/-20%) |
| **P3** | < 0.5% (predicted 0.017%) | **0.0162%** | - | **PASS** |
| **P4** | within 10% of hover (predicted +0.22%) | **+2.84%** (68.15 -> 70.08 W) | - | **PASS** |
| **P5** | 1.225 kg/m3 | **1.22478 kg/m3** | **-0.02%** | **PASS** |

The drag fit returned **r2 = 1.0000** across the 0/2/5/8/12 m/s sweep. The
identified drag factor, recovered purely from observed tilt angles, lands 1.7%
from a value computed by reading `MultiRotorPhysicsBody.hpp` before the test
existed. Nothing was tuned to make those agree.

**The probe also confirmed the rotor-state contract read from the C++.**
`rotor_keys` came back as `['speed', 'thrust', 'torque_scaler']` - exactly the
`MSGPACK_DEFINE_MAP(thrust, torque_scaler, speed)` in
`MultirotorRpcLibAdaptors.hpp:54`. The runtime check was still worth doing, but
the source reading was right.

**P4 note.** Measured +2.84% against a predicted +0.22%. Well inside the band,
but the discrepancy is real and comes from thrust: hover measured 9.930 N
against a theoretical 9.807 N, so the aircraft was doing more control work than
the idealised calculation assumes. The finding is unaffected - the sign is what
matters. A real Mavic 3 at 9 m/s costs **less** than hover; the simulator costs
**more**. AirSim cannot reproduce translational lift.

### CORRECTION 2026-09-11 - P4 was quoted from a disavowed run

**What was published.** P4 read **+2.51% (68.17 -> 69.88 W)** from
`results/test_3a_hover_20260910_003446.txt`. That run measured a **14.54x**
clock ratio and collected **41 samples** across 60 s of simulation time - one
sample per 1.47 simulated seconds.

**Why that was wrong.** This document already required otherwise. The caveats
recorded below state that "3.a should be re-run at ClockSpeed 1.0 before its
energy figures are quoted", and `VALIDATION.md` explains why: the integration
step is roughly `3 ms x ClockSpeed`, so a 14.54x run integrates in ~44 ms steps.
The figure was quoted anyway, in this file, in `README.md` and in
`START_HERE.md`.

**What it is now.** `results/test_3a_hover_20260910_053318.txt` is the
ClockSpeed **1.00x** re-run, 597 samples, and it had been sitting in `results/`
uncited since the day it was produced. It gives:

```
  hover  68.15 W      cruise (9 m/s)  70.08 W      difference  +2.84%
  total thrust  9.930 N hover / 10.114 N cruise
```

**What changes.** The number, and nothing else. P4 asked whether simulator
shaft power at 9 m/s stays within 10% of hover; +2.84% passes as comfortably as
+2.51% did, in the same direction, for the same reason. **No conclusion in this
register moves.** P5 is unaffected - both runs report air density 1.2248 kg/m3,
-0.02%.

**Why this is recorded rather than edited away.** A silent swap from +2.51% to
+2.84% would have left no trace that the project spent a day publishing a
figure its own method forbade. The failure here was not the measurement; it was
that nothing checked the published figures against the rule the documents
state. See `AGENT_WORKFLOW.md` section 5.7.

### Two caveats on the run itself

1. **ClockSpeed was not 1.0.** Test 3.a ran at a measured **14.54x** and 3.b at
   **3.00x**. Test 3.b's own header printed the warning. The tilt results are
   steady-state and survive this, but see the next point.
2. **Sample density collapsed in 3.a.** 41 samples across 60.17 s of simulation
   time - one sample per 1.47 sim-seconds - because the sampling loop sleeps in
   *wall* time while the sim clock runs 14.5x faster. Energy integration on 41
   points is coarse. The tilt and shaft-power results are steady-state averages
   and are not materially affected, but **3.a should be re-run at ClockSpeed
   1.0** before its energy figures are quoted.

### P8 - resolved 2026-09-10, after the prediction was pushed to GitHub

`wind_demo.py`, y axis, ClockSpeed 1.0. Full output in
`results/wind_demo_20260910_015456.txt`.

| wind m/s | predicted tilt | measured tilt | downwind travel | state |
|---|---|---|---|---|
| 0 | 0.00 | 0.00 | 0.0 m | HOLDS |
| 5 | 1.04 | 1.02 | 0.1 m | HOLDS |
| 12 | 5.99 | 5.78 | 0.6 m | HOLDS |
| 20 | 16.26 | 15.11 | 1.8 m | HOLDS |
| 25 | 24.50 | 24.47 | 6.2 m | HOLDS |
| 30 | 33.27 | **29.28** | 36.9 m | **BREAKAWAY** |
| 40 | 49.40 | **31.35** | 119.5 m | **BREAKAWAY** |
| 60 | 69.14 | **31.72** | 290.0 m | **BREAKAWAY** |

```
Highest wind still holding station : 25.0 m/s
Lowest wind causing breakaway      : 30.0 m/s
Predicted transition               : 29.7 m/s
```

**PASS.** The predicted transition falls inside the observed bracket, and all
8 stages matched their predicted hold/saturate classification.

**The mechanism is visible, not just the threshold.** Past the transition the
measured tilt stops tracking the prediction and asymptotes: 29.28, 31.35,
31.72 degrees, against the 32.73 degree commanded-tilt cap read from
`simple_flight/firmware/Params.hpp:80` before this test was written. Below
saturation the two agree to within 7%; above it they diverge *because* the cap
has been reached. Predicted **required** tilt and measured **achievable** tilt
are different quantities once the controller saturates, so the growing error in
the report's error column past 30 m/s is the confirmation rather than a miss.
The report's formatting does not currently make that distinction clear, which
is a presentation defect logged against `wind_demo.py`, not a result defect.

**Ordering is independently verifiable for this row.** Commit `5063d2f`
contained P8's prediction and `wind_demo.py`, and contained no
`results/wind_demo_*` file. It was pushed to
`github.com/ConorMaloney/suas-entity-catalog` before the demo was ever run.
GitHub holds the timestamp; it is not an assertion made by this document.

### Secondary result - runtime wind, settled empirically

Every wind change in the run above was applied with `simSetWind()` to an
already-flying aircraft: no simulator restart, no edit to `settings.json`. The
aircraft tilted, saturated and was carried 290 m downwind. Wind set through the
API reaches the physics engine at runtime.

This had been established by reading the source - `SimModeWorldBase.cpp:137`
and `:76` both route to `physics_engine->setWind()`, one from the API and one
from the settings loader - but source reading is evidence, not proof, and the
installed server binary is what actually answers. Now both agree.

`settings.json` wind remains a separate thing: it seeds the same variable at
startup and does require a restart to change.

```bash
python settings_helper.py --clock 1.0    # then RESTART the simulator
python wind_demo.py                      # P8
```

### Note on the anchor table shape, 2026-09-10

The catalog refactor made `validate_against_spec` data-driven, which surfaced
`max_wind_resistance_ms` - declared a held-out anchor in the Mavic's record
since the beginning, and never scored by any code. It now reports **UNSCORED**
with a stated reason rather than being silently absent, because an anchor
missing from a board is indistinguishable from one that passed.

So the validation output has four anchor rows instead of three, and held-out
**declared** is 3 rather than 2. **Scored is still 2, passed 0, failed 2.** No
result in this register moved: P6's cruise miss is unchanged at +14.2%, and
`test_regression_pinned.py` holds every numeric figure to 1e-8.

The anchor is deliberately not filled in. A wind-resistance predictor would be
a new falsifiable claim and rule 1 requires it to be frozen before it is run.
Inventing one to turn an UNSCORED row green is precisely the move this register
exists to prevent.

### Validation of the test procedure itself

Because the identification math can be checked without a simulator, it was:
synthetic tilt data generated from the source-derived drag law was fed through
`identify_drag()`.

| Case | Result |
|---|---|
| Clean data, drag exactly as source predicts | recovered CdA to **0.0000%**, r2 = 1.000000 |
| Realistic attitude noise, 0.15 deg stdev | recovered to **-2.24%**, r2 = 0.9996, P1 PASS |
| **Negative control**: simulated drag 1.6x the source value | P1 and P2 both **FAIL**, error +60.0% |
| Degenerate input (no non-zero wind points) | refuses to fit, returns an error |

The negative control is the important row. A test that cannot fail when the
underlying physics is wrong is not a test, and this one fails correctly.
