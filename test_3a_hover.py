"""
test_3a_hover.py - Test 3.a, hover endurance.

WHAT THIS MEASURES, AND WHAT IT DOES NOT
    AirSim simulates no battery. Nothing in this test measures a Mavic 3's
    endurance, because nothing in the simulator knows what a battery is. What
    it DOES do is drive the parametric model (L2) from quantities the
    simulator genuinely produces (L3) - elapsed simulation time, reported
    velocity, attitude and air density - so that if the simulator misbehaves,
    the resulting number is visibly wrong instead of quietly plausible.

    That distinction is the whole point. A previous hover test computed
    "30 seconds" from a loop counter with its sleep commented out, ran for
    0.76 s of wall time, and then reported FAIL because 0.5 minutes is less
    than the 46 minute endurance target. It was comparing HOW LONG THE TEST
    RAN against HOW LONG THE AIRCRAFT FLIES. Those are different quantities
    and no tolerance band makes that comparison meaningful.

HOW THIS ONE AVOIDS THAT
    1. Time comes from simulation timestamp deltas. Not wall clock, not a
       loop counter, and never distance divided by speed.
    2. Energy is integrated forward with tick(), sample by sample, using the
       velocity the simulator reports at that instant.
    3. Validation is on the DISCHARGE RATE in percent per minute, extrapolated
       to a full-pack endurance and compared against spec. A 60 second sample
       can then legitimately probe a 40 minute claim.
    4. Air density is read from the simulator, testing prediction P5.
    5. Wall time, sim time and the measured clock ratio are all logged, so
       the reader can check the timebase rather than trust it.

USAGE
    python test_3a_hover.py                 # 60 s of sim time, default
    python test_3a_hover.py --duration 120
    python test_3a_hover.py --altitude 20 --sample-hz 5

    Run probe_sim_capabilities.py first.

ASCII only throughout.
"""

import argparse
import json
import math
import os
import sys
import time

import battery_model
import catalog
import probe_sim_capabilities as probe
import settings_helper

RESULTS_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "results")


def quaternion_to_euler_deg(w, x, y, z):
    """
    Convert a quaternion to (roll, pitch, yaw) in degrees.

    AirSim returns orientation as a quaternion; the tilt predictions in
    PREDICTIONS.md are in degrees of pitch and roll, so the conversion has to
    happen somewhere. Standard aerospace ZYX sequence.
    """
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))     # clamp against domain error
    pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


def check_air_density(client, model):
    """
    Prediction P5: the simulator's own air density is 1.225 +/- 2% at sea
    level.

    This is the fastest genuinely independent check available. The simulator
    computes air density itself, so agreement corroborates the modeling
    assumption rather than restating it. Disagreement means every power
    number in the model is scaled wrong and should be caught before anything
    else runs.
    """
    result = {"prediction": "P5", "tested": False}
    try:
        environment = client.simGetGroundTruthEnvironment()
    except Exception as exc:
        result["error"] = str(exc)
        return result

    measured = float(environment.air_density)
    assumed = model.air_density_kg_m3
    error_percent = ((measured - assumed) / assumed * 100.0
                     if assumed else 0.0)

    result.update({
        "tested": True,
        "measured_air_density": measured,
        "model_air_density": assumed,
        "error_percent": error_percent,
        "tolerance_percent": 2.0,
        "status": "PASS" if abs(error_percent) <= 2.0 else "FAIL",
        "temperature_c": float(environment.temperature) - 273.15,
        "air_pressure_pa": float(environment.air_pressure),
        "gravity_z": float(environment.gravity.z_val),
    })
    return result


