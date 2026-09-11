# sUAS Entity Catalog

> ### New here? Read [START_HERE.md](START_HERE.md) first - seven minutes.
>
> It covers the four findings that matter, four commands that run with no
> simulator, and where to go for detail.
>
> **This README is the environment, the file map and the run instructions.
> The argument lives elsewhere** - deliberately, so there is one place to fix
> a number rather than four.

A simulation entity catalog for small unmanned aircraft: a schema with
enforced requirement classes, an agent-directed research pipeline, an
automated validation suite, and a readiness gate that refuses to produce a
number from an incomplete record.

The catalog feeds a physics-based endurance model built against Cosys-AirSim
3.4.1 / Unreal Engine 5.

```
  UAS-QUAD-DJI-MAVIC3     16/16  100%   R3 VALIDATED
  UAS-QUAD-SKYDIO-X2D      8/16   50%   R0 STUB
  UAS-QUAD-DJI-MINI4PRO    6/16   38%   R0 STUB

  Modelable (R1 or better) : 1 of 3
```

Run `python catalog.py` for the live board - this block is a snapshot and the
tool is the source of truth.

---

## Environment

| What | Path |
|---|---|
| Python 3.14 (**not on PATH**) | `C:\Users\black\AppData\Local\Python\pythoncore-3.14-64\python.exe` |
| `cosysairsim` 3.4.1 | `...\pythoncore-3.14-64\Lib\site-packages\cosysairsim\` |
| Live AirSim settings | `C:\Users\black\Documents\AirSim\settings.json` |
| Plugin source | `G:\SourceControl\New_Perforce_Workspaces\DJI_Mavic_Simulation\Plugins\AirSim\` |

Installed: numpy 2.5.3, msgpack 1.2.2, rpc_msgpack 0.6 (imports as
`msgpackrpc`), tornado 6.5.8, PyYAML. **Not installed:** matplotlib, pandas,
scipy - so nothing here plots, and nothing here needs to.

The interpreter is not on PATH. Either use the full path or set an alias:

```bash
PY="C:/Users/black/AppData/Local/Python/pythoncore-3.14-64/python.exe"
"$PY" catalog.py
```

No installation step. Standard library plus numpy, and PyYAML for the
validation runner.

### ASCII policy

Everything is ASCII-only, with two documented exemptions:

1. **Verbatim quoted material.** A `source_quote` reproduces what a document
   actually says. If a datasheet uses an en dash, correcting it would falsify
   the quote. Quoted strings are exempt; the prose around them is not.
2. **[`prior_work/`](prior_work/)**, which preserves the first iteration of
   this project unedited as evidence for the defect analysis in
   `VALIDATION.md` section 3. Two files there carry non-ASCII bytes:
   `battery_model_v1.py` has an emoji at line 50, and `HoverScript_01.py`
   carries ten distinct emoji across fourteen lines - in files whose own
   constraint list forbade them. Stripping them would destroy the evidence for
   a claim made about them.

---

## Files

| File | Purpose |
|---|---|
| **The catalog** | |
| `catalog.py` | Loader, validator, coverage tracker and readiness gate. |
| `catalog/entities/*.json` | One entity per file. Every value carries `confidence`, `source` and a verbatim `source_quote`. |
| `catalog/schema/entity_schema_3.0.json` | Machine-readable requirement declaration. The validator reads this, not the prose. |
| `catalog/coverage_plan.json` | Declared intent - the only place the catalog knows about entities that do not exist. |
| `catalog/environment/` | The simulator's own airframe. Not an entity. |
| **The pipeline** | |
| `run_validation.py` | Per-entity validation runner. Reads only the record, the schema and the suite. |
| `catalog/tests/*.yaml` | Frozen per-entity validation suites. 77 tests for the X2D. |
| `catalog/reports/` | Machine-readable validation output. **Not** `catalog/entities/` - that directory is one entity per file, and a report placed there loads as an entity. |
| `catalog/reviews/` | Human adjudication of the gaps a suite declares not automatable. The promotion gate, in writing. |
| `drafts/` | Records and research logs before promotion. Nothing here is in the catalog. |
| **The model** | |
| `battery_model.py` | Momentum-theory energy model. Entity-driven, no AirSim import, runs offline. |
| `probe_sim_capabilities.py` | **Step 0.** Discovers what this install actually exposes. Gates the tests. |
| `test_3a_hover.py` | Test 3.a - hover endurance (rate-based), plus P4 and P5. |
| `test_3b_wind.py` | Test 3.b - wind scenarios plus drag identification (P1, P2, P3). |
| `wind_demo.py` | Visual high-wind ramp (P8). |
| `settings_helper.py` | Safe read/modify of `settings.json` - atomic writes, backups, key preservation. |
| **Checks** | |
| `test_catalog.py` | Catalog test battery - nine ways the catalog could go wrong while looking fine. |
| `test_regression_pinned.py` | Change detector for every published figure. 36 pins at 1e-8. |
| `run_tests.py` | Interactive menu. |
| **Documents** | |
| `START_HERE.md` | **Read this first.** The four findings, with pointers to the detail. |
| `STANDARDS.md` | **How to build an entity here.** Written to be followed by a person or an AI agent. |
| `AGENT_WORKFLOW.md` | The pipeline, the prompt patterns, the review loop, and seven times the agent was caught being wrong. |
| `PREDICTIONS.md` | **Frozen pre-registration**, plus every result and two recorded corrections. |
| `VALIDATION.md` | The VV&A article - layer model, calibration discipline, defects, limitations. |
| `MODEL_UNCERTAINTY.md` | Where the model's *structure* is weak - the induced-power defect, quantified, and why it was not silently fixed. |
| **Evidence** | |
| `results/` | Committed test output. See [`results/README.md`](results/README.md) for which run backs which prediction. |
| `prior_work/` | The first iteration, unedited - the evidence for `VALIDATION.md` section 3. |

---

## Running it

### 1. No simulator needed

```bash
"$PY" catalog.py                  # coverage board
"$PY" catalog.py --entity UAS-QUAD-DJI-MAVIC3   # one record, with its gaps
"$PY" catalog.py --schema         # the requirement declaration
"$PY" test_catalog.py             # 9 structural checks
"$PY" test_regression_pinned.py   # 36 published figures, unmoved
"$PY" battery_model.py            # the model's own self-test
"$PY" run_tests.py                # interactive menu for all of the above
```

All exit 0 with nothing running.

### 2. Validating a record

```bash
"$PY" run_validation.py --record catalog/entities/UAS-QUAD-SKYDIO-X2D.json
```

Writes `catalog/reports/validation_report.json`. Tests that declare themselves
not automatable are reported as **gaps** and go to a human - see
`catalog/reviews/` for a worked example.

### 3. Before any simulator run: ClockSpeed 1.0

```bash
"$PY" settings_helper.py --clock 1.0     # then RESTART the simulator
```

This is not optional and it is not cosmetic. The physics thread runs on a
fixed **wall-clock** 3 ms cadence while the integration step is whatever
*simulation* time elapsed, so `dt_sim ~= 3 ms * ClockSpeed`. A higher
ClockSpeed does not run more steps; it makes each step cover more simulated
time. `VALIDATION.md` has the mechanism, and `AGENT_WORKFLOW.md` section 5.7
has what happened when a figure was published from a run that ignored this.

### 4. Simulator tests

```bash
"$PY" probe_sim_capabilities.py   # step 0 - gates what the tests may claim
"$PY" test_3a_hover.py            # hover endurance, P4, P5
"$PY" test_3b_wind.py             # drag identification, P1, P2, P3
"$PY" wind_demo.py                # visual high-wind ramp, P8
```

`--entity <id>` selects the record. An entity below R1 readiness is **refused**,
not modelled with its gaps filled in:

```
$ "$PY" test_3a_hover.py --entity UAS-QUAD-SKYDIO-X2D
ERROR: ... it is R0 STUB. Missing required parameters: physical.mass_kg,
physical.propeller_diameter_m, battery.capacity_wh (+7 more...). Refusing to
produce a number from an incomplete record.
```

---

## Where the argument lives

| Question | Document |
|---|---|
| What did this project find? | [START_HERE.md](START_HERE.md) |
| How do I add an entity? | [STANDARDS.md](STANDARDS.md) |
| How was it built, and where did the agent go wrong? | [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) |
| What was predicted, and what happened? | [PREDICTIONS.md](PREDICTIONS.md) |
| Why should I believe any of it? | [VALIDATION.md](VALIDATION.md) |
| Where is the model weakest? | [MODEL_UNCERTAINTY.md](MODEL_UNCERTAINTY.md) |
| What does a promotion gate look like? | [catalog/reviews/](catalog/reviews/) |
| Which run produced which number? | [results/README.md](results/README.md) |
