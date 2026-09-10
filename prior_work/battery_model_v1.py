# battery_model.py
"""
Custom battery model for DJI Mavic 3 with wind compensation.
"""

import math


class BatteryModel:
    """
    Battery model for DJI Mavic 3 with wind compensation.
    """
    
    def __init__(self, specs_file=None):
        # Core specifications (DJI Mavic 3)
        self.capacity_wh = 77.0
        self.voltage_full = 16.8
        self.voltage_empty = 14.0
        self.hover_time_target_minutes = 46.0
        self.mass_kg = 0.895
        
        # Physical parameters for drag calculation
        self.frontal_area_m2 = 0.05
        self.drag_coefficient = 0.8
        self.air_density_kg_m3 = 1.225
        
        # Wind compensation parameters
        self.wind_speed_ms = 0.0
        self.wind_direction = 0.0
        self.wind_compensation_factor = 1.0
        self.base_hover_power_w = self.capacity_wh / (self.hover_time_target_minutes / 60.0)
        
        # Runtime state
        self.percentage = 100.0
        self.voltage = self.voltage_full
        self.energy_consumed_wh = 0.0
        self.total_elapsed_seconds = 0.0
        
        # Drift tracking
        self.drift_x = 0.0
        self.drift_y = 0.0
        self.drift_z = 0.0
        self.start_position = None
        self.drift_measurements = []
        
        # Calculated values
        self.energy_per_second_wh = self.capacity_wh / (self.hover_time_target_minutes * 60)
        self.percentage_per_second = 100.0 / (self.hover_time_target_minutes * 60)
        
        print(f"✅ BatteryModel initialized:")
        print(f"   Capacity: {self.capacity_wh} Wh")
        print(f"   Target hover: {self.hover_time_target_minutes} min")
        print(f"   Base hover power: {self.base_hover_power_w:.1f} W")
    
    def set_wind(self, wind_speed_ms, wind_direction_deg=0.0):
        """Set wind conditions and calculate compensation factor."""
        self.wind_speed_ms = abs(wind_speed_ms)
        self.wind_direction = wind_direction_deg
        
        if self.wind_speed_ms == 0:
            self.wind_compensation_factor = 1.0
            return self.wind_compensation_factor
        
        wind_effect = 1.0 + (self.wind_speed_ms / 50.0) ** 2
        angle_rad = math.radians(self.wind_direction)
        direction_factor = 1.0 + 0.5 * (1 - math.cos(angle_rad))
        
        self.wind_compensation_factor = wind_effect * direction_factor
        return self.wind_compensation_factor
    
    def calculate_drag_power(self, flight_speed_ms, wind_speed_ms=0.0):
        """Calculate additional power from aerodynamic drag."""
        if flight_speed_ms <= 0:
            return 0.0
        
        wind = wind_speed_ms if wind_speed_ms > 0 else self.wind_speed_ms
        relative_velocity = flight_speed_ms + wind
        
        drag_force = 0.5 * self.air_density_kg_m3 * (relative_velocity ** 2) * self.drag_coefficient * self.frontal_area_m2
        drag_power = drag_force * flight_speed_ms
        
        return drag_power
    
    def update(self, elapsed_seconds, flight_speed_ms=0.0):
        """Update battery state based on elapsed time."""
        self.total_elapsed_seconds = elapsed_seconds
        elapsed_minutes = elapsed_seconds / 60.0
        
        self.percentage = max(0, 100 - (elapsed_minutes / self.hover_time_target_minutes) * 100)
        base_energy_wh = self.capacity_wh * (1 - self.percentage / 100)
        
        compensated_energy_wh = base_energy_wh * self.wind_compensation_factor
        
        if flight_speed_ms > 0:
            drag_power = self.calculate_drag_power(flight_speed_ms)
            drag_energy_wh = (drag_power / 3600.0) * elapsed_seconds
            compensated_energy_wh += drag_energy_wh
        
        self.energy_consumed_wh = min(compensated_energy_wh, self.capacity_wh)
        self.percentage = max(0, 100 * (1 - self.energy_consumed_wh / self.capacity_wh))
        
        voltage_drop = (1 - self.percentage / 100) * (self.voltage_full - self.voltage_empty)
        self.voltage = self.voltage_full - voltage_drop
        
        return self.percentage, self.voltage, self.energy_consumed_wh
    
    def tick(self, delta_seconds, flight_speed_ms=0.0):
        """Incrementally update battery model."""
        self.total_elapsed_seconds += delta_seconds
        return self.update(self.total_elapsed_seconds, flight_speed_ms)
    
    def reset(self):
        """Reset battery to full charge."""
        self.percentage = 100.0
        self.voltage = self.voltage_full
        self.energy_consumed_wh = 0.0
        self.total_elapsed_seconds = 0.0
        self.drift_x = 0.0
        self.drift_y = 0.0
        self.drift_z = 0.0
        self.start_position = None
        self.drift_measurements = []
    
    def get_state(self):
        """Return current battery state as a dictionary."""
        return {
            'percentage': self.percentage,
            'voltage': self.voltage,
            'energy_consumed_wh': self.energy_consumed_wh,
            'capacity_wh': self.capacity_wh,
            'time_elapsed_seconds': self.total_elapsed_seconds,
            'time_elapsed_minutes': self.total_elapsed_seconds / 60.0,
            'hover_time_target_minutes': self.hover_time_target_minutes,
            'remaining_minutes': max(0, self.hover_time_target_minutes - (self.total_elapsed_seconds / 60.0)),
            'wind_speed_ms': self.wind_speed_ms,
            'wind_compensation_factor': self.wind_compensation_factor,
            'drift_x': self.drift_x,
            'drift_y': self.drift_y,
            'drift_z': self.drift_z
        }
    
    def record_drift(self, position, is_start=False):
        """Record position for drift tracking."""
        if is_start:
            self.start_position = position
            self.drift_x = 0.0
            self.drift_y = 0.0
            self.drift_z = 0.0
            self.drift_measurements = []
        elif self.start_position is not None:
            self.drift_x = position[0] - self.start_position[0]
            self.drift_y = position[1] - self.start_position[1]
            self.drift_z = position[2] - self.start_position[2]
            
            self.drift_measurements.append({
                'time': self.total_elapsed_seconds,
                'drift_x': self.drift_x,
                'drift_y': self.drift_y,
                'drift_z': self.drift_z,
                'position': position
            })
    
    def get_estimated_range_with_wind(self, battery_percentage=None):
        """Estimate remaining range considering wind conditions."""
        if battery_percentage is None:
            battery_percentage = self.percentage
        
        base_speed_ms = 5.0
        base_range_m = (battery_percentage / 100) * 30.0 * 1000
        
        if self.wind_speed_ms > 0:
            wind_effect = 1.0 - (self.wind_speed_ms / base_speed_ms) * 0.5
            wind_effect = max(0.5, min(1.5, wind_effect))
            adjusted_range = base_range_m * wind_effect
        else:
            adjusted_range = base_range_m
        
        return {
            'base_range_m': base_range_m,
            'adjusted_range_m': adjusted_range,
            'wind_speed_ms': self.wind_speed_ms,
            'wind_direction_deg': self.wind_direction,
            'battery_percentage': battery_percentage
        }