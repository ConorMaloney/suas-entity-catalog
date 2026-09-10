"""
test_3b_wind.py - Test 3.b, wind response and drag identification.

TWO PHASES
    Phase 1, SCENARIOS: the briefed comparison - zero wind, headwind,
    crosswind - with station-keeping drift and model energy for each.

    Phase 2, DRAG IDENTIFICATION: the phase that carries the actual science.
    A wind sweep, reading the tilt angle the aircraft holds at each wind
    speed, then fitting the simulator's drag coefficient from that tilt and
    comparing it against a value derived independently by reading the C++
    source. This is a real test with a real way to fail.

WHY IDENTIFICATION AND NOT JUST COMPARISON
    Cosys-AirSim exposes no mass, no drag and no power through its API. But
    the physics is readable, and it is simple:

        MultiRotorPhysicsBody.hpp:190-217   builds per-axis drag factors
        FastPhysicsEngine.hpp:269-308       drag = -factor * rho * v^2

    Matching that against F = 0.5 * rho * CdA * v^2 gives CdA = 2 * factor,
    which for the generic quad works out to CdA_y = 0.01168 m2. To hold
    station in wind the aircraft must tilt until the horizontal thrust
    component balances that drag:

        tan(theta) = drag / (m * g) = factor * rho * v^2 / (m * g)

    Tilt IS readable, from kinematics_estimated.orientation. So fitting
    tan(theta) against v^2 across a sweep recovers the drag factor from
    observed behaviour, and it either matches the number read out of the
    source or it does not. Predictions P1, P2 and P3 are registered in
    PREDICTIONS.md before this runs.

WHAT THE ENERGY NUMBERS ARE WORTH
    Very little, and the test says so. At 5 m/s the thrust increase needed to
    hold station is a factor of 1.00017 - seventeen thousandths of one
    percent. No energy difference between calm and 5 m/s wind is measurable
    in this simulator, which is prediction P3 and is exactly why the briefed
    "wind reduces range" investigation cannot be run against AirSim as
    configured. An earlier version produced a clean-looking wind penalty by
    applying an invented multiplier, and reported identical adjusted range
    for all three scenarios while doing it.

USAGE
    python test_3b_wind.py
    python test_3b_wind.py --sweep 0 2 5 8 12 --axis y
    python test_3b_wind.py --wind-mode settings     # briefed restart path
    python test_3b_wind.py --scenarios-only

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
from test_3a_hover import quaternion_to_euler_deg

RESULTS_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "results")

# Pre-registered acceptance bands. Frozen in PREDICTIONS.md before any run.
PREDICTION_BANDS = {
    "P1_cda_tolerance_percent": 15.0,
    "P2_tilt_tolerance_percent": 20.0,
    "P3_energy_delta_max_percent": 0.5,
}


# ---------------------------------------------------------------------------
# Wind application
# ---------------------------------------------------------------------------
def apply_wind(client, wind_ned, mode="simset", verbose=True):
    """
    Establish a wind condition.

    mode "simset"   - client.simSetWind(), takes effect immediately.
    mode "settings" - write settings.json and wait for the operator to
                      restart the simulator. This is the briefed path and is
                      retained because wind written to settings.json is
                      present from the very first physics tick, whereas
                      simSetWind applies to an already-running world.
    """
    if mode == "simset":
        import cosysairsim as airsim
        client.simSetWind(airsim.Vector3r(float(wind_ned[0]),
                                          float(wind_ned[1]),
                                          float(wind_ned[2])))
        if verbose:
            print("  Wind set via simSetWind: (%.2f, %.2f, %.2f) NED"
                  % tuple(wind_ned))
        return True

    settings_helper.set_wind(wind_ned[0], wind_ned[1], wind_ned[2])
    print("")
    print("  Wind written to settings.json: (%.2f, %.2f, %.2f) NED"
          % tuple(wind_ned))
    print("  settings.json wind is read at simulator START.")
    print("  RESTART the simulator now, then press Enter to continue.")
    try:
        input("  > ")
    except EOFError:
        print("  (no console available; continuing without restart - this "
              "run's wind condition is NOT established)")
        return False
    return True


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------
def measure_station_keeping(client, model, wind_ned, hold_s=20.0,
                            settle_s=8.0, altitude_m=10.0, sample_hz=10.0,
                            label="", verbose=True):
    """
    Hold station in a given wind and measure what the simulator does.

    The settle period matters and is not padding. The aircraft needs time to
    reach the steady tilt that balances drag; sampling before that measures a
    transient. Settle time is counted in SIMULATION seconds like everything
    else.

    Returns a dict of measured quantities. Tilt is the headline: it is the
    quantity the drag identification is built on.
    """
    if verbose:
        print("")
        print("  Repositioning and settling (%s) ..." % (label or "scenario"))

    client.moveToPositionAsync(0.0, 0.0, -abs(altitude_m), 3.0).join()
    client.hoverAsync().join()

    sample_interval = 1.0 / sample_hz if sample_hz > 0 else 0.1

    # ---- Settle, in simulation time ----
    state = client.getMultirotorState()
    settle_start = probe.timestamp_to_seconds(state.timestamp)[0]
    while True:
        state = client.getMultirotorState()
        now = probe.timestamp_to_seconds(state.timestamp)[0]
        if now - settle_start >= settle_s:
            break
        time.sleep(sample_interval)

    # ---- Reference position captured only AFTER settling ----
    kinematics = state.kinematics_estimated
    start_position = (kinematics.position.x_val,
                      kinematics.position.y_val,
                      kinematics.position.z_val)
    model.record_drift(start_position, is_start=True)

    sim_start = probe.timestamp_to_seconds(state.timestamp)[0]
    wall_start = time.time()
    previous_sim = sim_start

    rolls = []
    pitches = []
    speeds = []
    samples = []
    energy_start_wh = model.energy_consumed_wh
    sim_elapsed = 0.0

    if verbose:
        print("  Holding %.1f s of simulation time ..." % hold_s)

    while sim_elapsed < hold_s:
        state = client.getMultirotorState()
        now_sim = probe.timestamp_to_seconds(state.timestamp)[0]
        delta = now_sim - previous_sim
        if delta <= 0.0:
            time.sleep(sample_interval)
            continue
        previous_sim = now_sim
        sim_elapsed = now_sim - sim_start

        kinematics = state.kinematics_estimated
        velocity = (kinematics.linear_velocity.x_val,
                    kinematics.linear_velocity.y_val,
                    kinematics.linear_velocity.z_val)
        position = (kinematics.position.x_val,
                    kinematics.position.y_val,
                    kinematics.position.z_val)

        model.tick(delta, ground_velocity_ned=velocity)
        model.record_drift(position)

        roll, pitch, yaw = quaternion_to_euler_deg(
            kinematics.orientation.w_val, kinematics.orientation.x_val,
            kinematics.orientation.y_val, kinematics.orientation.z_val)
        rolls.append(roll)
        pitches.append(pitch)
        speeds.append(math.sqrt(velocity[0] ** 2 + velocity[1] ** 2))

        samples.append({
            "sim_time_s": sim_elapsed,
            "roll_deg": roll,
            "pitch_deg": pitch,
            "yaw_deg": yaw,
            "position_ned": list(position),
            "velocity_ned": list(velocity),
            "drift_m": model.total_drift_m(),
            "power_w": model.last_power_w,
        })
        time.sleep(sample_interval)

    def mean(values):
        return sum(values) / len(values) if values else 0.0

    def stdev(values):
        if len(values) < 2:
            return 0.0
        average = mean(values)
        return math.sqrt(sum((v - average) ** 2 for v in values)
                         / (len(values) - 1))

    mean_roll = mean(rolls)
    mean_pitch = mean(pitches)
    # Total tilt from the vertical, combining both axes.
    mean_tilt = math.degrees(math.atan2(
        math.sqrt(math.tan(math.radians(mean_roll)) ** 2
                  + math.tan(math.radians(mean_pitch)) ** 2), 1.0))

    result = {
        "label": label,
        "wind_ned": list(wind_ned),
        "wind_speed_ms": math.sqrt(sum(w * w for w in wind_ned)),
        "sim_elapsed_s": sim_elapsed,
        "wall_elapsed_s": time.time() - wall_start,
        "sample_count": len(samples),
        "mean_roll_deg": mean_roll,
        "mean_pitch_deg": mean_pitch,
        "mean_tilt_deg": mean_tilt,
        "roll_stdev_deg": stdev(rolls),
        "pitch_stdev_deg": stdev(pitches),
        "mean_ground_speed_ms": mean(speeds),
        "max_ground_speed_ms": max(speeds) if speeds else 0.0,
        "final_drift_m": model.total_drift_m(),
        "drift_ned_m": [model.drift_x, model.drift_y, model.drift_z],
        "energy_consumed_wh": model.energy_consumed_wh - energy_start_wh,
        "mean_power_w": ((model.energy_consumed_wh - energy_start_wh) * 3600.0
                         / sim_elapsed if sim_elapsed > 0 else 0.0),
        "samples": samples,
    }

    if verbose:
        print("    mean tilt %.4f deg (roll %.4f, pitch %.4f), drift %.3f m"
              % (mean_tilt, mean_roll, mean_pitch, result["final_drift_m"]))
    return result


# ---------------------------------------------------------------------------
# Drag identification
# ---------------------------------------------------------------------------
def identify_drag(measurements, axis, mass_kg, air_density):
    """
    Fit the simulator's drag factor from measured tilt.

    Model, straight from the source reading:

        tan(theta) = (factor * rho / (m * g)) * v^2

    so a least-squares line through the origin of tan(theta) against v^2 has
    slope k = factor * rho / (m * g), giving

        factor = k * m * g / rho        and        CdA = 2 * factor

    Forcing the fit through the origin is a physical constraint, not a
    convenience: at zero wind there is no drag and therefore no tilt. A free
    intercept would happily absorb a trim bias and quietly corrupt the slope.

    Returns the fit plus diagnostics, or a dict with "error" if there is not
    enough usable data.
    """
    points = []
    for measurement in measurements:
        wind_speed = measurement["wind_speed_ms"]
        if axis == "x":
            angle_deg = measurement["mean_pitch_deg"]
        else:
            angle_deg = measurement["mean_roll_deg"]
        points.append((wind_speed, abs(math.tan(math.radians(angle_deg))),
                       angle_deg))

    usable = [(v, t) for v, t, _ in points if v > 0.0]
    if len(usable) < 2:
        return {"error": "need at least two non-zero wind points, got %d"
                         % len(usable)}

    sum_xy = sum((v * v) * t for v, t in usable)
    sum_xx = sum((v * v) ** 2 for v, t in usable)
    if sum_xx <= 0.0:
        return {"error": "degenerate fit (all wind speeds zero)"}
    slope = sum_xy / sum_xx

    # Coefficient of determination about the origin-constrained model.
    mean_t = sum(t for _, t in usable) / len(usable)
    ss_residual = sum((t - slope * v * v) ** 2 for v, t in usable)
    ss_total = sum((t - mean_t) ** 2 for _, t in usable)
    r_squared = (1.0 - ss_residual / ss_total) if ss_total > 0.0 else 0.0

    weight_n = mass_kg * battery_model.GRAVITY_MS2
    fitted_factor = slope * weight_n / air_density
    fitted_cda = 2.0 * fitted_factor

    source = battery_model.airsim_drag_factors()
    source_factor = source["drag_factor_%s" % axis]
    source_cda = source["effective_cda_%s_m2" % axis]
    error_percent = ((fitted_cda - source_cda) / source_cda * 100.0
                     if source_cda else 0.0)

    return {
        "axis": axis,
        "points": [{"wind_ms": v, "tilt_deg": a, "tan_tilt": t}
                   for v, t, a in points],
        "slope": slope,
        "r_squared": r_squared,
        "mass_kg_assumed": mass_kg,
        "air_density": air_density,
        "fitted_drag_factor": fitted_factor,
        "fitted_cda_m2": fitted_cda,
        "source_drag_factor": source_factor,
        "source_cda_m2": source_cda,
        "error_percent": error_percent,
    }


def evaluate_predictions(fit, measurements, air_density):
    """Score P1, P2 and P3 against their pre-registered bands."""
    results = []

    # ---- P1: fitted CdA matches the source-derived value ----
    if "error" in fit:
        results.append({
            "id": "P1", "status": "NOT TESTED", "detail": fit["error"]})
    else:
        tolerance = PREDICTION_BANDS["P1_cda_tolerance_percent"]
        results.append({
            "id": "P1",
            "statement": "Sim effective CdA_%s matches the C++ derivation "
                         "within +/-%.0f%%" % (fit["axis"], tolerance),
            "predicted": fit["source_cda_m2"],
            "measured": fit["fitted_cda_m2"],
            "error_percent": fit["error_percent"],
            "tolerance_percent": tolerance,
            "status": ("PASS" if abs(fit["error_percent"]) <= tolerance
                       else "FAIL"),
            "detail": "fit r2 = %.4f" % fit["r_squared"],
        })

    # ---- P2: tilt at 5 and 12 m/s ----
    tolerance = PREDICTION_BANDS["P2_tilt_tolerance_percent"]
    for target_wind in (5.0, 12.0):
        match = None
        for measurement in measurements:
            if abs(measurement["wind_speed_ms"] - target_wind) < 0.01:
                match = measurement
                break
        if match is None:
            results.append({
                "id": "P2@%.0f" % target_wind, "status": "NOT TESTED",
                "detail": "no sweep point at %.0f m/s" % target_wind})
            continue

        axis = "y" if abs(match["wind_ned"][1]) > abs(match["wind_ned"][0]) \
            else "x"
        predicted = battery_model.airsim_predicted_tilt_deg(
            target_wind, axis=axis, air_density=air_density)
        measured = abs(match["mean_roll_deg"] if axis == "y"
                       else match["mean_pitch_deg"])
        error_percent = ((measured - predicted) / predicted * 100.0
                         if predicted else 0.0)
        results.append({
            "id": "P2@%.0f" % target_wind,
            "statement": "Station-keeping tilt at %.0f m/s is %.2f deg "
                         "+/-%.0f%%" % (target_wind, predicted, tolerance),
            "predicted": predicted,
            "measured": measured,
            "error_percent": error_percent,
            "tolerance_percent": tolerance,
            "status": ("PASS" if abs(error_percent) <= tolerance else "FAIL"),
            "detail": "axis %s, stdev %.4f deg"
                      % (axis, match["roll_stdev_deg"] if axis == "y"
                         else match["pitch_stdev_deg"]),
        })

    # ---- P3: thrust/energy penalty between calm and 5 m/s is negligible ----
    calm = next((m for m in measurements
                 if m["wind_speed_ms"] < 0.01), None)
    windy = next((m for m in measurements
                  if abs(m["wind_speed_ms"] - 5.0) < 0.01), None)
    if calm is None or windy is None:
        results.append({
            "id": "P3", "status": "NOT TESTED",
            "detail": "need both a 0 m/s and a 5 m/s sweep point"})
    else:
        # Thrust to hold station is weight / cos(tilt), so the thrust penalty
        # follows directly from the measured tilt. This is a MEASURED
        # quantity, not a modeled one.
        tilt_rad = math.radians(windy["mean_tilt_deg"])
        thrust_ratio = 1.0 / math.cos(tilt_rad) if math.cos(tilt_rad) else 1.0
        delta_percent = (thrust_ratio - 1.0) * 100.0
        limit = PREDICTION_BANDS["P3_energy_delta_max_percent"]
        results.append({
            "id": "P3",
            "statement": "Thrust (hence energy) penalty from 5 m/s wind is "
                         "below %.1f%%" % limit,
            "predicted": 0.017,
            "measured": delta_percent,
            "error_percent": delta_percent,
            "tolerance_percent": limit,
            "status": "PASS" if abs(delta_percent) <= limit else "FAIL",
            "detail": "from measured tilt %.4f deg, thrust ratio %.6f"
                      % (windy["mean_tilt_deg"], thrust_ratio),
        })

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def format_report(scenarios, sweep, fit, predictions, air_density,
                  settings_summary, model, clock_ratio):
    lines = []
    lines.append("=" * 72)
    lines.append("TEST 3.B - WIND RESPONSE AND DRAG IDENTIFICATION")
    lines.append("=" * 72)
    lines.append("Run on : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")
    lines.append("  L1 = real aircraft   L2 = parametric model   L3 = simulator")
    lines.append("")
    lines.append(settings_summary)
    lines.append("")
    lines.append("  Entity               : %s [%s], record %s"
                 % (model.entity_name, model.entity_id, model.readiness))
    lines.append("  Measured clock ratio : %.2fx" % clock_ratio)
    lines.append("  Simulator air density: %.4f kg/m3" % air_density)
    lines.append("")

    if scenarios:
        lines.append("-" * 72)
        lines.append("PHASE 1 - BRIEFED SCENARIOS [L3 measured, L2 energy]")
        lines.append("-" * 72)
        header = ("  %-22s %8s %9s %9s %9s %10s"
                  % ("Scenario", "wind", "tilt deg", "drift m", "speed",
                     "energy Wh"))
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for scenario in scenarios:
            lines.append("  %-22s %8.2f %9.4f %9.3f %9.4f %10.5f"
                         % (scenario["label"][:22],
                            scenario["wind_speed_ms"],
                            scenario["mean_tilt_deg"],
                            scenario["final_drift_m"],
                            scenario["mean_ground_speed_ms"],
                            scenario["energy_consumed_wh"]))
        lines.append("")
        lines.append("  Each scenario had its wind set EXPLICITLY, including")
        lines.append("  the zero-wind case. A baseline that inherits whatever")
        lines.append("  wind the previous scenario left behind is not a")
        lines.append("  baseline, and reports calm numbers for a windy run.")
        lines.append("")

    if sweep:
        lines.append("-" * 72)
        lines.append("PHASE 2 - WIND SWEEP [L3]")
        lines.append("-" * 72)
        header = ("  %8s %10s %10s %10s %9s %9s"
                  % ("wind m/s", "roll deg", "pitch deg", "tilt deg",
                     "stdev", "drift m"))
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for point in sweep:
            lines.append("  %8.2f %10.4f %10.4f %10.4f %9.4f %9.3f"
                         % (point["wind_speed_ms"], point["mean_roll_deg"],
                            point["mean_pitch_deg"], point["mean_tilt_deg"],
                            max(point["roll_stdev_deg"],
                                point["pitch_stdev_deg"]),
                            point["final_drift_m"]))
        lines.append("")

    lines.append("-" * 72)
    lines.append("DRAG IDENTIFICATION [L3 fitted vs C++ source]")
    lines.append("-" * 72)
    if "error" in fit:
        lines.append("  NOT PERFORMED: %s" % fit["error"])
    else:
        lines.append("  Model fitted     : tan(tilt) = k * v^2, through origin")
        lines.append("  Fitted slope k   : %.8f" % fit["slope"])
        lines.append("  Fit quality r2   : %.4f" % fit["r_squared"])
        lines.append("  Mass assumed     : %.3f kg (simulator generic quad)"
                     % fit["mass_kg_assumed"])
        lines.append("")
        lines.append("  Fitted drag factor : %.6f" % fit["fitted_drag_factor"])
        lines.append("  Source drag factor : %.6f" % fit["source_drag_factor"])
        lines.append("  Fitted CdA_%s       : %.5f m2"
                     % (fit["axis"], fit["fitted_cda_m2"]))
        lines.append("  Source CdA_%s       : %.5f m2"
                     % (fit["axis"], fit["source_cda_m2"]))
        lines.append("  Error              : %+.2f%%" % fit["error_percent"])
        lines.append("")
        lines.append("  The source value was derived by reading")
        lines.append("  MultiRotorPhysicsBody.hpp and FastPhysicsEngine.hpp,")
        lines.append("  BEFORE this test ran. The fitted value comes only from")
        lines.append("  observed tilt angles. Nothing was tuned to make them")
        lines.append("  agree, and the fit had no free intercept to absorb an")
        lines.append("  error with.")
    lines.append("")

    lines.append("-" * 72)
    lines.append("PRE-REGISTERED PREDICTIONS")
    lines.append("-" * 72)
    header = ("  %-8s %12s %12s %9s  %s"
              % ("ID", "Predicted", "Measured", "Error", "Status"))
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for prediction in predictions:
        if prediction.get("status") == "NOT TESTED":
            lines.append("  %-8s %12s %12s %9s  %s"
                         % (prediction["id"], "-", "-", "-", "NOT TESTED"))
            lines.append("           %s" % prediction.get("detail", ""))
            continue
        lines.append("  %-8s %12.5f %12.5f %8.1f%%  %s"
                     % (prediction["id"], prediction["predicted"],
                        prediction["measured"], prediction["error_percent"],
                        prediction["status"]))
        if prediction.get("detail"):
            lines.append("           %s" % prediction["detail"])
    lines.append("")
    lines.append("  These bands were frozen in PREDICTIONS.md before the test")
    lines.append("  ran. They were not widened to accommodate a result.")
    lines.append("")

    lines.append("-" * 72)
    lines.append("INTERPRETATION")
    lines.append("-" * 72)
    lines.append("  The wind penalty on energy in this simulator is far too")
    lines.append("  small to measure. At 5 m/s the aircraft tilts about one")
    lines.append("  degree, and thrust rises by roughly 0.017 percent. Any")
    lines.append("  test claiming to show wind reducing range in AirSim is")
    lines.append("  reporting an artifact of its own model, not a simulated")
    lines.append("  effect.")
    lines.append("")
    lines.append("  Note also what the simulated airframe is: a 1.0 kg generic")
    lines.append("  quad, not the 0.895 kg Mavic 3. The drag identified here")
    lines.append("  is the SIMULATOR's, which is the point - it is what makes")
    lines.append("  the fitted-versus-source comparison a genuine test.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Test 3.b - wind response and drag identification.")
    parser.add_argument("--sweep", nargs="*", type=float,
                        default=[0.0, 2.0, 5.0, 8.0, 12.0],
                        help="wind speeds for the identification sweep")
    parser.add_argument("--axis", default="y", choices=["x", "y"],
                        help="sweep axis: y is an east wind producing roll, "
                             "x a north wind producing pitch "
                             "(default: %(default)s)")
    parser.add_argument("--wind-mode", default="simset",
                        choices=["simset", "settings"],
                        help="how to apply wind (default: %(default)s)")
    parser.add_argument("--hold", type=float, default=20.0,
                        help="simulation seconds per point (default: %(default)s)")
    parser.add_argument("--settle", type=float, default=8.0,
                        help="simulation seconds to settle (default: %(default)s)")
    parser.add_argument("--altitude", type=float, default=10.0)
    parser.add_argument("--sample-hz", type=float, default=10.0)
    parser.add_argument("--scenarios-only", action="store_true",
                        help="run phase 1 only, skip drag identification")
    parser.add_argument("--sweep-only", action="store_true",
                        help="run phase 2 only, skip the briefed scenarios")
    parser.add_argument("--profile", default="operational",
                        choices=["operational", "spec"])
    parser.add_argument("--entity", default=catalog.DEFAULT_ENTITY_ID,
                        help="catalog entity id (default: %(default)s). An "
                             "entity below R1 readiness is REFUSED.")
    parser.add_argument("--visual-demo", action="store_true",
                        help="run the high-wind visual ramp first, so the "
                             "wind can be SEEN acting on the aircraft before "
                             "any tilt table is trusted")
    parser.add_argument("--demo-ramp", nargs="*", type=float, default=None,
                        help="wind speeds for --visual-demo "
                             "(default: 0 5 12 20 25 30 40 60)")
    arguments = parser.parse_args(argv)

    capabilities = probe.load_capabilities()
    if capabilities is None:
        print("WARNING: no probe results found. Run "
              "probe_sim_capabilities.py first for a fully gated run.")
    elif not capabilities.get("summary", {}).get("can_test_p1_p2_tilt"):
        print("ERROR: the probe reports attitude is not readable on this "
              "install, so the drag identification cannot run.",
              file=sys.stderr)
        return 2

    try:
        settings_summary = settings_helper.format_summary()
    except settings_helper.SettingsError as exc:
        settings_summary = "settings.json unavailable: %s" % exc

    try:
        model = battery_model.BatteryModel(
            entity=arguments.entity, profile=arguments.profile,
            calibration="hover", verbose=True)
    except catalog.CatalogError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 3

    try:
        client = probe.connect()
    except RuntimeError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    # Air density from the simulator, not assumed.
    try:
        environment = client.simGetGroundTruthEnvironment()
        air_density = float(environment.air_density)
    except Exception as exc:
        print("WARNING: could not read air density (%s), using 1.225" % exc)
        air_density = 1.225

    clock = probe.probe_clock_ratio(client, sample_seconds=2.0)
    clock_ratio = clock["measured_clock_ratio"]
    print("")
    print("Measured clock ratio: %.2fx" % clock_ratio)
    if clock_ratio > 1.5:
        print("WARNING: ClockSpeed is above 1.0. FastPhysics integrates with")
        print("a fixed 3 ms WALL cadence and integrates over elapsed SIM")
        print("time, so the step is roughly 3 ms x ClockSpeed. Drag")
        print("identification should be run at ClockSpeed 1.0.")

    # ---- Optional visual demonstration, before any measurement ----
    # The measured tilts below are around one degree and invisible on screen.
    # This ramp drives the wind well past the controller's saturation point so
    # the effect can be seen directly, which is also a live proof that
    # simSetWind reaches the physics engine without a simulator restart.
    demo_results = None
    if arguments.visual_demo:
        import wind_demo
        demo_ramp = arguments.demo_ramp or list(wind_demo.DEFAULT_RAMP)
        demo_results = wind_demo.run_demo(
            client, demo_ramp, axis=arguments.axis,
            altitude_m=max(arguments.altitude, 40.0),
            hold_s=max(arguments.hold * 0.5, 8.0),
            sample_hz=arguments.sample_hz)
        print("")
        print(wind_demo.format_report(demo_results))
        print("")
        print("Visual demonstration complete. Proceeding to measurement.")

    client.enableApiControl(True)
    client.armDisarm(True)
    client.takeoffAsync().join()

    scenarios = []
    sweep = []

    try:
        # ---- Phase 1: briefed scenarios ----
        if not arguments.sweep_only:
            print("")
            print("=" * 72)
            print("PHASE 1 - BRIEFED SCENARIOS")
            print("=" * 72)
            scenario_definitions = [
                ("Zero wind", (0.0, 0.0, 0.0)),
                ("Headwind 5 m/s", (5.0, 0.0, 0.0)),
                ("Crosswind 5 m/s", (0.0, 5.0, 0.0)),
            ]
            for label, wind in scenario_definitions:
                print("")
                print("Scenario: %s" % label)
                apply_wind(client, wind, arguments.wind_mode)
                model.reset()
                model.set_wind(*wind)
                scenarios.append(measure_station_keeping(
                    client, model, wind, arguments.hold, arguments.settle,
                    arguments.altitude, arguments.sample_hz, label))

        # ---- Phase 2: drag identification sweep ----
        if not arguments.scenarios_only:
            print("")
            print("=" * 72)
            print("PHASE 2 - DRAG IDENTIFICATION SWEEP (axis %s)"
                  % arguments.axis)
            print("=" * 72)
            for wind_speed in arguments.sweep:
                if arguments.axis == "x":
                    wind = (wind_speed, 0.0, 0.0)
                else:
                    wind = (0.0, wind_speed, 0.0)
                print("")
                print("Sweep point: %.1f m/s" % wind_speed)
                apply_wind(client, wind, arguments.wind_mode)
                model.reset()
                model.set_wind(*wind)
                sweep.append(measure_station_keeping(
                    client, model, wind, arguments.hold, arguments.settle,
                    arguments.altitude, arguments.sample_hz,
                    "sweep %.1f m/s" % wind_speed))
    finally:
        print("")
        print("Clearing wind and landing ...")
        try:
            apply_wind(client, (0.0, 0.0, 0.0), "simset", verbose=False)
            client.hoverAsync().join()
            client.landAsync().join()
            client.armDisarm(False)
            client.enableApiControl(False)
        except Exception as exc:
            print("WARNING: shutdown sequence raised %s" % exc)

    if sweep:
        fit = identify_drag(sweep, arguments.axis,
                            battery_model.AIRSIM_GENERIC_QUAD["mass_kg"],
                            air_density)
        predictions = evaluate_predictions(fit, sweep, air_density)
    else:
        fit = {"error": "sweep not run (--scenarios-only)"}
        predictions = evaluate_predictions(fit, scenarios, air_density)

    report = format_report(scenarios, sweep, fit, predictions, air_density,
                           settings_summary, model, clock_ratio)
    print("")
    print(report)

    if not os.path.isdir(RESULTS_DIRECTORY):
        os.makedirs(RESULTS_DIRECTORY)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    text_path = os.path.join(RESULTS_DIRECTORY, "test_3b_wind_%s.txt" % stamp)
    with open(text_path, "w") as handle:
        handle.write(report + "\n")

    payload = {
        "visual_demo": demo_results,
        "scenarios": scenarios,
        "sweep": sweep,
        "drag_fit": fit,
        "predictions": predictions,
        "air_density": air_density,
        "clock_ratio": clock_ratio,
        "axis": arguments.axis,
        "wind_mode": arguments.wind_mode,
    }
    json_path = os.path.join(RESULTS_DIRECTORY, "test_3b_wind_%s.json" % stamp)
    with open(json_path, "w") as handle:
        json.dump(payload, handle, indent=2, default=str)

    print("")
    print("Report written : %s" % text_path)
    print("Samples written: %s" % json_path)

    failures = [p for p in predictions if p.get("status") == "FAIL"]
    if failures:
        print("")
        print("%d pre-registered prediction(s) FAILED: %s"
              % (len(failures), ", ".join(p["id"] for p in failures)))
        print("That is a result, not a defect to tune away.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
