"""
test_regression_pinned.py - Change detector for published figures.

WHY THIS EXISTS
    Several numbers produced by this project are published: they appear in
    PREDICTIONS.md, in VALIDATION.md, in committed results/ files, and in a
    git history that has been pushed. P6 in particular is a PRE-REGISTERED
    result - the model overshoots DJI's cruise figure by +14.2%, predicted in
    advance to land in a +10 to +25% band.

    If a refactor moves cruise endurance by even a tenth of a minute, that
    recorded result becomes wrong and the register - the strongest artifact in
    the repo - is compromised. The register's value comes from being unable to
    change after the fact. A number that quietly drifts breaks that.

    So every published figure is pinned here, with tight ABSOLUTE tolerances.
    This is a change detector, not a physics test. Any movement is a finding.
    A generous tolerance would turn the safety net into decoration.

    This file must be written and passing BEFORE any refactor begins, against
    the unmodified code, or it is pinning the bug rather than the behaviour.

PIN GROUP ZERO
    The equivalence check is the important one. It asserts that constructing
    the model from built-in defaults and constructing it from the catalog JSON
    produce identical numbers. That is the formal proof that inverting the
    model - deleting the defaults and making the file authoritative - cannot
    move anything.

    After the inversion this check becomes trivially true, because both paths
    load the same file. It is deliberately NOT deleted at that point: it is
    the audit trail recording why the refactor was safe to attempt.

USAGE
    python test_regression_pinned.py
    python test_regression_pinned.py --verbose
    python test_regression_pinned.py --update-pins-dry-run

    No simulator required. Exit 0 if every pin holds, 1 otherwise.

    There is deliberately no --update-pins that writes. Auto-updating a
    regression pin defeats the entire purpose of having one; the values are
    edited by hand, in a commit whose message says why they moved.

ASCII only throughout.
"""

import argparse
import sys

from battery_model import (AIRSIM_GENERIC_QUAD, BatteryModel, GRAVITY_MS2,
                           airsim_drag_factors, airsim_predicted_tilt_deg)

MAVIC_SPECS_CANDIDATES = [
    "catalog/entities/UAS-QUAD-DJI-MAVIC3.json",   # post-migration location
    "data/mavic3_specs.json",                      # pre-migration location
]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _model(profile, calibration):
    return BatteryModel(profile=profile, calibration=calibration,
                        verbose=False)


def _sim_thrust_to_weight():
    weight = AIRSIM_GENERIC_QUAD["mass_kg"] * GRAVITY_MS2
    maximum = (AIRSIM_GENERIC_QUAD["rotor_count"]
               * AIRSIM_GENERIC_QUAD["max_thrust_per_rotor_n"])
    return maximum / weight


def _tick_sequence():
    """Fly 60 s at 9 m/s, then hover 60 s. Returns both cumulative totals."""
    model = _model("spec", "hover")
    model.set_wind(0.0, 0.0, 0.0)
    model.tick(60.0, (9.0, 0.0, 0.0))
    after_cruise = model.energy_consumed_wh
    model.tick(60.0, (0.0, 0.0, 0.0))
    return after_cruise, model.energy_consumed_wh


