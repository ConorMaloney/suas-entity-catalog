"""
wind_demo.py - Visual wind demonstration, and empirical proof that
simSetWind() takes effect at runtime.

WHAT YOU WILL SEE
    The aircraft is commanded to hold one position while the wind is ramped
    up in stages. At low wind it tilts into the wind and holds station - the
    tilt is small and easy to miss. Past a threshold the flight controller
    saturates, cannot generate enough horizontal thrust to balance drag, and
    the aircraft is visibly blown downwind while still holding altitude.

    That threshold is not a guess. It is computed from the firmware source.

THE PREDICTION
    simple_flight limits commanded roll and pitch in angle-level mode:

        Params.hpp:80   Axis4r max_limit = Axis4r(pi/5.5f, pi/5.5f, pi, 1.0f)

    pi/5.5 rad = 32.73 degrees, and the comment on the line above explains
    why: beyond about that angle the vertical thrust component is no longer
    enough to keep the vehicle airborne at control extremities.

    Station-keeping needs tan(theta) = drag / (m*g), with the drag factors
    read out of MultiRotorPhysicsBody.hpp. Setting theta to the 32.73 degree
    limit and solving for wind speed:

        y axis (east wind, rolls):   29.7 m/s
        x axis (north wind, pitches): 30.9 m/s

    So the aircraft should hold station cleanly up to roughly 25 m/s, and be
    unmistakably blown away by 35 m/s. Watching that transition happen at the
    predicted speed is a stronger demonstration than any number in a log.

WHY THIS DOUBLES AS A CONTROL EXPERIMENT
    settings.json wind is read only at simulator start. simSetWind() is a
    different path: it writes the same variable the settings loader seeds
    (SimModeWorldBase.cpp:76 and :137 both call physics_engine->setWind()),
    and FastPhysicsEngine reads it fresh on every physics tick. If wind
    applied through this script visibly moves an already-flying aircraft,
    that settles the question without needing to read any more C++.

USAGE
    python wind_demo.py                       # full ramp, 0 to 60 m/s
    python wind_demo.py --extreme             # single 100 m/s blast
    python wind_demo.py --axis x              # north wind, pitches instead
    python wind_demo.py --ramp 0 10 20 30 40
    python wind_demo.py --altitude 60 --hold 12

    Requires the simulator running. Wind is always restored to zero on exit,
    including on Ctrl-C.

ASCII only throughout.
"""

import argparse
import json
import math
import os
import sys
import time

import battery_model
import probe_sim_capabilities as probe
from test_3a_hover import quaternion_to_euler_deg

RESULTS_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "results")

# simple_flight angle-level limit, Params.hpp:80. This is the number that
# decides where station-keeping breaks down.
MAX_COMMANDED_TILT_DEG = math.degrees(math.pi / 5.5)

DEFAULT_RAMP = [0.0, 5.0, 12.0, 20.0, 25.0, 30.0, 40.0, 60.0]

# A stage counts as breakaway if the aircraft is being carried downwind
# faster than this. Station-keeping jitter is well under 0.5 m/s.
BREAKAWAY_SPEED_MS = 1.0


def breakaway_wind_speed(axis="y", air_density=1.225):
    """
    Wind speed at which the required station-keeping tilt reaches the
    controller's commanded-tilt limit.

    Solves tan(max_tilt) = drag_factor * rho * v^2 / (m * g) for v.
    """
    factors = battery_model.airsim_drag_factors()
    factor = factors["drag_factor_%s" % axis]
    weight_n = (battery_model.AIRSIM_GENERIC_QUAD["mass_kg"]
                * battery_model.GRAVITY_MS2)
    slope = factor * air_density / weight_n
    return math.sqrt(math.tan(math.radians(MAX_COMMANDED_TILT_DEG)) / slope)


def wind_vector(speed_ms, axis):
    """Build a NED wind vector along the chosen axis."""
    if axis == "x":
        return (float(speed_ms), 0.0, 0.0)
    return (0.0, float(speed_ms), 0.0)


