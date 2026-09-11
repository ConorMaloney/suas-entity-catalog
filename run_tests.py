"""
run_tests.py - Interactive menu for the DJI Mavic 3 simulation entity tests.

The briefed menu is 1 / 2 / 3 / q. The probe, the offline model self-test and
the settings view are added because running 3.a or 3.b without first knowing
what the simulator exposes - and at what ClockSpeed - produces numbers whose
provenance nobody can reconstruct afterwards.

RECOMMENDED ORDER
    k   the coverage board first - it says which entities can produce a
        number at all, and an entity below R1 is REFUSED by the tests
    r   the pinned regression check, which must be green before anything
    s   check settings; ClockSpeed should be 1.0 for validation runs
    0   probe, so the tests know what they are allowed to claim
    m   offline model self-test, which needs no simulator at all
    1   test 3.a, hover
    2   test 3.b, wind and drag identification
    w   wind demo, if you want to SEE the wind working before trusting
        a table of tilt angles - it also proves simSetWind is live

USAGE
    python run_tests.py

ASCII only throughout.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

MENU = """
========================================================================
SUAS ENTITY CATALOG - TEST RUNNER
========================================================================

  Simulator required:
    1  Test 3.a  - hover endurance (rate-based)
    2  Test 3.b  - wind response and drag identification
    3  Run both, 3.a then 3.b
    0  Probe simulator capabilities  [RUN THIS FIRST]

  Visual:
    w  Wind demo - ramp 0 to 60 m/s, watch it get blown away
    x  Wind demo - single 100 m/s blast (extreme)

  Catalog (no simulator required):
    k  Coverage board - what exists, how good it is, what is missing
    e  Entity record detail (prompts for an id)
    v  Validate one record against its frozen suite (prompts for an id)
    t  Catalog test battery
    r  Pinned regression check

  No simulator required:
    m  battery_model.py offline self-test
    s  Show AirSim settings.json
    c  Set ClockSpeed to 1.0 (recommended for validation)
    p  Show the pre-registered predictions
    d  Show the entity-building standards

    q  Quit

"""


def run_script(script_name, arguments=None):
    """Run one script as a subprocess and report its exit code."""
    command = [PYTHON, os.path.join(HERE, script_name)] + (arguments or [])
    print("")
    print("Running: %s" % " ".join(command[1:]))
    print("-" * 72)
    try:
        completed = subprocess.run(command, cwd=HERE)
    except KeyboardInterrupt:
        print("")
        print("Interrupted.")
        return 130
    print("-" * 72)
    if completed.returncode == 0:
        print("Finished: %s (exit 0)" % script_name)
    else:
        print("Finished: %s (exit %d)" % (script_name, completed.returncode))
    return completed.returncode


def show_file(filename):
    """Print a text file from the project directory."""
    path = os.path.join(HERE, filename)
    if not os.path.exists(path):
        print("")
        print("Not found: %s" % path)
        return
    print("")
    with open(path, "r") as handle:
        print(handle.read())


def probe_status():
    """One-line reminder of whether the probe has been run."""
    path = os.path.join(HERE, "results", "sim_capabilities.json")
    if os.path.exists(path):
        return "Probe results: present (%s)" % path
    return ("Probe results: NOT PRESENT. Run option 0 first, or tests will "
            "run ungated.")


def main():
    while True:
        print(MENU)
        print("  %s" % probe_status())
        print("")
        try:
            choice = input("  Select: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0

        if choice in ("q", "quit", "exit"):
            print("")
            print("Reminder: a green board is not the objective. P6 is")
            print("pre-registered to fail, and failures ship as findings.")
            return 0

        if choice == "0":
            run_script("probe_sim_capabilities.py")
        elif choice == "1":
            run_script("test_3a_hover.py")
        elif choice == "2":
            run_script("test_3b_wind.py")
        elif choice == "3":
            code = run_script("test_3a_hover.py")
            if code != 0:
                print("")
                print("3.a did not exit cleanly. Running 3.b anyway, since a")
                print("failure in one test is not a reason to skip the other.")
            run_script("test_3b_wind.py")
        elif choice == "w":
            run_script("wind_demo.py")
        elif choice == "x":
            run_script("wind_demo.py", ["--extreme"])
        elif choice == "k":
            run_script("catalog.py")
        elif choice == "e":
            try:
                entity_id = input("  Entity id (blank to list): ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if entity_id:
                run_script("catalog.py", ["--entity", entity_id])
            else:
                run_script("catalog.py", ["--list"])
        elif choice == "v":
            try:
                entity_id = input("  Entity id: ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if entity_id:
                run_script("run_validation.py",
                           ["--record",
                            os.path.join("catalog", "entities",
                                         "%s.json" % entity_id)])
        elif choice == "t":
            run_script("test_catalog.py")
        elif choice == "r":
            run_script("test_regression_pinned.py")
        elif choice == "d":
            show_file("STANDARDS.md")
        elif choice == "m":
            run_script("battery_model.py")
        elif choice == "s":
            run_script("settings_helper.py", ["--show"])
        elif choice == "c":
            run_script("settings_helper.py", ["--clock", "1.0", "--show"])
        elif choice == "p":
            show_file("PREDICTIONS.md")
        elif choice == "":
            continue
        else:
            print("")
            print("  Unrecognized option: %r" % choice)

        try:
            input("\n  Press Enter to return to the menu ...")
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0


if __name__ == "__main__":
    sys.exit(main())
