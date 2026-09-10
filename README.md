# sUAS Entity Catalog

A simulation entity catalog for small unmanned aircraft, with a validated
energy and endurance model, a coverage tracker that reports its own gaps, and
a test suite designed so that its tests can actually fail.

Built against Cosys-AirSim 3.4.1 / Unreal Engine 5.

**Current state of the catalog:**

```
  UAS-QUAD-DJI-MAVIC3     16/16  100%   R3 VALIDATED
  UAS-QUAD-DJI-MINI4PRO    6/16   38%   R0 STUB
  UAS-QUAD-SKYDIO-X2D      6/16   38%   R0 STUB

  Modelable (R1 or better) : 1 of 3
```

Two of the three entities cannot produce a number, and the tooling refuses to
let them. That is reported rather than hidden, and the stubs are not filled
with plausible values to improve the board - see [STANDARDS.md](STANDARDS.md)
section 5. A catalog reading "3 of 3" on invented data would be worth nothing,
because nothing on it could be acted on.

---

## The short version

AirSim does not simulate a battery. It has no mass property exposed through its
API, no drag model you can query, and no power model at all. So an "endurance
test" run against it measures nothing unless you are careful about what each
number means and where it came from.

This project is built around that constraint rather than around it:

- The **parametric model** (`battery_model.py`) does the energy physics and is
  validated directly against published and independently measured aircraft
  data. It imports nothing from AirSim and runs with no simulator present.
- The **simulator** supplies a trustworthy timebase, attitude, trajectory and
  an independently computed air density - and is tested on those.
- Every reported number carries a layer tag, so a simulator figure is never
  read as an aircraft figure.

The most useful finding is a negative one: **the simulated aircraft is not a
Mavic 3.** `VehicleType: SimpleFlight` routes to `setupFrameGenericQuad`, a
1.0 kg F450-class quad on Phantom 2 propellers, and mass and rotor geometry are
C++ compile-time constants that `settings.json` cannot reach. See
[VALIDATION.md](VALIDATION.md) section 2.

---

## Environment

