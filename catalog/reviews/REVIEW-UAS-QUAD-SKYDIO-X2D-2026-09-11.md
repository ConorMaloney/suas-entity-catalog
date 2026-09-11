# Human review - UAS-QUAD-SKYDIO-X2D

| | |
|---|---|
| **Record** | `catalog/entities/UAS-QUAD-SKYDIO-X2D.json` |
| **Suite** | `VS-UAS-QUAD-SKYDIO-X2D-004` v3.0.0 (frozen) |
| **Report** | `catalog/reports/validation_report.json`, run 2026-09-11T03:53:38Z |
| **Reviewer** | Conor Maloney |
| **Review date** | 2026-09-11 |
| **Record tier** | declared R0, computed R0 - agree |
| **Outcome** | **NOT PROMOTED.** Remains R0 STUB. XF-014 blocks; SQS-006's authenticity half and CC-008's re-run condition stay open. |

Automated outcome: 77 tests - 55 pass, 8 skipped, 4 fail, 1 warn, **9 gaps**.
This document resolves the 9 gaps. It does not change the record, the schema
or the suite.

---

## 1. Scope of this review

A "gap" is a test the suite declares **not automatable** - `target: human` or
`target: tooling`. The runner cannot decide it from the artifact, so it is
parked for a person. Leaving gaps unresolved and promoting anyway would make
the automated board a false negative: green because nobody asked the hard
question, not because the answer was good.

Nine gaps, partitioned as follows. SQS-006 is a single gap with two halves
that land in different buckets, which is why a naive count of this section can
come to ten:

```
  4  closed on evidence     XF-011, RT-009, XF-016, CC-008      section 2
  1  settled by decision    KC-003B                             section 3
  2  deferred               RT-005, VT-005B                     section 4
  1  split                  SQS-006 - policy deferred (s4),
                                      authenticity open (s6)
  1  open and blocking      XF-014                              section 6
  --
  9
```

---

## 2. Gaps closed on evidence

### XF-011 - segment_id is not inferred by tooling. RATIFIED CLEAN.

Inspected `catalog.py`, `test_catalog.py`, `run_validation.py`.

`catalog.py:561` reads `document.get("segment_id")` - a bare lookup with no
default, no `or` fallback, and no derivation from `category` anywhere in the
codebase. `test_catalog.py` check 5 validates the value against
`coverage_plan.json` but never supplies one. `run_validation.py:1574` reads it
for comparison only.

**Nothing infers segment_id.** The gap is closed.

### RT-009 - tier computation reads only local artifacts. RATIFIED CLEAN.

Inspected `run_validation.py` imports and file handles.

Imports are `argparse, datetime, json, os, re, sys, OrderedDict, yaml`. No
`urllib`, no `requests`, no `socket`, no `http`. Four file handles: three
reads and one write (the report).

**No network, no other entity record, no research-agent output.** Closed.

One correction to the gap's own wording: it says the runner reads "the record
file, the schema file, and validation_time". It also reads **the suite file**,
which is correct and necessary. The gap text should say so.

### XF-016 - declared segment is correct. RATIFIED.

The X2D is the **defense** variant - established twice in ESC-1, most recently
by owner direction on the grounds that this catalog feeds a military
simulation. The declared segment `SEG-US-DEF-2020S-QUAD-G1` is "Group 1
quadcopter, defense, Blue UAS list platforms".

Variant and segment agree. **Re-check if the variant ever changes again** -
that is exactly what invalidated this at suite v2.1.0.

### CC-008 - no class-typical constant is substituted for an airframe-specific path. RATIFIED, with a caveat about scope.

Smaller in practice than the gap text implies. Of the five airframe-specific
REQUIRED_MODELING paths, four are `status: "missing"`, so there is nothing to
substitute into. Exactly one is present:

```
performance_published.max_speed_ms = 11.2
  source: Skydio X2D Color/Thermal datasheet - Technical Specs, Aircraft
```

That is a citation about this airframe, not a class-typical default. The
substantive check passes.

The caveat: this is trivially true *because the record is nearly empty*. It
must be re-run, not carried forward, once the four missing paths are filled.
A pass here today says nothing about the record it will be tomorrow.

---

## 3. Decision taken

### KC-003B - the operational profile is NOT in use for this entity.

**Decision: spec profile only.**

Consequences:
- `KC-003` stays conditional on R3 and does not apply at lower tiers.
- `performance_operational.usable_energy_fraction` and
  `operational_overhead_factor` remain legitimate declared gaps, not blockers.
- **No operational planning figure may be produced for the X2D.** If that
  changes, this decision must be revisited before any such figure is quoted.

---

## 4. Deferred - logged, not fixed

Three subsections follow. Two are whole gaps (RT-005, VT-005B); the third is
the policy half of SQS-006, whose other half is open in section 6.

