"""
settings_helper.py - Safe read/modify access to the AirSim settings.json.

WHY THIS EXISTS
    Some AirSim settings cannot be changed through the RPC API and are only
    read at simulator start. ClockSpeed is the important one: it is applied
    when the sim boots and there is no runtime setter. Wind CAN be set at
    runtime through simSetWind(), but the settings.json path is retained here
    because the briefed test procedure uses it, and because it is the only way
    to establish a wind condition that is present from the first physics tick.

WHAT IT GUARANTEES
    1. Unrelated keys are preserved. A helper that rewrites the file from a
       template silently drops SimMode and Vehicles, which turns the next sim
       launch into a car simulator.
    2. Writes are atomic. New content goes to a temporary file in the SAME
       directory and is then os.replace()d over the target, so an interrupted
       write cannot leave a truncated settings.json - which the simulator
       would refuse to start with.
    3. A timestamped .bak is written before the first modification.
    4. Malformed JSON is reported, never silently overwritten.

    Key order survives a round trip because json.load builds dicts, which are
    insertion-ordered, and json.dump writes them in that order.

CLI
    python settings_helper.py --show
    python settings_helper.py --wind 0 5 0
    python settings_helper.py --clock 1.0
    python settings_helper.py --show --path <some other settings.json>

ASCII only throughout.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

DEFAULT_SETTINGS_PATH = os.path.join(
    os.path.expanduser("~"), "Documents", "AirSim", "settings.json")


class SettingsError(Exception):
    """Raised when settings.json is missing, unreadable or malformed."""


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def read_settings(path=None):
    """
    Load settings.json and return it as a dict.

    Raises SettingsError on a missing file or malformed JSON. It deliberately
    does NOT fall back to a default template: silently substituting defaults
    for a file the user has edited is how configuration drift starts.
    """
    path = path or DEFAULT_SETTINGS_PATH
    if not os.path.exists(path):
        raise SettingsError("settings.json not found: %s" % path)
    try:
        with open(path, "r") as handle:
            text = handle.read()
    except IOError as exc:
        raise SettingsError("could not read %s: %s" % (path, exc))

    try:
        settings = json.loads(text)
    except ValueError as exc:
        raise SettingsError(
            "settings.json is not valid JSON (%s): %s -- refusing to "
            "overwrite it. Fix or restore the file first." % (exc, path))

    if not isinstance(settings, dict):
        raise SettingsError(
            "settings.json must contain a JSON object, found %s: %s"
            % (type(settings).__name__, path))
    return settings


def read_wind(path=None):
    """Return the configured wind as an (x, y, z) tuple of floats, NED m/s."""
    settings = read_settings(path)
    wind = settings.get("Wind", {})
    if not isinstance(wind, dict):
        return (0.0, 0.0, 0.0)
    return (float(wind.get("X", 0.0)),
            float(wind.get("Y", 0.0)),
            float(wind.get("Z", 0.0)))


def read_clock_speed(path=None):
    """Return ClockSpeed as a float. AirSim's own default is 1.0."""
    settings = read_settings(path)
    try:
        return float(settings.get("ClockSpeed", 1.0))
    except (TypeError, ValueError):
        return 1.0


def read_vehicle_type(path=None, vehicle_name=None):
    """
    Return the VehicleType string for a vehicle, or None.

    Used by the tests to record WHICH airframe produced a result. For
    "SimpleFlight" that airframe is setupFrameGenericQuad - a 1.0 kg generic
    quad, not a Mavic 3 - and every sim-derived number must be labelled
    accordingly.
    """
    settings = read_settings(path)
    vehicles = settings.get("Vehicles", {})
    if not isinstance(vehicles, dict) or not vehicles:
        return None
    if vehicle_name is None:
        vehicle_name = sorted(vehicles.keys())[0]
    entry = vehicles.get(vehicle_name, {})
    if not isinstance(entry, dict):
        return None
    return entry.get("VehicleType")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def _backup(path):
    """
    Copy path to a timestamped .bak beside it. Returns the backup path.

    The timestamp resolves to one second, so two writes in the same second
    would collide and the second backup would overwrite the first - throwing
    away the ONLY copy of the original. A collision therefore gets a counter
    suffix instead; a backup is never overwritten.
    """
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = "%s.%s.bak" % (path, stamp)
    counter = 1
    while os.path.exists(backup_path):
        backup_path = "%s.%s_%02d.bak" % (path, stamp, counter)
        counter += 1
    shutil.copy2(path, backup_path)
    return backup_path


