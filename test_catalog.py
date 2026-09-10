"""
test_catalog.py - Automated test battery for the entity catalog.

WHAT IT GUARDS
    A catalog degrades quietly. Nobody notices that an entity's readiness
    claim has drifted above what its record supports, or that a stub was
    filled in with plausible numbers to make a board look better, or that two
    copies of the simulator's parameters have diverged. Each of those is
    invisible in a diff and fatal to trust.

    So each check below is a specific way the catalog could go wrong while
    still looking fine.

CHECKS
    1  Schema loads and declares the version this loader supports
    2  Every entity file loads - filename matches entity_id, version accepted
    3  No entity has a schema ERROR
    4  No entity over-claims its readiness
    5  Every entity's segment_id exists in the coverage plan
    6  Every R1-or-better entity actually constructs a working model
    7  Every R0 entity is REFUSED by the gate - the refusal must happen
    8  The environment JSON has not drifted from AIRSIM_GENERIC_QUAD
    9  The pinned regression check still passes

    Check 7 is the one worth reading twice. It asserts a FAILURE occurs. A
    gate that has never been observed refusing anything is not known to work,
    and the moment a stub silently produces numbers is the moment the catalog
    stops meaning anything.

USAGE
    python test_catalog.py
    python test_catalog.py --verbose

    No simulator required. Exit 0 if every check passes, 1 otherwise.

ASCII only throughout.
"""

import argparse
import sys

import battery_model
import catalog
import test_regression_pinned


def _result(name, passed, detail="", severity="FAIL"):
    return {"name": name, "passed": passed, "detail": detail,
            "severity": severity}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def check_schema():
    try:
        schema = catalog.load_schema()
    except catalog.CatalogError as exc:
        return _result("1  Schema loads", False, str(exc)), None
    version = schema.get("schema_version")
    if version not in catalog.SUPPORTED_SCHEMA_VERSIONS:
        return _result("1  Schema loads", False,
                       "schema declares %r, loader supports %s"
                       % (version, ", ".join(
                           catalog.SUPPORTED_SCHEMA_VERSIONS))), None
    count = len(schema.get("parameters", []))
    return _result("1  Schema loads", True,
                   "version %s, %d parameters declared" % (version, count)), schema


def check_entities_load(entity_ids):
    failures, documents = [], {}
    for entity_id in entity_ids:
        try:
            documents[entity_id] = catalog.load_entity(entity_id)
        except catalog.CatalogError as exc:
            failures.append("%s: %s" % (entity_id, exc))
    return _result("2  Every entity file loads", not failures,
                   "; ".join(failures) if failures
                   else "%d entity file(s)" % len(documents)), documents


def check_no_schema_errors(assessments):
    offenders = []
    for assessment in assessments:
        errors = [i for i in assessment["issues"] if i["severity"] == "ERROR"]
        if errors:
            offenders.append("%s: %d ERROR(s), first is %s - %s"
                             % (assessment["entity_id"], len(errors),
                                errors[0]["path"], errors[0]["message"]))
    return _result("3  No schema ERRORs", not offenders,
                   "; ".join(offenders) if offenders
                   else "%d entity record(s) clean" % len(assessments))


def check_no_over_claim(assessments):
    offenders = []
    for assessment in assessments:
        if assessment["over_claimed"]:
            offenders.append(
                "%s declares %s but computes %s"
                % (assessment["entity_id"], assessment["readiness_declared"],
                   assessment["readiness"]))
    detail = ("; ".join(offenders) if offenders else
              "; ".join("%s=%s" % (a["entity_id"], a["readiness"])
                        for a in assessments))
    return _result("4  No entity over-claims readiness", not offenders, detail)


def check_segments(assessments):
    plan = catalog.load_coverage_plan()
    if plan is None:
        return _result("5  Segment ids resolve", True,
                       "no coverage plan present, skipped", severity="WARN")
    known = set(s["segment_id"] for s in plan.get("segments", []))
    offenders = []
    for assessment in assessments:
        segment_id = assessment.get("segment_id")
        if not segment_id:
            offenders.append("%s declares no segment_id"
                             % assessment["entity_id"])
        elif segment_id not in known:
            offenders.append("%s names unknown segment %r"
                             % (assessment["entity_id"], segment_id))
    return _result("5  Segment ids resolve", not offenders,
                   "; ".join(offenders) if offenders
                   else "%d segment(s) declared in the plan" % len(known))


def check_modelable_construct(assessments):
    """Every entity the gate admits must actually produce a working model."""
    admitted = [a for a in assessments if a["readiness"] != "R0"]
    failures, built = [], []
    for assessment in admitted:
        try:
            model = battery_model.BatteryModel(
                entity=assessment["entity_id"], verbose=False)
            endurance = model.endurance_minutes()
            if not (endurance > 0):
                failures.append("%s: non-positive endurance %r"
                                % (assessment["entity_id"], endurance))
            else:
                built.append("%s=%.1f min" % (assessment["entity_id"],
                                              endurance))
        except Exception as exc:
            failures.append("%s: %s: %s" % (assessment["entity_id"],
                                            type(exc).__name__, exc))
    return _result("6  Modelable entities construct", not failures,
                   "; ".join(failures) if failures
                   else ("; ".join(built) if built
                         else "no entity is above R0"))


