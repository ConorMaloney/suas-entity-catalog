"""
probe_sim_capabilities.py - Step 0. Discover what this AirSim install exposes.

WHY THIS RUNS FIRST
    Several things the test plan depends on are UNVERIFIED CONTRACTS in the
    Python client:

      - getRotorStates() has a docstring promising rotor speed, thrust and
        torque, but the RotorStates class declares only "timestamp" and
        "rotors", and the elements of "rotors" arrive as raw dicts. No
        per-rotor class exists anywhere in the package. The key names are a
        server-side contract that the client never validates.
      - BarometerData declares altitude as Quaternionr and pressure as
        Vector3r, though plain floats arrive at runtime.
      - RotorStates uses "timestamp" while ImuData uses "time_stamp".
      - Timestamp UNITS are documented nowhere in the client.

    Guessing at any of these and writing a test on top of the guess produces
    a test that fails for the wrong reason, or worse, silently reports a
    default. So the probe discovers all of it at runtime, writes the findings
    to results/sim_capabilities.json, and downstream tests assert against that
    file and FAIL LOUDLY on anything missing.

    What is testable gets decided by the probe, not by assumption.

USAGE
    python probe_sim_capabilities.py

    Requires the simulator to be running. Exits 1 if it cannot connect, or 2
    if it connects but the install is missing something the tests need.

ASCII only throughout.
"""

import json
import os
import sys
import time

RESULTS_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "results")
CAPABILITIES_PATH = os.path.join(RESULTS_DIRECTORY, "sim_capabilities.json")


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def connect(verbose=True):
    """
    Connect to a running simulator.

    Returns a MultirotorClient, or raises RuntimeError with an actionable
    message. Deliberately does not retry forever: a hung connect in a test
    harness looks identical to a slow one.
    """
    try:
        import cosysairsim as airsim
    except ImportError as exc:
        raise RuntimeError(
            "cannot import cosysairsim (%s). Expected interpreter:\n"
            "  C:\\Users\\black\\AppData\\Local\\Python"
            "\\pythoncore-3.14-64\\python.exe" % exc)

    if verbose:
        print("Connecting to simulator ...")
    client = airsim.MultirotorClient()
    try:
        client.confirmConnection()
    except Exception as exc:
        raise RuntimeError(
            "could not connect to the simulator (%s).\n"
            "Start the UE5 project and press Play, then rerun." % exc)
    if verbose:
        print("Connected.")
    return client


def timestamp_to_seconds(raw_timestamp):
    """
    Convert an AirSim timestamp to seconds, DETECTING the unit at runtime.

    The client documents no unit. AirSim uses nanoseconds since the Unix
    epoch, but rather than hard-code that assumption the unit is detected, so
    a build that changed it is caught instead of silently producing a number
    that is wrong by a factor of a thousand.

    Returns (seconds, detected_unit_string).

    Each candidate divisor is tested by asking whether it yields a PLAUSIBLE
    wall-clock date rather than by bucketing raw magnitude. Magnitude alone
    is ambiguous: 5e9 could be 5 seconds expressed in nanoseconds since sim
    start, or a date in the year 2128. Requiring the decoded value to land
    between 2020 and 2100 resolves it, and anything that fits no divisor is
    reported as a since-start counter instead of being forced into a bucket.
    """
    value = float(raw_timestamp)
    if value <= 0.0:
        return 0.0, "unknown (non-positive)"

    epoch_floor = 1.5e9      # 2017-07-14
    epoch_ceiling = 4.1e9    # 2099-12-16

    for divisor, unit in ((1e9, "nanoseconds since epoch"),
                          (1e6, "microseconds since epoch"),
                          (1e3, "milliseconds since epoch"),
                          (1.0, "seconds since epoch")):
        seconds = value / divisor
        if epoch_floor <= seconds <= epoch_ceiling:
            return seconds, unit

    # Fits no epoch interpretation, so it is a counter from simulator start.
    # Nanoseconds is AirSim's convention for that too.
    return value / 1e9, "nanoseconds since sim start (no epoch fit)"


# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------
def _attempt(label, function):
    """
    Run one probe. Returns a result dict; never raises.

    Every probe records available True/False plus the error text, because
    "this method threw" is itself a finding worth writing down.
    """
    record = {"name": label, "available": False, "error": None, "data": {}}
    try:
        record["data"] = function()
        record["available"] = True
    except Exception as exc:
        record["error"] = "%s: %s" % (type(exc).__name__, exc)
    return record