# ---------------------------------------------------------------------------
# P4 - translational lift
# ---------------------------------------------------------------------------
def read_rotor_shaft_power(client):
    """
    Measure total rotor shaft power from getRotorStates().

    Each rotor reports thrust, torque_scaler and speed. Verified against the
    C++ source, where MultirotorCommon.hpp declares RotorParameters and
    MultirotorRpcLibAdaptors.hpp serializes it with
    MSGPACK_DEFINE_MAP(thrust, torque_scaler, speed) - so these three keys are
    the actual wire contract, not a docstring promise. Shaft power is then

        P = sum over rotors of |torque| * omega       [W]

    with speed in radians per second.

    Returns None if the keys are absent, so the caller can report P4 as NOT
    TESTABLE rather than silently substituting a modeled number.
    """
    states = client.getRotorStates()
    rotors = list(getattr(states, "rotors", []) or [])
    if not rotors:
        return None

    total_power = 0.0
    total_thrust = 0.0
    speeds = []
    for rotor in rotors:
        if isinstance(rotor, dict):
            torque = rotor.get("torque_scaler")
            speed = rotor.get("speed")
            thrust = rotor.get("thrust")
        else:
            torque = getattr(rotor, "torque_scaler", None)
            speed = getattr(rotor, "speed", None)
            thrust = getattr(rotor, "thrust", None)
        if torque is None or speed is None:
            return None
        total_power += abs(float(torque)) * float(speed)
        total_thrust += float(thrust) if thrust is not None else 0.0
        speeds.append(float(speed))

    return {
        "shaft_power_w": total_power,
        "total_thrust_n": total_thrust,
        "mean_speed_rad_s": sum(speeds) / len(speeds) if speeds else 0.0,
        "rotor_count": len(rotors),
    }


def _average_rotor_power(client, seconds, sample_hz=10.0):
    """Average rotor shaft power over a window of SIMULATION seconds."""
    interval = 1.0 / sample_hz if sample_hz > 0 else 0.1
    state = client.getMultirotorState()
    start = probe.timestamp_to_seconds(state.timestamp)[0]
    readings = []
    while True:
        state = client.getMultirotorState()
        now = probe.timestamp_to_seconds(state.timestamp)[0]
        reading = read_rotor_shaft_power(client)
        if reading is None:
            return None
        readings.append(reading)
        if now - start >= seconds:
            break
        time.sleep(interval)

    count = len(readings)
    return {
        "shaft_power_w": sum(r["shaft_power_w"] for r in readings) / count,
        "total_thrust_n": sum(r["total_thrust_n"] for r in readings) / count,
        "mean_speed_rad_s": sum(r["mean_speed_rad_s"] for r in readings) / count,
        "sample_count": count,
    }


def test_p4_translational_lift(client, altitude_m=10.0, cruise_speed_ms=9.0,
                               window_s=8.0, sample_hz=10.0, verbose=True):
    """
    Prediction P4: simulator shaft power at 9 m/s is within 10% of hover.

    A real helicopter is MORE efficient in forward flight than in hover,
    because forward airspeed reduces the induced velocity the rotor has to
    generate. That is translational lift, and it is why DJI publishes a
    46 min flight time against a 40 min hover time.

    AirSim has no such term. RotorParams.hpp computes

        thrust = C_T * rho * n^2 * D^4

    which depends only on rotor speed - there is no airspeed or
    induced-velocity term anywhere in it. So the simulator's power at cruise
    should differ from hover only by the small extra thrust needed to
    overcome airframe drag, a fraction of a percent.

    A PASS here confirms the simulator is structurally incapable of
    reproducing the flight-time-exceeds-hover-time relationship, and
    therefore that sim-derived power can never validate cruise endurance.
    That physics has to live in the parametric model. This is a clean
    negative result, and it is the point of the test rather than a
    disappointment.
    """
    result = {"prediction": "P4", "tested": False}

    if read_rotor_shaft_power(client) is None:
        result["error"] = ("getRotorStates() exposes no torque/speed keys on "
                           "this install")
        return result

    if verbose:
        print("")
        print("P4: measuring rotor shaft power at hover ...")
    client.moveToPositionAsync(0.0, 0.0, -abs(altitude_m), 3.0).join()
    client.hoverAsync().join()
    time.sleep(2.0)
    hover = _average_rotor_power(client, window_s, sample_hz)

    if verbose:
        print("P4: measuring rotor shaft power at %.1f m/s ..." % cruise_speed_ms)
    # Fly a straight leg and sample only while it is established at speed.
    leg_duration = window_s + 6.0
    client.moveByVelocityZAsync(cruise_speed_ms, 0.0, -abs(altitude_m),
                                leg_duration)
    time.sleep(3.0)      # let it accelerate before sampling
    cruise = _average_rotor_power(client, window_s, sample_hz)
    client.hoverAsync().join()

    if hover is None or cruise is None:
        result["error"] = "rotor state became unreadable mid-test"
        return result

    error_percent = ((cruise["shaft_power_w"] - hover["shaft_power_w"])
                     / hover["shaft_power_w"] * 100.0
                     if hover["shaft_power_w"] else 0.0)

    result.update({
        "tested": True,
        "hover_shaft_power_w": hover["shaft_power_w"],
        "cruise_shaft_power_w": cruise["shaft_power_w"],
        "cruise_speed_ms": cruise_speed_ms,
        "hover_thrust_n": hover["total_thrust_n"],
        "cruise_thrust_n": cruise["total_thrust_n"],
        "hover_speed_rad_s": hover["mean_speed_rad_s"],
        "cruise_speed_rad_s": cruise["mean_speed_rad_s"],
        "error_percent": error_percent,
        "tolerance_percent": 10.0,
        "status": "PASS" if abs(error_percent) <= 10.0 else "FAIL",
    })
    return result