# ---------------------------------------------------------------------------
# The pins
#
# (label, callable, expected, absolute_tolerance)
#
# Captured 2026-09-10 from unmodified code, before the catalog inversion.
#
# Every value below was MEASURED at full precision, not rounded and then
# extended. A first draft of this file carried hand-typed values whose trailing
# digits had never been measured - the printout they came from showed four
# decimal places and the pins claimed ten. Twelve pins reported CHANGED on the
# first run against code that had not been touched.
#
# That is the failure mode this whole project exists to name: a number quoted
# to more precision than its source supports. It is recorded here rather than
# quietly corrected, because the check earning its keep on its first execution
# is the best evidence that it works.
# ---------------------------------------------------------------------------
PINS = [
    # ---- Geometry and the hover operating point ----
    ("disk area m2",
     lambda: _model("spec", "hover").disk_area_m2, 0.1791507034, 1e-9),
    ("hover thrust N",
     lambda: _model("spec", "hover").hover_thrust_n, 8.7769517500, 1e-9),
    ("hover induced velocity m/s",
     lambda: _model("spec", "hover").hover_induced_velocity_ms,
     4.4717709927, 1e-9),
    ("hover rotor speed rpm",
     lambda: _model("spec", "hover").hover_rpm, 4245.8053341051, 1e-6),
    ("rotor tip speed m/s",
     lambda: _model("spec", "hover").rotor_tip_speed_ms, 53.0875915679, 1e-9),

    # ---- The single fitted parameter, and hover power ----
    ("spec/hover profile power W (THE fitted parameter)",
     lambda: _model("spec", "hover").profile_power_hover_w,
     20.0176642461, 1e-8),
    ("spec/hover hover power W",
     lambda: _model("spec", "hover").hover_power_w, 115.5000000000, 1e-8),

    # ---- Power breakdown at DJI's flight-time test speed ----
    ("9 m/s induced W",
     lambda: _model("spec", "hover").power_required((9.0, 0, 0))["induced_w"],
     29.2637885697, 1e-8),
    ("9 m/s profile W",
     lambda: _model("spec", "hover").power_required((9.0, 0, 0))["profile_w"],
     22.6929201195, 1e-8),
    ("9 m/s parasitic W",
     lambda: _model("spec", "hover").power_required((9.0, 0, 0))["parasitic_w"],
     6.3787500000, 1e-8),
    ("9 m/s total W",
     lambda: _model("spec", "hover").power_required((9.0, 0, 0))["total_w"],
     87.9193233614, 1e-8),
    ("9 m/s tilt deg",
     lambda: _model("spec", "hover").power_required((9.0, 0, 0))["tilt_deg"],
     3.2352520681, 1e-8),
    ("9 m/s induced velocity m/s",
     lambda: _model("spec", "hover").power_required(
         (9.0, 0, 0))["induced_velocity_ms"], 2.1637519812, 1e-8),

    # ---- Endurance and range, spec profile, hover-calibrated ----
    # P6 LIVES HERE. Cruise at 9 m/s is the pre-registered +14.2% miss.
    ("spec/hover cruise endurance min  [P6]",
     lambda: _model("spec", "hover").endurance_minutes((9.0, 0, 0)),
     52.5481751151, 1e-8),
    ("spec/hover max range km",
     lambda: _model("spec", "hover").max_range_km(), 38.0806530534, 1e-8),
    ("spec/hover best range speed m/s",
     lambda: _model("spec", "hover").best_range_speed_ms(), 15.0, 1e-8),

    # ---- Zero-free-parameter mode ----
    ("spec/none hover endurance min",
     lambda: _model("spec", "none").endurance_minutes(), 40.0396468108, 1e-8),
    ("spec/none cruise endurance min",
     lambda: _model("spec", "none").endurance_minutes((9.0, 0, 0)),
     52.6257803827, 1e-8),
    ("spec/none max range km",
     lambda: _model("spec", "none").max_range_km(), 38.1354252968, 1e-8),

    # ---- Operational profile ----
    ("oper/hover hover endurance min",
     lambda: _model("operational", "hover").endurance_minutes(),
     28.8135593220, 1e-8),
    ("oper/hover cruise endurance min",
     lambda: _model("operational", "hover").endurance_minutes((9.0, 0, 0)),
     37.8524990236, 1e-8),
    ("oper/hover max range km",
     lambda: _model("operational", "hover").max_range_km(),
     27.4309788944, 1e-8),

    # ---- Drag: force vs power, the units distinction ----
    ("drag force at 9 m/s N",
     lambda: _model("spec", "hover").calculate_drag_force(9.0),
     0.4961250000, 1e-9),
    ("drag power at 9 m/s W",
     lambda: _model("spec", "hover").calculate_drag_power(9.0),
     4.4651250000, 1e-9),

    # ---- Forward integration: tick() must not rewrite history ----
    ("tick 60 s at 9 m/s, cumulative Wh",
     lambda: _tick_sequence()[0], 1.4653220560, 1e-9),
    ("tick + 60 s hover, cumulative Wh",
     lambda: _tick_sequence()[1], 3.3903220560, 1e-9),

    # ---- Simulator reference: P1, P2, P7, P8 all trace to these ----
    ("sim effective CdA_x m2  [P1]",
     lambda: airsim_drag_factors()["effective_cda_x_m2"], 0.0107661850, 1e-9),
    ("sim effective CdA_y m2  [P1]",
     lambda: airsim_drag_factors()["effective_cda_y_m2"], 0.0116761850, 1e-9),
    ("sim thrust-to-weight  [P7]",
     _sim_thrust_to_weight, 1.7047396483, 1e-9),
    ("sim hover throttle pct  [P7]",
     lambda: 100.0 / _sim_thrust_to_weight(), 58.6599837106, 1e-8),
    ("sim tilt at 2 m/s deg  [P2]",
     lambda: airsim_predicted_tilt_deg(2.0, "y"), 0.1671351435, 1e-9),
    ("sim tilt at 5 m/s deg  [P2]",
     lambda: airsim_predicted_tilt_deg(5.0, "y"), 1.0444818936, 1e-9),
    ("sim tilt at 8 m/s deg  [P2]",
     lambda: airsim_predicted_tilt_deg(8.0, "y"), 2.6722306330, 1e-9),
    ("sim tilt at 12 m/s deg  [P2]",
     lambda: airsim_predicted_tilt_deg(12.0, "y"), 5.9949093306, 1e-9),
]