def probe_environment(client):
    """
    simGetGroundTruthEnvironment - the only genuinely INDEPENDENT source of
    air density available. The sim computes it, so comparing it against the
    assumed 1.225 is a real cross-check rather than a restatement of an input.
    This is prediction P5.
    """
    environment = client.simGetGroundTruthEnvironment()
    return {
        "air_density": float(environment.air_density),
        "air_pressure": float(environment.air_pressure),
        "temperature": float(environment.temperature),
        "gravity_z": float(environment.gravity.z_val),
        "position_z": float(environment.position.z_val),
        "geo_altitude": float(environment.geo_point.altitude),
    }


def probe_rotor_states(client):
    """
    getRotorStates - the contract that most needs discovering.

    Records the ACTUAL key names present on rotors[0]. Downstream, any test
    that wants per-rotor thrust must check these keys rather than assume the
    docstring is accurate.
    """
    states = client.getRotorStates()
    rotors = list(getattr(states, "rotors", []) or [])

    record = {
        "rotor_count": len(rotors),
        "timestamp_attribute": ("timestamp" if hasattr(states, "timestamp")
                                else None),
        "rotor_element_type": type(rotors[0]).__name__ if rotors else None,
        "rotor_keys": [],
        "rotor_zero_sample": {},
    }
    if not rotors:
        return record

    first = rotors[0]
    if isinstance(first, dict):
        record["rotor_keys"] = sorted(first.keys())
        record["rotor_zero_sample"] = {
            key: (float(value) if isinstance(value, (int, float)) else str(value))
            for key, value in first.items()}
    else:
        record["rotor_keys"] = sorted(
            attribute for attribute in dir(first)
            if not attribute.startswith("_")
            and not callable(getattr(first, attribute, None)))
        record["rotor_zero_sample"] = {
            key: str(getattr(first, key, None)) for key in record["rotor_keys"]}

    if hasattr(states, "timestamp"):
        seconds, unit = timestamp_to_seconds(states.timestamp)
        record["timestamp_raw"] = str(states.timestamp)
        record["timestamp_unit"] = unit
    return record


def probe_multirotor_state(client):
    """getMultirotorState - position, velocity, orientation, and the clock."""
    state = client.getMultirotorState()
    kinematics = state.kinematics_estimated
    seconds, unit = timestamp_to_seconds(state.timestamp)
    return {
        "timestamp_raw": str(state.timestamp),
        "timestamp_unit": unit,
        "timestamp_seconds": seconds,
        "timestamp_attribute": "timestamp",
        "landed_state": int(state.landed_state),
        "can_arm": bool(state.can_arm),
        "position": [float(kinematics.position.x_val),
                     float(kinematics.position.y_val),
                     float(kinematics.position.z_val)],
        "linear_velocity": [float(kinematics.linear_velocity.x_val),
                            float(kinematics.linear_velocity.y_val),
                            float(kinematics.linear_velocity.z_val)],
        "orientation_wxyz": [float(kinematics.orientation.w_val),
                             float(kinematics.orientation.x_val),
                             float(kinematics.orientation.y_val),
                             float(kinematics.orientation.z_val)],
        "linear_acceleration": [float(kinematics.linear_acceleration.x_val),
                                float(kinematics.linear_acceleration.y_val),
                                float(kinematics.linear_acceleration.z_val)],
    }


def probe_imu(client):
    """
    getImuData - an independent acceleration source to cross-check against
    KinematicsState.linear_acceleration. Note the attribute is time_stamp
    here and timestamp elsewhere.
    """
    imu = client.getImuData()
    seconds, unit = timestamp_to_seconds(imu.time_stamp)
    return {
        "timestamp_attribute": "time_stamp",
        "timestamp_unit": unit,
        "linear_acceleration": [float(imu.linear_acceleration.x_val),
                                float(imu.linear_acceleration.y_val),
                                float(imu.linear_acceleration.z_val)],
        "angular_velocity": [float(imu.angular_velocity.x_val),
                             float(imu.angular_velocity.y_val),
                             float(imu.angular_velocity.z_val)],
    }


def probe_barometer(client):
    """
    getBarometerData - declared types in types.py are WRONG (altitude is
    declared Quaternionr, pressure Vector3r) but floats arrive. Record what
    actually turns up rather than what is declared.
    """
    barometer = client.getBarometerData()
    return {
        "altitude_declared_type": "Quaternionr",
        "altitude_actual_type": type(barometer.altitude).__name__,
        "altitude_value": (float(barometer.altitude)
                           if isinstance(barometer.altitude, (int, float))
                           else None),
        "pressure_declared_type": "Vector3r",
        "pressure_actual_type": type(barometer.pressure).__name__,
        "pressure_value": (float(barometer.pressure)
                           if isinstance(barometer.pressure, (int, float))
                           else None),
    }