| What | Path |
|---|---|
| Python 3.14 (**not on PATH**) | `C:\Users\black\AppData\Local\Python\pythoncore-3.14-64\python.exe` |
| `cosysairsim` 3.4.1 | `...\pythoncore-3.14-64\Lib\site-packages\cosysairsim\` |
| Live AirSim settings | `C:\Users\black\Documents\AirSim\settings.json` |
| This project | `C:\Users\black\Documents\AirSim_Scripts_Claude\` |
| Plugin source | `G:\SourceControl\New_Perforce_Workspaces\DJI_Mavic_Simulation\Plugins\AirSim\` |

Installed: numpy 2.5.3, msgpack 1.2.2, rpc_msgpack 0.6 (imports as
`msgpackrpc`), tornado 6.5.8. **Not installed:** matplotlib, pandas, scipy - so
nothing here plots, and nothing here needs to.

The interpreter is not on PATH. Either use the full path or set an alias:

```bash
"C:/Users/black/AppData/Local/Python/pythoncore-3.14-64/python.exe" battery_model.py
```

Everything is ASCII-only, standard library plus numpy. No installation step.

---

## Files

| File | Purpose |
|---|---|
| `catalog.py` | Loader, validator, coverage tracker and readiness gate. |
| `catalog/entities/*.json` | One file per entity. Every parameter carries `confidence`, `source` and `verified_on`. |
| `catalog/schema/entity_schema_3.0.json` | Machine-readable requirement declaration. The validator reads this. |
| `catalog/coverage_plan.json` | Declared intent - the only place the catalog knows about entities that do not exist. |
| `catalog/environment/` | The simulator's own airframe. Not an entity. |
| `STANDARDS.md` | **How to build an entity here.** Written to be followed by a person or an AI agent. |
| `battery_model.py` | Momentum-theory energy model. Entity-driven, no AirSim import, runs offline. |
| `settings_helper.py` | Safe read/modify of `settings.json` - atomic writes, backups, key preservation. |
| `probe_sim_capabilities.py` | **Step 0.** Discovers what this install actually exposes. Gates the tests. |
| `test_3a_hover.py` | Test 3.a - hover endurance (rate-based), plus P5 and P4. |
| `test_3b_wind.py` | Test 3.b - wind scenarios plus drag identification (P1, P2, P3). |
| `wind_demo.py` | Visual high-wind ramp (P8). Watch the aircraft get blown away. |
| `test_catalog.py` | Catalog test battery - nine ways the catalog could go wrong while looking fine. |
| `test_regression_pinned.py` | Change detector for every published figure. |
| `run_tests.py` | Interactive menu. |
| `PREDICTIONS.md` | **Frozen pre-registration.** Written before any run. |
| `VALIDATION.md` | The VV&A knowledge article - layer model, calibration discipline, defects, limitations. |
| `results/` | Test output, created on first run. |

---

## Running it

### 1. Offline, no simulator needed

```bash
python battery_model.py
```

Prints both calibration modes, both profiles, every anchor with the held-out
ones flagged, a power breakdown, a wind sweep, drag force against drag power, a
forward-integration check, and a sensitivity table.

```bash
python settings_helper.py --show
```

### 2. The catalog

```bash
python catalog.py                              # coverage board
python catalog.py --entity UAS-QUAD-DJI-MAVIC3 # one record, with its gaps
python catalog.py --schema                     # the requirement declaration
python test_catalog.py                         # nine structural checks
python test_regression_pinned.py               # published figures unmoved
```

Every entity gets a **readiness tier**, computed from its record rather than
asserted by it:

| Tier | The gate does |
|---|---|
| R0 STUB | **refuses** - a required input is absent, so there is no number to produce |
| R1 PROVISIONAL | runs, every output stamped with an unmissable banner |
| R2 MODELED | runs clean |
| R3 VALIDATED | quotable as a planning product |

Each entity file also declares a tier, and `test_catalog.py` **fails if the
computed tier is below the declared one**. Over-claiming is a red build rather
than a matter of taste.

Pointing a test at a stub does not produce a hedged number; it produces a
refusal, without needing a simulator:

```
$ python test_3a_hover.py --entity UAS-QUAD-SKYDIO-X2D
ERROR: BatteryModel(UAS-QUAD-SKYDIO-X2D) requires entity
'UAS-QUAD-SKYDIO-X2D' at readiness R1 or better; it is R0 STUB. Missing
required parameters: physical.mass_kg, physical.propeller_diameter_m,
battery.capacity_wh (+7 more...). Refusing to produce a number from an
incomplete record.
```

### 3. Set ClockSpeed to 1.0 before validating

```bash
python settings_helper.py --clock 1.0
```

Then **restart the simulator** - `ClockSpeed` is read at start.

This matters more than it looks, and not for the reason usually given.

The physics thread is scheduled on a fixed **wall-clock** cadence of 3 ms
(`ScheduledExecutor`, which uses `std::chrono::high_resolution_clock`). The
integration step is NOT fixed: `FastPhysicsEngine::updatePhysics` computes
`dt = clock()->updateSince(body.last_kinematics_time)` - elapsed *simulation*
time - and `World::worldUpdatorAsync` explicitly discards the scheduled period
(`unused(dt_nanos)`). With `ScalableClock(1/clock_speed)`, sim time advances
`clock_speed` times faster than wall time, so:

```
dt_sim  ~=  3 ms * ClockSpeed
```

ClockSpeed 1 -> ~3 ms steps. ClockSpeed 25 -> ~75 ms steps.

So raising ClockSpeed does **not** run more physics steps per second. It runs
the same ~333 steps per wall-second and makes each one cover more simulated
time. You are not buying speed with CPU; you are buying it with resolution.

Steady-state equilibria (like station-keeping tilt) barely care. Transients,
control response, collisions and anything time-integrated do. Treat any value
above 1.0 as an accelerant that must be validated by running the same test at
both settings and comparing.

### 4. Probe first

```bash
python probe_sim_capabilities.py
```

Requires the simulator running. Records what this install exposes -
`getRotorStates()` key names, sensor availability, timestamp units, and the
measured simulation-to-wall clock ratio - and writes
`results/sim_capabilities.json`. The tests assert against that file and fail
loudly rather than substituting a modeled number for a measured one.

### 5. The tests

```bash
python test_3a_hover.py        # hover endurance, P5, P4
python test_3b_wind.py         # wind scenarios, drag identification, P1/P2/P3
python run_tests.py            # or use the menu
```

### 6. Seeing the wind

The measured tilts in 3.b are around one degree - correct, but invisible on
screen. To actually watch wind act on the aircraft:

```bash
python wind_demo.py            # ramp 0 -> 60 m/s
python wind_demo.py --extreme  # single 100 m/s blast
```

The ramp holds position while stepping the wind up. Below **29.7 m/s** the
aircraft tilts and holds station; above it the flight controller hits its
32.73 degree commanded-tilt limit (`simple_flight/firmware/Params.hpp:80`),
saturates, and is visibly carried downwind while still holding altitude. That
threshold is prediction P8, computed from the firmware source.

It doubles as a control experiment: every wind change is applied with
`simSetWind()` to an already-flying aircraft, with no restart and no edit to
`settings.json`. If it moves, wind set through the API is live.

Useful options:

```bash
python test_3a_hover.py --entity UAS-QUAD-DJI-MAVIC3
python test_3a_hover.py --duration 120 --altitude 20
python test_3a_hover.py --calibration none        # fit nothing at all
python test_3b_wind.py --sweep 0 2 5 8 12 --axis y
python test_3b_wind.py --wind-mode settings       # briefed restart path
```

---

## How the tests are kept honest

The briefed tests, as originally structured, could not fail: `battery_model.py`
is a pure function of time and velocity, so checking that a 77 Wh pack empties
at 115.5 W after 40 minutes is checking that `77/115.5 = 0.667`. Six things
change that.

1. **Pre-registration.** [PREDICTIONS.md](PREDICTIONS.md) is frozen before any
   run and is append-only for results.
2. **Calibration is declared, never scored.** Exactly one parameter is fitted -
   profile power at hover. That anchor reports `CALIBRATED`, never `PASS`,
   because it cannot fail by construction. Only held-out anchors are scored.
3. **A zero-free-parameter mode.** `calibration="none"` fits nothing and reports
   raw error everywhere.
4. **Rates, not durations.** Validation compares discharge rate in %/min and
   extrapolated endurance. A 60-second test legitimately probes a 40-minute
   claim; comparing test length against aircraft endurance does not.
5. **Time comes from simulation timestamps.** Never wall clock, never a loop
   counter, never `distance / speed`. Every report prints wall time, sim time
   and the measured clock ratio.
6. **Failures ship.** P6 is pre-registered as an expected failure.

---

## Results so far

**Resolved offline:**

| ID | Prediction | Result |
|---|---|---|
| P6 | Hover-calibrated model overshoots DJI's 46 min cruise by 10-25% | **+14.2% - FAIL as predicted** |
| P7 | Simulator T/W = 1.705, hover throttle 58.7% | **confirmed** |

**Resolved against the running simulator (2026-09-10):**

| ID | Predicted | Measured | Status |
|---|---|---|---|
| P1 | CdA_y 0.011676 m2 | **0.011476 m2** (-1.71%, r2 = 1.0000) | **PASS** |
| P2@5 | 1.044 deg | **1.031 deg** (-1.3%) | **PASS** |
| P2@12 | 5.994 deg | **5.888 deg** (-1.8%) | **PASS** |
| P3 | < 0.5% | **0.0162%** | **PASS** |
| P4 | within 10% of hover | **+2.51%** (68.17 -> 69.88 W) | **PASS** |
| P5 | 1.225 kg/m3 | **1.22478** (-0.02%) | **PASS** |

The drag coefficient recovered from observed tilt angles alone lands 1.7% from
the value computed by reading the C++ before the test existed.

**Two caveats on that run:** ClockSpeed was 14.5x for 3.a and 3.0x for 3.b, not
1.0, and 3.a collected only 41 samples across 60 s of sim time because the
sampling loop sleeps in wall time. The steady-state tilt and shaft-power
results are unaffected, but **3.a should be re-run at ClockSpeed 1.0** before
its energy figures are quoted.

**Pending** - P8, which needs `wind_demo.py` run against the simulator.

The headline validation result, `spec` profile, hover-calibrated:

| Anchor | Target | Predicted | Error | Status |
|---|---|---|---|---|
| Hover endurance | 40.00 min | 40.00 min | 0.0% | `CALIBRATED` - not scored |
| Cruise at 9 m/s | 46.00 min | 52.55 min | +14.2% | **FAIL** (held out) |
| Max range | 30.00 km | 38.08 km | +26.9% | **FAIL** (held out) |

Both held-out anchors fail. That is the honest state of the model, and P6
predicted the cruise failure's direction and magnitude in advance.

Separately, with **nothing fitted at all** the model predicts 40.04 min hover
against DJI's published 40 - not a fit, since there is no free parameter, but a
sign that the momentum-theory parameter set is independently reasonable.

---

## Key assumptions

| Assumption | Value | Source |
|---|---|---|
| Mass | 0.895 kg | DJI Mavic 3 Classic specifications |
| Propeller diameter | 0.2388 m | DJI 9453F, 9.4 in |
| Battery | 77 Wh, Li-ion 4S, 17.6 V full | DJI Intelligent Flight Battery |
| Equivalent flat plate (CdA) | 0.010 m2 | Literature, 0.005-0.020 range |
| Figure of merit | 0.65 | Rotorcraft literature |
| Motor/ESC efficiency | 0.80 | Literature |
| Avionics power | 15 W | Engineering estimate |
| Usable energy fraction | 0.85 | Land at 15% reserve |
| Operational overhead | 1.18 | Gusts, temperature, maneuvering |

Figure of merit and motor efficiency are literature values rather than
measurements for this airframe, and the sensitivity analysis shows both matter
at roughly +17% endurance per +20% parameter. They are the two most worth
replacing with measured values.

The default profile is **`operational`** (0.85/1.18 = 0.720 combined), which
reproduces the observed 28-30 min hover. Use `--profile spec` for compliance
checks against DJI's ideal-condition maxima. Planning against the spec sheet
overstates endurance by about 30%, which is the dangerous direction to be
wrong.

---

## Limitations

1. **The simulator does not fly a Mavic 3.** It flies a 1.0 kg generic quad.
   Not fixable from configuration - see next steps.
2. **No simulator-derived energy validation is possible.** AirSim has no
   battery, no exposed mass, no power model.
3. **The cruise anchor fails by +14.2%** and max range by +26.9%.
4. **Ground truth is contested.** DJI's specifications page says 40 min hover;
   DJI's own manual says 42. Independent measurements sit 25-35% below both.
5. **P1-P5 are unexecuted**, pending a simulator session.

Full detail in [VALIDATION.md](VALIDATION.md) section 9.

---

## Next steps

**Phase 2 - rebuild the plugin.** Add `setupFrameMavic3()` to
`MultiRotorParams.hpp` (mass 0.895, propeller 0.2388, tuned `C_T`/`C_P`/
`max_rpm`, Mavic body box and arm length) and rebuild. This is the only path to
a simulator that actually flies a Mavic 3.

Caveat from `MultiRotorParams.hpp:319-322`: with the default rotors, mass must
exceed roughly 0.8 kg or the aircraft climbs at idle throttle. 0.895 kg clears
it, but changing the rotor parameters means rechecking that margin.

Running the same suite before and after that rebuild is a stronger artifact
than either half alone, which is why the work was staged this way rather than
starting with the C++.

Still outstanding: tests 3.c (target tracking) and 3.d (reconnaissance
profile). Both are trajectory-domain problems, which is what AirSim is
genuinely good at.

**On the catalog side**, the tooling generalises and the content does not yet.
The next work is research, not code: source the two stubs against their
vendors' documentation and raise them off R0. Every gap in them already carries
a `todo` naming what would close it, so `python catalog.py --entity <id>` is
the work queue. The fixed-wing segments in `coverage_plan.json` need a second
energy model before they can be populated at all - momentum theory has no
fixed-wing equivalent - and that is deliberately listed as a gap rather than
quietly omitted.
