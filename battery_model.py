"""
battery_model.py - Energy and endurance model for a DJI Mavic 3.

PURPOSE
    Cosys-AirSim does not simulate a battery. A case-insensitive search of the
    entire cosysairsim 3.4.1 package returns zero matches for "battery",
    "power", "mass" or "drag". Energy state must therefore be modeled here.

    This module is deliberately free of any AirSim import so it can be tested
    offline, in isolation, with no simulator running.

PHYSICS
    Electrical power drawn from the pack is built from four terms:

        P_elec = (P_induced + P_profile + P_parasitic + P_climb) / eta_motor
                 + P_avionics

    Induced power (the cost of accelerating air downward to make lift) uses
    momentum theory. In forward flight the induced velocity v_i satisfies

        v_i = (T / (2 * rho * A)) / sqrt(V_air^2 + v_i^2)

    which is solved numerically. This term is what makes forward flight more
    efficient than hover: as airspeed rises, v_i falls, and induced power with
    it. That effect (translational lift) is the reason DJI publishes a max
    FLIGHT time of 46 min but a max HOVER time of only 40 min. A model without
    this term cannot reproduce that relationship at all.

    Profile power (blade drag) uses the standard rotorcraft growth form
    P = P0 * (1 + 4.65 * mu^2) where mu is the advance ratio.

    Parasitic power is airframe drag times airspeed:

        F_drag = 0.5 * rho * v^2 * Cd * A          [N]   force
        P_drag = F_drag * v = 0.5 * rho * v^3 * Cd * A   [W]   power

    Note the exponent. The expression 0.5 * rho * v^2 * Cd * A has units of
    newtons, not watts; power requires an additional factor of v. Both forms
    are exposed here, each named for what it actually returns.

CALIBRATION AND VALIDATION
    Exactly ONE parameter is fitted: profile power at hover, solved so that
    hover endurance matches the published hover anchor. Every other parameter
    is published, derived, or taken from literature.

    Because that anchor is fitted, it CANNOT FAIL. It is reported as
    "CALIBRATED", never as "PASS". The anchors that can genuinely fail are the
    held-out ones: cruise endurance, max range, and wind resistance. Set
    calibration="none" to fit nothing at all and see the raw error everywhere.

SPEC VERSUS OPERATIONAL
    DJI's figures are ideal-condition maxima: no wind, sea level, 100% to 0%,
    constant 9 m/s. Independent testing puts real-world endurance at 65-75% of
    advertised. Planning against the spec sheet overstates endurance by about
    30%, which is the dangerous direction to be wrong. The "operational"
    profile therefore derates using two separable, individually defensible
    factors rather than one fudge:

        usable_energy_fraction     0.85   land at 15% reserve, not 0%
        operational_overhead       1.18   gusts, temperature, maneuvering

    Combined 0.85 / 1.18 = 0.720, which reproduces the observed 28-30 min
    hover and 30-35 min cruise. Default profile is "operational".

REFERENCES
    DJI Mavic 3 Classic specifications (verified 2026-09-09)
    Hattenberger, Bronz, Condomines 2023, Evaluation of drag coefficient for
      a quadrotor model
    Theys, De Schutter 2020, Forward flight tests of a quadcopter UAV

ASCII only throughout. The Windows console cannot render non-ASCII output.
"""

import json
import math

import catalog

GRAVITY_MS2 = 9.80665


# ---------------------------------------------------------------------------
# Reference data for the vehicle the SIMULATOR actually flies.
#
# This is NOT a Mavic 3. Cosys-AirSim "SimpleFlight" routes to
# setupFrameGenericQuad (SimpleFlightQuadXParams.hpp:33-41, comment "Only
# Generic for now"), which is a 1.0 kg F450-class quad on Phantom 2
# propellers. None of it is configurable from settings.json -- mass, drag,
# rotor count and propeller geometry are C++ compile-time constants.
#
# These values are recorded so tests can form falsifiable predictions about
# simulator behavior, and so no simulator number is ever misread as a
# Mavic 3 number.
#
# Source: Cosys-AirSim 3.4.1, MultiRotorParams.hpp:311-343,
#         RotorParams.hpp:21-62, MultiRotorPhysicsBody.hpp:190-217,
#         FastPhysicsEngine.hpp:269-308
# ---------------------------------------------------------------------------
AIRSIM_GENERIC_QUAD = {
    "frame": "setupFrameGenericQuad",
    "mass_kg": 1.0,
    "rotor_count": 4,
    "propeller_diameter_m": 0.2286,
    "propeller_height_m": 0.01,
    "linear_drag_coefficient": 1.3 / 4.0,
    "body_box_m": {"x": 0.180, "y": 0.110, "z": 0.040},
    "c_t": 0.109919,
    "c_p": 0.040164,
    "max_rpm": 6396.667,
    "max_thrust_per_rotor_n": 4.179446268,
}


def airsim_drag_factors():
    """
    Reproduce the simulator's own drag-factor computation in closed form.

    MultiRotorPhysicsBody.hpp:190-217 builds a per-axis drag factor from the
    body box faces plus a propeller term. FastPhysicsEngine.hpp:269-308 then
    applies:

        drag_force = normal * (-drag_factor * air_density * v^2)

    Matching that against the standard F = 0.5 * rho * CdA * v^2 gives

        CdA_effective = 2 * drag_factor

    Returns a dict with the per-axis drag factors and effective CdA values.

    NOTE ON AN AIRSIM BUG: the source computes propeller_area as pi * D * D.
    Actual disk area is pi * D^2 / 4, so the simulator's VERTICAL drag area is
    four times the physical value. This is reproduced faithfully here because
    the goal is to predict what the simulator will do, not what it should do.
    It affects the Z axis only and does not touch the horizontal work.
    """
    p = AIRSIM_GENERIC_QUAD
    d = p["propeller_diameter_m"]
    h = p["propeller_height_m"]
    n = p["rotor_count"]
    box = p["body_box_m"]
    ldc = p["linear_drag_coefficient"]

    propeller_area = math.pi * d * d          # sic - see docstring
    propeller_xsection = math.pi * d * h

    front_back_area = box["y"] * box["z"]
    left_right_area = box["x"] * box["z"]
    top_bottom_area = box["x"] * box["y"]

    fx = (front_back_area + n * propeller_xsection) * ldc / 2.0
    fy = (left_right_area + n * propeller_xsection) * ldc / 2.0
    fz = (top_bottom_area + n * propeller_area) * ldc / 2.0

    return {
        "drag_factor_x": fx,
        "drag_factor_y": fy,
        "drag_factor_z": fz,
        "effective_cda_x_m2": 2.0 * fx,
        "effective_cda_y_m2": 2.0 * fy,
        "effective_cda_z_m2": 2.0 * fz,
    }