def run_hover_test(client, model, duration_s=60.0, altitude_m=10.0,
                   sample_hz=10.0, verbose=True):
    """
    Fly to altitude, hold station, and integrate energy over sim time.

    Returns a results dictionary. Every duration in it is simulation time
    derived from timestamp deltas.
    """
    if verbose:
        print("Preparing vehicle ...")
    client.enableApiControl(True)
    client.armDisarm(True)

    if verbose:
        print("Taking off ...")
    client.takeoffAsync().join()
    if verbose:
        print("Climbing to %.1f m ..." % altitude_m)
    client.moveToPositionAsync(0.0, 0.0, -abs(altitude_m), 3.0).join()

    # Let the aircraft settle BEFORE capturing the drift reference. Capturing
    # it during the post-takeoff transient makes "drift" measure the settling
    # transient instead of station-keeping error - which is how an earlier run
    # reported 129 m of drift in dead calm.
    if verbose:
        print("Settling ...")
    client.hoverAsync().join()
    time.sleep(2.0)

    settle_state = client.getMultirotorState()
    start_position = (settle_state.kinematics_estimated.position.x_val,
                      settle_state.kinematics_estimated.position.y_val,
                      settle_state.kinematics_estimated.position.z_val)
    model.record_drift(start_position, is_start=True)

    sim_start_s = probe.timestamp_to_seconds(settle_state.timestamp)[0]
    timestamp_unit = probe.timestamp_to_seconds(settle_state.timestamp)[1]
    wall_start = time.time()
    previous_sim_s = sim_start_s

    samples = []
    sample_interval = 1.0 / sample_hz if sample_hz > 0 else 0.1
    sim_elapsed = 0.0

    if verbose:
        print("Holding station for %.1f s of SIMULATION time ..." % duration_s)
        print("")
        print("  %8s %8s %9s %9s %8s %8s %9s"
              % ("sim s", "wall s", "batt %", "power W", "speed", "drift m",
                 "tilt deg"))

    next_report = 0.0
    while sim_elapsed < duration_s:
        state = client.getMultirotorState()
        now_sim_s = probe.timestamp_to_seconds(state.timestamp)[0]
        delta_s = now_sim_s - previous_sim_s

        # A non-advancing clock means the sim is paused or the timestamp is
        # not what it appears to be. Either way, integrating a zero or
        # negative dt would silently produce a flat, tidy-looking result.
        if delta_s <= 0.0:
            time.sleep(sample_interval)
            continue

        previous_sim_s = now_sim_s
        sim_elapsed = now_sim_s - sim_start_s

        kinematics = state.kinematics_estimated
        velocity = (kinematics.linear_velocity.x_val,
                    kinematics.linear_velocity.y_val,
                    kinematics.linear_velocity.z_val)
        position = (kinematics.position.x_val,
                    kinematics.position.y_val,
                    kinematics.position.z_val)

        # Forward integration over the measured sim-time delta.
        model.tick(delta_s, ground_velocity_ned=velocity)
        model.record_drift(position)

        roll, pitch, yaw = quaternion_to_euler_deg(
            kinematics.orientation.w_val, kinematics.orientation.x_val,
            kinematics.orientation.y_val, kinematics.orientation.z_val)

        sample = {
            "sim_time_s": sim_elapsed,
            "wall_time_s": time.time() - wall_start,
            "dt_s": delta_s,
            "battery_percent": model.percentage,
            "power_w": model.last_power_w,
            "energy_wh": model.energy_consumed_wh,
            "velocity_ned": list(velocity),
            "ground_speed_ms": math.sqrt(velocity[0] ** 2 + velocity[1] ** 2),
            "position_ned": list(position),
            "drift_m": model.total_drift_m(),
            "roll_deg": roll,
            "pitch_deg": pitch,
            "yaw_deg": yaw,
        }
        samples.append(sample)

        if verbose and sim_elapsed >= next_report:
            print("  %8.2f %8.2f %9.3f %9.2f %8.3f %8.3f %9.3f"
                  % (sim_elapsed, sample["wall_time_s"], model.percentage,
                     model.last_power_w, sample["ground_speed_ms"],
                     sample["drift_m"], max(abs(roll), abs(pitch))))
            next_report += max(5.0, duration_s / 12.0)

        time.sleep(sample_interval)

    wall_elapsed = time.time() - wall_start

    if verbose:
        print("")
        print("Landing ...")
    try:
        client.hoverAsync().join()
        client.landAsync().join()
        client.armDisarm(False)
        client.enableApiControl(False)
    except Exception as exc:
        print("WARNING: landing sequence raised %s" % exc)

    return _analyze(model, samples, sim_elapsed, wall_elapsed, altitude_m,
                    timestamp_unit)