def _atomic_write(path, settings):
    """
    Serialize settings to path atomically.

    The temporary file is created in the SAME directory as the target so that
    os.replace() is a rename within one filesystem, which is atomic. Writing
    to the system temp directory and moving across volumes is not.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    handle_fd, temporary_path = tempfile.mkstemp(
        prefix=".settings_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(handle_fd, "w") as handle:
            json.dump(settings, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def write_settings(settings, path=None, backup=True):
    """Validate, back up, then atomically write the settings dict."""
    path = path or DEFAULT_SETTINGS_PATH
    if not isinstance(settings, dict):
        raise SettingsError("settings must be a dict")

    # Serialize BEFORE touching the target: if the dict is not JSON
    # serializable, fail here rather than after truncating anything.
    try:
        json.dumps(settings)
    except (TypeError, ValueError) as exc:
        raise SettingsError("settings dict is not JSON serializable: %s" % exc)

    backup_path = None
    if backup and os.path.exists(path):
        backup_path = _backup(path)
    _atomic_write(path, settings)
    return backup_path


def set_wind(wind_x, wind_y=0.0, wind_z=0.0, path=None, backup=True):
    """
    Set the Wind block, preserving every other key in the file.

    Axes are NED world frame, m/s, matching simSetWind(Vector3r):
        X positive = wind blowing toward NORTH
        Y positive = wind blowing toward EAST
        Z positive = wind blowing DOWNWARD

    Returns (previous_wind_tuple, new_wind_tuple, backup_path).

    NOTE: wind set here takes effect only at simulator START. Changing this
    file while the sim is running changes nothing until restart. Use
    client.simSetWind() for a running simulator.
    """
    path = path or DEFAULT_SETTINGS_PATH
    settings = read_settings(path)

    previous = read_wind(path)
    settings["Wind"] = {"X": float(wind_x),
                        "Y": float(wind_y),
                        "Z": float(wind_z)}
    backup_path = write_settings(settings, path, backup=backup)
    return previous, (float(wind_x), float(wind_y), float(wind_z)), backup_path


def set_clock_speed(clock_speed, path=None, backup=True):
    """
    Set ClockSpeed, preserving every other key.

    Returns (previous, new, backup_path).

    On the value: the physics thread is scheduled on a fixed 3 ms WALL clock
    cadence, but the integration step is whatever SIMULATION time elapsed since
    the last update (FastPhysicsEngine: dt = clock()->updateSince(...), and
    World::worldUpdatorAsync discards the scheduled period). Since ScalableClock
    makes sim time run ClockSpeed times faster than wall time:

        dt_sim ~= 3 ms * ClockSpeed

    So raising ClockSpeed does not run more physics steps - it runs the same
    number and makes each cover more simulated time. Steady-state results
    survive it; transients, control response and time integration do not.
    Validation runs should use 1.0.
    """
    clock_speed = float(clock_speed)
    if clock_speed <= 0.0:
        raise SettingsError("ClockSpeed must be positive, got %r" % clock_speed)

    path = path or DEFAULT_SETTINGS_PATH
    settings = read_settings(path)
    previous = read_clock_speed(path)
    settings["ClockSpeed"] = clock_speed
    backup_path = write_settings(settings, path, backup=backup)
    return previous, clock_speed, backup_path


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def format_summary(path=None):
    """Render the settings that matter to these tests as ASCII text."""
    path = path or DEFAULT_SETTINGS_PATH
    settings = read_settings(path)
    wind = read_wind(path)
    clock = read_clock_speed(path)

    lines = []
    lines.append("AirSim settings: %s" % path)
    lines.append("  SettingsVersion : %s" % settings.get("SettingsVersion"))
    lines.append("  SimMode         : %s" % settings.get("SimMode"))
    lines.append("  ClockSpeed      : %s" % clock)
    lines.append("  Wind (NED m/s)  : X=%.2f  Y=%.2f  Z=%.2f" % wind)

    vehicles = settings.get("Vehicles", {})
    if isinstance(vehicles, dict) and vehicles:
        for name in sorted(vehicles.keys()):
            entry = vehicles[name] if isinstance(vehicles[name], dict) else {}
            lines.append("  Vehicle '%s'    : VehicleType=%s, state=%s"
                         % (name, entry.get("VehicleType"),
                            entry.get("DefaultVehicleState")))
    else:
        lines.append("  Vehicles        : none declared")

    others = sorted(k for k in settings
                    if k not in ("SettingsVersion", "SimMode", "ClockSpeed",
                                 "Wind", "Vehicles"))
    lines.append("  Other top keys  : %s" % (", ".join(others) or "none"))

    if clock != 1.0:
        lines.append("")
        lines.append("  WARNING: ClockSpeed is %s, not 1.0. FastPhysics uses a"
                     % clock)
        lines.append("  fixed 3 ms WALL cadence but integrates over elapsed")
        lines.append("  SIM time, so the step is about 3 ms x ClockSpeed =")
        lines.append("  %.0f ms. Coarser, not busier. Use 1.0 to validate."
                     % (3.0 * clock))
    if wind != (0.0, 0.0, 0.0):
        lines.append("")
        lines.append("  WARNING: a non-zero wind is configured. A test that")
        lines.append("  calls itself a zero-wind baseline without clearing")
        lines.append("  this is reporting a windy result under a calm label.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read and modify the AirSim settings.json safely.")
    parser.add_argument("--show", action="store_true",
                        help="print the current settings summary")
    parser.add_argument("--wind", nargs=3, type=float,
                        metavar=("X", "Y", "Z"),
                        help="set wind vector in NED m/s")
    parser.add_argument("--clock", type=float, metavar="N",
                        help="set ClockSpeed (1.0 recommended for validation)")
    parser.add_argument("--path", default=DEFAULT_SETTINGS_PATH,
                        help="settings.json path (default: %(default)s)")
    parser.add_argument("--no-backup", action="store_true",
                        help="skip writing a .bak before modifying")
    arguments = parser.parse_args(argv)

    if not (arguments.show or arguments.wind is not None
            or arguments.clock is not None):
        parser.print_help()
        return 0

    backup = not arguments.no_backup

    try:
        if arguments.wind is not None:
            previous, new, backup_path = set_wind(
                arguments.wind[0], arguments.wind[1], arguments.wind[2],
                path=arguments.path, backup=backup)
            print("Wind changed: (%.2f, %.2f, %.2f) -> (%.2f, %.2f, %.2f)"
                  % (previous + new))
            if backup_path:
                print("Backup written: %s" % backup_path)
            print("NOTE: takes effect at simulator START. To change wind in a")
            print("      running sim use client.simSetWind(Vector3r(x,y,z)).")

        if arguments.clock is not None:
            previous, new, backup_path = set_clock_speed(
                arguments.clock, path=arguments.path, backup=backup)
            print("ClockSpeed changed: %.3f -> %.3f" % (previous, new))
            if backup_path:
                print("Backup written: %s" % backup_path)
            print("NOTE: takes effect at simulator START. Restart the sim.")

        if arguments.show:
            print(format_summary(arguments.path))

    except SettingsError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
