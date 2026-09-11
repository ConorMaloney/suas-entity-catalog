# results/ - which run backs which number

Committed test output, kept as evidence rather than ignored as build waste.
`.gitignore` explains why.

**This index exists because its absence caused a defect.** For a day, P4 was
published from a run this project disavows in writing - a 41-sample,
14.54x-ClockSpeed run - while the correct 597-sample run sat here uncited.
Sixteen files, two of them cited by name anywhere, and no way to tell which
produced which figure. See `AGENT_WORKFLOW.md` section 5.7 and the correction
in `PREDICTIONS.md`.

Every run is kept, including the superseded ones. They are the evidence trail
for how that happened.

---

## Authoritative runs

These are the runs the published figures come from. Nothing else should be
quoted.

| File | Clock | Samples | Backs | Key figures |
|---|---|---|---|---|
| `test_3a_hover_20260910_053318.{txt,json}` | **1.00x** | **597** | **P4**, **P5** | shaft power 68.15 -> 70.08 W, **+2.84%**; air density 1.2248, -0.02% |
| `test_3b_wind_20260910_003816.{txt,json}` | 3.00x | - | **P1**, **P2**, **P3** | CdA_y 0.011476, -1.71%, r2 = 1.0000; tilt 1.0306 / 5.8877 deg; wind penalty 0.0162% |
| `wind_demo_20260910_015456.{txt,json}` | 1.00x | - | **P8** | holds to 25 m/s, breaks away at 30; predicted 29.7 |
| `probe_20260910_002250.txt` | 1.00x | - | capability gate | rotor keys `['speed','thrust','torque_scaler']` |
| `sim_capabilities.json` | - | - | capability gate | the file `probe.require()` asserts against |

### Why 3.b's authoritative run is at ClockSpeed 3.0, not 1.0

Because what it measures is a **steady-state equilibrium**, and those are
insensitive to integration step size. The aircraft tilts until horizontal
thrust balances drag and then stays there; it arrives at the same angle whether
the journey is integrated in 3 ms or 9 ms steps. `VALIDATION.md` makes this
argument in full.

The tell is in the data: the fit returned **r2 = 1.0000** across five wind
speeds. A coarse integration corrupting the measurement would not produce that.

This is a genuine asymmetry with 3.a, which measures **energy integrated over
time** and therefore does care - which is exactly why 3.a was re-run at 1.0 and
3.b was not. Recorded here rather than left for a reader to notice.

---

## Superseded runs

Kept, not deleted. Do not quote these.

| File | Clock | Samples | Why superseded |
|---|---|---|---|
| `test_3a_hover_20260910_003446.{txt,json}` | 14.54x | 41 | **Was the source of the mis-published +2.51%.** One sample per 1.47 simulated seconds. Retained as the evidence for correction 5.7 |
| `test_3a_hover_20260910_003159.{txt,json}` | 14.56x | 41 | Rehearsal. Same test three minutes earlier; differs only in the fourth decimal |
| `test_3b_wind_20260910_003322.{txt,json}` | 14.93x | - | Rehearsal at an unvalidated ClockSpeed |
| `test_3b_wind_20260910_003514.{txt,json}` | 14.91x | - | Rehearsal. Also reports air density **1.2148**, which disagrees with every other run's 1.2248 - a further reason not to quote it |

That last row is worth a second look. Five runs report 1.2248 kg/m3 and one
reports 1.2148. The outlier is a 14.91x run. Nobody noticed at the time,
because nothing compared runs against each other.

---

## Reading the anchor tables

Files produced **before 05:33 on 2026-09-10** carry a three-row anchor table.
Later files carry four rows, the extra one being `max_wind_resistance_ms`
reporting `UNSCORED`.

That is a deliberate shape change, not a discrepancy - the anchor was always
declared held-out in the Mavic's calibration block and never scored by any
code. `PREDICTIONS.md` records it. Held-out **declared** went 2 -> 3; held-out
**scored** stayed 2, passed 0, failed 2.

---

## House rules

1. **An authoritative run is named here or it is not authoritative.** A figure
   in a document must trace to a row in the table above.
2. **Superseded runs are kept.** They cost 240 KB and they are the only record
   of how a wrong figure got published.
3. **Re-running to "refresh" a figure is not free.** The pinned values in
   `test_regression_pinned.py` are tied to these runs; a new run means a
   deliberate, documented pin edit, not a silent update.