def run_stage(client, speed_ms, axis, hold_s, sample_hz, air_density,
              max_displacement_m, verbose=True):
    """
    Apply one wind level and observe what happens for hold_s SIMULATION
    seconds.

    Returns a dict of measurements. Aborts the stage early if the aircraft is
    carried past max_displacement_m, so an extreme setting cannot fly it into
    the next county while the operator watches.
    """
    import cosysairsim as airsim

    wind = wind_vector(speed_ms, axis)
    client.simSetWind(airsim.Vector3r(*wind))

    predicted_tilt = battery_model.airsim_predicted_tilt_deg(
        speed_ms, axis=axis, air_density=air_density)
    predicted_state = ("HOLDS" if predicted_tilt < MAX_COMMANDED_TILT_DEG
                       else "SATURATED")

    interval = 1.0 / sample_hz if sample_hz > 0 else 0.1
    state = client.getMultirotorState()
    start_sim = probe.timestamp_to_seconds(state.timestamp)[0]
    origin = (state.kinematics_estimated.position.x_val,
              state.kinematics_estimated.position.y_val,
              state.kinematics_estimated.position.z_val)

    tilts = []
    rolls = []
    pitches = []
    displacement = 0.0
    downwind_displacement = 0.0
    sim_elapsed = 0.0
    collided = False
    aborted = False
    next_print = 0.0

    while sim_elapsed < hold_s:
        state = client.getMultirotorState()
        now = probe.timestamp_to_seconds(state.timestamp)[0]
        sim_elapsed = now - start_sim

        kinematics = state.kinematics_estimated
        position = (kinematics.position.x_val,
                    kinematics.position.y_val,
                    kinematics.position.z_val)
        roll, pitch, yaw = quaternion_to_euler_deg(
            kinematics.orientation.w_val, kinematics.orientation.x_val,
            kinematics.orientation.y_val, kinematics.orientation.z_val)

        tilt = math.degrees(math.atan2(math.sqrt(
            math.tan(math.radians(roll)) ** 2
            + math.tan(math.radians(pitch)) ** 2), 1.0))
        rolls.append(roll)
        pitches.append(pitch)
        tilts.append(tilt)

        offset = (position[0] - origin[0], position[1] - origin[1],
                  position[2] - origin[2])
        displacement = math.sqrt(offset[0] ** 2 + offset[1] ** 2)
        downwind_displacement = offset[0] if axis == "x" else offset[1]

        if getattr(state.collision, "has_collided", False):
            collided = True

        if verbose and sim_elapsed >= next_print:
            print("      t=%5.1fs  roll %+7.2f  pitch %+7.2f  tilt %6.2f  "
                  "downwind %+8.2f m  alt %6.1f m"
                  % (sim_elapsed, roll, pitch, tilt, downwind_displacement,
                     -position[2]))
            next_print += 1.0

        if abs(downwind_displacement) > max_displacement_m:
            aborted = True
            if verbose:
                print("      -- displacement cap %.0f m reached, ending stage"
                      % max_displacement_m)
            break

        time.sleep(interval)

    def mean(values):
        return sum(values) / len(values) if values else 0.0

    downwind_rate = (downwind_displacement / sim_elapsed
                     if sim_elapsed > 0 else 0.0)
    observed_state = ("BREAKAWAY" if abs(downwind_rate) > BREAKAWAY_SPEED_MS
                      else "HOLDS")

    return {
        "wind_speed_ms": speed_ms,
        "axis": axis,
        "sim_elapsed_s": sim_elapsed,
        "predicted_tilt_deg": predicted_tilt,
        "predicted_state": predicted_state,
        "mean_tilt_deg": mean(tilts),
        "max_tilt_deg": max(tilts) if tilts else 0.0,
        "mean_roll_deg": mean(rolls),
        "mean_pitch_deg": mean(pitches),
        "displacement_m": displacement,
        "downwind_displacement_m": downwind_displacement,
        "downwind_rate_ms": downwind_rate,
        "observed_state": observed_state,
        "state_matches_prediction": (
            (predicted_state == "HOLDS") == (observed_state == "HOLDS")),
        "collided": collided,
        "aborted": aborted,
    }


