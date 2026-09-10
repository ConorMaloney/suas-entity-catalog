# VALIDATION.md - DJI Mavic 3 simulation entity

Verification, Validation and Accreditation notes for the Mavic 3 entity built
against Cosys-AirSim 3.4.1 / UE5. This is the "show your work" document: every
modeling decision here should be defensible to a subject-matter expert, and
where a decision is weak it is labelled weak rather than dressed up.

---

## 1. The layer model

Three different things get called "the Mavic 3" in a project like this, and
conflating them is the single fastest route to a briefing that misleads.

| Layer | What it is | What it can be trusted for |
|---|---|---|
| **L1** | The real aircraft: DJI published figures and independent measurements | Ground truth, with the caveats in section 5 |
| **L2** | The parametric model in `battery_model.py` | Energy, endurance, range - the only layer that models power at all |
| **L3** | Cosys-AirSim / UE5 | Trajectory, attitude, timebase, air density. **Not** energy |

Every number in every report produced here is tagged with its layer. The rule
that follows is simple and absolute: **no L3 number is ever presented as an L1
number.**

That is not pedantry. It is the central finding of this exercise.

---

## 2. The simulated aircraft is not a Mavic 3

`settings.json` declares `"VehicleType": "SimpleFlight"`. That routes to
`setupFrameGenericQuad` (`SimpleFlightQuadXParams.hpp:33-41`, whose own comment
reads *"Only Generic for now"*). What is actually flying:

| Parameter | Simulator | Mavic 3 | Delta |
|---|---|---|---|
| Mass | **1.000 kg** | 0.895 kg | +11.7% |
| Propeller | **0.2286 m** (GWS 9x5, a Phantom 2 part) | 0.2388 m (9453F) | -4.3% |
| Arm length | **0.2275 m** | ~0.13 m half-span | +75% |
| Body box | 0.18 x 0.11 x 0.04 m | folding Mavic body | - |
| Max thrust | 16.72 N total | - | T/W 1.70 |

**None of it is reachable from `settings.json`.** `AirSimSettings.hpp` was
searched for `Mass`, `LinearDragCoefficient`, `RotorCount`,
`PropellerDiameter`, `MaxRpm`, `C_T`, `Inertia`, `BodyBox` and `ArmLength`:
no matches. The per-vehicle keys that exist are `VehicleType`, `PawnPath`,
`DefaultVehicleState`, `AllowAPIAlways`, `AutoCreate`, collision and trace
flags, `X/Y/Z`, `Yaw/Pitch/Roll`, `Cameras`, `Lights` and `Sensors`.

Mass and rotor geometry are **C++ compile-time constants**.

So the "Mavic 3 entity" currently exists only in the Python side-model. The
object in Unreal is a 1 kg F450-class quad wearing the name. Any endurance
figure attributed to the simulation is attributable to that airframe, not to a
Mavic 3.

---

## 3. Why the original tests could not fail

This section is included because it is the strongest argument for the
restructure, and because a VV&A document that omits its own predecessor's
defects is not a VV&A document.

Evidence from the existing outputs in `AirSim_Scripts/results/`:

| Artifact | What it actually shows |
|---|---|
| `wind_test_complete_20260908_204146.txt` | "Sim Time 40.0s" is `distance / speed`, not a measurement. Wall time was 2.3 s; true elapsed at ClockSpeed 25 was ~57 s. **Every energy value is `P * (d/v)`** - the simulator contributed nothing to it. |
| same | "Adjusted Range: 14.64 km" is identical across Zero Wind, Headwind and Crosswind, and is exactly half the base range. The factor `1-(w/5)*0.5` only reaches 0.5 at `w=5`, so **wind state leaked into the Zero Wind run**. |
| same | Drift is identical to two decimal places across all three scenarios (`-0.22 / -16.08 / -129.09`). Wind had **no** measured effect on the trajectory. |
| same | Start Z of `+118.6` in NED was captured before the post-`reset()` state settled, so the reported "drift" is the reset offset. |
| same | Crosswind factor **1.515** against headwind **1.010** - charging 50% more for a crosswind than for a headwind. Backwards. |
| `hover_test_20260908_003202.txt` | `time.sleep(1)` is commented out at `HoverScript_01.py:88`, so "30 seconds" is a loop counter. Wall time 0.76 s. |
| same | `Target 46.00 min / Actual 0.50 min / FAIL` compares **how long the test ran** against **how long the aircraft flies**. A red FAIL carrying no information. |

