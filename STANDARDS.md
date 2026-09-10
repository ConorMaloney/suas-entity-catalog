# STANDARDS.md - How to build a catalog entity

This is the governing document for anyone adding or amending an entity in
`catalog/entities/`. It is written to be followed literally, by a person or by
an AI agent, without needing to ask what was meant.

The machine-readable half lives in `catalog/schema/entity_schema_3.0.json` and
is enforced by `catalog.py`. **This document does not restate the parameter
list**; it points at the schema, so prose here cannot drift from what the
validator actually checks. Where this document and the schema disagree, the
schema wins and this document is the bug.

---

## 1. The one rule everything else serves

**A number must never appear more trustworthy than its source.**

Every other rule below is a mechanism for enforcing that one. If you are ever
unsure what to do, choose the option that makes a weak number look weak.

---

## 2. What an entity file is

One JSON file per entity, at `catalog/entities/<entity_id>.json`. The filename
must equal the `entity_id` inside it; the loader refuses a mismatch, because
copying an existing entity and forgetting to change the id inside is the
commonest way to corrupt a catalog.

`entity_id` format: `UAS-<CONFIG>-<MAKER>-<MODEL>`, uppercase, hyphen
separated, no spaces. Example: `UAS-QUAD-DJI-MAVIC3`. It is an identifier, not
a label - it never changes once published, even if the marketing name does.

---

## 3. Every parameter carries its own provenance

A parameter is an object, never a bare value:

```json
"mass_kg": {
  "value": 0.895,
  "unit": "kg",
  "confidence": "published",
  "source": "DJI Mavic 3 Classic specs - Takeoff Weight",
  "source_url": "https://www.dji.com/mavic-3-classic/specs",
  "verified_on": "2026-09-09",
  "note": "DJI standard weight includes battery, propellers and microSD card."
}
```

`value`, `confidence` and `source` are mandatory for a present parameter.
`verified_on` is mandatory. `source_url` where one exists. `note` where the
number needs explaining.

A bare `"mass_kg": 0.895` is a schema error. It is not shorthand; it is an
unsourced number, and unsourced numbers are the thing this catalog exists to
prevent.

---

## 4. The confidence vocabulary

Defined in the schema file. Repeated here only as a decision procedure:

| If the number came from | Use |
|---|---|
| The vendor's specification sheet or official manual | `published` |
| Arithmetic on published values | `derived` - state the computation in `note` |
| A peer-reviewed paper or engineering textbook | `literature` - cite it |
| Your own judgement | `estimated` - state the basis AND a tolerance |

**Choosing the flattering label is the failure mode.** `estimated` is not an
admission of sloppiness; it is the correct label for a defensible engineering
judgement, and mislabelling one as `literature` to make a record look stronger
is falsification. If you cannot name the paper, it is not `literature`.

When two credible sources disagree, do not average them and do not silently
pick one. Record the one you are using, set `"contested": true`, and put both
figures and your reasoning in `note`. The Mavic 3's hover time is the worked
example: DJI's specifications page says 40 minutes, DJI's own manual says 42.

---

## 5. Declaring a gap

An unknown parameter is recorded, not omitted:

```json
"figure_of_merit": {
  "value": null,
  "status": "missing",
  "todo": "Needs a rotor efficiency figure. Try the manufacturer's motor data, or a wind-tunnel paper for a comparable 9-inch propeller."
}
```

`status: "missing"` requires `value: null`, forbids `confidence`, and requires
a `todo` saying what would close the gap. `status: "not_applicable"` is the
same but requires a `note` explaining why the parameter does not apply.

Leaving the key out entirely is legal but reports as **NOT RECORDED** rather
than **DECLARED GAP**. The distinction is deliberate: an author who wrote
`status: "missing"` has demonstrably looked and failed to find it; an author
who omitted the key has not looked. Both block modelling. Only one of them
tells the next person anything.

**You may not put a plausible number in a field you have not sourced.** This is
the single most likely thing to go wrong, because an empty field looks like
unfinished work and filling it feels like progress. It is not progress. A
catalog whose board reads "1 of 3 entities modelable" is more useful than one
reading "3 of 3" on invented data, because the first can be trusted and acted
on and the second cannot.

---

## 6. Requirement classes

Four, defined in the schema. The split that matters:

- **`REQUIRED_MEASURED`** must be `published` or `derived`. These are the
  parameters the model is most sensitive to - mass, propeller diameter, rotor
  count, pack capacity, and the hover anchor. The sensitivity table in
  `battery_model.py` shows mass and propeller diameter moving endurance by
  about 20 percent for a 20 percent change. A guess in any one of them
  invalidates everything downstream no matter how well sourced the rest is.
- **`REQUIRED_MODELING`** may be `literature` or `estimated`. These are
  modelling choices rather than facts about the aircraft - figure of merit,
  motor efficiency, equivalent flat plate area. A `source` is still mandatory
  so the choice is auditable.

That split is why the Mavic 3 reaches R3 while carrying `estimated` values for
avionics power and empty-cell voltage. A flat "no required parameter may be
estimated" rule would park the best-documented entity in the catalog at
PROVISIONAL forever and make the tier system useless.

---

## 7. Readiness tiers

Computed by `catalog.py`, never asserted. The file carries
`readiness_declared`, `catalog.py` computes the tier independently, and
`test_catalog.py` **fails the build if the computed tier is below the declared
one**. Writing `"readiness_declared": "R3"` in a stub does not make it R3; it
makes the test go red.