# Non-numeric pins, compared exactly.
# EDITED IN C4, deliberately, and this is the only pin edit that commit made.
#
# Making validation data-driven surfaced max_wind_resistance_ms, which the
# Mavic's calibration block has always declared as a held-out anchor and which
# no code has ever scored. It now reports UNSCORED rather than being silently
# absent, because an anchor missing from a board is indistinguishable from one
# that passed.
#
# So the SHAPE changed: four anchor rows instead of three, and held_out
# declared 3 instead of 2. What did not change is anything scored - passed 0,
# failed 2, and every numeric pin above held to 1e-8. P6's +14.2% cruise miss
# is intact.
STATUS_PINS = [
    ("spec/hover anchor statuses",
     lambda: [a["status"] for a in
              _model("spec", "hover").validate_against_spec()["anchors"]],
     ["CALIBRATED", "FAIL", "FAIL", "UNSCORED"]),
    ("spec/hover counts (held_out, scored, passed, failed)",
     lambda: tuple(_model("spec", "hover").validate_against_spec()[key]
                   for key in ("held_out_count", "scored_count",
                               "passed_count", "failed_count")),
     (3, 2, 0, 2)),
]


# ---------------------------------------------------------------------------
# Pin group zero - the equivalence proof
# ---------------------------------------------------------------------------
def _find_mavic_specs():
    """Locate the Mavic catalog file at whichever path currently holds it."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for relative in MAVIC_SPECS_CANDIDATES:
        candidate = os.path.join(here, relative.replace("/", os.sep))
        if os.path.exists(candidate):
            return candidate
    return None


def check_equivalence(verbose=False):
    """
    PIN GROUP ZERO.

    Assert that built-in defaults and the catalog file produce identical
    models across every profile x calibration combination. This is the proof
    that making the file authoritative cannot move a published number.

    Once the inversion has landed, both paths load the same file and this is
    trivially true. Keep it anyway - it records why the refactor was safe.
    """
    specs_path = _find_mavic_specs()
    lines = []
    lines.append("PIN GROUP ZERO - defaults vs catalog file equivalence")
    lines.append("")

    if specs_path is None:
        lines.append("  SKIPPED: no Mavic catalog file found at any of:")
        for relative in MAVIC_SPECS_CANDIDATES:
            lines.append("    %s" % relative)
        return True, lines, 0

    lines.append("  Catalog file: %s" % specs_path)
    lines.append("")

    attributes = ("hover_power_w", "profile_power_hover_w", "disk_area_m2",
                  "usable_energy_wh", "hover_rpm", "hover_thrust_n")
    worst = 0.0
    failures = 0

    for profile in ("spec", "operational"):
        for calibration in ("hover", "none"):
            from_defaults = BatteryModel(profile=profile,
                                         calibration=calibration,
                                         verbose=False)
            from_file = BatteryModel(specs_file=specs_path, profile=profile,
                                     calibration=calibration, verbose=False)
            deltas = []
            for attribute in attributes:
                delta = abs(getattr(from_defaults, attribute)
                            - getattr(from_file, attribute))
                deltas.append(delta)
            deltas.append(abs(from_defaults.endurance_minutes((9.0, 0, 0))
                              - from_file.endurance_minutes((9.0, 0, 0))))
            deltas.append(abs(from_defaults.max_range_km()
                              - from_file.max_range_km()))

            combination_worst = max(deltas)
            worst = max(worst, combination_worst)
            status = "OK" if combination_worst <= 1e-12 else "DIFFERS"
            if combination_worst > 1e-12:
                failures += 1
            if verbose or combination_worst > 1e-12:
                lines.append("  %-12s %-6s  max delta %.3e  %s"
                             % (profile, calibration, combination_worst,
                                status))

    lines.append("")
    lines.append("  Worst difference across all 4 combinations: %.3e" % worst)
    if failures == 0:
        lines.append("  RESULT: identical. Making the file authoritative")
        lines.append("  cannot move a published number.")
    else:
        lines.append("  RESULT: %d combination(s) DIFFER. The catalog file and")
        lines.append("  the built-in defaults disagree. Do NOT proceed with an")
        lines.append("  inversion until this is understood.")
    return failures == 0, lines, failures


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_pins(verbose=False):
    """Evaluate every pin. Returns (results, failure_count)."""
    results = []
    failures = 0

    for label, getter, expected, tolerance in PINS:
        try:
            actual = float(getter())
            delta = abs(actual - expected)
            ok = delta <= tolerance
        except Exception as exc:
            results.append({"label": label, "expected": expected,
                            "actual": None, "delta": None, "ok": False,
                            "error": "%s: %s" % (type(exc).__name__, exc)})
            failures += 1
            continue
        if not ok:
            failures += 1
        results.append({"label": label, "expected": expected,
                        "actual": actual, "delta": delta, "ok": ok,
                        "tolerance": tolerance, "error": None})

    for label, getter, expected in STATUS_PINS:
        try:
            actual = getter()
            ok = actual == expected
        except Exception as exc:
            results.append({"label": label, "expected": expected,
                            "actual": None, "delta": None, "ok": False,
                            "error": "%s: %s" % (type(exc).__name__, exc)})
            failures += 1
            continue
        if not ok:
            failures += 1
        results.append({"label": label, "expected": expected,
                        "actual": actual, "delta": None, "ok": ok,
                        "tolerance": None, "error": None})

    return results, failures


def format_report(results, failures, equivalence_lines, verbose=False):
    lines = []
    lines.append("=" * 72)
    lines.append("PINNED REGRESSION CHECK")
    lines.append("=" * 72)
    lines.append("Pins guard figures that are already published in")
    lines.append("PREDICTIONS.md, VALIDATION.md, committed results/ files and")
    lines.append("a pushed git history. Any movement is a finding.")
    lines.append("")
    lines.extend(equivalence_lines)
    lines.append("")
    lines.append("-" * 72)
    lines.append("PINNED VALUES")
    lines.append("-" * 72)

    header = "  %-46s %14s  %s" % ("Pin", "Delta", "Result")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for record in results:
        if record["error"]:
            lines.append("  %-46s %14s  ERROR" % (record["label"][:46], "-"))
            lines.append("      %s" % record["error"])
            continue
        if record["delta"] is None:
            marker = "OK" if record["ok"] else "CHANGED"
            lines.append("  %-46s %14s  %s"
                         % (record["label"][:46], "exact", marker))
            if not record["ok"] or verbose:
                lines.append("      expected %r" % (record["expected"],))
                lines.append("      actual   %r" % (record["actual"],))
            continue

        marker = "OK" if record["ok"] else "CHANGED"
        lines.append("  %-46s %14.3e  %s"
                     % (record["label"][:46], record["delta"], marker))
        if not record["ok"] or verbose:
            lines.append("      expected %.10f  actual %.10f  tol %.1e"
                         % (record["expected"], record["actual"],
                            record["tolerance"]))

    lines.append("")
    lines.append("-" * 72)
    if failures == 0:
        lines.append("ALL %d PINS HOLD. No published figure has moved."
                     % len(results))
    else:
        lines.append("%d OF %d PINS CHANGED." % (failures, len(results)))
        lines.append("")
        lines.append("A changed pin is not automatically a bug - but it IS a")
        lines.append("decision. If the change is intended, edit the pin by")
        lines.append("hand in a commit whose message explains why it moved,")
        lines.append("and check whether PREDICTIONS.md, VALIDATION.md or")
        lines.append("README.md quote the old value. If it is not intended,")
        lines.append("you have just caught a regression.")
    lines.append("-" * 72)
    return "\n".join(lines)


def print_dry_run_pins():
    """Print what the pins WOULD be. Never writes - that is the point."""
    print("Current values, for hand-editing into PINS. Nothing is written.")
    print("")
    for label, getter, expected, tolerance in PINS:
        try:
            actual = float(getter())
        except Exception as exc:
            print("  %-50s ERROR %s" % (label[:50], exc))
            continue
        flag = "" if abs(actual - expected) <= tolerance else "   <-- CHANGED"
        print("  %-50s %.10f%s" % (label[:50], actual, flag))
    for label, getter, expected in STATUS_PINS:
        try:
            print("  %-50s %r" % (label[:50], getter()))
        except Exception as exc:
            print("  %-50s ERROR %s" % (label[:50], exc))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pinned regression check for published figures.")
    parser.add_argument("--verbose", action="store_true",
                        help="show expected and actual for every pin")
    parser.add_argument("--update-pins-dry-run", action="store_true",
                        help="print current values for hand-editing; writes "
                             "nothing, by design")
    arguments = parser.parse_args(argv)

    if arguments.update_pins_dry_run:
        print_dry_run_pins()
        return 0

    equivalence_ok, equivalence_lines, equivalence_failures = \
        check_equivalence(arguments.verbose)
    results, failures = run_pins(arguments.verbose)
    print(format_report(results, failures, equivalence_lines,
                        arguments.verbose))

    return 0 if (failures == 0 and equivalence_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