def check_gate_refuses(assessments):
    """
    Assert the gate REFUSES every R0 record.

    This check asserts that a failure happens. A gate nobody has watched
    refuse anything is not known to work, and a stub that silently produces
    numbers is the exact failure the catalog exists to prevent.
    """
    stubs = [a for a in assessments if a["readiness"] == "R0"]
    if not stubs:
        return _result("7  Gate refuses R0 records", True,
                       "no R0 entity present to refuse", severity="WARN")
    failures, refused = [], []
    for assessment in stubs:
        try:
            battery_model.BatteryModel(entity=assessment["entity_id"],
                                       verbose=False)
            failures.append(
                "%s is R0 but constructed WITHOUT refusal - the gate is not "
                "protecting anything" % assessment["entity_id"])
        except catalog.CatalogError:
            refused.append(assessment["entity_id"])
        except Exception as exc:
            failures.append("%s raised %s instead of CatalogError: %s"
                            % (assessment["entity_id"], type(exc).__name__,
                               exc))
    return _result("7  Gate refuses R0 records", not failures,
                   "; ".join(failures) if failures
                   else "refused: %s" % ", ".join(refused))


def check_environment_drift():
    """
    The environment JSON documents AIRSIM_GENERIC_QUAD, which stays
    authoritative. Two copies of the same numbers will drift unless something
    watches them.
    """
    try:
        environment = catalog._read_json(catalog.ENVIRONMENT_PATH,
                                         "environment file")
    except catalog.CatalogError as exc:
        return _result("8  Environment JSON matches source", False, str(exc))

    inputs = environment.get("inputs", {})
    source = battery_model.AIRSIM_GENERIC_QUAD
    mismatches = []
    for key in ("mass_kg", "rotor_count", "propeller_diameter_m",
                "propeller_height_m", "linear_drag_coefficient", "c_t", "c_p",
                "max_rpm", "max_thrust_per_rotor_n"):
        recorded = inputs.get(key)
        actual = source.get(key)
        if recorded is None:
            mismatches.append("%s absent from JSON" % key)
        elif abs(float(recorded) - float(actual)) > 1e-9:
            mismatches.append("%s: JSON %r vs source %r"
                              % (key, recorded, actual))
    box_json = inputs.get("body_box_m") or {}
    box_source = source.get("body_box_m") or {}
    for axis in ("x", "y", "z"):
        if abs(float(box_json.get(axis, -1)) - float(box_source[axis])) > 1e-9:
            mismatches.append("body_box_m.%s differs" % axis)

    derived = environment.get("derived", {})
    factors = battery_model.airsim_drag_factors()
    for key, actual in (("effective_cda_x_m2", factors["effective_cda_x_m2"]),
                        ("effective_cda_y_m2", factors["effective_cda_y_m2"])):
        recorded = derived.get(key)
        if recorded is None or abs(float(recorded) - actual) > 1e-7:
            mismatches.append("%s: JSON %r vs computed %.10f"
                              % (key, recorded, actual))

    return _result("8  Environment JSON matches source", not mismatches,
                   "; ".join(mismatches) if mismatches
                   else "9 inputs and 2 derived values agree")


def check_regression_pins(verbose=False):
    equivalence_ok, _, _ = test_regression_pinned.check_equivalence(False)
    results, failures = test_regression_pinned.run_pins(False)
    passed = failures == 0 and equivalence_ok
    detail = ("%d of %d pins hold" % (len(results) - failures, len(results))
              if passed else
              "%d pin(s) changed: %s"
              % (failures, ", ".join(r["label"] for r in results
                                     if not r["ok"])[:120]))
    return _result("9  Pinned regression check", passed, detail)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_all(verbose=False):
    checks = []

    schema_result, schema = check_schema()
    checks.append(schema_result)
    if schema is None:
        return checks

    entity_ids = catalog.list_entity_ids()
    load_result, documents = check_entities_load(entity_ids)
    checks.append(load_result)

    assessments = [catalog.assess_entity(document, schema)
                   for document in documents.values()]

    checks.append(check_no_schema_errors(assessments))
    checks.append(check_no_over_claim(assessments))
    checks.append(check_segments(assessments))
    checks.append(check_modelable_construct(assessments))
    checks.append(check_gate_refuses(assessments))
    checks.append(check_environment_drift())
    checks.append(check_regression_pins(verbose))
    return checks


def format_report(checks):
    lines = []
    lines.append("=" * 72)
    lines.append("CATALOG TEST BATTERY")
    lines.append("=" * 72)
    lines.append("Each check is a specific way the catalog could go wrong")
    lines.append("while still looking fine.")
    lines.append("")

    for check in checks:
        marker = "PASS" if check["passed"] else check["severity"]
        lines.append("  [%-4s] %s" % (marker, check["name"]))
        if check["detail"]:
            lines.append("         %s" % check["detail"][:200])

    failed = [c for c in checks if not c["passed"] and c["severity"] == "FAIL"]
    warned = [c for c in checks if not c["passed"] and c["severity"] == "WARN"]
    lines.append("")
    lines.append("-" * 72)
    if failed:
        lines.append("%d CHECK(S) FAILED." % len(failed))
    else:
        lines.append("ALL %d CHECKS PASS.%s"
                     % (len(checks),
                        "  (%d advisory)" % len(warned) if warned else ""))
    lines.append("-" * 72)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Automated test battery for the entity catalog.")
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args(argv)

    checks = run_all(arguments.verbose)
    print(format_report(checks))
    failed = [c for c in checks if not c["passed"] and c["severity"] == "FAIL"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