| Tier | Name | The gate does |
|---|---|---|
| R0 | STUB | **raises** - a required input is absent, so there is no number to produce |
| R1 | PROVISIONAL | runs, every output stamped with an unmissable banner |
| R2 | MODELED | runs clean |
| R3 | VALIDATED | quotable as a planning product |

Below R1 refusal is not a policy choice - the model cannot compute disk area
without a propeller diameter. At R1 the house style applies: this project
prints `FAIL`, prints `CALIBRATED` rather than hiding a fit, and ships red
boards. **Label loudly, do not withhold.**

---

## 8. Validation, and why a miss does not demote you

R3 requires at least **two** scorable held-out anchors. One held-out anchor
plus one fitted anchor is two equations in two unknowns and cannot falsify
anything; two is the minimum at which the model can be caught being wrong.

R3 asks whether an anchor is **scored and on the record**, not whether it is
green. The Mavic 3's cruise anchor misses by +14.2% and its range anchor by
+26.9%, and it is still R3.

That is deliberate. A "held-out anchors must pass" rule would demote the
best-documented entity in the catalog for being honest, and would create
standing pressure to widen tolerances until the board went green. A
pre-registered miss, whose direction and magnitude were called in advance, is
stronger evidence of understanding than a pass. See `PREDICTIONS.md` rule 4.

Exactly **one** parameter may be fitted. Declare it in the entity's
`calibration` block. A fitted anchor is reported `CALIBRATED`, never `PASS` -
it cannot fail by construction, so scoring it would be dishonest.

An anchor with no predictor is reported `UNSCORED` with a stated reason. Do not
invent a predictor to turn an `UNSCORED` row green: a new predictor is a new
falsifiable claim and must be pre-registered in `PREDICTIONS.md` before it is
run, not written to close a gap in a board.

---

## 9. Freshness

`verified_on` is when **you** checked the source, not when the source was
published. Re-checking an unchanged value is real work and updates the date.

Default thresholds, overridable with `--stale-days` and printed in the report
header so a reader can see which standard was applied:

- older than **180 days**: WARN. Re-check before briefing it.
- older than **365 days**: blocks R3. Do not brief it.

This means the Mavic 3 automatically demotes from R3 to R2 on 2027-09-09
without anyone touching the file. **That is a feature.** A catalog that never
decays is a catalog lying about its freshness. Vendors revise specification
pages on roughly annual product-refresh cycles, so a year-old figure is a
figure that deserves a second look.

A `verified_on` in the future is an error, not a very fresh value.

---

## 10. Adding an entity: the procedure

1. Copy an existing entity file. Rename it to `<entity_id>.json` **and change
   `entity_id` inside it.**
2. Set `readiness_declared` to `"R0"`. Raise it only when `catalog.py` agrees.
3. Work through `catalog/schema/entity_schema_3.0.json` parameter by
   parameter. For each: find a source, record it, set the confidence honestly.
   Where you cannot, write `status: "missing"` with a `todo`.
4. Fill the `calibration` block: one fitted parameter, its anchor, and the
   held-out anchors. The fitted anchor may not also be held out.
5. Run `python catalog.py --entity <entity_id>`. Fix every ERROR. Read the
   gaps table.
6. Run `python test_catalog.py`. It must exit 0.
7. Run `python test_regression_pinned.py`. It must exit 0 - adding an entity
   must never move an existing entity's numbers.
8. Commit the entity and its board output together.

## 11. Amending an existing entity

Changing a `value` on a published entity can move a number that appears in
`PREDICTIONS.md`, `VALIDATION.md`, `README.md` or a committed `results/` file.

So: run `python test_regression_pinned.py` before and after. If a pin moves,
that is a decision, not an accident. Edit the pin **by hand**, in a commit
whose message says why it moved, and check every document that quotes the old
value. There is deliberately no tooling to auto-update a pin.

---

## 12. Instructions for an AI agent working in this catalog

You are a force multiplier for research and data entry, and you are also the
most likely source of a confident, well-formatted, wrong number. These rules
exist because of that asymmetry.

1. **Never write a value you did not read from a source.** Not an
   interpolation, not a figure for a similar model, not a plausible round
   number. If you did not find it, write `status: "missing"` with a `todo`.
2. **Never write more precision than the source gives you.** If the spec sheet
   says 895 g, write `0.895`, not `0.8950000`. Trailing digits you did not
   measure are fabricated data. This has already happened once in this repo -
   see the header of `test_regression_pinned.py` - and the check caught it.
3. **Quote the source, do not paraphrase it into authority.** "DJI Mavic 3
   Classic specs - Takeoff Weight" is a source. "Manufacturer data" is not.
4. **When sources conflict, surface the conflict.** Set `contested`, record
   both, and say which you used and why. Do not resolve it silently, and do
   not average.
5. **Stop and ask when a modelling call is genuinely contested.** Choosing a
   figure of merit for an unfamiliar airframe is a judgement a human should
   make or ratify. Escalating is not failure; a fabricated constant that looks
   authoritative is.
6. **Run the checks and read the output.** `catalog.py --entity <id>`, then
   `test_catalog.py`, then `test_regression_pinned.py`. A green board you did
   not read is not evidence.
7. **Do not raise `readiness_declared` to make a test pass.** The declaration
   is a claim about the record. If the computed tier is lower, the record is
   what needs work.
8. **Do not widen a tolerance to turn a row green.** If an anchor misses,
   that is the finding. Report it.

The single sentence to carry: **it is always better to return a gap than a
guess.** A declared gap costs someone an afternoon of research. A confident
wrong number costs someone their plan.
