<!-- ASCII NOTE 2026-09-11: editorial punctuation in this log was
transliterated to comply with the project's ASCII policy - em and en
dashes to '-', arrows to '->', section signs to 's', multiplication
signs to 'x', ellipses to '...', check marks to '[OK]'. No verbatim
quoted material was altered; every quoted source string in this file
was already ASCII. No finding, value or citation changed. -->

# Research log - UAS-QUAD-SKYDIO-X2DENTERPRISE

Target record: `drafts/UAS-QUAD-SKYDIO-X2DENTERPRISE.json`
Schema: `catalog/schema/entity_schema_3.0.json` (read; not modified)
Governing prose: `STANDARDS.md` sections 3, 4, 5, 12
Configuration as given: *Skydio X2D, Enterprise variant, standard configuration, stock battery*

---

> **AMENDMENT 2, 2026-09-10 - ESC-1 RE-RESOLVED TO X2D. This supersedes Amendment 1.**
> The owner corrected the variant to the **Skydio X2D** (defense), on the grounds that
> this catalog feeds a **military simulation**. The record has been re-based back onto the
> X2D line: display name, `max_speed_ms` 13.9 -> **11.2 m/s**, and all five airframe
> citations returned to X2D documents. This restores the values sections 0-6 describe, so
> those sections are once again accurate as written. See **s9** for the full amendment
> record and for the one thing this change breaks - an `entity_id` collision that now
> blocks promotion.
>
> <sub>**Amendment 1, superseded:** ESC-1 was first answered "X2E" and the record was
> re-based onto the X2E line. s8 is retained as the record of that turn. Nothing from it
> survives in the current file except the X2E readings kept in `conflicting_values`.</sub>

---

## 0. The headline finding, before any numbers

**"Skydio X2D, Enterprise variant" does not exist as a Skydio configuration.**

Skydio's X2 line splits into exactly two aircraft:

| | X2D | X2E |
|---|---|---|
| Positioning | **Defense** | **Enterprise** |
| Radio | 1.8 / 5 GHz | 5 GHz |
| Wireless encryption | AES-256 | AES-128 |
| Max range | 10 km (1.8 GHz) / 6 km (5 GHz) | expected up to 6 km |
| **Max flight speed (SL, no wind)** | **25 mph (40 km/h)** | **31 mph (49-50 km/h)** |
| Weight, dimensions, flight time, wind resistance | identical | identical |

"D" *is* the defense variant and "E" *is* the enterprise variant. The request pairs
the defense airframe with the enterprise qualifier. The only "Enterprise" thing that
legitimately attaches to an X2D is the **software** add-on *Skydio Autonomy Enterprise
Foundation*, which appears on the X2D datasheet under "Optional add-ons" - a licence,
not an airframe.