def probe_distance(client):
    """getDistanceSensorData - independent altitude check against position.z."""
    distance = client.getDistanceSensorData()
    return {
        "distance": float(distance.distance),
        "min_distance": float(distance.min_distance),
        "max_distance": float(distance.max_distance),
    }


def probe_clock_ratio(client, sample_seconds=2.0):
    """
    Measure the ACTUAL simulation-to-wall clock ratio.

    This is the single most important probe for interpreting any previous
    result. A test that reports "40 seconds of flight" after 2.3 seconds of
    wall time has not flown for 40 seconds unless this ratio says so, and a
    test that computes duration as distance/speed is not measuring time at
    all.

    Samples the sim clock across a real wall-clock interval and divides.
    """
    first_state = client.getMultirotorState()
    wall_start = time.time()
    sim_start, unit = timestamp_to_seconds(first_state.timestamp)

    time.sleep(sample_seconds)

    second_state = client.getMultirotorState()
    wall_elapsed = time.time() - wall_start
    sim_elapsed = timestamp_to_seconds(second_state.timestamp)[0] - sim_start

    ratio = (sim_elapsed / wall_elapsed) if wall_elapsed > 0.0 else 0.0
    return {
        "wall_elapsed_s": wall_elapsed,
        "sim_elapsed_s": sim_elapsed,
        "measured_clock_ratio": ratio,
        "timestamp_unit": unit,
        "sim_clock_advances": sim_elapsed > 0.0,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def probe(client, sample_seconds=2.0):
    """Run every probe and return one findings dictionary."""
    findings = {
        "probed_on": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python_version": sys.version.split()[0],
        "probes": {},
    }

    try:
        import cosysairsim
        findings["cosysairsim_version"] = getattr(
            cosysairsim, "__version__", "unknown")
    except Exception:
        findings["cosysairsim_version"] = "unknown"

    # Record the configured airframe, so no result is ever read as a Mavic 3.
    try:
        import settings_helper
        findings["settings"] = {
            "vehicle_type": settings_helper.read_vehicle_type(),
            "clock_speed_configured": settings_helper.read_clock_speed(),
            "wind_configured": list(settings_helper.read_wind()),
        }
    except Exception as exc:
        findings["settings"] = {"error": str(exc)}

    ordered = [
        ("environment", lambda: probe_environment(client)),
        ("multirotor_state", lambda: probe_multirotor_state(client)),
        ("rotor_states", lambda: probe_rotor_states(client)),
        ("imu", lambda: probe_imu(client)),
        ("barometer", lambda: probe_barometer(client)),
        ("distance_sensor", lambda: probe_distance(client)),
        ("clock_ratio", lambda: probe_clock_ratio(client, sample_seconds)),
    ]
    for label, function in ordered:
        findings["probes"][label] = _attempt(label, function)

    findings["summary"] = _summarize(findings)
    return findings


def _summarize(findings):
    """Decide what the downstream tests are ALLOWED to claim."""
    probes = findings["probes"]

    def ok(name):
        return probes.get(name, {}).get("available", False)

    rotor_keys = probes.get("rotor_states", {}).get("data", {}).get(
        "rotor_keys", [])
    has_thrust = any("thrust" in key.lower() for key in rotor_keys)
    has_speed = any("speed" in key.lower() or "rpm" in key.lower()
                    for key in rotor_keys)

    clock = probes.get("clock_ratio", {}).get("data", {})

    return {
        "can_measure_sim_time": bool(clock.get("sim_clock_advances", False)),
        "measured_clock_ratio": clock.get("measured_clock_ratio"),
        "can_read_air_density": ok("environment"),
        "can_read_rotor_thrust": bool(has_thrust),
        "can_read_rotor_speed": bool(has_speed),
        "rotor_keys_found": rotor_keys,
        "can_test_p4_shaft_power": bool(has_thrust or has_speed),
        "can_read_attitude": ok("multirotor_state"),
        "can_test_p1_p2_tilt": ok("multirotor_state"),
        "independent_cross_checks": [
            name for name, enabled in [
                ("imu vs kinematics acceleration", ok("imu")),
                ("barometer vs environment pressure", ok("barometer")),
                ("distance sensor vs position z", ok("distance_sensor")),
            ] if enabled],
    }


# ---------------------------------------------------------------------------
# Capability gate used by the tests
# ---------------------------------------------------------------------------
def load_capabilities(path=None):
    """Load the probe findings. Returns None if the probe has not been run."""
    path = path or CAPABILITIES_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except (ValueError, IOError):
        return None


def require(capabilities, capability_name, test_name):
    """
    Assert that the probe found a capability. Raises RuntimeError if not.

    This is the "fail loudly" gate. A test that needs per-rotor thrust and
    does not have it must stop and say so, not quietly substitute a modeled
    number and present it as measured.
    """
    if capabilities is None:
        raise RuntimeError(
            "%s requires probe results. Run probe_sim_capabilities.py first."
            % test_name)
    summary = capabilities.get("summary", {})
    if not summary.get(capability_name, False):
        raise RuntimeError(
            "%s requires capability '%s', which this AirSim install does NOT "
            "provide (see results/sim_capabilities.json). Refusing to report "
            "a modeled number as a measured one." % (test_name, capability_name))
    return True


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def format_report(findings):
    """Render findings as an ASCII report."""
    lines = []
    lines.append("=" * 72)
    lines.append("AIRSIM CAPABILITY PROBE")
    lines.append("=" * 72)
    lines.append("Probed on      : %s" % findings["probed_on"])
    lines.append("cosysairsim    : %s" % findings["cosysairsim_version"])
    lines.append("Python         : %s" % findings["python_version"])

    settings = findings.get("settings", {})
    if "error" not in settings:
        lines.append("VehicleType    : %s" % settings.get("vehicle_type"))
        lines.append("ClockSpeed set : %s" % settings.get("clock_speed_configured"))
        lines.append("Wind set       : %s" % settings.get("wind_configured"))
    lines.append("")

    if settings.get("vehicle_type") == "SimpleFlight":
        lines.append("NOTE: VehicleType SimpleFlight routes to")
        lines.append("setupFrameGenericQuad - a 1.0 kg generic quad on 0.2286 m")
        lines.append("propellers. It is NOT a Mavic 3 (0.895 kg, 0.2388 m), and")
        lines.append("mass and rotor geometry are C++ compile-time constants")
        lines.append("that settings.json cannot change. Label accordingly.")
        lines.append("")

    lines.append("-" * 72)
    lines.append("PROBE RESULTS")
    lines.append("-" * 72)
    for name, record in findings["probes"].items():
        status = "OK" if record["available"] else "UNAVAILABLE"
        lines.append("")
        lines.append("[%s] %s" % (status, name))
        if record["error"]:
            lines.append("    error: %s" % record["error"])
        for key, value in sorted(record["data"].items()):
            lines.append("    %-26s %s" % (key, value))

    lines.append("")
    lines.append("-" * 72)
    lines.append("WHAT THE TESTS MAY CLAIM")
    lines.append("-" * 72)
    summary = findings["summary"]
    for key in sorted(summary):
        lines.append("  %-30s %s" % (key, summary[key]))

    lines.append("")
    if not summary.get("can_test_p4_shaft_power"):
        lines.append("P4 (shaft power hover vs cruise) is NOT TESTABLE on this")
        lines.append("install: getRotorStates() exposes no thrust or speed key.")
        lines.append("This is a finding, not a failure. The no-translational-")
        lines.append("lift result still stands on the source reading of")
        lines.append("RotorParams.hpp, where thrust = C_T * rho * n^2 * D^4")
        lines.append("carries no induced-velocity term at all.")
    else:
        lines.append("P4 is testable: rotor keys %s"
                     % summary.get("rotor_keys_found"))

    ratio = summary.get("measured_clock_ratio")
    if ratio:
        lines.append("")
        lines.append("Measured clock ratio %.2fx. Every duration in a test must"
                     % ratio)
        lines.append("come from sim timestamps, never from wall time or from")
        lines.append("distance divided by speed.")
    return "\n".join(lines)


def main():
    try:
        client = connect()
    except RuntimeError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    findings = probe(client)
    report = format_report(findings)
    print(report)

    if not os.path.isdir(RESULTS_DIRECTORY):
        os.makedirs(RESULTS_DIRECTORY)
    with open(CAPABILITIES_PATH, "w") as handle:
        json.dump(findings, handle, indent=2)
    text_path = os.path.join(
        RESULTS_DIRECTORY,
        "probe_%s.txt" % time.strftime("%Y%m%d_%H%M%S"))
    with open(text_path, "w") as handle:
        handle.write(report + "\n")

    print("")
    print("Capabilities written: %s" % CAPABILITIES_PATH)
    print("Report written      : %s" % text_path)

    essential = ["can_measure_sim_time", "can_read_air_density",
                 "can_read_attitude"]
    missing = [name for name in essential
               if not findings["summary"].get(name)]
    if missing:
        print("")
        print("WARNING: essential capabilities missing: %s"
              % ", ".join(missing))
        print("Tests 3.a and 3.b cannot produce trustworthy numbers without")
        print("these. Investigate before running them.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