def run_demo(client, ramp, axis="y", altitude_m=40.0, hold_s=10.0,
             sample_hz=10.0, max_displacement_m=300.0, verbose=True):
    """Fly the ramp. Wind is always cleared before returning."""
    import cosysairsim as airsim

    air_density = 1.225
    try:
        air_density = float(
            client.simGetGroundTruthEnvironment().air_density)
    except Exception:
        pass

    threshold = breakaway_wind_speed(axis, air_density)

    if verbose:
        print("")
        print("=" * 72)
        print("WIND DEMONSTRATION")
        print("=" * 72)
        print("  Axis                    : %s (%s)"
              % (axis, "north wind, pitches" if axis == "x"
                 else "east wind, rolls"))
        print("  Air density from sim    : %.4f kg/m3" % air_density)
        print("  Controller tilt limit   : %.2f deg (Params.hpp:80, pi/5.5)"
              % MAX_COMMANDED_TILT_DEG)
        print("  PREDICTED BREAKAWAY     : %.1f m/s" % threshold)
        print("")
        print("  Below that the aircraft should hold station. Above it the")
        print("  controller saturates and the aircraft gets blown downwind.")
        print("")

    print("Preparing vehicle ...")
    client.enableApiControl(True)
    client.armDisarm(True)
    client.takeoffAsync().join()
    print("Climbing to %.0f m ..." % altitude_m)
    client.moveToPositionAsync(0.0, 0.0, -abs(altitude_m), 5.0).join()
    client.hoverAsync().join()
    time.sleep(3.0)

    stages = []
    try:
        for speed_ms in ramp:
            predicted = battery_model.airsim_predicted_tilt_deg(
                speed_ms, axis=axis, air_density=air_density)
            print("")
            print("-" * 72)
            print("  WIND %.1f m/s   (predicted tilt %.2f deg, %s)"
                  % (speed_ms, predicted,
                     "holds" if predicted < MAX_COMMANDED_TILT_DEG
                     else "SATURATED - expect it to be blown away"))
            print("-" * 72)

            # Re-establish the reference point between stages so each stage's
            # displacement is its own, not an accumulation of earlier ones.
            client.simSetWind(airsim.Vector3r(0.0, 0.0, 0.0))
            client.moveToPositionAsync(0.0, 0.0, -abs(altitude_m), 8.0).join()
            client.hoverAsync().join()
            time.sleep(2.0)

            stage = run_stage(client, speed_ms, axis, hold_s, sample_hz,
                              air_density, max_displacement_m, verbose)
            stages.append(stage)

            print("    -> mean tilt %.2f deg (predicted %.2f), carried "
                  "%.1f m downwind at %.2f m/s : %s"
                  % (stage["mean_tilt_deg"], stage["predicted_tilt_deg"],
                     stage["downwind_displacement_m"],
                     stage["downwind_rate_ms"], stage["observed_state"]))
    finally:
        print("")
        print("Clearing wind ...")
        try:
            client.simSetWind(airsim.Vector3r(0.0, 0.0, 0.0))
            time.sleep(1.0)
            print("Returning to start and landing ...")
            client.moveToPositionAsync(0.0, 0.0, -abs(altitude_m), 8.0).join()
            client.landAsync().join()
            client.armDisarm(False)
            client.enableApiControl(False)
        except Exception as exc:
            print("WARNING: shutdown sequence raised %s" % exc)

    return {"stages": stages, "axis": axis, "air_density": air_density,
            "predicted_breakaway_ms": threshold,
            "controller_tilt_limit_deg": MAX_COMMANDED_TILT_DEG}


