"""
catalog.py - Loader, validator, coverage tracker and gate for the entity
catalog.

WHAT THIS IS FOR
    A catalog that only reports what it contains cannot report a hole in
    itself. This module answers three questions that a directory listing
    cannot:

      1. Is this entity's record complete enough to produce a number at all?
      2. How much of what it does contain is measured, and how much is guessed?
      3. What is the catalog supposed to contain that it does not?

    The third question is why catalog/coverage_plan.json exists. Scanning
    catalog/entities/ answers "what do we have". Only a declaration of intent
    can answer "what are we missing", and tracking completion per segment is
    the job.

THE GATE
    require_modelable() is modelled directly on
    probe_sim_capabilities.require(). Same contract: name the consumer, name
    the specific missing thing, and refuse rather than substitute.

    Below R1 it raises, because a required input is absent and there is
    genuinely no number to produce - the model cannot compute a disk area
    without a propeller diameter. At R1 it does not refuse; it stamps. This
    project prints FAIL, prints CALIBRATED rather than hiding a fit, and ships
    red boards. The house style is label loudly, not withhold.

READ STANDARDS.md FIRST if you are adding or amending an entity. The
requirement classes, confidence vocabulary and readiness tiers are defined in
catalog/schema/entity_schema_3.0.json and enforced here.

ASCII only throughout.
"""

import argparse
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_ROOT = os.path.join(HERE, "catalog")
ENTITIES_DIRECTORY = os.path.join(CATALOG_ROOT, "entities")
SCHEMA_PATH = os.path.join(CATALOG_ROOT, "schema", "entity_schema_3.0.json")
COVERAGE_PLAN_PATH = os.path.join(CATALOG_ROOT, "coverage_plan.json")
ENVIRONMENT_PATH = os.path.join(CATALOG_ROOT, "environment",
                                "airsim_generic_quad.json")

DEFAULT_ENTITY_ID = "UAS-QUAD-DJI-MAVIC3"
SUPPORTED_SCHEMA_VERSIONS = ("3.0",)

STALE_WARN_DAYS = 180
STALE_FAIL_DAYS = 365

CONFIDENCE_VALUES = ("published", "derived", "literature", "estimated")
MEASURED_CONFIDENCE = ("published", "derived")
PARAMETER_STATUSES = ("present", "missing", "not_applicable")

TIER_ORDER = ("R0", "R1", "R2", "R3")
TIER_NAMES = {"R0": "STUB", "R1": "PROVISIONAL", "R2": "MODELED",
              "R3": "VALIDATED"}

# Anchors this project currently has a predictor for. An anchor declared
# held-out but absent from this set is reported UNSCORED with a reason, never
# quietly dropped. Adding to this set means adding a predictor, which is a new
# falsifiable claim and must be pre-registered in PREDICTIONS.md first.
SCORABLE_ANCHORS = ("max_hover_time_min", "max_flight_time_min",
                    "max_flight_distance_km")