def _analyze(model, samples, sim_elapsed, wall_elapsed, altitude_m,
             timestamp_unit):
    """Turn the sample series into rate-based results."""
    if not samples:
        return {"error": "no samples collected"}

    discharge_percent = 100.0 - model.percentage
    rate_percent_per_min = (discharge_percent / (sim_elapsed / 60.0)
                            if sim_elapsed > 0 else 0.0)
    extrapolated_min = (100.0 / rate_percent_per_min
                        if rate_percent_per_min > 0 else float("inf"))

    mean_speed = sum(s["ground_speed_ms"] for s in samples) / len(samples)
    max_speed = max(s["ground_speed_ms"] for s in samples)
    mean_power = sum(s["power_w"] for s in samples) / len(samples)
    max_tilt = max(max(abs(s["roll_deg"]), abs(s["pitch_deg"]))
                   for s in samples)
    final_drift = samples[-1]["drift_m"]

    return {
        "samples": samples,
        "sample_count": len(samples),
        "sim_elapsed_s": sim_elapsed,
        "wall_elapsed_s": wall_elapsed,
        "measured_clock_ratio": (sim_elapsed / wall_elapsed
                                 if wall_elapsed > 0 else 0.0),
        "timestamp_unit": timestamp_unit,
        "altitude_m": altitude_m,
        "energy_consumed_wh": model.energy_consumed_wh,
        "battery_remaining_percent": model.percentage,
        "discharge_percent": discharge_percent,
        "discharge_rate_percent_per_min": rate_percent_per_min,
        "extrapolated_endurance_min": extrapolated_min,
        "mean_power_w": mean_power,
        "mean_ground_speed_ms": mean_speed,
        "max_ground_speed_ms": max_speed,
        "max_tilt_deg": max_tilt,
        "final_drift_m": final_drift,
    }