def format_report(results):
    """Render the demo results, including where breakaway actually happened."""
    stages = results["stages"]
    lines = []
    lines.append("=" * 72)
    lines.append("WIND DEMONSTRATION - RESULTS")
    lines.append("=" * 72)
    lines.append("Run on : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("Axis   : %s" % results["axis"])
    lines.append("")
    lines.append("  Controller tilt limit : %.2f deg (simple_flight "
                 "Params.hpp:80)" % results["controller_tilt_limit_deg"])
    lines.append("  Predicted breakaway   : %.1f m/s"
                 % results["predicted_breakaway_ms"])
    lines.append("")

    header = ("  %8s %10s %10s %9s %11s %11s"
              % ("wind m/s", "pred tilt", "meas tilt", "error",
                 "downwind m", "state"))
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for stage in stages:
        predicted = stage["predicted_tilt_deg"]
        measured = stage["mean_tilt_deg"]
        error = ((measured - predicted) / predicted * 100.0
                 if predicted > 0.01 else 0.0)
        lines.append("  %8.1f %10.2f %10.2f %8.1f%% %11.1f %11s"
                     % (stage["wind_speed_ms"], predicted, measured, error,
                        stage["downwind_displacement_m"],
                        stage["observed_state"]))
    lines.append("")

    # Where did behaviour actually change?
    held = [s["wind_speed_ms"] for s in stages
            if s["observed_state"] == "HOLDS"]
    blown = [s["wind_speed_ms"] for s in stages
             if s["observed_state"] == "BREAKAWAY"]
    lines.append("-" * 72)
    lines.append("BREAKAWAY")
    lines.append("-" * 72)
    if held and blown:
        lines.append("  Highest wind still holding station : %.1f m/s"
                     % max(held))
        lines.append("  Lowest wind causing breakaway      : %.1f m/s"
                     % min(blown))
        lines.append("  Predicted transition               : %.1f m/s"
                     % results["predicted_breakaway_ms"])
        if max(held) <= results["predicted_breakaway_ms"] <= min(blown):
            lines.append("")
            lines.append("  The predicted transition falls INSIDE the observed")
            lines.append("  bracket. The controller's tilt limit, read from")
            lines.append("  Params.hpp before this ran, predicts where station")
            lines.append("  keeping fails.")
        else:
            lines.append("")
            lines.append("  The predicted transition falls OUTSIDE the observed")
            lines.append("  bracket. That is a finding: either the drag factors")
            lines.append("  or the assumed tilt limit do not describe this")
            lines.append("  build. Worth chasing rather than smoothing over.")
    elif blown:
        lines.append("  Every stage broke away. Add lower wind speeds to")
        lines.append("  bracket the transition.")
    else:
        lines.append("  No stage broke away. Add higher wind speeds - the")
        lines.append("  prediction says above %.1f m/s."
                     % results["predicted_breakaway_ms"])
    lines.append("")

    mismatches = [s for s in stages if not s["state_matches_prediction"]]
    lines.append("  Stages where hold/saturate matched prediction: %d of %d"
                 % (len(stages) - len(mismatches), len(stages)))
    lines.append("")

    lines.append("-" * 72)
    lines.append("WHAT THIS ALSO PROVES")
    lines.append("-" * 72)
    lines.append("  Every wind change above was applied with simSetWind() to")
    lines.append("  an ALREADY FLYING aircraft, with no simulator restart and")
    lines.append("  no edit to settings.json. If the aircraft visibly tilted")
    lines.append("  and was blown downwind, wind set through the API reaches")
    lines.append("  the physics engine at runtime.")
    lines.append("")
    lines.append("  settings.json wind is a different thing: it seeds the same")
    lines.append("  variable at startup (SimModeWorldBase.cpp:76) and does")
    lines.append("  need a restart to change.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Visual wind demonstration and runtime wind proof.")
    parser.add_argument("--ramp", nargs="*", type=float, default=None,
                        help="wind speeds to step through (default: "
                             "0 5 12 20 25 30 40 60)")
    parser.add_argument("--extreme", action="store_true",
                        help="single 100 m/s blast instead of the ramp")
    parser.add_argument("--axis", default="y", choices=["x", "y"],
                        help="y is an east wind (rolls), x a north wind "
                             "(pitches) (default: %(default)s)")
    parser.add_argument("--altitude", type=float, default=40.0,
                        help="demo altitude in m (default: %(default)s)")
    parser.add_argument("--hold", type=float, default=10.0,
                        help="simulation seconds per stage "
                             "(default: %(default)s)")
    parser.add_argument("--sample-hz", type=float, default=10.0)
    parser.add_argument("--max-displacement", type=float, default=300.0,
                        help="abort a stage after this much downwind travel "
                             "(default: %(default)s m)")
    parser.add_argument("--no-save", action="store_true",
                        help="do not write a report file")
    arguments = parser.parse_args(argv)

    if arguments.extreme:
        ramp = [0.0, 100.0]
    elif arguments.ramp:
        ramp = list(arguments.ramp)
    else:
        ramp = list(DEFAULT_RAMP)

    try:
        client = probe.connect()
    except RuntimeError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    try:
        results = run_demo(client, ramp, arguments.axis, arguments.altitude,
                           arguments.hold, arguments.sample_hz,
                           arguments.max_displacement)
    except KeyboardInterrupt:
        print("")
        print("Interrupted. Wind cleared by the demo's own cleanup.")
        return 130

    report = format_report(results)
    print("")
    print(report)

    if not arguments.no_save:
        if not os.path.isdir(RESULTS_DIRECTORY):
            os.makedirs(RESULTS_DIRECTORY)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        text_path = os.path.join(RESULTS_DIRECTORY,
                                 "wind_demo_%s.txt" % stamp)
        with open(text_path, "w") as handle:
            handle.write(report + "\n")
        json_path = os.path.join(RESULTS_DIRECTORY,
                                 "wind_demo_%s.json" % stamp)
        with open(json_path, "w") as handle:
            json.dump(results, handle, indent=2, default=str)
        print("")
        print("Report written : %s" % text_path)
        print("Data written   : %s" % json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