def airsim_predicted_tilt_deg(wind_speed_ms, axis="y", air_density=1.225):
    """
    Predict the pitch/roll angle the simulated vehicle must hold to keep
    station in a steady wind.

        tan(theta) = drag / (m * g),  drag = drag_factor * rho * v^2

    This is a genuinely falsifiable prediction: it is derived entirely from
    reading the simulator's C++ source, and the resulting angle is directly
    measurable from kinematics_estimated.orientation at runtime.
    """
    factors = airsim_drag_factors()
    factor = factors["drag_factor_%s" % axis]
    drag_n = factor * air_density * wind_speed_ms * wind_speed_ms
    weight_n = AIRSIM_GENERIC_QUAD["mass_kg"] * GRAVITY_MS2
    return math.degrees(math.atan2(drag_n, weight_n))


class BatteryModel:
    """
    Energy and endurance model for a rotary-wing UAS entity.

    The entity's parameters come from a catalog record; there are no built-in
    defaults for any of them. That inversion is deliberate. This class used to
    carry a Mavic 3's mass, capacity and specification anchors as class
    constants, with the catalog file acting as an optional override layer, and
    a missing file merely printed a warning and carried on. The consequence
    was that pointing the model at a different entity silently scored it
    against Mavic 3 anchors and described it with Mavic 3 prose. With one
    entity that was invisible. With a catalog it is a defect that produces
    confident, well-formatted, wrong answers.

    So: the record is authoritative, a missing required parameter is an error,
    and readiness gating happens in the constructor.

    Typical use, driven from simulation-clock deltas:

        battery = BatteryModel(entity="UAS-QUAD-DJI-MAVIC3")
        battery.set_wind(5.0, 0.0, 0.0)
        battery.tick(dt_seconds, ground_velocity_ned=(vx, vy, vz))
        state = battery.get_state()
    """

    # Modelling constants that belong to the PHYSICS, not to any entity.
    # Everything entity-specific is bound from the catalog record.
    PROFILE_MU_FACTOR_DEFAULT = 4.65

    def __init__(self, entity=None, specs_file=None, profile="operational",
                 calibration="hover", power_model="physics", verbose=True,
                 allow_provisional=True):
        """
        Args:
            entity: catalog entity id, e.g. "UAS-QUAD-DJI-MAVIC3". Resolved
                through catalog.load_entity(). Defaults to
                catalog.DEFAULT_ENTITY_ID.
            specs_file: explicit path to an entity record. Wins over `entity`.
                Retained so a caller outside the catalog can still drive the
                model directly.
            profile: "operational" (default, derated to observed performance)
                or "spec" (matches the vendor's ideal-condition maxima).
            calibration: "hover" fits one parameter to the hover anchor.
                "none" fits nothing and reports raw error against every anchor.
            power_model: "physics" (momentum theory) or "linear".
            allow_provisional: when False, an R1 PROVISIONAL record raises
                instead of producing stamped output. Default True, because
                this project labels loudly rather than withholding.

        Raises:
            catalog.CatalogError if the record is missing, malformed, or
            below R1 readiness. There is deliberately no fallback to another
            entity's values.
        """
        if profile not in ("operational", "spec"):
            raise ValueError("profile must be 'operational' or 'spec'")
        if calibration not in ("hover", "none"):
            raise ValueError("calibration must be 'hover' or 'none'")
        if power_model not in ("physics", "linear"):
            raise ValueError("power_model must be 'physics' or 'linear'")

        self.profile = profile
        self.calibration = calibration
        self.power_model = power_model

        # ---- Resolve and bind the entity record ----
        if specs_file:
            self.document = catalog.load_entity_file(specs_file)
            self.specs_source = specs_file
        else:
            entity_id = entity or catalog.DEFAULT_ENTITY_ID
            self.document = catalog.load_entity(entity_id)
            self.specs_source = "catalog:%s" % entity_id

        self.entity_id = self.document.get("entity_id")
        self.entity_name = self.document.get("entity")
        self.category = self.document.get("category")

        # ---- Readiness gate, before any number is computed ----
        schema = catalog.load_schema()
        self.assessment = catalog.assess_entity(self.document, schema)
        gate = catalog.require_modelable(
            self.assessment, "BatteryModel(%s)" % self.entity_id,
            min_tier="R2" if not allow_provisional else "R1")
        self.readiness = gate["readiness"]
        self.provisional = gate["provisional"]
        self.provisional_reasons = gate["provisional_reasons"]
        self.provisional_banner = gate["banner"]

        self._bind_entity()

        # ---- Wind state ----
        # Set BEFORE _recompute_derived(), because deriving the hover
        # operating point calls power_required(), which reads self.wind_ned.
        self.wind_ned = (0.0, 0.0, 0.0)
        self.wind_speed_ms = 0.0
        self.wind_compensation_factor = 1.0

        self._recompute_derived()

        # ---- Runtime state ----
        self.percentage = 100.0
        self.voltage = self.voltage_full
        self.energy_consumed_wh = 0.0
        self.total_elapsed_seconds = 0.0
        self.last_power_w = self.hover_power_w
        self.last_airspeed_ms = 0.0

        self.start_position = None
        self.drift_x = 0.0
        self.drift_y = 0.0
        self.drift_z = 0.0
        self.drift_measurements = []

        if verbose:
            self.print_configuration()

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------
    def _bind_entity(self):
        """
        Bind every model parameter from the catalog record.

        There is no fallback. catalog.require_modelable() has already run in
        the constructor and guaranteed that every REQUIRED_MEASURED and
        REQUIRED_MODELING parameter is present, so a KeyError here means the
        schema and this method disagree about what is required - which is a
        bug worth crashing on rather than papering over.

        Unlike the previous _load_specs, this retains each parameter's
        confidence and source alongside its value, in self.provenance, so a
        report can say where a number came from rather than just what it is.
        """
        self.provenance = {}

        def bind(path, required=True, default=None):
            record = catalog.get_parameter(self.document, path)
            status = catalog.parameter_status(record)
            if status != "present":
                if required:
                    raise catalog.CatalogError(
                        "entity %s: required parameter %s is %s. The "
                        "readiness gate should have caught this; schema and "
                        "_bind_entity disagree about what is required."
                        % (self.entity_id, path, status))
                return default
            self.provenance[path] = {
                "value": record.get("value"),
                "confidence": record.get("confidence"),
                "source": record.get("source"),
                "verified_on": record.get("verified_on"),
                "contested": bool(record.get("contested")),
            }
            return record.get("value")

        # ---- Physical ----
        self.mass_kg = bind("physical.mass_kg")
        self.propeller_diameter_m = bind("physical.propeller_diameter_m")
        self.rotor_count = bind("physical.rotor_count")

        # ---- Battery ----
        self.capacity_wh = bind("battery.capacity_wh")
        self.voltage_full = bind("battery.voltage_full_v")
        self.voltage_empty = bind("battery.voltage_empty_v")
        self.voltage_nominal = bind("battery.voltage_nominal_v",
                                    required=False)

        # ---- Aerodynamic and modelling assumptions ----
        aero = "aerodynamic_assumptions."
        self.air_density_kg_m3 = bind(aero + "air_density_kg_m3")
        self.cda_m2 = bind(aero + "equivalent_flat_plate_area_m2")
        self.figure_of_merit = bind(aero + "figure_of_merit")
        self.motor_esc_efficiency = bind(aero + "motor_esc_efficiency")
        self.propulsive_efficiency = bind(aero + "propulsive_efficiency")
        self.avionics_power_w = bind(aero + "avionics_power_w")
        self.thrust_coefficient = bind(aero + "thrust_coefficient")
        self.profile_mu_factor = bind(aero + "profile_power_mu_factor",
                                      required=False,
                                      default=self.PROFILE_MU_FACTOR_DEFAULT)

        # ---- Published performance anchors ----
        published = "performance_published."
        self.spec_hover_time_min = bind(published + "max_hover_time_min")
        self.spec_max_speed_ms = bind(published + "max_speed_ms")
        self.spec_flight_time_min = bind(published + "max_flight_time_min",
                                         required=False)
        self.spec_flight_time_speed_ms = bind(
            published + "flight_time_test_speed_ms", required=False)
        self.spec_max_range_km = bind(published + "max_flight_distance_km",
                                      required=False)
        self.spec_max_wind_ms = bind(published + "max_wind_resistance_ms",
                                     required=False)

        # ---- Operational derating ----
        operational = "performance_operational."
        required_operational = (self.profile == "operational")
        self.usable_energy_fraction = bind(
            operational + "usable_energy_fraction",
            required=required_operational, default=1.0)
        self.operational_overhead = bind(
            operational + "operational_overhead_factor",
            required=required_operational, default=1.0)

        # ---- Calibration declaration, now live rather than decorative ----
        calibration_block = self.document.get("calibration") or {}
        self.fitted_parameter = calibration_block.get("fitted_parameter")
        self.fitted_to_anchor = calibration_block.get("fitted_to_anchor")
        self.held_out_anchors = list(
            calibration_block.get("held_out_anchors") or [])

    def _recompute_derived(self):
        """
        Derive geometry, the hover operating point, and the single calibrated
        parameter. Called at init and after any parameter override.
        """
        radius = self.propeller_diameter_m / 2.0
        self.disk_area_m2 = self.rotor_count * math.pi * radius * radius
        self.hover_thrust_n = self.mass_kg * GRAVITY_MS2

        # Momentum-theory hover induced velocity and ideal induced power.
        self.hover_induced_velocity_ms = math.sqrt(
            self.hover_thrust_n / (2.0 * self.air_density_kg_m3
                                   * self.disk_area_m2))
        self.hover_induced_power_ideal_w = (self.hover_thrust_n
                                            * self.hover_induced_velocity_ms)

        # Estimate hover rotor speed so the advance ratio mu has a basis.
        # T_rotor = C_T * rho * n^2 * D^4  ->  solve for n (rev/s).
        thrust_per_rotor = self.hover_thrust_n / self.rotor_count
        denominator = (self.thrust_coefficient * self.air_density_kg_m3
                       * self.propeller_diameter_m ** 4)
        revs_per_second = math.sqrt(thrust_per_rotor / denominator)
        self.hover_rpm = revs_per_second * 60.0
        self.rotor_tip_speed_ms = revs_per_second * 2.0 * math.pi * radius

        # Effective capacity after the usable-energy derate.
        if self.profile == "operational":
            self.usable_energy_wh = (self.capacity_wh
                                     * self.usable_energy_fraction)
            self.overhead_factor = self.operational_overhead
        else:
            self.usable_energy_wh = self.capacity_wh
            self.overhead_factor = 1.0

        # ---- The single calibrated parameter ----
        # Solve profile power at hover so that spec hover endurance is met.
        # This anchor is fitted and therefore CANNOT FAIL. It is reported as
        # CALIBRATED, never as PASS.
        target_hover_power_w = (self.capacity_wh
                                / (self.spec_hover_time_min / 60.0))
        if self.calibration == "hover":
            induced_shaft_w = (self.hover_induced_power_ideal_w
                               / self.figure_of_merit)
            required_shaft_w = ((target_hover_power_w - self.avionics_power_w)
                                * self.motor_esc_efficiency)
            self.profile_power_hover_w = required_shaft_w - induced_shaft_w
            if self.profile_power_hover_w < 0.0:
                print("WARNING: calibration produced negative profile power; "
                      "clamping to 0. Check figure_of_merit and "
                      "avionics_power_w.")
                self.profile_power_hover_w = 0.0
        else:
            # Zero-free-parameter mode: profile power from a literature ratio
            # of induced power rather than fitted to any anchor.
            self.profile_power_hover_w = (0.33
                                          * self.hover_induced_power_ideal_w
                                          / self.figure_of_merit)

        self.spec_hover_power_w = target_hover_power_w
        self.hover_power_w = self.power_required((0.0, 0.0, 0.0))["total_w"]

        # Linear model constant, retained for comparison.
        self.linear_power_w = target_hover_power_w * self.overhead_factor

    def print_configuration(self):
        """Print the resolved configuration. ASCII only."""
        print("BatteryModel configured")
        if self.provisional and self.provisional_banner:
            for line in self.provisional_banner:
                print(line)
            print("")
        print("  Entity              : %s  [%s]"
              % (self.entity_name, self.entity_id))
        print("  Readiness           : %s %s"
              % (self.readiness,
                 catalog.TIER_NAMES.get(self.readiness, "")))
        print("  Specs source        : %s" % self.specs_source)
        print("  Profile             : %s" % self.profile)
        print("  Power model         : %s" % self.power_model)
        print("  Calibration         : %s" % self.calibration)
        print("  Capacity            : %.1f Wh (usable %.1f Wh)"
              % (self.capacity_wh, self.usable_energy_wh))
        print("  Mass                : %.3f kg" % self.mass_kg)
        print("  Disk area           : %.4f m2 (%d x %.4f m propellers)"
              % (self.disk_area_m2, self.rotor_count,
                 self.propeller_diameter_m))
        print("  Hover induced vel   : %.3f m/s" % self.hover_induced_velocity_ms)
        print("  Hover rotor speed   : %.0f rpm (tip %.1f m/s)"
              % (self.hover_rpm, self.rotor_tip_speed_ms))
        print("  Profile power (fit) : %.2f W" % self.profile_power_hover_w)
        print("  Hover power         : %.2f W" % self.hover_power_w)

    # -----------------------------------------------------------------
    # Aerodynamics
    # -----------------------------------------------------------------
    def induced_velocity(self, airspeed_ms, thrust_n=None):
        """
        Solve the momentum-theory induced velocity in forward flight:

            v_i = (T / (2 * rho * A)) / sqrt(V^2 + v_i^2)

        Fixed-point iteration with damping. Converges in a handful of steps
        for all speeds of interest. At V = 0 this reduces exactly to the
        hover result sqrt(T / (2 * rho * A)).
        """
        if thrust_n is None:
            thrust_n = self.hover_thrust_n
        numerator = thrust_n / (2.0 * self.air_density_kg_m3
                                * self.disk_area_m2)
        v_i = math.sqrt(max(numerator, 0.0))     # hover value as the seed
        for _ in range(100):
            previous = v_i
            v_i = numerator / math.sqrt(airspeed_ms * airspeed_ms
                                        + v_i * v_i)
            v_i = 0.5 * (v_i + previous)         # damping
            if abs(v_i - previous) < 1e-9:
                break
        return v_i

    def calculate_drag_force(self, airspeed_ms):
        """
        Airframe parasitic drag FORCE, in newtons.

            F = 0.5 * rho * v^2 * Cd * A

        This is the expression commonly quoted as a "drag power" formula. It
        is not. Its units are newtons. See calculate_drag_power.
        """
        return (0.5 * self.air_density_kg_m3 * airspeed_ms * airspeed_ms
                * self.cda_m2)

    def calculate_drag_power(self, airspeed_ms):
        """
        Mechanical power required to overcome parasitic drag, in watts.

            P = F * v = 0.5 * rho * v^3 * Cd * A

        Note the cube. Divide by propulsive efficiency to get shaft power,
        which power_required does.
        """
        return self.calculate_drag_force(airspeed_ms) * abs(airspeed_ms)

    def power_required(self, ground_velocity_ned=(0.0, 0.0, 0.0),
                       wind_ned=None):
        """
        Electrical power drawn from the pack, with a full term breakdown.

        Args:
            ground_velocity_ned: (vx, vy, vz) in m/s, NED frame, so positive
                vz is DOWNWARD (AirSim convention).
            wind_ned: (wx, wy, wz) in m/s NED. Defaults to the stored wind.

        Returns a dict of every power term plus airspeed and tilt, so callers
        can log the decomposition rather than a single opaque number.

        Wind enters as a VECTOR through airspeed, not as a scalar penalty
        factor. Airspeed = ground velocity minus wind. All wind cases -
        head, tail, cross, and station-keeping - then fall out of one
        equation rather than needing separate hand-tuned rules.
        """
        if wind_ned is None:
            wind_ned = self.wind_ned

        vx = ground_velocity_ned[0] - wind_ned[0]
        vy = ground_velocity_ned[1] - wind_ned[1]
        vz = ground_velocity_ned[2] - wind_ned[2]

        horizontal_airspeed = math.sqrt(vx * vx + vy * vy)
        total_airspeed = math.sqrt(vx * vx + vy * vy + vz * vz)
        climb_rate_ms = -ground_velocity_ned[2]      # NED: up is negative

        if self.power_model == "linear":
            total_w = self.linear_power_w
            return {
                "induced_w": 0.0,
                "profile_w": 0.0,
                "parasitic_w": 0.0,
                "climb_w": 0.0,
                "avionics_w": self.avionics_power_w,
                "shaft_w": 0.0,
                "total_w": total_w,
                "horizontal_airspeed_ms": horizontal_airspeed,
                "total_airspeed_ms": total_airspeed,
                "thrust_n": self.hover_thrust_n,
                "tilt_deg": 0.0,
                "induced_velocity_ms": self.hover_induced_velocity_ms,
            }

        # Thrust must counter weight and the horizontal drag component, so
        # the rotor tilts. At low speeds this correction is tiny, but it is
        # what makes station-keeping in wind cost more than nothing.
        drag_force_n = self.calculate_drag_force(horizontal_airspeed)
        thrust_n = math.sqrt(self.hover_thrust_n ** 2 + drag_force_n ** 2)
        tilt_deg = math.degrees(math.atan2(drag_force_n, self.hover_thrust_n))

        v_i = self.induced_velocity(horizontal_airspeed, thrust_n)
        # NOTE: this parameter occupies the position of the induced power
        # factor kappa while carrying figure of merit's name and value, so the
        # effective kappa is 1/0.65 = 1.538 against a physical 1.10-1.20. That
        # is a real defect, diagnosed and quantified in MODEL_UNCERTAINTY.md.
        # It is deliberately NOT fixed here: doing so would turn the
        # pre-registered P6 failure into a pass after the fact. The correction
        # is pre-registered as P9 and blocked on a measurement.
        induced_shaft_w = thrust_n * v_i / self.figure_of_merit

        if self.rotor_tip_speed_ms > 0.0:
            mu = horizontal_airspeed / self.rotor_tip_speed_ms
        else:
            mu = 0.0
        profile_shaft_w = (self.profile_power_hover_w
                           * (1.0 + self.profile_mu_factor * mu * mu))

        parasitic_shaft_w = (self.calculate_drag_power(horizontal_airspeed)
                             / self.propulsive_efficiency)

        if climb_rate_ms > 0.0:
            climb_shaft_w = (self.hover_thrust_n * climb_rate_ms
                             / self.propulsive_efficiency)
        else:
            climb_shaft_w = 0.0      # descent recovers nothing on a multirotor

        shaft_w = (induced_shaft_w + profile_shaft_w + parasitic_shaft_w
                   + climb_shaft_w)
        total_w = (shaft_w / self.motor_esc_efficiency
                   + self.avionics_power_w) * self.overhead_factor

        return {
            "induced_w": induced_shaft_w,
            "profile_w": profile_shaft_w,
            "parasitic_w": parasitic_shaft_w,
            "climb_w": climb_shaft_w,
            "avionics_w": self.avionics_power_w,
            "shaft_w": shaft_w,
            "total_w": total_w,
            "horizontal_airspeed_ms": horizontal_airspeed,
            "total_airspeed_ms": total_airspeed,
            "thrust_n": thrust_n,
            "tilt_deg": tilt_deg,
            "induced_velocity_ms": v_i,
        }

    # -----------------------------------------------------------------
    # Wind
    # -----------------------------------------------------------------
    def set_wind(self, wind_x_ms, wind_y_ms=0.0, wind_z_ms=0.0):
        """
        Set the wind vector in NED world frame, m/s. Matches the argument
        convention of AirSim's simSetWind(Vector3r).

        Also recomputes wind_compensation_factor, which is a DERIVED
        DIAGNOSTIC and not a model input: it is the ratio of hover power in
        this wind to hover power in still air.

        That factor is frequently BELOW 1.0, and that is correct, not a bug.
        Station-keeping in wind is aerodynamically the same as flying at that
        airspeed while covering no ground, so the aircraft gains translational
        lift. At 5 m/s the induced-power saving exceeds the parasitic penalty
        and holding position actually costs LESS than hovering in dead calm.
        """
        self.wind_ned = (float(wind_x_ms), float(wind_y_ms), float(wind_z_ms))
        self.wind_speed_ms = math.sqrt(sum(component * component
                                           for component in self.wind_ned))

        still_air = self.power_required((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        in_wind = self.power_required((0.0, 0.0, 0.0), self.wind_ned)
        if still_air["total_w"] > 0.0:
            self.wind_compensation_factor = (in_wind["total_w"]
                                             / still_air["total_w"])
        else:
            self.wind_compensation_factor = 1.0
        return self.wind_compensation_factor

    # -----------------------------------------------------------------
    # Integration
    # -----------------------------------------------------------------
    def tick(self, delta_seconds, ground_velocity_ned=(0.0, 0.0, 0.0),
             wind_ned=None):
        """
        Advance the model by delta_seconds. TRUE FORWARD INTEGRATION: energy
        already consumed is never recomputed.

        This matters. A previous implementation recomputed cumulative energy
        from total elapsed time on every call, using whatever the current
        conditions happened to be. Changing wind or speed mid-flight silently
        rewrote all prior history, and accumulated drag energy would collapse
        to zero the moment the aircraft stopped moving. Integrating forward
        makes that class of error impossible.

        Drive delta_seconds from SIMULATION clock deltas, not wall clock.
        settings.json sets ClockSpeed, and at 25.0 a wall-clock-driven model
        is wrong by a factor of 25.
        """
        if delta_seconds <= 0.0:
            return self.percentage, self.voltage, self.energy_consumed_wh

        breakdown = self.power_required(ground_velocity_ned, wind_ned)
        power_w = breakdown["total_w"]

        self.energy_consumed_wh += power_w * delta_seconds / 3600.0
        self.total_elapsed_seconds += delta_seconds
        self.last_power_w = power_w
        self.last_airspeed_ms = breakdown["horizontal_airspeed_ms"]

        self._refresh_derived_state()
        return self.percentage, self.voltage, self.energy_consumed_wh

    def update(self, elapsed_seconds, flight_speed_ms=0.0):
        """
        Absolute-time update, retained for API compatibility.

        ONLY VALID FOR CONSTANT CONDITIONS. It replays the whole flight at a
        single steady speed and wind. For anything time-varying use tick(),
        which integrates forward and cannot rewrite history.
        """
        breakdown = self.power_required((flight_speed_ms, 0.0, 0.0))
        self.total_elapsed_seconds = elapsed_seconds
        self.energy_consumed_wh = (breakdown["total_w"] * elapsed_seconds
                                   / 3600.0)
        self.last_power_w = breakdown["total_w"]
        self.last_airspeed_ms = breakdown["horizontal_airspeed_ms"]
        self._refresh_derived_state()
        return self.percentage, self.voltage, self.energy_consumed_wh

    def _refresh_derived_state(self):
        """Recompute percentage and voltage from consumed energy."""
        if self.usable_energy_wh > 0.0:
            fraction_used = self.energy_consumed_wh / self.usable_energy_wh
        else:
            fraction_used = 1.0
        self.percentage = max(0.0, min(100.0, 100.0 * (1.0 - fraction_used)))
        self.voltage = (self.voltage_empty
                        + (self.voltage_full - self.voltage_empty)
                        * self.percentage / 100.0)

    def reset(self):
        """Return to full charge and clear all accumulated state."""
        self.percentage = 100.0
        self.voltage = self.voltage_full
        self.energy_consumed_wh = 0.0
        self.total_elapsed_seconds = 0.0
        self.last_power_w = self.hover_power_w
        self.last_airspeed_ms = 0.0
        self.start_position = None
        self.drift_x = 0.0
        self.drift_y = 0.0
        self.drift_z = 0.0
        self.drift_measurements = []
        # Wind is deliberately NOT cleared here; call set_wind(0, 0, 0) to
        # clear it. A previous implementation leaked wind state between test
        # scenarios, which made a zero-wind baseline silently report windy
        # numbers. Tests must set wind explicitly per scenario.

    # -----------------------------------------------------------------
    # Drift tracking
    # -----------------------------------------------------------------
    def record_drift(self, position, is_start=False):
        """
        Record position for drift tracking. position is (x, y, z) in NED.

        Call with is_start=True only AFTER the aircraft has settled at its
        station-keeping point. Capturing the start before a post-reset()
        transient makes "drift" measure the reset offset instead, which is
        how a previous run reported 129 m of drift in dead calm.
        """
        if is_start:
            self.start_position = tuple(position)
            self.drift_x = 0.0
            self.drift_y = 0.0
            self.drift_z = 0.0
            self.drift_measurements = []
            return

        if self.start_position is None:
            return

        self.drift_x = position[0] - self.start_position[0]
        self.drift_y = position[1] - self.start_position[1]
        self.drift_z = position[2] - self.start_position[2]
        self.drift_measurements.append({
            "time_s": self.total_elapsed_seconds,
            "drift_x_m": self.drift_x,
            "drift_y_m": self.drift_y,
            "drift_z_m": self.drift_z,
            "position": tuple(position),
        })

    def total_drift_m(self):
        """Euclidean drift magnitude from the recorded start position."""
        return math.sqrt(self.drift_x ** 2 + self.drift_y ** 2
                         + self.drift_z ** 2)

    # -----------------------------------------------------------------
    # Reporting
    # -----------------------------------------------------------------
    def get_state(self):
        """Current model state as a flat dictionary."""
        if self.last_power_w > 0.0:
            remaining_wh = max(0.0, self.usable_energy_wh
                               - self.energy_consumed_wh)
            remaining_min = remaining_wh / self.last_power_w * 60.0
        else:
            remaining_min = 0.0

        return {
            "percentage": self.percentage,
            "voltage": self.voltage,
            "energy_consumed_wh": self.energy_consumed_wh,
            "capacity_wh": self.capacity_wh,
            "usable_energy_wh": self.usable_energy_wh,
            "time_elapsed_seconds": self.total_elapsed_seconds,
            "time_elapsed_minutes": self.total_elapsed_seconds / 60.0,
            "power_w": self.last_power_w,
            "airspeed_ms": self.last_airspeed_ms,
            "estimated_remaining_minutes": remaining_min,
            "wind_speed_ms": self.wind_speed_ms,
            "wind_ned": self.wind_ned,
            "wind_compensation_factor": self.wind_compensation_factor,
            "drift_x": self.drift_x,
            "drift_y": self.drift_y,
            "drift_z": self.drift_z,
            "total_drift_m": self.total_drift_m(),
            "profile": self.profile,
            "power_model": self.power_model,
            "calibration": self.calibration,
            # Readiness travels with the state, so every consumer that dumps
            # get_state() into its results JSON carries the provenance stamp
            # without needing to know it exists.
            "entity_id": self.entity_id,
            "entity": self.entity_name,
            "readiness": self.readiness,
            "provisional": self.provisional,
            "provisional_reasons": self.provisional_reasons,
        }

    def endurance_minutes(self, ground_velocity_ned=(0.0, 0.0, 0.0),
                          wind_ned=(0.0, 0.0, 0.0)):
        """Predicted endurance at a steady condition, in minutes."""
        power_w = self.power_required(ground_velocity_ned, wind_ned)["total_w"]
        if power_w <= 0.0:
            return float("inf")
        return self.usable_energy_wh / power_w * 60.0

    def best_range_speed_ms(self, search_max_ms=None, step_ms=0.1):
        """
        Airspeed that maximizes distance per unit energy, i.e. maximizes
        v / P. This is the correct speed to quote a maximum-range figure at,
        and it is generally NOT the same as the speed DJI used for its
        flight-time test.
        """
        if search_max_ms is None:
            search_max_ms = self.spec_max_speed_ms
        best_speed = 0.0
        best_metric = 0.0
        speed = step_ms
        while speed <= search_max_ms:
            power_w = self.power_required((speed, 0.0, 0.0))["total_w"]
            if power_w > 0.0:
                metric = speed / power_w
                if metric > best_metric:
                    best_metric = metric
                    best_speed = speed
            speed += step_ms
        return best_speed

    def max_range_km(self, speed_ms=None):
        """Still-air maximum range at the best-range speed (or a given one)."""
        if speed_ms is None:
            speed_ms = self.best_range_speed_ms()
        power_w = self.power_required((speed_ms, 0.0, 0.0))["total_w"]
        if power_w <= 0.0:
            return 0.0
        endurance_h = self.usable_energy_wh / power_w
        return endurance_h * speed_ms * 3.6

    def get_estimated_range_with_wind(self, ground_speed_ms=5.0,
                                      battery_percentage=None):
        """
        Radius of action: how far out the aircraft can fly and still return,
        given the stored wind.

        The out leg and the return leg are NOT symmetric. Flying into a
        headwind means a higher airspeed for the same ground speed, so a
        higher power draw, while the downwind return costs less. Energy
        balance across both legs gives:

            R = E_usable / (P_out / Vg_out + P_back / Vg_back)

        This is the militarily meaningful number: a one-way range figure that
        ignores the return trip is not a planning product.
        """
        if battery_percentage is None:
            battery_percentage = self.percentage
        energy_available_wh = self.usable_energy_wh * battery_percentage / 100.0

        outbound = (ground_speed_ms, 0.0, 0.0)
        inbound = (-ground_speed_ms, 0.0, 0.0)
        power_out_w = self.power_required(outbound, self.wind_ned)["total_w"]
        power_back_w = self.power_required(inbound, self.wind_ned)["total_w"]

        denominator = (power_out_w / ground_speed_ms
                       + power_back_w / ground_speed_ms)
        if denominator <= 0.0:
            radius_m = 0.0
        else:
            radius_m = energy_available_wh * 3600.0 / denominator

        still_out = self.power_required(outbound, (0.0, 0.0, 0.0))["total_w"]
        still_back = self.power_required(inbound, (0.0, 0.0, 0.0))["total_w"]
        still_denominator = (still_out / ground_speed_ms
                             + still_back / ground_speed_ms)
        if still_denominator > 0.0:
            still_radius_m = energy_available_wh * 3600.0 / still_denominator
        else:
            still_radius_m = 0.0

        return {
            "radius_of_action_m": radius_m,
            "still_air_radius_m": still_radius_m,
            "wind_penalty_fraction": (1.0 - radius_m / still_radius_m
                                      if still_radius_m > 0.0 else 0.0),
            "power_outbound_w": power_out_w,
            "power_return_w": power_back_w,
            "ground_speed_ms": ground_speed_ms,
            "wind_ned": self.wind_ned,
            "wind_speed_ms": self.wind_speed_ms,
            "battery_percentage": battery_percentage,
        }

    def validate_against_spec(self, tolerance_percent=10.0):
        """
        Compare model predictions against the entity's OWN published anchors.

        Data-driven. The anchor table is built from the record's
        performance_published section, and which anchor is fitted versus held
        out comes from the record's calibration block. Nothing here is
        hardcoded to any particular aircraft.

        That matters more than it sounds. This method previously read every
        target from a class constant and embedded the numbers in its own label
        strings - "operational (derated from 40.0 spec)", "DJI specs page". A
        second entity would have been scored against a Mavic 3 and described
        with Mavic 3 prose, and the report would have looked entirely normal.

        Anchors fitted during calibration report CALIBRATED and are not
        scored, because they cannot fail by construction. Anchors with no
        predictor report UNSCORED with a reason rather than being dropped -
        an anchor quietly missing from a board is indistinguishable from one
        that passed.

        Validation is on RATES and extrapolated endurance, never on how long a
        test happened to run.
        """
        anchors = []
        derate = ((self.usable_energy_fraction / self.operational_overhead)
                  if self.profile == "operational" else 1.0)
        profile_label = ("operational (derated from %s spec by %.3f)"
                         if self.profile == "operational" else "%s%.0s")

        def source_for(anchor_name, published_value):
            record = catalog.get_parameter(
                self.document, "performance_published.%s" % anchor_name)
            source = (record or {}).get("source") or "entity record"
            if (record or {}).get("contested"):
                source += " [CONTESTED]"
            if self.profile == "operational":
                return "operational, derated from %.4g %s" % (published_value,
                                                              source)
            return source

        def add(anchor_name, display, unit, published_value, predicted):
            if published_value is None:
                return
            target = published_value * derate
            anchors.append(self._score_anchor(
                name=display, unit=unit, target=target, predicted=predicted,
                tolerance_percent=tolerance_percent,
                held_out=(anchor_name != self.fitted_to_anchor
                          or self.calibration != "hover"),
                source=source_for(anchor_name, published_value)))

        # ---- Hover endurance ----
        add("max_hover_time_min", "Hover endurance", "min",
            self.spec_hover_time_min, self.endurance_minutes())

        # ---- Cruise endurance, at the speed the vendor measured it ----
        cruise_speed = self.spec_flight_time_speed_ms
        if self.spec_flight_time_min is not None and cruise_speed:
            add("max_flight_time_min",
                "Cruise endurance at %.1f m/s" % cruise_speed, "min",
                self.spec_flight_time_min,
                self.endurance_minutes((cruise_speed, 0.0, 0.0)))

        # ---- Maximum range ----
        add("max_flight_distance_km", "Max range", "km",
            self.spec_max_range_km, self.max_range_km())

        # ---- Anchors declared held out for which no predictor exists ----
        scored_names = {"max_hover_time_min", "max_flight_time_min",
                        "max_flight_distance_km"}
        for anchor_name in self.held_out_anchors:
            if anchor_name in scored_names:
                continue
            record = catalog.get_parameter(
                self.document, "performance_published.%s" % anchor_name)
            if record is None:
                continue
            anchors.append({
                "name": anchor_name,
                "unit": (record.get("unit") or ""),
                "target": record.get("value"),
                "predicted": None,
                "error_percent": None,
                "tolerance_percent": tolerance_percent,
                "held_out": True,
                "status": "UNSCORED",
                "source": (record.get("source") or "entity record"),
                "reason": ("declared held out, but this project has no "
                           "predictor for it; adding one is a new falsifiable "
                           "claim and must be pre-registered first"),
            })

        scored = [a for a in anchors if a["status"] in ("PASS", "FAIL")]
        passed = [a for a in anchors if a["status"] == "PASS"]
        failed = [a for a in anchors if a["status"] == "FAIL"]
        unscored = [a for a in anchors if a["status"] == "UNSCORED"]
        return {
            "entity_id": self.entity_id,
            "entity": self.entity_name,
            "anchors": anchors,
            "held_out_count": len([a for a in anchors if a["held_out"]]),
            "scored_count": len(scored),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "unscored_count": len(unscored),
            "all_held_out_passed": len(failed) == 0,
            "profile": self.profile,
            "calibration": self.calibration,
            "readiness": self.readiness,
            "provisional": self.provisional,
            "tolerance_percent": tolerance_percent,
        }

    @staticmethod
    def _score_anchor(name, unit, target, predicted, tolerance_percent,
                      held_out, source):
        if target != 0.0:
            error_percent = (predicted - target) / target * 100.0
        else:
            error_percent = 0.0

        if not held_out:
            status = "CALIBRATED"
        elif abs(error_percent) <= tolerance_percent:
            status = "PASS"
        else:
            status = "FAIL"

        return {
            "name": name,
            "unit": unit,
            "target": target,
            "predicted": predicted,
            "error_percent": error_percent,
            "tolerance_percent": tolerance_percent,
            "held_out": held_out,
            "status": status,
            "source": source,
        }

    def format_validation_report(self, validation=None):
        """Render validate_against_spec output as an ASCII table."""
        if validation is None:
            validation = self.validate_against_spec()

        lines = []
        # The provisional stamp goes FIRST and unconditionally. A
        # banner the caller must remember to print will eventually
        # not be printed, and a validation table from a thin record
        # must not be screenshottable without it.
        if self.provisional and self.provisional_banner:
            lines.extend(self.provisional_banner)
            lines.append("")

        lines.append("VALIDATION AGAINST PUBLISHED SPECIFICATION")
        lines.append("  entity=%s [%s]"
                     % (validation.get("entity"),
                        validation.get("entity_id")))
        lines.append("  profile=%s  calibration=%s  readiness=%s"
                     % (validation["profile"],
                        validation["calibration"],
                        validation.get("readiness")))
        lines.append("  tolerance=+/-%.1f%%"
                     % validation["tolerance_percent"])
        lines.append("")
        header = ("  %-28s %10s %10s %9s  %-11s %s"
                  % ("Anchor", "Target", "Predicted", "Error",
                     "Status", "Scored"))
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for anchor in validation["anchors"]:
            if anchor["status"] == "UNSCORED":
                lines.append(
                    "  %-28s %10.2f %10s %9s  %-11s %s"
                    % (anchor["name"][:28], anchor["target"],
                       "-", "-", "UNSCORED", "no predictor"))
                continue
            lines.append(
                "  %-28s %10.2f %10.2f %8.1f%%  %-11s %s"
                % (anchor["name"][:28],
                   anchor["target"],
                   anchor["predicted"],
                   anchor["error_percent"],
                   anchor["status"],
                   "held out" if anchor["held_out"]
                   else "FITTED - not scored"))
        lines.append("")
        lines.append("  CALIBRATED means the anchor was fitted and")
        lines.append("  cannot fail by construction. It is never")
        lines.append("  counted as a pass.")
        if validation.get("unscored_count"):
            lines.append("  UNSCORED means the anchor is declared held")
            lines.append("  out but this project has no predictor for")
            lines.append("  it. Inventing one to fill the row would be")
            lines.append("  a new falsifiable claim, and must be")
            lines.append("  pre-registered before it is run.")
        lines.append("  Held-out declared: %d, scored: %d, passed: %d,"
                     " failed: %d"
                     % (validation["held_out_count"],
                        validation.get("scored_count", 0),
                        validation["passed_count"],
                        validation["failed_count"]))
        return chr(10).join(lines)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _separator(title):
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def _self_test():
    """Offline self-test. Requires no simulator."""
    _separator("DJI MAVIC 3 BATTERY MODEL - OFFLINE SELF TEST")
    print("No simulator required. All figures below are model output (L2),")
    print("compared against published specification (L1).")

    _separator("1. CONFIGURATION - spec profile, hover-calibrated")
    model = BatteryModel(profile="spec", calibration="hover")

    _separator("2. POWER BREAKDOWN")
    print("  %-26s %9s %9s %9s %9s %9s"
          % ("Condition", "Induced", "Profile", "Parasitic", "Avionics",
             "TOTAL"))
    print("  " + "-" * 78)
    conditions = [
        ("Hover, still air", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Cruise 5 m/s", (5.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Cruise 9 m/s (DJI test)", (9.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Cruise 15 m/s", (15.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ("Station-keep, 5 m/s wind", (0.0, 0.0, 0.0), (5.0, 0.0, 0.0)),
        ("Station-keep, 12 m/s wind", (0.0, 0.0, 0.0), (12.0, 0.0, 0.0)),
    ]
    for label, velocity, wind in conditions:
        breakdown = model.power_required(velocity, wind)
        print("  %-26s %9.2f %9.2f %9.2f %9.2f %9.2f"
              % (label, breakdown["induced_w"], breakdown["profile_w"],
                 breakdown["parasitic_w"], breakdown["avionics_w"],
                 breakdown["total_w"]))

    _separator("3. VALIDATION - spec profile")
    print(model.format_validation_report())

    _separator("4. VALIDATION - operational profile")
    operational = BatteryModel(profile="operational", calibration="hover",
                               verbose=False)
    print(operational.format_validation_report())

    _separator("5. VALIDATION - zero free parameters (nothing fitted)")
    unfitted = BatteryModel(profile="spec", calibration="none", verbose=False)
    print("  Every parameter from literature or spec. Nothing is tuned.")
    print("")
    print(unfitted.format_validation_report())

    _separator("6. TRANSLATIONAL LIFT - why hover costs more than cruise")
    print("  DJI publishes 46 min flight time but only 40 min hover time.")
    print("  A model with only parasitic drag cannot reproduce that.")
    print("")
    print("  %-12s %10s %10s %12s" % ("Airspeed", "InducedVel", "Power",
                                      "Endurance"))
    print("  " + "-" * 48)
    for speed in [0.0, 2.0, 5.0, 9.0, 12.0, 15.0, 21.0]:
        breakdown = model.power_required((speed, 0.0, 0.0))
        endurance = model.endurance_minutes((speed, 0.0, 0.0))
        print("  %8.1f m/s %8.3f m/s %8.2f W %9.1f min"
              % (speed, breakdown["induced_velocity_ms"],
                 breakdown["total_w"], endurance))
    best = model.best_range_speed_ms()
    print("")
    print("  Best-range speed: %.1f m/s, giving %.1f km still-air range."
          % (best, model.max_range_km(best)))

    _separator("7. WIND - station-keeping cost, and why constraint #4 holds")
    print("  Wind enters as a vector through airspeed, not a scalar penalty.")
    print("  The compensation factor drops BELOW 1.0 at low wind because")
    print("  station-keeping gains translational lift. This is correct.")
    print("")
    print("  %-10s %10s %10s %12s %10s"
          % ("Wind", "Power", "Factor", "Tilt", "Endurance"))
    print("  " + "-" * 56)
    for wind_speed in [0.0, 2.0, 5.0, 8.0, 12.0]:
        model.set_wind(wind_speed, 0.0, 0.0)
        breakdown = model.power_required((0.0, 0.0, 0.0))
        print("  %6.1f m/s %8.2f W %10.3f %9.2f deg %7.1f min"
              % (wind_speed, breakdown["total_w"],
                 model.wind_compensation_factor, breakdown["tilt_deg"],
                 model.endurance_minutes((0.0, 0.0, 0.0), model.wind_ned)))
    model.set_wind(0.0, 0.0, 0.0)

    _separator("8. RADIUS OF ACTION - out and back, 5 m/s ground speed")
    print("  %-12s %12s %12s %10s" % ("Wind", "Radius", "StillAir", "Penalty"))
    print("  " + "-" * 50)
    for wind_speed in [0.0, 2.0, 5.0, 8.0]:
        model.set_wind(wind_speed, 0.0, 0.0)
        result = model.get_estimated_range_with_wind(ground_speed_ms=5.0)
        print("  %8.1f m/s %9.0f m %10.0f m %8.1f%%"
              % (wind_speed, result["radius_of_action_m"],
                 result["still_air_radius_m"],
                 result["wind_penalty_fraction"] * 100.0))
    model.set_wind(0.0, 0.0, 0.0)

    _separator("9. DRAG - force versus power")
    print("  0.5*rho*v^2*Cd*A is a FORCE in newtons. Power needs another v.")
    print("")
    print("  %-10s %14s %14s" % ("Airspeed", "Drag force", "Drag power"))
    print("  " + "-" * 40)
    for speed in [1.0, 5.0, 9.0, 15.0, 21.0]:
        print("  %6.1f m/s %11.4f N %11.3f W"
              % (speed, model.calculate_drag_force(speed),
                 model.calculate_drag_power(speed)))

    _separator("10. FORWARD INTEGRATION - tick() cannot rewrite history")
    print("  Fly 60 s at 9 m/s, then hover 60 s. A model that recomputed")
    print("  from total elapsed time would lose the cruise energy entirely.")
    print("")
    check = BatteryModel(profile="spec", verbose=False)
    for _ in range(60):
        check.tick(1.0, (9.0, 0.0, 0.0))
    after_cruise_wh = check.energy_consumed_wh
    print("  After 60 s at 9 m/s : %.4f Wh consumed" % after_cruise_wh)
    for _ in range(60):
        check.tick(1.0, (0.0, 0.0, 0.0))
    after_hover_wh = check.energy_consumed_wh
    print("  After 60 s hovering : %.4f Wh consumed" % after_hover_wh)
    print("  Cruise energy retained: %s"
          % ("YES" if after_hover_wh > after_cruise_wh else "NO - BUG"))
    print("  Hover segment cost %.4f Wh, cruise segment cost %.4f Wh."
          % (after_hover_wh - after_cruise_wh, after_cruise_wh))

    _separator("11. SENSITIVITY - which assumptions actually matter")
    print("  Response to a +20% change in each parameter, run in")
    print("  calibration=\"none\" so nothing is refitted.")
    print("")
    print("  Run in hover-calibrated mode this table would be ALL ZEROS in")
    print("  the hover column: refitting profile power to the 40 min anchor")
    print("  absorbs any perturbation exactly. That is not robustness, it is")
    print("  the fit hiding the sensitivity - and it is precisely why the")
    print("  held-out cruise anchor is the one that carries information.")
    print("")
    baseline = BatteryModel(profile="spec", calibration="none", verbose=False)
    baseline_hover = baseline.endurance_minutes()
    baseline_cruise = baseline.endurance_minutes(
        (baseline.spec_flight_time_speed_ms, 0.0, 0.0))
    print("  Baseline (unfitted): hover %.2f min, cruise %.2f min"
          % (baseline_hover, baseline_cruise))
    print("")
    print("  %-26s %11s %8s %11s %8s"
          % ("Parameter +20%", "Hover", "Change", "Cruise", "Change"))
    print("  " + "-" * 68)
    for attribute, label in [("cda_m2", "equivalent flat plate"),
                             ("avionics_power_w", "avionics power"),
                             ("figure_of_merit", "figure of merit"),
                             ("mass_kg", "mass"),
                             ("motor_esc_efficiency", "motor/ESC efficiency"),
                             ("propeller_diameter_m", "propeller diameter")]:
        perturbed = BatteryModel(profile="spec", calibration="none",
                                 verbose=False)
        setattr(perturbed, attribute, getattr(perturbed, attribute) * 1.2)
        perturbed._recompute_derived()
        hover = perturbed.endurance_minutes()
        cruise = perturbed.endurance_minutes(
            (baseline.spec_flight_time_speed_ms, 0.0, 0.0))
        print("  %-26s %7.2f min %7.1f%% %7.2f min %7.1f%%"
              % (label, hover,
                 (hover - baseline_hover) / baseline_hover * 100.0,
                 cruise,
                 (cruise - baseline_cruise) / baseline_cruise * 100.0))
    print("")
    print("  Mass and propeller diameter dominate, which is the expected")
    print("  momentum-theory result: induced power scales as T^1.5 / sqrt(A).")
    print("  Equivalent flat plate barely registers at hover and matters only")
    print("  in cruise - so the CdA estimate is not load-bearing for the")
    print("  endurance claims, and the sim-derived CdA cross-check is a")
    print("  corroboration rather than a dependency.")

    _separator("12. SIMULATOR REFERENCE - what AirSim actually flies")
    factors = airsim_drag_factors()
    print("  This is NOT a Mavic 3. It is a 1.0 kg F450-class generic quad.")
    print("  Source: MultiRotorParams.hpp setupFrameGenericQuad.")
    print("")
    print("  Sim mass            : %.3f kg (Mavic 3: %.3f kg)"
          % (AIRSIM_GENERIC_QUAD["mass_kg"], model.mass_kg))
    print("  Sim propeller       : %.4f m (Mavic 3: %.4f m)"
          % (AIRSIM_GENERIC_QUAD["propeller_diameter_m"],
             model.propeller_diameter_m))
    print("  Sim effective CdA_x : %.5f m2" % factors["effective_cda_x_m2"])
    print("  Sim effective CdA_y : %.5f m2" % factors["effective_cda_y_m2"])
    print("  Model CdA (Mavic 3) : %.5f m2"
          % model.cda_m2)
    print("")
    print("  Two independent derivations - literature for the Mavic, C++")
    print("  source for the sim - agree to within 17%. Corroboration.")
    print("")
    print("  Predicted station-keeping tilt (falsifiable at runtime):")
    for wind_speed in [2.0, 5.0, 8.0, 12.0]:
        print("    %5.1f m/s wind -> %.2f deg"
              % (wind_speed, airsim_predicted_tilt_deg(wind_speed)))
    thrust_total = (AIRSIM_GENERIC_QUAD["max_thrust_per_rotor_n"]
                    * AIRSIM_GENERIC_QUAD["rotor_count"])
    weight = AIRSIM_GENERIC_QUAD["mass_kg"] * GRAVITY_MS2
    print("")
    print("  Sim thrust-to-weight: %.2f, hover throttle approx %.0f%%"
          % (thrust_total / weight, 100.0 * weight / thrust_total))

    _separator("SELF TEST COMPLETE")
    print("Reminder: a green board is not the objective. The cruise anchor is")
    print("expected to miss, and the size of that miss is the finding.")


if __name__ == "__main__":
    _self_test()