None of this is a criticism of the effort. It is what happens when a test
harness is built before the simulator's actual capabilities are established -
which is precisely why `probe_sim_capabilities.py` now runs first.

### Defects found by reading the prior `battery_model.py` in full

- `tick()` recomputed cumulative energy from total elapsed time on every call,
  so changing speed or wind mid-flight **retroactively rewrote all prior
  history**.
- Drag energy collapsed to zero the instant the aircraft stopped, because it
  multiplied total elapsed time by instantaneous speed.
- A `1 + (v/50)^2` wind curve with no physical basis - worth 1% at 5 m/s.
- An inverted direction factor that charged more for a tailwind than a
  headwind.
- Wind was added regardless of direction.
- Drag power used ground speed rather than airspeed, with no propulsive
  efficiency term.
- `CdA = 0.04 m2`, which is 2-8x too high for this airframe.
- No induced-power term at all - the dominant term in multirotor hover.
- An arbitrary range model.
- An emoji at line 50, in the file whose own constraint list forbids them.

---

## 4. What reading the source bought

Because the physics is readable, several results become derivable in closed
form and therefore **pre-registerable as falsifiable predictions**. See
`PREDICTIONS.md`.

### The drag model, solved

`MultiRotorPhysicsBody.hpp:190-217` builds per-axis drag factors;
`FastPhysicsEngine.hpp:269-308` applies
`drag_force = normal * (-drag_factor * air_density * v^2)`.

Matching that against the standard `F = 0.5 * rho * CdA * v^2` gives
`CdA_effective = 2 * drag_factor`:

- **CdA_x = 0.010766 m2**
- **CdA_y = 0.011676 m2**

An independent literature estimate for a Mavic-class airframe was **0.010 m2**.
Two unrelated derivations - one from published aerodynamics, one from someone
else's C++ - landing within 8-17% is genuine corroboration.

