# HoverScript_01.py
import cosysairsim as airsim
import time
import datetime
import os
import json

# Import your custom battery model
from battery_model import BatteryModel

print("=" * 70)
print("🚁 Hover Test 3.a - DJI Mavic 3 Baseline Validation")
print("=" * 70)
print(f"Test started at: {datetime.datetime.now()}")

# Initialize the battery model
battery = BatteryModel('data/mavic3_specs.json')
print("\n" + "=" * 70)

# Connect to the simulation
print("🔌 Connecting to simulation...")
client = airsim.MultirotorClient()
client.confirmConnection()
print("✅ Connected to simulation")

# Take control and arm the drone
print("🎮 Taking control...")
client.enableApiControl(True)
client.armDisarm(True)
print("✅ Armed and ready")

# Take off and hover
print("🛫 Taking off...")
client.takeoffAsync().join()
print("🔄 Hovering... Starting battery test")
print("-" * 70)

# Test duration
# TEST_DURATION_SECONDS = 30  # Quick test
# TEST_DURATION_SECONDS = 60   # 1 minute test
TEST_DURATION_SECONDS = 2760  # Full 46-minute test

battery_data = []
start_time = time.time()

# Get initial state
initial_state = client.getMultirotorState()
initial_pos = initial_state.kinematics_estimated.position
print(f"📍 Initial position: x={initial_pos.x_val:.2f}, y={initial_pos.y_val:.2f}, z={initial_pos.z_val:.2f}")
print("-" * 70)

print("Time(s) | Minutes | Battery% | Voltage(V) | Energy(Wh) | Position")
print("-" * 70)

for i in range(TEST_DURATION_SECONDS):
    elapsed_seconds = i + 1
    elapsed_minutes = elapsed_seconds / 60.0
    
    # Update battery model
    percentage, voltage, energy_consumed = battery.update(elapsed_seconds)
    
    # Get simulation state
    state = client.getMultirotorState()
    kin = state.kinematics_estimated
    landed_state = state.landed_state
    
    # Check if flying (landed_state: 0=landed, 1=flying)
    is_flying = (landed_state == 1)
    
    # Print status
    pos = f"({kin.position.x_val:.1f}, {kin.position.y_val:.1f}, {kin.position.z_val:.1f})"
    print(f"{elapsed_seconds:6} | {elapsed_minutes:7.2f} | {percentage:8.1f} | {voltage:10.2f} | {energy_consumed:10.2f} | {pos}")
    
    # Store data
    battery_data.append({
        'time': elapsed_seconds,
        'minutes': elapsed_minutes,
        'percentage': percentage,
        'voltage': voltage,
        'energy_consumed': energy_consumed,
        'is_flying': is_flying,
        'position_x': kin.position.x_val,
        'position_y': kin.position.y_val,
        'position_z': kin.position.z_val,
        'landed_state': landed_state
    })
    
   # time.sleep(1)

# Land
print("-" * 70)
print("🛬 Landing...")
client.landAsync().join()
print("✅ Hover test complete!")

end_time = time.time()
actual_wall_time = end_time - start_time

# Calculate results
actual_minutes = TEST_DURATION_SECONDS / 60.0
validation = battery.validate_against_spec(actual_minutes)

print("\n" + "=" * 70)
print("📊 TEST RESULTS")
print("=" * 70)
print(f"Target Hover Time:  {validation['target_minutes']:.2f} minutes")
print(f"Actual Hover Time:  {validation['actual_minutes']:.2f} minutes")
print(f"Error:              {validation['error_percent']:.2f}%")
print(f"Status:             {'✅ PASS' if validation['passed'] else '❌ FAIL'} (within 5% tolerance)")
print(f"Wall Clock Time:    {actual_wall_time:.2f} seconds")
print("=" * 70)

# Save results
os.makedirs('results', exist_ok=True)

timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
results_file = f'results/hover_test_{timestamp}.txt'

with open(results_file, 'w') as f:
    f.write("=" * 80 + "\n")
    f.write("Hover Test 3.a - DJI Mavic 3 Baseline Validation\n")
    f.write("=" * 80 + "\n")
    f.write(f"Test started:          {datetime.datetime.now()}\n")
    f.write(f"Test duration:         {TEST_DURATION_SECONDS} seconds ({actual_minutes:.2f} minutes)\n")
    f.write(f"Wall clock time:       {actual_wall_time:.2f} seconds\n")
    f.write("-" * 80 + "\n")
    
    # Write specifications
    f.write("\nDRONE SPECIFICATIONS:\n")
    f.write("-" * 80 + "\n")
    f.write(f"Mass:                  {battery.mass_kg} kg\n")
    f.write(f"Battery Capacity:      {battery.capacity_wh} Wh\n")
    f.write(f"Full Voltage:          {battery.voltage_full} V\n")
    f.write(f"Empty Voltage:         {battery.voltage_empty} V\n")
    f.write(f"Target Hover Time:     {battery.hover_time_target_minutes} minutes\n")
    f.write(f"Energy per second:     {battery.energy_per_second_wh:.4f} Wh/s\n")
    f.write("-" * 80 + "\n")
    
    # Write validation results
    f.write("\nVALIDATION RESULTS:\n")
    f.write("-" * 80 + "\n")
    f.write(f"Target Hover Time:     {validation['target_minutes']:.2f} minutes\n")
    f.write(f"Actual Hover Time:     {validation['actual_minutes']:.2f} minutes\n")
    f.write(f"Error:                 {validation['error_percent']:.2f}%\n")
    f.write(f"Status:                {'PASS' if validation['passed'] else 'FAIL'}\n")
    f.write("-" * 80 + "\n")
    
    # Write time series data
    f.write("\nTIME SERIES DATA:\n")
    f.write("-" * 80 + "\n")
    f.write("Time(s) | Minutes | Battery% | Voltage(V) | Energy(Wh) | Flying? | Position\n")
    f.write("-" * 80 + "\n")
    for data in battery_data:
        pos = f"({data['position_x']:.1f}, {data['position_y']:.1f}, {data['position_z']:.1f})"
        f.write(f"{data['time']:7} | {data['minutes']:7.2f} | {data['percentage']:8.1f} | {data['voltage']:10.2f} | {data['energy_consumed']:10.2f} | {str(data['is_flying']):7} | {pos}\n")

print(f"\n📊 Results saved to: {results_file}")

# Also save a summary as JSON
summary_file = f'results/hover_test_{timestamp}.json'
with open(summary_file, 'w') as f:
    json.dump({
        'test': '3.a - Baseline Hover Validation',
        'entity': 'DJI Mavic 3',
        'timestamp': datetime.datetime.now().isoformat(),
        'duration_seconds': TEST_DURATION_SECONDS,
        'target_hover_time_minutes': battery.hover_time_target_minutes,
        'actual_hover_time_minutes': actual_minutes,
        'error_percent': validation['error_percent'],
        'passed': validation['passed'],
        'data': battery_data
    }, f, indent=2)

print(f"📊 Summary saved to: {summary_file}")