def format_report(results, model, density_check, settings_summary,
                  capabilities, p4_check=None):
    """Render the full ASCII report."""
    lines = []
    lines.append("=" * 72)
    lines.append("TEST 3.A - HOVER ENDURANCE")
    lines.append("=" * 72)
    lines.append("Run on : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")
    lines.append("LAYER LABELS")
    lines.append("  L1 = real aircraft (DJI published or independently measured)")
    lines.append("  L2 = parametric model in battery_model.py")
    lines.append("  L3 = simulator output")
    lines.append("")
    lines.append(settings_summary)
    lines.append("")

    lines.append("-" * 72)
    lines.append("TIMEBASE [L3] - check this before believing anything below")
    lines.append("-" * 72)
    lines.append("  Simulation time elapsed : %.2f s"
                 % results["sim_elapsed_s"])
    lines.append("  Wall clock elapsed      : %.2f s"
                 % results["wall_elapsed_s"])
    lines.append("  Measured clock ratio    : %.2fx"
                 % results["measured_clock_ratio"])
    lines.append("  Timestamp unit detected : %s" % results["timestamp_unit"])
    lines.append("  Samples collected       : %d" % results["sample_count"])
    lines.append("")
    lines.append("  Every duration above is a difference of simulation")
    lines.append("  timestamps. None is a loop counter, and none is a")
    lines.append("  distance divided by a speed.")
    lines.append("")

    lines.append("-" * 72)
    lines.append("P5 - AIR DENSITY CROSS-CHECK [L3 vs L2]")
    lines.append("-" * 72)
    if density_check.get("tested"):
        lines.append("  Simulator air density : %.4f kg/m3"
                     % density_check["measured_air_density"])
        lines.append("  Model assumption      : %.4f kg/m3"
                     % density_check["model_air_density"])
        lines.append("  Error                 : %+.2f%% (tolerance +/-2.0%%)"
                     % density_check["error_percent"])
        lines.append("  Result                : %s" % density_check["status"])
        lines.append("  Simulator temperature : %.1f C"
                     % density_check["temperature_c"])
    else:
        lines.append("  NOT TESTED: %s" % density_check.get("error", "unknown"))
    lines.append("")

    lines.append("-" * 72)
    lines.append("STATION KEEPING [L3]")
    lines.append("-" * 72)
    lines.append("  Commanded altitude    : %.1f m" % results["altitude_m"])
    lines.append("  Mean ground speed     : %.4f m/s"
                 % results["mean_ground_speed_ms"])
    lines.append("  Max ground speed      : %.4f m/s"
                 % results["max_ground_speed_ms"])
    lines.append("  Final drift           : %.3f m" % results["final_drift_m"])
    lines.append("  Max tilt              : %.3f deg" % results["max_tilt_deg"])
    lines.append("")
    lines.append("  Drift is measured from a reference captured AFTER the")
    lines.append("  aircraft settled, so it is station-keeping error and not")
    lines.append("  a post-takeoff transient.")
    lines.append("")

    lines.append("-" * 72)
    lines.append("ENERGY [L2 driven by L3]")
    lines.append("-" * 72)
    lines.append("  Entity                : %s [%s]"
                 % (model.entity_name, model.entity_id))
    lines.append("  Record readiness      : %s" % model.readiness)
    lines.append("  Model profile         : %s" % model.profile)
    lines.append("  Calibration           : %s" % model.calibration)
    lines.append("  Usable capacity       : %.2f Wh of %.2f Wh"
                 % (model.usable_energy_wh, model.capacity_wh))
    lines.append("  Mean power            : %.2f W" % results["mean_power_w"])
    lines.append("  Energy consumed       : %.4f Wh"
                 % results["energy_consumed_wh"])
    lines.append("  Battery remaining     : %.3f %%"
                 % results["battery_remaining_percent"])
    lines.append("")
    lines.append("  These are MODEL figures. The simulator contributed the")
    lines.append("  timebase and the velocity, not the energy: AirSim has no")
    lines.append("  battery, no mass property exposed, and no power model.")
    lines.append("")

    lines.append("-" * 72)
    lines.append("RATE-BASED VALIDATION [L2 vs L1]")
    lines.append("-" * 72)
    lines.append("  Discharge rate        : %.4f %%/min"
                 % results["discharge_rate_percent_per_min"])
    lines.append("  Extrapolated endurance: %.2f min"
                 % results["extrapolated_endurance_min"])
    lines.append("")
    lines.append("  A %.0f second sample legitimately probes a 40 minute claim"
                 % results["sim_elapsed_s"])
    lines.append("  because the comparison is between RATES, not durations.")
    lines.append("  Comparing test length against aircraft endurance, as an")
    lines.append("  earlier version did, tells you nothing at all.")
    lines.append("")
    lines.append(model.format_validation_report())
    lines.append("")

    lines.append("-" * 72)
    lines.append("P4 - TRANSLATIONAL LIFT [L3 measured]")
    lines.append("-" * 72)
    if p4_check and p4_check.get("tested"):
        lines.append("  Rotor shaft power at hover     : %.2f W"
                     % p4_check["hover_shaft_power_w"])
        lines.append("  Rotor shaft power at %.1f m/s   : %.2f W"
                     % (p4_check["cruise_speed_ms"],
                        p4_check["cruise_shaft_power_w"]))
        lines.append("  Difference                     : %+.2f%% "
                     "(tolerance +/-%.0f%%)"
                     % (p4_check["error_percent"],
                        p4_check["tolerance_percent"]))
        lines.append("  Result                         : %s"
                     % p4_check["status"])
        lines.append("  Total thrust hover / cruise    : %.3f / %.3f N"
                     % (p4_check["hover_thrust_n"],
                        p4_check["cruise_thrust_n"]))
        lines.append("")
        lines.append("  Shaft power measured as sum of |torque| * omega from")
        lines.append("  getRotorStates(). A PASS means cruise costs the same")
        lines.append("  as hover, i.e. the simulator has NO translational")
        lines.append("  lift. RotorParams.hpp computes thrust as")
        lines.append("  C_T * rho * n^2 * D^4, which contains no airspeed and")
        lines.append("  no induced-velocity term, so AirSim is structurally")
        lines.append("  incapable of reproducing DJI's 46 min flight time")
        lines.append("  against a 40 min hover time.")
        lines.append("")
        lines.append("  Consequence: sim-derived power can NEVER validate")
        lines.append("  cruise endurance. That physics lives in the L2 model.")
    else:
        lines.append("  NOT TESTED: %s"
                     % (p4_check or {}).get("error", "not run"))
        lines.append("")
        lines.append("  The no-translational-lift finding still stands on the")
        lines.append("  source reading of RotorParams.hpp, which is not")
        lines.append("  contingent on this measurement.")
    lines.append("")

    lines.append("-" * 72)
    lines.append("WHAT THIS TEST DOES NOT ESTABLISH")
    lines.append("-" * 72)
    lines.append("  The simulated airframe is not a Mavic 3. VehicleType")
    lines.append("  SimpleFlight routes to setupFrameGenericQuad: 1.0 kg on")
    lines.append("  0.2286 m propellers, against the Mavic 3's 0.895 kg on")
    lines.append("  0.2388 m. Mass and rotor geometry are C++ compile-time")
    lines.append("  constants and settings.json cannot change them.")
    lines.append("")
    lines.append("  So no hover-endurance number here is a measurement of a")
    lines.append("  Mavic 3. The endurance figure is the L2 model's, and the")
    lines.append("  simulator's contribution is a trustworthy clock and an")
    lines.append("  independently computed air density.")

    if capabilities:
        summary = capabilities.get("summary", {})
        lines.append("")
        lines.append("  Probe-reported capabilities in force for this run:")
        lines.append("    rotor thrust readable : %s"
                     % summary.get("can_read_rotor_thrust"))
        lines.append("    rotor speed readable  : %s"
                     % summary.get("can_read_rotor_speed"))

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Test 3.a - hover endurance, rate-based.")
    parser.add_argument("--duration", type=float, default=60.0,
                        help="simulation seconds to hold station "
                             "(default: %(default)s)")
    parser.add_argument("--altitude", type=float, default=10.0,
                        help="hover altitude in m (default: %(default)s)")
    parser.add_argument("--sample-hz", type=float, default=10.0,
                        help="sampling rate (default: %(default)s)")
    parser.add_argument("--profile", default="operational",
                        choices=["operational", "spec"],
                        help="model profile (default: %(default)s)")
    parser.add_argument("--calibration", default="hover",
                        choices=["hover", "none"],
                        help="model calibration (default: %(default)s)")
    parser.add_argument("--cruise-speed", type=float, default=9.0,
                        help="speed for the P4 comparison, m/s "
                             "(default: %(default)s, DJI's flight-time speed)")
    parser.add_argument("--skip-p4", action="store_true",
                        help="skip the translational-lift comparison")
    parser.add_argument("--entity", default=catalog.DEFAULT_ENTITY_ID,
                        help="catalog entity id (default: %(default)s). An "
                             "entity below R1 readiness is REFUSED, not "
                             "modelled with gaps filled in.")
    arguments = parser.parse_args(argv)

    capabilities = probe.load_capabilities()
    if capabilities is None:
        print("WARNING: no probe results found. Run "
              "probe_sim_capabilities.py first for a fully gated run.")
        print("")

    try:
        settings_summary = settings_helper.format_summary()
    except settings_helper.SettingsError as exc:
        settings_summary = "settings.json unavailable: %s" % exc

    try:
        model = battery_model.BatteryModel(
            entity=arguments.entity, profile=arguments.profile,
            calibration=arguments.calibration, verbose=True)
    except catalog.CatalogError as exc:
        # The gate refused. Do NOT fall back to another entity and do not
        # produce a number from an incomplete record - saying "cannot" is
        # the useful answer here.
        print("ERROR: %s" % exc, file=sys.stderr)
        return 3

    try:
        client = probe.connect()
    except RuntimeError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    # Clear any wind so a hover baseline is genuinely a hover baseline. An
    # earlier run reported a "Zero Wind" scenario while settings.json still
    # held a 5 m/s crosswind, and every figure in it was a windy figure.
    try:
        import cosysairsim as airsim
        client.simSetWind(airsim.Vector3r(0.0, 0.0, 0.0))
        model.set_wind(0.0, 0.0, 0.0)
        print("Wind explicitly zeroed for this baseline.")
    except Exception as exc:
        print("WARNING: could not zero wind (%s). A non-zero wind would make "
              "this NOT a still-air baseline." % exc)

    print("")
    density_check = check_air_density(client, model)
    if density_check.get("tested"):
        print("P5 air density: sim %.4f vs model %.4f, %+.2f%% -> %s"
              % (density_check["measured_air_density"],
                 density_check["model_air_density"],
                 density_check["error_percent"], density_check["status"]))
    print("")

    results = run_hover_test(client, model, arguments.duration,
                             arguments.altitude, arguments.sample_hz)
    if "error" in results:
        print("ERROR: %s" % results["error"], file=sys.stderr)
        return 1

    # ---- P4: translational lift, its own arm/takeoff/land cycle ----
    p4_check = {"prediction": "P4", "tested": False,
                "error": "skipped by --skip-p4"}
    if not arguments.skip_p4:
        try:
            client.enableApiControl(True)
            client.armDisarm(True)
            client.takeoffAsync().join()
            p4_check = test_p4_translational_lift(
                client, arguments.altitude, arguments.cruise_speed,
                sample_hz=arguments.sample_hz)
        except Exception as exc:
            p4_check = {"prediction": "P4", "tested": False,
                        "error": "P4 phase raised %s" % exc}
        finally:
            try:
                client.landAsync().join()
                client.armDisarm(False)
                client.enableApiControl(False)
            except Exception:
                pass

    report = format_report(results, model, density_check, settings_summary,
                           capabilities, p4_check)
    print("")
    print(report)

    if not os.path.isdir(RESULTS_DIRECTORY):
        os.makedirs(RESULTS_DIRECTORY)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    text_path = os.path.join(RESULTS_DIRECTORY, "test_3a_hover_%s.txt" % stamp)
    with open(text_path, "w") as handle:
        handle.write(report + "\n")

    payload = dict(results)
    payload["p5_air_density"] = density_check
    payload["p4_translational_lift"] = p4_check
    payload["validation"] = model.validate_against_spec()
    payload["model_state"] = model.get_state()
    json_path = os.path.join(RESULTS_DIRECTORY, "test_3a_hover_%s.json" % stamp)
    with open(json_path, "w") as handle:
        json.dump(payload, handle, indent=2, default=str)

    print("")
    print("Report written : %s" % text_path)
    print("Samples written: %s" % json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