class CatalogError(Exception):
    """Raised when a catalog file is missing, malformed, or refuses a gate."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _read_json(path, what):
    if not os.path.exists(path):
        raise CatalogError("%s not found: %s" % (what, path))
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except ValueError as exc:
        raise CatalogError("%s is not valid JSON (%s): %s"
                           % (what, exc, path))
    except IOError as exc:
        raise CatalogError("could not read %s: %s" % (path, exc))


def load_schema(path=None):
    """Load the requirement declaration."""
    return _read_json(path or SCHEMA_PATH, "schema")


def load_coverage_plan(path=None):
    """Load declared intent. Missing plan is tolerated - it is optional."""
    path = path or COVERAGE_PLAN_PATH
    if not os.path.exists(path):
        return None
    return _read_json(path, "coverage plan")


def list_entity_ids(directory=None):
    """Every entity id present on disk, sorted. Directory scan, no manifest."""
    directory = directory or ENTITIES_DIRECTORY
    if not os.path.isdir(directory):
        return []
    paths = glob.glob(os.path.join(directory, "*.json"))
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in paths)


def load_entity_file(path):
    """
    Load one entity document.

    Deliberately NOT tolerant, in contrast with
    probe_sim_capabilities.load_capabilities(), which returns None on a
    missing file. That tolerance is right there because "the simulator has
    not been interrogated yet" is a legitimate state. A missing or corrupt
    catalog entry is not a legitimate state: the file IS the entity.
    """
    document = _read_json(path, "entity file")

    version = document.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise CatalogError(
            "entity %s declares schema_version %r; this loader supports %s. "
            "Migrate the file by hand - there is deliberately no automatic "
            "migration, because silently accepting an old schema is the same "
            "class of error as silently falling back to another entity's "
            "defaults." % (path, version, ", ".join(SUPPORTED_SCHEMA_VERSIONS)))

    expected_id = os.path.splitext(os.path.basename(path))[0]
    actual_id = document.get("entity_id")
    if actual_id != expected_id:
        raise CatalogError(
            "filename/entity_id mismatch in %s: file is named %r but declares "
            "entity_id %r. Copying an existing entity and forgetting to change "
            "the id inside is the commonest way to corrupt a catalog."
            % (path, expected_id, actual_id))
    return document


def load_entity(entity_id, directory=None):
    """Load an entity by id. Raises CatalogError naming what is available."""
    directory = directory or ENTITIES_DIRECTORY
    path = os.path.join(directory, "%s.json" % entity_id)
    if not os.path.exists(path):
        available = list_entity_ids(directory)
        raise CatalogError(
            "no entity %r in %s. Available: %s"
            % (entity_id, directory,
               ", ".join(available) if available else "(none)"))
    return load_entity_file(path)


# ---------------------------------------------------------------------------
# Parameter access
# ---------------------------------------------------------------------------
def get_parameter(document, path):
    """
    Fetch a parameter record by dotted path, e.g. "physical.mass_kg".

    Returns None when the key is absent entirely - the NOT RECORDED state,
    which is distinct from a declared gap.
    """
    section_name, _, key = path.partition(".")
    section = document.get(section_name)
    if not isinstance(section, dict):
        return None
    record = section.get(key)
    if not isinstance(record, dict):
        return None
    return record


def parameter_status(record):
    """present | missing | not_applicable | not_recorded."""
    if record is None:
        return "not_recorded"
    return record.get("status", "present")


def iterate_parameters(document):
    """
    Yield (path, record) for every parameter in the document.

    Skips keys beginning with "_" at both levels: sections carry _note strings
    alongside real parameters, and the document carries _standards and
    _readiness_note.
    """
    for section_name, section in document.items():
        if section_name.startswith("_") or not isinstance(section, dict):
            continue
        if section_name == "calibration":
            continue
        for key, record in section.items():
            if key.startswith("_") or not isinstance(record, dict):
                continue
            if "value" not in record and "status" not in record:
                continue
            yield "%s.%s" % (section_name, key), record


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _issue(severity, path, message):
    return {"severity": severity, "path": path, "message": message}


def _check_value_type(value, declared):
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "string":
        return isinstance(value, str)
    if declared == "object":
        return isinstance(value, dict)
    if declared == "range":
        return (isinstance(value, list) and len(value) == 2
                and all(isinstance(v, (int, float)) for v in value))
    return True


def validate_entity(document, schema, today=None):
    """
    Check one entity against the schema. Returns a list of issue dicts.

    ERROR means the record is malformed. WARN means it is legal but worth
    someone's attention.
    """
    today = today or datetime.date.today()
    issues = []

    for key in schema.get("required_top_level_keys", []):
        if key not in document:
            issues.append(_issue("ERROR", key,
                                 "required top-level key is missing"))

    declared_tier = document.get("readiness_declared")
    if declared_tier is not None and declared_tier not in TIER_ORDER:
        issues.append(_issue("ERROR", "readiness_declared",
                             "must be one of %s, found %r"
                             % (", ".join(TIER_ORDER), declared_tier)))

    declared_types = {p["path"]: p.get("value_type")
                      for p in schema.get("parameters", [])}

    # ---- Per-parameter coherence ----
    for path, record in iterate_parameters(document):
        status = parameter_status(record)
        if status not in PARAMETER_STATUSES:
            issues.append(_issue("ERROR", path,
                                 "status %r is not one of %s"
                                 % (status, ", ".join(PARAMETER_STATUSES))))
            continue

        value = record.get("value")
        confidence = record.get("confidence")

        if status == "present":
            if value is None:
                issues.append(_issue(
                    "ERROR", path,
                    "status is 'present' but value is null. Declare the gap "
                    "with status 'missing' instead."))
            if confidence is None:
                issues.append(_issue("ERROR", path,
                                     "present parameter has no confidence"))
            elif confidence not in CONFIDENCE_VALUES:
                issues.append(_issue(
                    "ERROR", path, "confidence %r is not one of %s"
                    % (confidence, ", ".join(CONFIDENCE_VALUES))))
            if not record.get("source"):
                issues.append(_issue(
                    "ERROR", path,
                    "present parameter has no source. An unsourced number is "
                    "unauditable even when it is correct."))
            expected_type = declared_types.get(path)
            if expected_type and value is not None:
                if not _check_value_type(value, expected_type):
                    issues.append(_issue(
                        "ERROR", path, "value %r does not match declared type "
                        "%r" % (value, expected_type)))
        else:
            if value is not None:
                issues.append(_issue(
                    "ERROR", path,
                    "status is %r but value is not null. A number sitting in "
                    "a field declared as a gap is exactly the thing this "
                    "check exists to catch." % status))
            if confidence is not None:
                issues.append(_issue("ERROR", path,
                                     "status is %r but confidence is set"
                                     % status))
            if status == "missing" and not record.get("todo"):
                issues.append(_issue(
                    "ERROR", path,
                    "status 'missing' requires a 'todo' saying what would "
                    "close the gap"))
            if status == "not_applicable" and not record.get("note"):
                issues.append(_issue(
                    "ERROR", path,
                    "status 'not_applicable' requires a 'note' explaining why"))

        # ---- Dates ----
        verified = record.get("verified_on")
        if status == "present" and not verified:
            issues.append(_issue("WARN", path, "no verified_on date"))
        elif verified:
            parsed = _parse_date(verified)
            if parsed is None:
                issues.append(_issue("ERROR", path,
                                     "verified_on %r is not an ISO date"
                                     % verified))
            elif (parsed - today).days > 1:
                issues.append(_issue(
                    "ERROR", path,
                    "verified_on %s is in the future. A verification that has "
                    "not happened yet is a data-entry fault, and treating it "
                    "as fresh errs in the wrong direction." % verified))

    # ---- Calibration cross-field rules ----
    calibration = document.get("calibration")
    if not isinstance(calibration, dict):
        issues.append(_issue("ERROR", "calibration",
                             "calibration block is missing"))
    else:
        fitted_anchor = calibration.get("fitted_to_anchor")
        held_out = calibration.get("held_out_anchors") or []
        if not calibration.get("fitted_parameter"):
            issues.append(_issue("ERROR", "calibration.fitted_parameter",
                                 "not declared"))
        if not fitted_anchor:
            issues.append(_issue("ERROR", "calibration.fitted_to_anchor",
                                 "not declared"))
        for anchor in ([fitted_anchor] if fitted_anchor else []) + list(held_out):
            record = get_parameter(document, "performance_published.%s" % anchor)
            if record is None:
                issues.append(_issue(
                    "ERROR", "calibration",
                    "anchor %r is named but performance_published.%s does not "
                    "exist" % (anchor, anchor)))
            elif parameter_status(record) != "present":
                issues.append(_issue(
                    "WARN", "calibration",
                    "anchor %r is named but its parameter is not present"
                    % anchor))
        if fitted_anchor and fitted_anchor in held_out:
            issues.append(_issue(
                "ERROR", "calibration",
                "anchor %r is both fitted and held out. An anchor cannot both "
                "set a parameter and test it." % fitted_anchor))

    return issues


def _parse_date(text):
    try:
        return datetime.date.fromisoformat(str(text))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------
def assess_entity(document, schema, today=None, stale_warn=STALE_WARN_DAYS,
                  stale_fail=STALE_FAIL_DAYS):
    """Compute completeness, confidence, freshness, anchors and readiness."""
    today = today or datetime.date.today()
    issues = validate_entity(document, schema, today)

    classes = {"REQUIRED_MEASURED": [], "REQUIRED_MODELING": [],
               "REQUIRED_FOR_OPERATIONAL": [], "OPTIONAL": []}
    for parameter in schema.get("parameters", []):
        classes.setdefault(parameter["requirement"], []).append(parameter)

    def summarize(requirement):
        present, gaps = [], []
        for parameter in classes.get(requirement, []):
            path = parameter["path"]
            record = get_parameter(document, path)
            status = parameter_status(record)
            if status == "present":
                present.append(path)
            else:
                gaps.append({"path": path, "state": status,
                             "todo": (record or {}).get("todo")})
        total = len(classes.get(requirement, []))
        return {"total": total, "present": len(present),
                "present_paths": present, "missing": gaps}

    measured = summarize("REQUIRED_MEASURED")
    modeling = summarize("REQUIRED_MODELING")
    operational = summarize("REQUIRED_FOR_OPERATIONAL")
    optional = summarize("OPTIONAL")

    required_total = measured["total"] + modeling["total"]
    required_present = measured["present"] + modeling["present"]
    completeness = (100.0 * required_present / required_total
                    if required_total else 0.0)
    operational_total = required_total + operational["total"]
    operational_present = required_present + operational["present"]
    completeness_operational = (100.0 * operational_present / operational_total
                                if operational_total else 0.0)

    # ---- Confidence and sourcing over PRESENT parameters ----
    counts = dict((c, 0) for c in CONFIDENCE_VALUES)
    unsourced, contested, estimated_required = [], [], []
    measured_wrong_confidence = []
    required_measured_paths = set(measured["present_paths"])

    for path, record in iterate_parameters(document):
        if parameter_status(record) != "present":
            continue
        confidence = record.get("confidence")
        if confidence in counts:
            counts[confidence] += 1
        if not record.get("source"):
            unsourced.append(path)
        if record.get("contested"):
            contested.append(path)
        if path in required_measured_paths and confidence not in MEASURED_CONFIDENCE:
            measured_wrong_confidence.append(path)
        if confidence == "estimated" and (
                path in required_measured_paths
                or path in set(modeling["present_paths"])):
            estimated_required.append(path)

    present_total = sum(counts.values())
    percentages = dict((c, (100.0 * n / present_total if present_total else 0.0))
                       for c, n in counts.items())

    # ---- Freshness ----
    ages, undated, future_dated = [], [], []
    for path, record in iterate_parameters(document):
        if parameter_status(record) != "present":
            continue
        verified = record.get("verified_on")
        parsed = _parse_date(verified) if verified else None
        if parsed is None:
            undated.append(path)
            continue
        age = (today - parsed).days
        if age < -1:
            future_dated.append(path)
        ages.append(max(0, age))

    ages_sorted = sorted(ages)
    freshness = {
        "oldest_age_days": ages_sorted[-1] if ages_sorted else None,
        "newest_age_days": ages_sorted[0] if ages_sorted else None,
        "median_age_days": (ages_sorted[len(ages_sorted) // 2]
                            if ages_sorted else None),
        "warn_count": sum(1 for a in ages if a > stale_warn),
        "stale_count": sum(1 for a in ages if a > stale_fail),
        "undated": undated,
        "future_dated": future_dated,
        "stale_warn_days": stale_warn,
        "stale_fail_days": stale_fail,
    }

    # ---- Anchors ----
    calibration = document.get("calibration") or {}
    held_out_declared = list(calibration.get("held_out_anchors") or [])
    held_out_present, held_out_unscorable, held_out_missing = [], [], []
    for anchor in held_out_declared:
        record = get_parameter(document, "performance_published.%s" % anchor)
        if record is None or parameter_status(record) != "present":
            held_out_missing.append(anchor)
        elif anchor not in SCORABLE_ANCHORS:
            held_out_unscorable.append(anchor)
        else:
            held_out_present.append(anchor)

    anchors = {
        "fitted_parameter": calibration.get("fitted_parameter"),
        "fitted_to_anchor": calibration.get("fitted_to_anchor"),
        "held_out_declared": held_out_declared,
        "held_out_scorable": held_out_present,
        "held_out_unscorable": held_out_unscorable,
        "held_out_missing": held_out_missing,
    }

    errors = [i for i in issues if i["severity"] == "ERROR"]

    # ---- Readiness ----
    reasons = []
    tier = "R0"
    if errors:
        reasons.append("%d schema ERROR(s)" % len(errors))
    if measured["missing"]:
        reasons.append("%d REQUIRED_MEASURED parameter(s) absent"
                       % len(measured["missing"]))
    if modeling["missing"]:
        reasons.append("%d REQUIRED_MODELING parameter(s) absent"
                       % len(modeling["missing"]))

    if not errors and not measured["missing"] and not modeling["missing"]:
        tier = "R1"
        r2_blockers = []
        if measured_wrong_confidence:
            r2_blockers.append(
                "REQUIRED_MEASURED carrying non-measured confidence: %s"
                % ", ".join(measured_wrong_confidence))
        if unsourced:
            r2_blockers.append("%d present parameter(s) unsourced"
                               % len(unsourced))
        if future_dated:
            r2_blockers.append("%d future-dated parameter(s)"
                               % len(future_dated))
        if not calibration:
            r2_blockers.append("no calibration block")
        reasons.extend(r2_blockers)

        if not r2_blockers:
            tier = "R2"
            r3_blockers = []
            if len(held_out_present) < 2:
                r3_blockers.append(
                    "only %d scorable held-out anchor(s); 2 is the minimum at "
                    "which the model can be caught being wrong"
                    % len(held_out_present))
            if operational["missing"]:
                r3_blockers.append("%d REQUIRED_FOR_OPERATIONAL absent"
                                   % len(operational["missing"]))
            oldest = freshness["oldest_age_days"]
            if oldest is not None and oldest > stale_fail:
                r3_blockers.append(
                    "oldest verified_on is %d days old, over the %d day limit"
                    % (oldest, stale_fail))
            reasons.extend(r3_blockers)
            if not r3_blockers:
                tier = "R3"
                reasons = []

    declared = document.get("readiness_declared")
    over_claimed = (declared in TIER_ORDER and tier in TIER_ORDER
                    and TIER_ORDER.index(declared) > TIER_ORDER.index(tier))

    provisional = (tier == "R1")
    provisional_reasons = []
    if provisional:
        if estimated_required:
            provisional_reasons.append(
                "load-bearing inputs are ESTIMATED: %s"
                % ", ".join(estimated_required[:3]))
        provisional_reasons.extend(reasons[:2])

    return {
        "entity_id": document.get("entity_id"),
        "entity": document.get("entity"),
        "category": document.get("category"),
        "segment_id": document.get("segment_id"),
        "schema_version": document.get("schema_version"),
        "compiled_on": document.get("compiled_on"),
        "compiled_by": document.get("compiled_by"),
        "issues": issues,
        "error_count": len(errors),
        "warn_count": len(issues) - len(errors),
        "required_measured": measured,
        "required_modeling": modeling,
        "required_operational": operational,
        "optional": optional,
        "required_total": required_total,
        "required_present": required_present,
        "completeness_percent": completeness,
        "completeness_operational_percent": completeness_operational,
        "confidence_counts": counts,
        "confidence_percent": percentages,
        "unsourced": unsourced,
        "contested": contested,
        "estimated_required": estimated_required,
        "freshness": freshness,
        "anchors": anchors,
        "readiness": tier,
        "readiness_name": TIER_NAMES[tier],
        "readiness_declared": declared,
        "readiness_reasons": reasons,
        "over_claimed": over_claimed,
        "provisional": provisional,
        "provisional_reasons": provisional_reasons,
    }


def assess_catalog(directory=None, plan_path=None, schema_path=None,
                   today=None, stale_warn=STALE_WARN_DAYS,
                   stale_fail=STALE_FAIL_DAYS):
    """Assess every entity on disk and compare against declared intent."""
    directory = directory or ENTITIES_DIRECTORY
    schema = load_schema(schema_path)
    today = today or datetime.date.today()

    assessments, load_errors = [], []
    for entity_id in list_entity_ids(directory):
        try:
            document = load_entity(entity_id, directory)
        except CatalogError as exc:
            load_errors.append({"entity_id": entity_id, "error": str(exc)})
            continue
        assessments.append(assess_entity(document, schema, today, stale_warn,
                                         stale_fail))

    plan = load_coverage_plan(plan_path)
    segments = []
    if plan:
        by_segment = {}
        for assessment in assessments:
            by_segment.setdefault(assessment.get("segment_id"), []).append(
                assessment)
        for segment in plan.get("segments", []):
            members = by_segment.get(segment["segment_id"], [])
            modelable = [a for a in members if a["readiness"] != "R0"]
            segments.append({
                "segment_id": segment["segment_id"],
                "label": segment.get("label", segment["segment_id"]),
                "nation": segment.get("nation"),
                "era": segment.get("era"),
                "priority": segment.get("priority"),
                "planned": segment.get("planned_entity_count", 0),
                "present": len(members),
                "modelable": len(modelable),
                "rationale": segment.get("rationale"),
            })

    unassigned = [a["entity_id"] for a in assessments
                  if not a.get("segment_id")]

    modelable_count = sum(1 for a in assessments if a["readiness"] != "R0")
    quotable_count = sum(1 for a in assessments
                         if a["readiness"] in ("R2", "R3"))

    return {
        "generated_on": today.isoformat(),
        "directory": directory,
        "schema_version": schema.get("schema_version"),
        "stale_warn_days": stale_warn,
        "stale_fail_days": stale_fail,
        "entities": assessments,
        "load_errors": load_errors,
        "segments": segments,
        "unassigned": unassigned,
        "entity_count": len(assessments),
        "modelable_count": modelable_count,
        "quotable_count": quotable_count,
        "over_claimed": [a["entity_id"] for a in assessments
                         if a["over_claimed"]],
    }


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def require_modelable(assessment, consumer_name, min_tier="R1"):
    """
    Assert an entity's record is complete enough for what the caller is about
    to produce.

    Modelled on probe_sim_capabilities.require(). Raises CatalogError below
    min_tier. Returns a dict describing any provisional stamping the caller is
    then obliged to display.
    """
    tier = assessment["readiness"]
    if TIER_ORDER.index(tier) < TIER_ORDER.index(min_tier):
        gaps = [g["path"] for g in
                assessment["required_measured"]["missing"]
                + assessment["required_modeling"]["missing"]]
        shown = ", ".join(gaps[:3])
        extra = (" (+%d more; run 'python catalog.py --entity %s' for the full "
                 "list)" % (len(gaps) - 3, assessment["entity_id"])
                 if len(gaps) > 3 else "")
        detail = ("Missing required parameters: %s%s. " % (shown, extra)
                  if gaps else
                  "Blocking issues: %s. "
                  % "; ".join(assessment["readiness_reasons"][:3]))
        raise CatalogError(
            "%s requires entity %r at readiness %s or better; it is %s %s. "
            "%sRefusing to produce a number from an incomplete record."
            % (consumer_name, assessment["entity_id"], min_tier, tier,
               TIER_NAMES[tier], detail))

    return {
        "readiness": tier,
        "provisional": assessment["provisional"],
        "provisional_reasons": assessment["provisional_reasons"],
        "banner": provisional_banner(assessment)
        if assessment["provisional"] else None,
    }


def provisional_banner(assessment):
    """The unmissable stamp for an R1 record. Returns a list of lines."""
    reasons = assessment["provisional_reasons"] or ["record is incomplete"]
    width = 71
    lines = ["  " + "*" * width]
    def row(text):
        return "  *  %-*s*" % (width - 5, text[:width - 5])
    lines.append(row("PROVISIONAL - entity record is %s %s, not R2 MODELED."
                     % (assessment["readiness"],
                        TIER_NAMES[assessment["readiness"]])))
    for reason in reasons[:2]:
        lines.append(row(reason[:width - 6]))
    lines.append(row("These numbers are NOT a planning product. See "
                     "STANDARDS.md s7."))
    lines.append("  " + "*" * width)
    return lines


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def format_entity_report(assessment):
    """Per-entity detail, including the gaps table."""
    lines = []
    lines.append("=" * 72)
    lines.append("ENTITY RECORD - %s" % assessment["entity_id"])
    lines.append("=" * 72)
    lines.append("Name           : %s" % assessment["entity"])
    lines.append("Category       : %s" % assessment["category"])
    lines.append("Segment        : %s" % (assessment["segment_id"] or
                                          "UNASSIGNED"))
    lines.append("Compiled       : %s by %s" % (assessment["compiled_on"],
                                                assessment["compiled_by"]))
    lines.append("Readiness      : %s %s   (declared %s)"
                 % (assessment["readiness"], assessment["readiness_name"],
                    assessment["readiness_declared"]))
    if assessment["over_claimed"]:
        lines.append("")
        lines.append("  OVER-CLAIMED: the file declares %s but the record "
                     "computes %s."
                     % (assessment["readiness_declared"],
                        assessment["readiness"]))
        lines.append("  The declaration is a claim about the record. Fix the")
        lines.append("  record, or lower the claim.")
    lines.append("")

    if assessment["provisional"]:
        lines.extend(provisional_banner(assessment))
        lines.append("")

    lines.append("-" * 72)
    lines.append("COMPLETENESS")
    lines.append("-" * 72)
    header = "  %-28s %8s %8s  %s" % ("Requirement class", "Present", "Total",
                                      "State")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for label, key in (("REQUIRED_MEASURED", "required_measured"),
                       ("REQUIRED_MODELING", "required_modeling"),
                       ("REQUIRED_FOR_OPERATIONAL", "required_operational"),
                       ("OPTIONAL", "optional")):
        block = assessment[key]
        state = "complete" if not block["missing"] else "%d absent" % len(
            block["missing"])
        lines.append("  %-28s %8d %8d  %s"
                     % (label, block["present"], block["total"], state))
    lines.append("")
    lines.append("  Required completeness    : %.0f%% (%d of %d)"
                 % (assessment["completeness_percent"],
                    assessment["required_present"],
                    assessment["required_total"]))
    lines.append("  Including operational    : %.0f%%"
                 % assessment["completeness_operational_percent"])
    lines.append("")

    gaps = []
    for key in ("required_measured", "required_modeling",
                "required_operational", "optional"):
        for gap in assessment[key]["missing"]:
            gaps.append((key, gap))
    if gaps:
        lines.append("-" * 72)
        lines.append("GAPS")
        lines.append("-" * 72)
        header = "  %-46s %-14s %s" % ("Parameter", "State", "Class")
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for key, gap in gaps:
            state = ("DECLARED GAP" if gap["state"] == "missing"
                     else "NOT RECORDED" if gap["state"] == "not_recorded"
                     else gap["state"].upper())
            lines.append("  %-46s %-14s %s"
                         % (gap["path"][:46], state,
                            key.replace("required_", "req ")))
            if gap.get("todo"):
                lines.append("      todo: %s" % gap["todo"][:60])
        lines.append("")
        lines.append("  DECLARED GAP means the author looked and recorded the")
        lines.append("  absence. NOT RECORDED means the key is simply not")
        lines.append("  there. Both block modelling; only one tells the next")
        lines.append("  person anything.")
        lines.append("")

    lines.append("-" * 72)
    lines.append("CONFIDENCE (present parameters only)")
    lines.append("-" * 72)
    for confidence in CONFIDENCE_VALUES:
        lines.append("  %-12s %4d  %5.1f%%"
                     % (confidence, assessment["confidence_counts"][confidence],
                        assessment["confidence_percent"][confidence]))
    if assessment["estimated_required"]:
        lines.append("")
        lines.append("  ESTIMATED in required positions:")
        for path in assessment["estimated_required"]:
            lines.append("    %s" % path)
    if assessment["contested"]:
        lines.append("")
        lines.append("  CONTESTED (sources disagree):")
        for path in assessment["contested"]:
            lines.append("    %s" % path)
    if assessment["unsourced"]:
        lines.append("")
        lines.append("  UNSOURCED (blocks R2):")
        for path in assessment["unsourced"]:
            lines.append("    %s" % path)
    lines.append("")

    freshness = assessment["freshness"]
    lines.append("-" * 72)
    lines.append("FRESHNESS  (warn > %d d, fail > %d d)"
                 % (freshness["stale_warn_days"], freshness["stale_fail_days"]))
    lines.append("-" * 72)
    lines.append("  Oldest verified_on : %s days"
                 % freshness["oldest_age_days"])
    lines.append("  Median             : %s days" % freshness["median_age_days"])
    lines.append("  Over warn threshold: %d" % freshness["warn_count"])
    lines.append("  Over fail threshold: %d" % freshness["stale_count"])
    if freshness["undated"]:
        lines.append("  Undated            : %s"
                     % ", ".join(freshness["undated"][:4]))
    if freshness["future_dated"]:
        lines.append("  FUTURE DATED       : %s"
                     % ", ".join(freshness["future_dated"]))
    lines.append("")

    anchors = assessment["anchors"]
    lines.append("-" * 72)
    lines.append("ANCHORS")
    lines.append("-" * 72)
    lines.append("  Fitted parameter   : %s" % anchors["fitted_parameter"])
    lines.append("  Fitted to anchor   : %s  (reported CALIBRATED, never PASS)"
                 % anchors["fitted_to_anchor"])
    lines.append("  Held out, scorable : %s"
                 % (", ".join(anchors["held_out_scorable"]) or "none"))
    if anchors["held_out_unscorable"]:
        lines.append("  Held out, UNSCORED : %s"
                     % ", ".join(anchors["held_out_unscorable"]))
        lines.append("      Declared held-out but this project has no")
        lines.append("      predictor for it. Inventing one to turn the row")
        lines.append("      green would be a new falsifiable claim and must be")
        lines.append("      pre-registered in PREDICTIONS.md first.")
    if anchors["held_out_missing"]:
        lines.append("  Held out, MISSING  : %s"
                     % ", ".join(anchors["held_out_missing"]))
    lines.append("")

    if assessment["issues"]:
        lines.append("-" * 72)
        lines.append("SCHEMA ISSUES")
        lines.append("-" * 72)
        for issue in assessment["issues"]:
            lines.append("  [%-5s] %-40s %s"
                         % (issue["severity"], issue["path"][:40],
                            issue["message"]))
        lines.append("")

    if assessment["readiness_reasons"]:
        lines.append("-" * 72)
        lines.append("WHY NOT THE NEXT TIER UP")
        lines.append("-" * 72)
        for reason in assessment["readiness_reasons"]:
            lines.append("  - %s" % reason)
    return "\n".join(lines)


def format_catalog_board(catalog):
    """The coverage board: what exists, how good it is, and what is missing."""
    lines = []
    lines.append("=" * 72)
    lines.append("SUAS ENTITY CATALOG - COVERAGE BOARD")
    lines.append("=" * 72)
    lines.append("Generated      : %s" % catalog["generated_on"])
    lines.append("Catalog root   : %s"
                 % os.path.relpath(catalog["directory"], HERE))
    lines.append("Schema         : %s" % catalog["schema_version"])
    lines.append("Staleness      : warn > %d d, fail > %d d"
                 % (catalog["stale_warn_days"], catalog["stale_fail_days"]))
    lines.append("")

    if catalog["load_errors"]:
        lines.append("  FILES THAT WOULD NOT LOAD:")
        for failure in catalog["load_errors"]:
            lines.append("    %s: %s" % (failure["entity_id"],
                                         failure["error"][:100]))
        lines.append("")

    header = ("  %-26s %-16s %7s %6s  %-18s %7s  %s"
              % ("Entity ID", "Name", "Req", "Compl", "Confidence mix",
                 "Oldest", "Tier"))
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for entity in catalog["entities"]:
        counts = entity["confidence_counts"]
        mix = "P%-3d D%-3d L%-3d E%-3d" % (counts["published"],
                                           counts["derived"],
                                           counts["literature"],
                                           counts["estimated"])
        oldest = entity["freshness"]["oldest_age_days"]
        lines.append("  %-26s %-16s %3d/%-3d %5.0f%%  %-18s %5s d  %s %s"
                     % (entity["entity_id"][:26], (entity["entity"] or "")[:16],
                        entity["required_present"], entity["required_total"],
                        entity["completeness_percent"], mix,
                        oldest if oldest is not None else "-",
                        entity["readiness"], entity["readiness_name"]))
    lines.append("")
    lines.append("  P=published D=derived L=literature E=estimated. Counts are")
    lines.append("  over PRESENT parameters only, so a thin entity can show a")
    lines.append("  clean mix and still be a stub. Read the Compl column first.")
    lines.append("")

    total = catalog["entity_count"]
    lines.append("  Entities on disk         : %d" % total)
    lines.append("  Modelable (R1 or better) : %d" % catalog["modelable_count"])
    lines.append("  Quotable  (R2 or better) : %d" % catalog["quotable_count"])
    if total and catalog["modelable_count"] < total:
        lines.append("")
        lines.append("  THIS CATALOG IS THIN. %d of %d entities cannot produce"
                     % (total - catalog["modelable_count"], total))
        lines.append("  any number at all. That is reported rather than hidden,")
        lines.append("  and a stub is not filled with plausible values to make")
        lines.append("  this board look better - see STANDARDS.md section 5.")
    if catalog["over_claimed"]:
        lines.append("")
        lines.append("  OVER-CLAIMED READINESS: %s"
                     % ", ".join(catalog["over_claimed"]))

    if catalog["segments"]:
        lines.append("")
        lines.append("-" * 72)
        lines.append("SEGMENT COVERAGE - declared intent vs what exists")
        lines.append("-" * 72)
        header = ("  %-34s %-6s %8s %8s %10s"
                  % ("Segment", "Nation", "Planned", "Present", "Modelable"))
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        planned_total = present_total = modelable_total = 0
        for segment in catalog["segments"]:
            planned_total += segment["planned"]
            present_total += segment["present"]
            modelable_total += segment["modelable"]
            lines.append("  %-34s %-6s %8d %8d %10d"
                         % (segment["label"][:34], segment["nation"] or "-",
                            segment["planned"], segment["present"],
                            segment["modelable"]))
        lines.append("  " + "-" * (len(header) - 2))
        lines.append("  %-34s %-6s %8d %8d %10d"
                     % ("TOTAL", "", planned_total, present_total,
                        modelable_total))
        lines.append("")
        filled = sum(1 for s in catalog["segments"]
                     if s["present"] >= s["planned"] and s["planned"] > 0)
        lines.append("  %d of %d planned segments are fully populated."
                     % (filled, len(catalog["segments"])))
        lines.append("  Empty segments are listed because a catalog that only")
        lines.append("  reports what it contains cannot report a gap.")
        if catalog["unassigned"]:
            lines.append("")
            lines.append("  UNASSIGNED to any segment: %s"
                         % ", ".join(catalog["unassigned"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Entity catalog loader, validator and coverage tracker.")
    parser.add_argument("--entity", metavar="ID",
                        help="print the detailed record for one entity")
    parser.add_argument("--list", action="store_true",
                        help="list entity ids and exit")
    parser.add_argument("--schema", action="store_true",
                        help="print the requirement declaration and exit")
    parser.add_argument("--json", action="store_true",
                        help="emit the assessment as JSON instead of a board")
    parser.add_argument("--stale-days", type=int, default=STALE_FAIL_DAYS,
                        help="days before a verified_on blocks R3 "
                             "(default: %(default)s)")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero if any entity has a schema ERROR "
                             "or over-claims its readiness")
    arguments = parser.parse_args(argv)

    try:
        if arguments.list:
            for entity_id in list_entity_ids():
                print(entity_id)
            return 0

        if arguments.schema:
            print(json.dumps(load_schema(), indent=2))
            return 0

        stale_warn = min(STALE_WARN_DAYS, arguments.stale_days)

        if arguments.entity:
            schema = load_schema()
            document = load_entity(arguments.entity)
            assessment = assess_entity(document, schema, None, stale_warn,
                                       arguments.stale_days)
            if arguments.json:
                print(json.dumps(assessment, indent=2, default=str))
            else:
                print(format_entity_report(assessment))
            if arguments.strict and (assessment["error_count"]
                                     or assessment["over_claimed"]):
                return 1
            return 0

        catalog = assess_catalog(stale_warn=stale_warn,
                                 stale_fail=arguments.stale_days)
        if arguments.json:
            print(json.dumps(catalog, indent=2, default=str))
        else:
            print(format_catalog_board(catalog))
        if arguments.strict:
            if (catalog["load_errors"] or catalog["over_claimed"]
                    or any(e["error_count"] for e in catalog["entities"])):
                return 1
        return 0

    except CatalogError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