Each is a confirmed real defect. None affects the X2D today. The schema and
suite were deliberately left untouched, because other records may be
mid-validation against them.

### RT-005 - the R3 staleness limit is undefined in the schema. DEFERRED.

The schema's R3 clause reads "the oldest verified_on within the staleness
limit" and never defines one. The actual thresholds live in Python:

```python
catalog.py:55   STALE_WARN_DAYS = 180
catalog.py:56   STALE_FAIL_DAYS = 365
```

A validator reading only the schema cannot check R3 freshness. Harmless for
the X2D, which is R0 and never reaches the clause.

**Latent for UAS-QUAD-DJI-MAVIC3**, which is R3 today and demotes to R2 on
2027-09-09 by a rule the schema does not state. **Target: 30 days.**

### VT-005B - the range shape is undefined in the schema. DEFERRED.

`value_type: "range"` is declared for two paths and never specified. A de
facto convention exists in code and data:

- `UAS-QUAD-DJI-MAVIC3` uses `observed_flight_time_min: [30.0, 35.0]`
- `catalog.py:225-227` accepts list, length 2, both numeric

**Ordering is not enforced** - `[35.0, 30.0]` passes today. Nothing is
affected currently; both X2D range fields are `missing`. **Target: 60 days**,
or sooner if any record populates a range value. **Until then, any consumer of
a range value must handle both orderings.**

### SQS-006 (part b) - class-typical constants carry no source_quote. DEFERRED.

Four constants - `figure_of_merit`, `motor_esc_efficiency`,
`propulsive_efficiency`, `profile_power_mu_factor` - have no `source_quote`.
This is the sole cause of the SQS-001 and SQS-005 failures.