This is escalated as **ESC-1** in the record (R11: "you cannot determine which variant
a source describes"). It is blocking for one field and one field only - `max_speed_ms`,
which moves 24 percent between the two readings - because every other figure the two
product lines publish is identical. That is why the record was built rather than
withheld: the escalation is narrow and localised, and the remaining 32 parameters do
not depend on its answer.

The record was populated from the **X2D** line, on the grounds that the `entity_id`
string carries X2D and X2D is the literal model named. Every X2E figure that disagrees
is preserved in `conflicting_values` rather than discarded, so if the answer comes back
"X2E" the edit is mechanical.

A second, milder ambiguity is recorded as **ESC-2**: "standard configuration" was not
defined, and the X2D ships in at least two payload packages (Color/Thermal dual-sensor,
and Color single-sensor). Color/Thermal was treated as standard. No airframe figure in
the record depends on the choice - both datasheets print 1325 g and identical dimensions.

---

## 1. Sources consulted

Ranked as used. All publicly reachable, none behind a login, none distribution-limited.

### Primary - manufacturer

| # | Source | Reached | What it gave |
|---|---|---|---|
| S1 | **Skydio X2D Color/Thermal datasheet** (skydio.com/ja-jp/resources/datasheets/skydio-x2d-colorthermal) | fetched, PDF text extracted | The spine of this record: weight, both dimension sets, flight time, max flight speed *with conditions*, max wind speed resistance, service ceiling, temperature range |
| S2 | **Skydio X2D datasheet** (pages.skydio.com, `skydio-x2d-datasheet-v2-defense-pg.pdf`) | fetched | 1325 g, dimensions, 35 min - corroboration |
| S3 | **Skydio X2D datasheet** (webflow-hosted earlier revision) | fetched | Same three figures - corroboration |
| S4 | **Skydio X2D Color datasheet** (pages.skydio.com) | fetched | Same airframe figures plus speed/wind/ceiling. *Different payload package* - treated as corroboration for airframe rows only |
| S5 | **Skydio X2E Operator Manual, 2023** (Specifications, pp. 75-78) | fetched | Finer metric dimensions (66.3 x 56.9 x 21.1 cm), and the **31 mph** conflict |
| S6 | **Skydio X2E Color/Thermal datasheet, 28 Nov 2023** | fetched | Second instance of the 31 mph conflict |
| S7 | **Skydio X2E datasheet** (pages.skydio.com) | fetched | Airframe rows - corroboration |
| S8 | **Skydio support: "How to charge and maintain your Skydio X2 batteries"** | browser (WebFetch 403) | Battery chemistry (LiPo). **No** capacity, voltage or cell count |

### Government / defense

| # | Source | Marking | What it gave |
|---|---|---|---|
| S9 | **DHS S&T, "Urban OpEx 2022 Skydio X2 Autonomous Unmanned Aircraft System Technology Report"**, OpEx-T-R-15, 23 Jan 2023 | **"Approved for Public Release"** on every page - checked explicitly per R4/R11 | `rotor_count` ("four propellers"); independent restatement of 35 min and 12,000 ft; qualitative endurance feedback |
| S10 | **Skydio X2D User Guide**, eff. 6 Apr 2021, FCC filing 2ATQRSMO5GV1 | public FCC exhibit | Max speed as **air speed vs ground speed**; the 25 mph winds-or-gusts prohibition; four-arm airframe |

### Defense press

| # | Source | What it gave |
|---|---|---|
| S11 | army-technology.com, "Skydio X2D Reconnaissance Drone" | "1.3kg", "35 minutes", "10km" - all rounded restatements of S1. Confirms X2D = military, X2E = civilian |

### Aggregator / retail - consulted, mostly **rejected**

| # | Source | Outcome |
|---|---|---|
| S12 | Adorama, part SKYX2BAT100NA | Opened directly in-browser. **DOM contains no Wh, mAh, voltage or capacity field at all.** Yielded only the lithium-ion chemistry claim, which *was* read verbatim and is recorded as a conflict |
| S13 | Search-engine spec snippets (Adorama / grescouas / eBay) | **Rejected.** See s3 |
| S14 | originofbots.com | **Rejected.** See s3 |
| S15 | Wikipedia, "Standard sea-level conditions" | Used for `air_density_kg_m3`, cited *through* to its origin (McCormick 1979) with confidence dropped to `literature` per R6 |
| S16 | Safeware / safewarecontracts | 404 on the item page. Dead end |

Per-field source counts stayed within the R12 budget of six. The two battery
REQUIRED_MEASURED fields hit exactly six (S1, S4, S2, S5, S8, S10) with nothing found,
and the search stopped there rather than continuing until something turned up.

---

## 2. What was filled, and the reasoning

**9 present, 24 declared gaps, out of 33 declared parameters. No key is absent.**

### `physical.mass_kg` = 1.325 kg - REQUIRED_MEASURED, published
`1325 g` from S1, converted once (`/1000`), four sig figs as published. Corroborated
identically by S4 and S5. S9 says "2.9 pounds" = 1315 g; that is a rounding of 2.921 lb,
**not** an independent measurement, so it is noted as corroboration and *not* filed as a
conflict. Calling it a conflict would have been theatre.

### `physical.rotor_count` = 4 - REQUIRED_MEASURED, published
Quoted from S9 ("Well-designed with four propellers") rather than asserted from the
category. The sibling `UAS-QUAD-SKYDIO-X2D` record carries this with source "Quadcopter
airframe" and the note "Definitional from the category, not a measurement" - honest, but
a real quote is strictly better, and one was available.

### `physical.dimensions_unfolded_mm` / `dimensions_folded_mm` - OPTIONAL, published
Converted from the **inches**, not from the datasheet's own rounded centimetres, per R7.
The check that this was the right call: S5 prints `66.3 cm X 56.9 cm X 21.1 cm` for the
same inch figures, which matches the inch conversion to the millimetre and confirms
inches are the original unit. Folded dimensions are flagged **battery removed**.

### `battery.chemistry` = lithium polymer (LiPo) - OPTIONAL, published, **conflicting**
S8 (manufacturer) says LiPo. S12 (retailer, same part number) says lithium-ion. Both
quoted, both recorded, manufacturer used. Not cosmetic: the two chemistries have
different discharge curve shapes and different safe cutoffs.

### `performance_published.max_flight_time_min` = 35 min - OPTIONAL, published
Appears in S1, S2, S3, S4, S5 and is restated by S9 - but **all six trace to one
manufacturer claim**, so the `note` says so rather than implying six-way agreement.
Per R9 the `conditions` field records what is actually missing: no airspeed, no wind, no
altitude, no temperature, no start/end state of charge. Skydio's own hedge is the words
"Up to". This is a marketing ceiling and the record says so.

### `performance_published.max_wind_resistance_ms` = 10.3 m/s - OPTIONAL, published, **conflicting**
23 mph (S1, "Max Wind Speed Resistance") vs 25 mph (S10, "should not be flown when winds
or gusts are above"). Different quantities - a capability figure and an operating
prohibition. Used the capability figure. Flagged in the note that the prohibition sits
*above* the capability, which is the wrong direction for a safety limit and is worth a
query to Skydio. `23 x 0.44704 = 10.28192`, rounded to `10.3`.

### `performance_published.max_speed_ms` = 11.2 m/s - REQUIRED_MODELING, published, **conflicting**
Four values recorded. The split is **by variant, not by scatter**:
- X2D (S1): 25 mph (40 km/h), sea level, no wind
- X2D (S10): 25 mph air speed / **35 mph ground speed**
- X2E (S5): 31 mph (49 km/h) "fully autonomous"
- X2E (S6): 31 mph (50 km/h)

Used 25 mph: the entity is named X2D, and S10 independently corroborates it as *air
speed*. The 35 mph ground-speed figure is a third quantity and is not usable as a
still-air ceiling. `25 x 0.44704 = 11.176` -> `11.2`.

This field is REQUIRED_**MODELING**, so R11's 20-percent trigger does not formally bind
it. It is escalated anyway under ESC-1, because the 24-percent gap *is* the variant
question in numeric form.

### `aerodynamic_assumptions.air_density_kg_m3` = 1.225 - REQUIRED_MODELING, **literature**
Read on Wikipedia; Wikipedia attributes the table to McCormick, *Aerodynamics,
Aeronautics, and Flight Mechanics* (Wiley, 1979). Per R6 the citation names the textbook
as origin, the `source_url` honestly shows Wikipedia as the page actually read, and
confidence is `literature`, not `published`. The textbook was not opened.

Filled rather than gapped because it is an environmental constant, not a fact about this
aircraft, and it matches every other entity in the catalog. The `note` records the
tension worth knowing: Skydio publishes a 12,000 ft service ceiling, where 1.225 is well
off.

---

## 3. What was **not** filled, and why that was the right answer

### The four blocking gaps

| Field | Class | Why it is empty |
|---|---|---|
| `performance_published.max_hover_time_min` | REQUIRED_MEASURED | **The calibration anchor.** Skydio publishes one endurance number and never distinguishes hover from cruise. Zero values found - so R11's *three-or-more-values* trigger did not fire; the opposite problem applies |
| `battery.capacity_wh` | REQUIRED_MEASURED | Not published by Skydio anywhere. See below |
| `battery.voltage_full_v` | REQUIRED_MEASURED | Same |
| `physical.propeller_diameter_m` | REQUIRED_MEASURED | No Skydio document carries propeller geometry |

Because `max_hover_time_min` is absent, **nothing can be fitted and the gate must
REFUSE**. `readiness_declared` is `R0`. That is the correct output, not a defect.

### The battery numbers, and the temptation that was refused

Search engines confidently attribute **48.79 Wh / 4280 mAh / 11.4 V** to the X2 pack.
That would have closed two REQUIRED_MEASURED fields in one stroke. It was refused, for
three reasons that compound:

1. **It could not be read.** The Adorama page for SKYX2BAT100NA was opened directly in a
   browser and its DOM searched for `Watt|Voltage|mAh|Battery Capacity`. Result:
   `NO SPEC KEYWORDS IN DOM`. R5 is explicit - if you cannot quote it, you did not read
   it.
2. **The aggregation is demonstrably contaminated.** The same snippet that carried those
   numbers also carried "approximately 23 minutes of flight time". The X2 is a 35-minute
   aircraft. 23 minutes is a **Skydio 2/2+** figure. The snippet is blending two
   different products, so its other numbers are not trustworthy either.
3. **The sources disagree with each other anyway.** An eBay listing title for the same
   part number reads 11.55 VDC, against the snippet's 11.4 V.

R13 would have permitted a `literature`-tier fill with an explanatory note *if a
literature-tier source existed*. One did not: an unreadable retail page is not a source
at any tier. Both fields are `missing` with a todo naming the concrete routes that would
close them - the pack's own regulatory Wh marking, a Skydio dangerous-goods declaration,
or the FCC/IC test report for aircraft radio FCC ID 2ATQRSDRC2V1, whose EUT description
customarily states DC supply voltage.

The same reasoning rejected `max_ascent_speed_ms` (22 mph) and `max_descent_speed_ms`
(9 mph) from originofbots.com - unread page, low-tier aggregator, and that aggregator's
*max speed* figure contradicts both Skydio X2D datasheets. These are OPTIONAL reporting
fields; laundering an aggregator to fill them would buy nothing and cost the record's
credibility.

### Two traps flagged for the next author

- **`max_flight_distance_km` is not 10 km.** The famous "up to 10 km" is *wireless
  control range at 1.8 GHz* - the datasheet row is literally "Wireless range at 1.8 GHz",
  with a second row at 6 km for 5 GHz. Recording it as a distance anchor would be a
  category error, and it is the single most likely mistake here.
- **`max_hover_time_min` is not 35 minutes.** 35 min is already claimed as the *held-out*
  anchor (`max_flight_time_min`), and the schema forbids an anchor being both fitted to
  and held out. Copying it across would silently destroy the only falsification test this
  entity has.

### Deliberately out of scope

Per R10, the four modelling choices - `figure_of_merit`, `motor_esc_efficiency`,
`propulsive_efficiency`, `profile_power_mu_factor` - were **not researched**. They are
`missing`, and each todo says so explicitly and names the value the sibling
`UAS-QUAD-SKYDIO-X2D` record carries, with a warning not to copy it across unratified.

Per R15, **no calibration block was produced**. `calibration` is `null`. This leaves the
schema's `calibration_block_present` cross-field rule unsatisfied - a declared
consequence of the run's scope, recorded in `_calibration_note` rather than papered over.

---

## 4. Two places this record knowingly departs from STANDARDS.md

Both are consequences of binding task rules, and both are recorded *in the record* rather
than only here.

1. **`verified_on` is absent, and `compiled_on` / `compiled_by` are null.** STANDARDS.md
   s3 makes `verified_on` mandatory on a present parameter. R14 assigns these three to the
   promotion step and forbids this run from writing them. R14 was followed;
   `_metadata_note` in the record states the departure. The three top-level keys are
   *present but null* rather than omitted, so `required_top_level_keys` still resolves.
2. **Conflicts carry both `conflicting`/`conflicting_values` (R3) and `contested`
   (STANDARDS s4/s12.4).** The two documents name the same mechanism differently. Rather
   than pick one and fail the other check, conflicted fields carry both flags, with the
   full both-values-both-sources structure R3 requires.

---

## 5. Verification run

The record was checked programmatically against the schema before submission:

- 33 declared parameters, **33 present as keys, 0 absent** (R1 satisfied).
- Status coherence: **0 errors.** No number under `missing`, no null under `present`, no
  `confidence` on a gap, no gap without a `todo`.
- Every present parameter carries `value`, `confidence` from the vocabulary, `source`,
  `source_url` and `source_quote`.
- All 17 `source_quote` strings are **under 200 characters** (longest: 139).
- All 8 required top-level keys resolve.

Not yet run: `catalog.py --entity`, `test_catalog.py`, `test_regression_pinned.py`. The
file is in `drafts/`, not `catalog/entities/`, so it is not yet on the loader's path -
those belong to the promotion step, alongside the metadata stamping.

---

## 6. Closing tally

| Metric | Count |
|---|---|
| Declared parameters in schema | 33 |
| **Fields filled** (status present) | **9** |
| **Fields missing** (declared gaps, each with a todo) | **24** |
| Fields absent (not recorded) | **0** |
| **Fields conflicting** | **3** - `battery.chemistry`, `performance_published.max_wind_resistance_ms`, `performance_published.max_speed_ms` |
| **Fields escalated** | **1 blocking (ESC-1), 1 advisory (ESC-2)** |
| REQUIRED_MEASURED resting on a **single source** | **0** |

**REQUIRED_MEASURED detail** (6 declared):

| Field | Status | Confidence | Independent sources |
|---|---|---|---|
| `physical.mass_kg` | present | published | 3 Skydio docs + DHS restatement |
| `physical.rotor_count` | present | published | DHS report + X2D User Guide |
| `physical.propeller_diameter_m` | **missing** | - | - |
| `battery.capacity_wh` | **missing** | - | - |
| `battery.voltage_full_v` | **missing** | - | - |
| `performance_published.max_hover_time_min` | **missing** | - | - |

**REQUIRED_MEASURED fields carrying `literature` or `estimated` confidence: NONE.**
Both filled REQUIRED_MEASURED fields are `published` and rest on more than one source, so
R13's confidence floor is met without needing the literature-tier exemption, and no
escalation marker is required on either. The only `literature` value in the record is
`air_density_kg_m3`, which is REQUIRED_MODELING, where `literature` is explicitly
acceptable.

**Escalation marker check (R13's defect condition):** no REQUIRED_MEASURED field carries
`literature` or `estimated` confidence, so the "literature/estimated without an
escalation marker" defect cannot arise here.

---

## 7. What to do next, in order

1. **Answer ESC-1.** X2D, X2E, or X2D-with-Enterprise-licence? Nothing downstream should
   be quoted until a human settles it. If X2E: change `max_speed_ms` to 13.9 m/s (the
   value is already sitting in `conflicting_values` with its quote and source) and change
   the `entity` display name. Nothing else moves.
2. **Get a hover endurance.** It is the calibration anchor; the entity is R0 until it
   exists, and `observed_hover_time_min` would close it too. Highest-value single item
   outstanding.
3. **Get the pack off the shelf and read its label.** The regulatory Wh marking closes
   `capacity_wh` and probably `voltage_nominal_v` and `weight_g` in one action.
4. **Identify the propeller.** Part SKYX2PRP100NA. Diameter closes one REQUIRED_MEASURED
   field and unblocks `thrust_coefficient` behind it.
5. **Then** stamp metadata, add the calibration block, promote to `catalog/entities/`, and
   run `catalog.py` -> `test_catalog.py` -> `test_regression_pinned.py`.

---

## 8. Amendment record - ESC-1 resolved to X2E (2026-09-10) - **SUPERSEDED BY s9**

> This section is retained as the record of a turn that was later reversed. Its
> conclusions are **no longer in force**. Read s9. It is kept because anyone comparing
> this file against a board output, an intermediate copy or a git object from the X2E
> interval needs to be able to see why `max_speed_ms` moved 24 percent and back again.


**Determination:** the aircraft is the **Skydio X2E**. Confirmed by the catalog owner in
response to ESC-1. This is the sole authority: no document reconciles the `entity_id`
string with the airframe, and none was found that could.

ESC-1 was **not deleted**. It is retained in the record with a `resolution` field, so a
future reader can see that the variant was *decided* rather than assumed. Deleting a
resolved escalation would erase exactly the evidence that the question was asked.

### A correction to what I told you at handover

I said the fix was "a two-line edit" and that "nothing else moves". **The values don't
move; the citations do, and that is more than two lines.** Five fields were quoted from
the *Skydio X2D Color/Thermal datasheet*. The X2E publishes identical figures, so no
number changed - but leaving an X2D citation inside an X2E record is precisely the
variant mismatch ESC-1 exists to catch, and it would have been invisible on any board
because every value would have validated. Each was re-quoted from the **Skydio X2E
Color/Thermal datasheet (28 November 2023)**.

### What changed

| Field | Value before | Value after | Citation moved? |
|---|---|---|---|
| `entity` (display name) | Skydio X2D | **Skydio X2E** | - |
| `performance_published.max_speed_ms` | 11.2 m/s (25 mph) | **13.9 m/s (31 mph)** | [OK] X2D -> X2E |
| `physical.mass_kg` | 1.325 kg | unchanged | [OK] X2D -> X2E |
| `physical.dimensions_unfolded_mm` | 663 x 569 x 211 | unchanged | [OK] X2D -> X2E |
| `physical.dimensions_folded_mm` | 302 x 140 x 91 | unchanged | [OK] X2D -> X2E |
| `performance_published.max_flight_time_min` | 35 min | unchanged | [OK] X2D -> X2E |
| `performance_published.max_wind_resistance_ms` | 10.3 m/s (23 mph) | unchanged | [OK] X2D -> X2E |

`31 x 0.44704 = 13.85824` -> **13.9**, converted once from the published mph. Worth
noting: the two X2E sources give *different* metric conversions of the same 31 mph - the
datasheet says 50 km/h, the Operator Manual says 49 km/h - which is exactly why R7 says
convert from the original unit and not from someone else's rounding.

### What was deliberately left pointing at X2D documents

- **`max_speed_ms` -> `conflicting_values`.** Both X2D readings (25 mph) are retained,
  now tagged with a `variant` field, as the *rejected* reading. A reader must be able to
  see what the other answer would have been. The field stays `contested: true` even
  after resolution - the 24 percent spread is the residual uncertainty, and the X2E
  figure carries the Operator Manual's "fully autonomous" qualifier, which may not
  describe a manual-stick ceiling.
- **`max_wind_resistance_ms` -> the 25 mph gust prohibition** is quoted from the X2D User
  Guide. Retained on purpose: it is the only place Skydio states a gust limit at all, and
  its text says "Skydio X2" throughout rather than "X2D".
- **The "documents searched" lists** in the `capacity_wh` and `max_hover_time_min` todos
  now lead with the X2E documents and keep the X2D ones, flagged as checked because the
  airframe and pack are common to both variants. That is a stronger negative result than
  listing only X2E sources would be.

### Two things that got *better* on resolution

- **`rotor_count`** cites the DHS S&T report, which evaluated the X2 with FDNY and other
  first responders - the enterprise/public-safety role the X2E is actually sold into.
  A better variant match than it was.
- **`battery.chemistry`** cites a Skydio support article filed under *Skydio X2
  Enterprise / Getting Started X2E*. Also now a direct match.

### The residual, and it is not cosmetic

**`entity_id` remains `UAS-QUAD-SKYDIO-X2DENTERPRISE`, which still contains "X2D".** That
id was settled by separate direction, and STANDARDS.md s2 states an id never changes once
published. It is now *known* to be a misnomer: the display name, category and every
citation describe an X2E; only the identifier is legacy. This is flagged in ESC-1's
`residual` field so nobody infers the airframe from the id string.

This is worth a decision while the file is still in `drafts/` and the "never changes once
published" rule has not yet bitten. If the id is going to be corrected to something like
`UAS-QUAD-SKYDIO-X2E`, now is the only cheap moment - after promotion it is permanent,
and the validation suite at
`catalog/tests/validation_suite_UAS-QUAD-SKYDIO-X2DENTERPRISE.yaml` would need renaming
alongside it. Its own open item OI-1 anticipated this: it recorded that the id direction
"does not, by itself, establish which physical configuration the record's numbers
describe", kept test XF-014 open at `gap` severity for that reason, and warned that
settling the id would make an internally consistent record *look* reconciled while the
configuration question stayed open. That question is now answered - and the answer is
that the id and the airframe disagree.

### Revised tally

Structurally unchanged: **9 filled, 24 declared gaps, 0 absent, 3 contested, 33/33 keys
present, 0 coherence errors, 17 quotes all under 200 chars.** Still R0/STUB - the four
blocking gaps (hover time, pack Wh, full-charge voltage, propeller diameter) are
airframe-common and were untouched by the variant decision. Still **zero**
REQUIRED_MEASURED fields carrying `literature` or `estimated` confidence.

---

## 9. Amendment record - ESC-1 RE-RESOLVED to X2D (2026-09-10). In force.

**Determination:** the aircraft is the **Skydio X2D**, the defense variant. Confirmed by
the catalog owner, on the stated grounds that this catalog feeds a **military
simulation**. This supersedes Amendment 1 (s8) in full.

That reasoning is worth recording rather than just the answer: the X2D is the variant
Skydio builds to exceed the U.S. Army Short-Range Reconnaissance requirement, carries
AES-256 rather than AES-128, and adds the 1.8 GHz radio. For a military simulation it is
the right airframe, and the segment this entity is filed under -
`SEG-US-DEF-2020S-QUAD-G1`, *"Group 1 quadcopter, defense"* - agreed with X2D all along.
The segment was never re-examined during the X2E interval; it should have been, and the
mismatch would have caught the error one turn earlier.

### What moved back

| Field | X2E value (Amdt 1) | **X2D value (now)** | Citation |
|---|---|---|---|
| `entity` | Skydio X2E | **Skydio X2D** | - |
| `performance_published.max_speed_ms` | 13.9 m/s (31 mph) | **11.2 m/s (25 mph)** | X2E -> **X2D** |
| `physical.mass_kg` | 1.325 kg | unchanged | X2E -> **X2D** |
| `physical.dimensions_unfolded_mm` | 663 x 569 x 211 | unchanged | X2E -> **X2D** |
| `physical.dimensions_folded_mm` | 302 x 140 x 91 | unchanged | X2E -> **X2D** |
| `performance_published.max_flight_time_min` | 35 min | unchanged | X2E -> **X2D** |
| `performance_published.max_wind_resistance_ms` | 10.3 m/s (23 mph) | unchanged | X2E -> **X2D** |

`25 x 0.44704 = 11.176` -> **11.2**, converted once from the published mph.

One thing improves on the X2D reading: the 25 mph figure is independently corroborated
as **air speed** by the X2D User Guide, which is the quantity the energy model wants. The
X2E's 31 mph carried the Operator Manual's *"fully autonomous"* qualifier and no
air-vs-ground distinction. The X2D answer is the better-characterised number, not merely
the different one.

`conditions` on `max_speed_ms` now also records something that matters for a military
sim specifically: the User Guide states max speed is **reduced** with obstacle avoidance
set to Close or Minimal, or in GPS Night Flight. All three are plausible mission states.
25 mph is a ceiling, not a planning speed.

### On "we don't need anything related to Enterprise"

Applied to the aircraft, not as a word filter. The word still appears in eight places and
each is deliberate:

- **`entity_id`** - unresolved, see below.
- **ESC-1's `issue` and `residual`, and `_entity_id_note`** - these *explain* that the
  Enterprise framing was wrong. Deleting the explanation would leave a record that had
  silently changed variant twice with nothing saying why.

What was removed is the Enterprise *framing*: the X2E citations, the X2E display name,
ESC-2's X2E payload packages, and the "filed under X2E - a direct match" note on
`battery.chemistry`, which is now correctly a **caveat** rather than a point in the
source's favour.

Two X2E readings are deliberately **kept** in `max_speed_ms.conflicting_values`, tagged
`"variant": "X2E - retained as the rejected reading of ESC-1"`. R3 requires conflicts be
preserved rather than resolved away, and this particular conflict was answered both ways
inside one session - a reader is entitled to see both.

### The collision this creates - and it blocks promotion

**With the variant back to plain X2D, the natural `entity_id` is
`UAS-QUAD-SKYDIO-X2D` - and that id is already taken.**

`catalog/entities/UAS-QUAD-SKYDIO-X2D.json` exists, is committed, and describes the same
aircraft. So:

- **Renaming and promoting collides.** Same id, same filename, two files.
- **Promoting as `X2DENTERPRISE` double-counts.** Segment `SEG-US-DEF-2020S-QUAD-G1` has
  `planned_entity_count: 3`. Two entity files for one airframe make the coverage board
  read **2 of 3 populated** when one distinct aircraft is documented. The coverage plan's
  own stated purpose is that *"a catalog that only reports what it contains cannot report
  a hole in itself"* - this would put a false unit of progress on that board.

The existing stub is thinner than this record everywhere that is sourced. It has exactly
six populated fields:

| | Existing stub | This draft |
|---|---|---|
| `rotor_count` | 4, source *"Quadcopter airframe"* | 4, quoted from the DHS S&T report |
| `air_density_kg_m3` | 1.225, ISA | 1.225, cited through to McCormick |
| `mass_kg`, dims x2, flight time, wind, max speed, chemistry | **all missing** | **all sourced and quoted** |
| `figure_of_merit` 0.65 | **present**, literature | missing (R10 - not researched) |
| `motor_esc_efficiency` 0.80 | **present**, literature | missing (R10) |
| `propulsive_efficiency` 0.70 | **present**, literature | missing (R10) |
| `profile_power_mu_factor` 4.65 | **present**, literature | missing (R10) |

**A straight overwrite would lose those four modelling constants.** They are the only
things the old stub has that this record does not, and only because R10 put them out of
scope for this run. They must be carried across deliberately and re-ratified by a human -
not lost, and not copied in silently either, since STANDARDS.md s12.5 puts exactly that
kind of choice with a person.

This is recorded in the record itself under `_entity_id_note` and in ESC-1's `residual`.
**It is a human decision and it is the last thing blocking promotion.**

### Revised tally

Structurally unchanged, and identical to first compilation: **9 filled, 24 declared gaps,
0 absent, 3 contested, 33/33 keys present, 0 coherence errors, 17 quotes all under 200
chars.** Both filled REQUIRED_MEASURED fields (`mass_kg`, `rotor_count`) are `published`
on multiple sources; **zero** REQUIRED_MEASURED fields carry `literature` or `estimated`.
Still **R0/STUB** - the four blocking gaps are airframe-common and neither variant turn
touched them.

---

## 10. Suite-independence disclosure (2026-09-10)

Raised by the catalog owner as a sanity check: *why was the compiling agent reading the
validation suite, and did any data come from it?* Recorded here because the answer
affects how much weight a suite pass on this record can carry.

### What was read, and when

`catalog/tests/validation_suite_UAS-QUAD-SKYDIO-X2D.yaml` (then named for the
`X2DENTERPRISE` id) was opened during initial repo orientation, **before any research** -
the header, the `open_items` block, and the `derived_sets` block. It was consulted again
after the X2D reversal, for its header and amendments list.

**This was a mistake.** The suite's author states they deliberately did not open
`catalog/entities/`, so that no assertion could be reverse-engineered from a populated
record. Reading it from the other direction breaks the same guarantee symmetrically: the
record can be shaped to the test. The compiling task named
`catalog/schema/entity_schema_3.0.json` and `STANDARDS.md`; it did not name the suite.

### Did data come from it? No.

The suite contains **no aircraft data at all**. Grepping it for every value in this record
(`1325`, `663`, `35 min`, `23 mph`, `25 mph`, `10.3`, `11.2`, `1.225`, `LiPo`, ...) returns
nothing. The only decimal literals in its 95 KB are version numbers. It asserts structure
and procedure, never that a value is true - exactly as its own preamble says.

All nine present values trace to external sources, each with a verbatim quote: seven to
the Skydio X2D Color/Thermal datasheet, one to the DHS S&T report, one to Skydio support,
one to McCormick via Wikipedia.

### What it *did* influence - structure, not data

Two formatting decisions were made with the suite's open items in view:

- **Per-parameter `verified_on` omitted rather than written as null** - because OI-7/XF-009
  flags unparseable `verified_on` values at warn severity.
- **`compiled_on` / `compiled_by` present as null keys rather than omitted** - because
  OI-10/TL-002 asserts the required top-level keys are present.

R14 and R1 would probably have produced the same two choices on their own merits.
"Probably" is not "certainly", and both were decided partly to score well against a test
rather than purely on the merits. That is recorded rather than argued away.

### The one place an unsourced claim was imported - found and corrected

At suite v2.2.0 the header added: *"The X2E is a SIBLING airframe, not a variant of this
one, so an X2E source is a different aircraft."* This prompted a real catch - five notes
in this record had described the X2E as corroboration *"for the same common airframe"*,
an assertion never sourced, and therefore an R2 violation.

**But the fix imported the opposite unsourced claim.** The replacement text asserted, as
fact, that the X2E *is* a sibling airframe and *not* a variant - the suite's framing,
equally unsourced. One R2 violation was swapped for its mirror image.

Corrected on all five fields. The text now records the actual epistemic state:

> WHETHER THE X2D AND X2E SHARE AN AIRFRAME IS UNSOURCED, in both directions: no source
> was found stating they share structure, and none was found stating they do not.

No value changed at any point in this - every figure was already quoted from an X2D
document. What changed was the characterisation of X2E agreement: from *corroboration*,
to a borrowed claim, to *consistency under an open question*.

### Consequence for the suite

**A pass on this record is no longer fully independent evidence.** The suite can still
catch a structural defect this record happens to have - as it just did - but it can no
longer be cited as an untainted check, because the record was authored with its open
items in view. Two options for restoring that, both for the owner:

1. Have the suite re-verified by someone who has not read this record, and treat the
   current pass as provisional until then.
2. Accept it as a linter rather than an independent validator, and say so where the
   suite's result is quoted.

The values themselves are unaffected under either option: they rest on quoted external
sources, and the suite never contained a number to leak.