One trap worth recording: `setupFrameFlamewheel` and `setupFrameFlamewheelFLA`
both execute `params.linear_drag_coefficient *= 4` ("make top speed more
real"), while `setupFrameGenericQuad` does not. Switching `VehicleType` to a
Flamewheel frame would therefore quadruple `CdA` and invalidate P1 without
changing a single line of Python. The predictions here are specific to
`SimpleFlight` -> `setupFrameGenericQuad`, and the probe records the configured
`VehicleType` in every run so a mismatch is visible in the output.

This is what makes test 3.b a real test: the value is derived from source
*before* the run, and then identified from observed tilt angles during it.
Nothing is tuned to make the two agree, and the fit is constrained through the
origin so it has no free intercept to absorb an error with.

### Constraint #4, proven rather than explained

`tan(theta) = drag / (m*g)`:

| Wind | Drag | Tilt | Thrust increase |
|---|---|---|---|
| 5 m/s | 0.179 N | **1.044 deg** | 1.000166x |
| 12 m/s | 1.030 N | **5.995 deg** | 1.0055x |

At 5 m/s the energy penalty in this simulator is **0.017%**. The briefed
constraint that wind effects would be hard to isolate is not a limitation to
work around - it is a quantified certainty derived from source. No experiment
in this simulator can demonstrate wind affecting endurance.

### AirSim has no translational lift

`RotorParams.hpp:21-62`: `thrust = C_T * rho * n^2 * D^4`. Thrust depends only
on rotor speed. There is no induced-velocity term anywhere.

AirSim is therefore **structurally incapable** of reproducing DJI's
flight-time (46 min) > hover-time (40 min) relationship, and simulator-derived
power can never validate cruise endurance. That physics must live in the
parametric model. This is a clean, publishable negative result, and P4 tests it
directly by measuring rotor shaft power at hover and at 9 m/s.

### A real AirSim bug, found in passing

`MultiRotorPhysicsBody.hpp:190` computes `propeller_area = pi * D * D`. Disc
area is `pi * D^2 / 4`. **AirSim's vertical drag area is four times the
physical value.**

It affects the Z axis only, so it does not touch the horizontal work here, and
`airsim_drag_factors()` reproduces it faithfully - the goal is to predict what
the simulator *will* do, not what it *should* do. But it is worth reporting
upstream.

### What the API can and cannot give

**Absent:** `mass`, `drag`, `power`, `battery` - zero grep hits each.

**Present and genuinely independent:**

- `simGetGroundTruthEnvironment()` returns `air_density` **computed by the
  simulator**, so it cross-checks the assumed 1.225 rather than restating it.
- `ImuData.linear_acceleration` against `KinematicsState.linear_acceleration`.
- `BarometerData.pressure` against `EnvironmentState.air_pressure`.
- `DistanceSensorData.distance` against `position.z_val`.

**`getRotorStates()` - resolved.** The client is unhelpful here: `RotorStates`
declares only `timestamp` and `rotors`, the rotor elements arrive as raw dicts,
and no per-rotor class exists in the package. But the C++ settles it:
`MultirotorCommon.hpp:25-46` declares `RotorParameters {thrust, torque_scaler,
speed}` and `MultirotorRpcLibAdaptors.hpp:54` serializes it with
`MSGPACK_DEFINE_MAP(thrust, torque_scaler, speed)`. Those three keys are the
actual wire contract.

**It is still verified at runtime by the probe rather than assumed**, because a
contract read from source is evidence, not proof, and the installed server
binary is what will actually answer.

Landmines worth recording: `RotorStates.timestamp` against `ImuData.time_stamp`;
`BarometerData` declares `altitude`/`pressure`/`qnh` as `Quaternionr`/`Vector3r`
though floats arrive; `simGetPhysicsRawKinematics` is in physics-engine frame
with acceleration unpopulated.

### ClockSpeed

**Correction to an earlier claim in this document.** It previously said
FastPhysics uses a fixed-step integrator. That is wrong, and the truth is close
to the opposite. The step is *variable*; what is fixed is the wall-clock
cadence the physics thread is scheduled on.

| Component | Behaviour | Source |
|---|---|---|
| Physics thread schedule | fixed **3 ms wall clock** | `SimModeWorldBase.h:75`, `ScheduledExecutor` on `high_resolution_clock` |
| Scheduled period passed to the callback | **discarded** | `World.hpp:147-149`, `unused(dt_nanos)` |
| Integration step actually used | elapsed **sim** time since last update | `FastPhysicsEngine.hpp`, `dt = clock()->updateSince(...)` |
| Sim clock rate | wall time x ClockSpeed | `SimModeBase.cpp:1519`, `ScalableClock(1/clock_speed)` |

Composing those: `dt_sim ~= 3 ms * ClockSpeed`. The integration step grows
**linearly** with ClockSpeed. ClockSpeed 25 integrates in ~75 ms steps.

The practical conclusion is unchanged - higher ClockSpeed alters the trajectory
rather than merely replaying it faster - but the mechanism matters for knowing
*what* it damages. The integrator is trapezoidal (velocity from the mean of
current and next acceleration, position from mean velocity), so it is second
order and steady-state equilibria are robust to step size. What degrades is
anything time-resolved: control-loop bandwidth in particular, since the flight
controller's effective update interval in simulated time is inflated by the
same factor.

That is the real cost. A PID tuned for 3 ms updates running at 75 ms simulated
intervals is a different controller.

All validation runs should use **ClockSpeed 1.0**. Any higher setting is an
accelerant that must itself be validated by running the same test at both and
comparing.

---

## 5. Ground truth is contested, and that is a finding

| Source | Hover | Cruise / total |
|---|---|---|
| DJI specifications page | 40 min | 46 min at 9 m/s |
| DJI manual | **42 min** | 46 min |
| Pix-Pro (measured, ~0-1 C, zero wind) | - | 35 min to 20% |
| TechRadar (measured) | - | ~30 min to RTH |
| MavicPilots owner reports | ~28-30 min | 30-35 min |

DJI's figures are ideal-condition maxima: sea level, no wind, 100% to 0%,
constant 9 m/s. Real-world performance is **65-75% of advertised**, and the two
DJI sources **disagree with each other**.

A spec-anchored entity overstates operational endurance by roughly 30% - the
dangerous direction for mission planning. The model therefore carries two
profiles:

- **`spec`** - matches DJI's published maxima. For compliance checks.
- **`operational`** (default) - derated for planning.

The derating is **two separable, individually defensible factors**, not one
fudge:

```
usable_energy_fraction   0.85    land at 15% reserve, not at 0%
operational_overhead     1.18    gusts, temperature, maneuvering
combined                 0.85 / 1.18 = 0.720
```

That reproduces the observed 28-30 min hover and 30-35 min cruise. Splitting it
in two matters: the reserve fraction is a policy decision a planner can change,
while the overhead factor is an empirical observation. A single 0.72 multiplier
would hide that distinction.

---

## 6. Calibration discipline

**Exactly one parameter is fitted:** profile power at hover, solved so hover
endurance matches the published hover anchor. Everything else is published,
derived, or taken from literature.

Because that anchor is fitted, it **cannot fail**. It is reported as
`CALIBRATED`, never as `PASS`, and it is excluded from the pass/fail counts.
Only held-out anchors - cruise endurance and maximum range - are scored.

`calibration="none"` fits nothing at all and reports raw error everywhere.
Both modes appear below, because a model that only looks good in its fitted
configuration is not validated.

### Results, `spec` profile, hover-calibrated

| Anchor | Target | Predicted | Error | Status |
|---|---|---|---|---|
| Hover endurance | 40.00 min | 40.00 min | 0.0% | `CALIBRATED` - fitted, not scored |
| Cruise at 9 m/s | 46.00 min | 52.55 min | **+14.2%** | **FAIL** (held out) |
| Max range | 30.00 km | 38.08 km | **+26.9%** | **FAIL** (held out) |

Both held-out anchors fail, and P6 pre-registered the cruise failure at +10 to
+25% before the run. The measured +14.2% is inside that band.

### The zero-free-parameter result

With `calibration="none"` - nothing fitted, every parameter from literature and
specification - the model predicts **40.04 min** hover against DJI's published
40 min.

This was not pre-registered and is reported as an observation rather than a
test. It is worth recording because it is not a fit: there is no free parameter
to have landed it there. It says the momentum-theory parameter set is
independently reasonable.

### Sensitivity

Run in `calibration="none"` so nothing is refitted, +20% on each parameter:

| Parameter +20% | Hover | Change | Cruise | Change |
|---|---|---|---|---|
| equivalent flat plate (CdA) | 40.04 min | 0.0% | 51.66 min | -1.8% |
| avionics power | 39.03 min | -2.5% | 50.89 min | -3.3% |
| figure of merit | 46.83 min | +17.0% | 60.01 min | +14.0% |
| mass | 31.44 min | **-21.5%** | 41.47 min | **-21.2%** |
| motor/ESC efficiency | 46.83 min | +17.0% | 61.06 min | +16.0% |
| propeller diameter | 46.83 min | +17.0% | 62.87 min | +19.5% |

Two things worth noting.

First, **mass and propeller diameter dominate**, which is the expected
momentum-theory result: induced power scales as `T^1.5 / sqrt(A)`. This is why
the corrected `rotor_diameter` in the spec file matters so much - see section 7.

Second, **CdA barely registers at hover** and matters only in cruise. So the
equivalent-flat-plate estimate is not load-bearing for the endurance claims,
and the agreement between the literature estimate and the source-derived
simulator value is corroboration rather than a dependency.

Run in hover-calibrated mode this table would be **all zeros** in the hover
column, because refitting profile power to the 40 min anchor absorbs any
perturbation exactly. That is not robustness - it is the fit hiding the
sensitivity, and it is the clearest possible illustration of why held-out
anchors are the ones that carry information.

---

## 7. Corrections to the specification data

`data/mavic3_specs.json` was rebuilt with `source` and `verified_on` on every
parameter. Three errors in the previous file were corrected:

| Field | Was | Now | Why it matters |
|---|---|---|---|
| `rotor_diameter_mm` | 305 | **238.8** | 305 mm is a 12-inch propeller. The Mavic 3 uses the 9453F, 9.4 in. Disc area drives the entire induced-power term, and induced power is the dominant term in hover - see the sensitivity table. |
| `chemistry` | "LiPo 4S" | **"Li-ion 4S"** | DJI lists Li-ion. Different discharge curve and different safe cutoff. |
| `voltage_full_v` | 16.8 | **17.6** | 16.8 V is the standard-LiPo 4.2 V/cell figure. DJI's charge limit is 17.6 V. |

The first is the serious one. A 305 mm rotor gives a disc area 63% larger than
the real 238.8 mm rotor, which understates induced power throughout.

---

## 8. Method - how the tests are kept honest

1. **Pre-registration.** `PREDICTIONS.md` is frozen before any run. Results are
   appended; prediction rows are never edited. This is the structural defence
   against widening tolerances until the board goes green.
2. **Calibration is declared, never scored.** Fitted anchors print
   `CALIBRATED (cannot fail by construction)`.
3. **A zero-free-parameter mode** exists and is reported alongside.
4. **Rates, not durations.** Validation compares discharge rate in %/min and
   extrapolated endurance against specification. A 60-second test can then
   legitimately probe a 40-minute claim. Comparing test length against aircraft
   endurance, as the prior harness did, tells you nothing.
5. **Time comes from simulation timestamps.** Never wall clock, never a loop
   counter, and never `distance / speed`. Every report prints wall time, sim
   time and the measured clock ratio so a reader can check the timebase rather
   than trust it.
6. **Capability gating.** `probe_sim_capabilities.py` runs first and records
   what this install actually exposes. Tests assert against it and fail loudly
   on a missing key rather than substituting a modeled number for a measured
   one.
7. **Wind is set explicitly for every scenario, including the zero-wind
   baseline**, because the prior harness inherited a 5 m/s crosswind into a run
   it labelled calm.
8. **Failures ship.**

### The test procedure was itself validated

The drag identification math was checked without a simulator, by generating
synthetic tilt data from the source-derived drag law and inverting it:

| Case | Result |
|---|---|
| Clean data, drag exactly as source predicts | CdA recovered to **0.0000%**, r2 = 1.000000 |
| Realistic attitude noise, 0.15 deg stdev | recovered to **-2.24%**, r2 = 0.9996, P1 PASS |
| **Negative control**: simulated drag 1.6x source | P1 and P2 both **FAIL** at +60.0% |
| Degenerate input | refuses to fit, returns an error |

The negative control is the row that matters. A test that still passes when the
underlying physics is wrong is not a test.

---

## 9. Limitations

Stated plainly, because a validation document that reads as advocacy is not
worth much.

1. **The simulator does not fly a Mavic 3.** It flies a 1.0 kg generic quad.
   Until the plugin is rebuilt with Mavic parameters, no simulator result is a
   Mavic 3 result. This is the largest limitation and it is not fixable from
   configuration.
2. **No simulator-derived energy validation is possible.** AirSim has no
   battery, no exposed mass, and no power model. L2 is validated against L1
   directly; L3 contributes a timebase, attitude, trajectory and air density.
3. **The cruise anchor fails by +14.2%** and max range by +26.9%. The model's
   structure reproduces the right relationships; its absolute calibration in
   forward flight is optimistic. This is stated, not smoothed over.
4. **Ground truth itself is contested** - the two DJI sources disagree, and
   independent measurements sit 25-35% below both.
5. **Figure of merit (0.65) and motor/ESC efficiency (0.80) are literature
   values, not measurements** for this aircraft. The sensitivity table shows
   both matter at +17% per +20%, so they are the parameters most worth
   replacing with measured values.
6. **P1-P5 have not been executed.** They require the running simulator and are
   marked pending in `PREDICTIONS.md`. They are not passes.

---

## 10. Next steps

**Phase 2 - rebuild the plugin.** Add `setupFrameMavic3()` to
`MultiRotorParams.hpp` with mass 0.895 kg, propeller 0.2388 m, tuned
`C_T`/`C_P`/`max_rpm`, and the Mavic body box and arm length; then rebuild. This
is the only path to a simulator that actually flies a Mavic 3, and the project
is already named `DJI_Mavic_Simulation`.

One caveat from `MultiRotorParams.hpp:319-322`: mass must exceed roughly 0.8 kg
with the default rotors or the aircraft climbs at idle throttle. 0.895 kg
clears it, but changing the rotor parameters requires rechecking that margin.

The before/after comparison - the same test suite run against the generic quad
and then against a real Mavic 3 airframe - is a stronger artifact than either
half alone, which is why the work was staged this way rather than starting with
the C++.

Also outstanding: tests 3.c (target tracking) and 3.d (reconnaissance profile),
both of which are trajectory-domain problems and therefore things AirSim is
genuinely good at - unlike energy.