Context: these were inherited verbatim from the superseded stub, and
`source_quote` was never part of schema 3.0 - the convention was introduced by
this validation suite. The suite is applying a new requirement retroactively
to carried-across data. Their sources are genre citations ("Rotorcraft
literature, typical small electric multirotor") rather than documents a
sentence can be quoted from.

**Decision: leave the failures standing as a visible flag.** They are not
suppressed and not silently exempted. SQS-006 itself warns against "a silent
softening of SQS-001 and SQS-005", and an unresolved red is more honest than
an undeclared exemption. **Target: 30 days** - either replace the genre
citations with quotable ones, or write an explicit exemption into the schema.

### SQS-006 (part a) - quote authenticity. OPEN, see section 6.

---

## 5. Suite defect found during review

### CC-007 fires at R0 against a requirement it declares for R2.

Its description reads "The five airframe-specific REQUIRED_MODELING paths
carry a real researched value **by R2**." The record is R0. But:

```
CC-007    condition = None
CC-002C   condition = {readiness_declared_in: [R2, R3]}
KC-003    condition = {readiness_declared_in: [R3]}
```

Its two siblings, which express the same kind of tier-gated rule, both skip at
R0. CC-007 does not, and produces **4 of the report's 4 failures** as a
result. An R0 stub having absent airframe values is the definition of R0.

**Decision: leave as-is and log.** The suite is frozen at v3.0.0 and other
records may be validating against it. **Target: next suite revision.**

### Related finding - the four CC-007 failures are less blocked than they appear

Recorded because it was misread during this review and the correction changes
the work estimate.

All four failing paths are **REQUIRED_MODELING**, not REQUIRED_MEASURED:

| Path | Class |
|---|---|
| `battery.voltage_empty_v` | REQUIRED_MODELING |
| `aerodynamic_assumptions.equivalent_flat_plate_area_m2` | REQUIRED_MODELING |
| `aerodynamic_assumptions.avionics_power_w` | REQUIRED_MODELING |
| `aerodynamic_assumptions.thrust_coefficient` | REQUIRED_MODELING |

The schema: *"REQUIRED_MODELING - Must be present. 'literature' and
'estimated' are acceptable, because these are modelling choices rather than
facts about the aircraft, but 'source' is still mandatory so the choice is
auditable."*

These therefore **do not require classified data or field testing.** They
require a documented engineering judgement with a stated basis and tolerance -
frontal area from the published dimensions for the flat plate, a
comparable-propeller lookup for `C_T`, cell count times per-cell cutoff for
`voltage_empty_v` once chemistry is pinned. Desk work. **Target: 30 days.**

### Structural finding - the X2D may be permanently unpromotable

The four REQUIRED_MEASURED gaps are the real wall, and that class forbids
estimation:

`propeller_diameter_m` - `capacity_wh` - `voltage_full_v` -
**`max_hover_time_min`**

Per the record's own `_readiness_note`, Skydio publishes no battery electrical
specification, no propeller geometry, and no separate hover endurance figure
reachable by the author.

`max_hover_time_min` is the calibration anchor. **If it is never published,
this entity can never reach R1** - not because the record is incomplete, but
because the requirement is unsatisfiable for this platform.

That is a policy question, not a research task: does the catalog accept a
`derived` hover time (from the published 35 min flight time plus a documented
assumption) as the anchor, or does it accept that some platforms are
permanently R0? **Target: 60-90 days.** Deferring it is fine; discovering it
at promotion time would not be.

---

## 6. Open items - these block promotion

### XF-014 - re-confirm every value against an X2D source. OPEN. BLOCKING.

The gap's own wording: *"Until done, no figure from this record should be
quoted."* That stands.

**What this is not.** A check on whether X2E appears in the record. It does,
in two legitimate roles, and both were inspected during this review:

- **As data, in exactly one field.** `max_speed_ms` carries two rejected X2E
  readings of 13.9 m/s in `conflicting_values`, against the chosen X2D value
  of 11.2. That is the conflict-preservation rule working as designed and it
  should stay.
- **As prose**, in roughly twenty `note`, `todo`, `conditions`, `_escalations`
  and `_supersedes` strings that explain the variant distinction.

**No X2E value is used as a fill anywhere in the record.** Verified.

**What this is.** A process check. The record was re-based twice - X2D
Enterprise, then X2E, then back to X2D. Values populated during the X2E
interval had to be re-read from an X2D document on the way back, or left in
place on the assumption that the shared X2 airframe makes them identical. The
artifact cannot distinguish those two cases: a citation reading "X2D
datasheet" looks the same whether someone opened it or assumed it.

The record itself shows the assumption is unsafe. ESC-2 asserts every airframe
figure "is published identically across both" - but `max_speed_ms` is 11.2 on
the X2D and 13.9 on the X2E, **24 percent apart**. Commonality held for five
fields and failed for the sixth.

Checklist - open the cited source and confirm the reading:

| # | Field | Value | Cited to | Note |
|---|---|---|---|---|
| 1 | `physical.mass_kg` | 1.325 kg | X2D Color/Thermal datasheet | |
| 2 | `physical.dimensions_unfolded_mm` | object | X2D datasheet | |
| 3 | `physical.dimensions_folded_mm` | object | X2D datasheet | |
| 4 | `performance_published.max_flight_time_min` | 35 | X2D datasheet | |
| 5 | `performance_published.max_wind_resistance_ms` | 10.3 | X2D datasheet | **conflicting** - see below |
| 6 | `performance_published.max_speed_ms` | 11.2 | X2D datasheet | **conflicting** - the field the variant question moves |
| 7 | `physical.rotor_count` | 4 | DHS S&T | **only aircraft fact not cited to Skydio** - second source wanted |
| 8 | `battery.chemistry` | lithium polymer | Skydio support | **conflicting** - retail listing says lithium-ion |

Two sub-items:

- **`max_wind_resistance_ms` has an intra-X2D conflict**, unrelated to the
  variant question: the datasheet says 10.3 m/s, the X2D User Guide says
  11.2 m/s. Adjudicate on its own merits and record the reasoning.
- **ESC-1 says "All five airframe fields are cited to X2D documents."** Six
  fields are cited to the X2D datasheet (rows 1-6). Reconcile the wording.

### SQS-006 (part a) - quote authenticity. OPEN. BLOCKING at R2.

Nine parameters carry a `source_quote`. A reviewer must open each cited source
and confirm the quoted string appears in it **and supports the value beside
it**. Structural checks (SQS-002, SQS-003, SQS-004) all pass, which confirms
the quotes are well-formed - it says nothing about whether they are real.

Not blocking today, because the record is R0 and blocked on harder grounds.
Blocking before any R2 promotion.

### CC-008 - re-run on fill. OPEN as a standing condition.

Ratified today only because four of five paths are empty. Must be re-reviewed
when they are filled.

---

## 7. What this review did not do

- **No file was changed.** Record, schema and suite are untouched.
- **No failure was suppressed.** The 4 failures and 1 warning stand in the
  report. Three of the four are believed to be the CC-007 tier bug; they were
  not reclassified, because the suite is frozen.
- **No source was opened.** Every closure in section 2 rests on inspecting
  code and the record. XF-014 and SQS-006(a) require source access and remain
  open for that reason.
- **The entity was not promoted.** It stays R0 STUB, and the gate continues to
  refuse it.

## 8. Next review triggers

Re-run this review when any of the following occurs:

1. Any REQUIRED_MEASURED path is filled (changes the tier calculation).
2. The variant changes again (invalidates XF-016 and XF-014 together).
3. The suite is revised past v3.0.0 (CC-007 may stop firing; skipped tests may
   start).
4. The schema is amended for RT-005 or VT-005B.
5. A decision is taken on the `max_hover_time_min` policy question.
