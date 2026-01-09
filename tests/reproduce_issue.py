
import numpy as np
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.analysis.processing import SignalProcessor

def test_delayed_start_issue():
    print("Testing delayed start issue...")
    fs = 10000.0 # 10kHz
    dt = 1.0/fs
    
    # Create synthetic signal
    # Scenario: Signal is already active (below -0.5g) from the start
    # Linearly ramping from -1.0g to -6.0g over 50ms
    # Anchor (-5g) will be hit at some point.
    
    # 0 ms: -1.0g
    # 50 ms: -6.0g
    # Slope = -5g / 50ms = -0.1 g/ms
    
    # -5g reached at: -1 - 0.1*t = -5 => 0.1*t = 4 => t = 40ms
    
    time_ms = np.linspace(0, 50, 500) # 500 samples
    accel_g = -1.0 - (0.1 * time_ms) 
    accel_mps2 = accel_g * 9.80665
    
    # Expected behavior currently:
    # Anchor at 40ms.
    # Backtrack finds NO point > -0.5g (start is -1.0g).
    # Fallback: 40ms - 20ms = 20ms.
    # Start Index should comprise 20ms.
    
    expected_fallback_idx = int(0.020 * fs)
    anchor_idx = int(0.040 * fs)
    predicted_start = anchor_idx - expected_fallback_idx
    
    start_idx = SignalProcessor.find_impact_start_robust(accel_mps2, fs)
    start_time_ms = start_idx * dt * 1000
    
    print(f"Anchor Time: 40.0 ms (approx)")
    print(f"Calculated Start Time: {start_time_ms:.2f} ms")
    
    if abs(start_time_ms - 20.0) < 1.0:
        print("PASS: Reproduction confirmed. Start time is clamped to ~20ms due to fallback.")
    else:
        print(f"FAIL: Behavior different than expected. Got {start_time_ms} ms")

if __name__ == "__main__":
    test_delayed_start_issue()
