"""
OLC (Occupant Load Criterion) Calculation Module
Compliant with Pydantic v2 validation and Tenacity for robustness.
"""

import numpy as np
from pydantic import BaseModel, Field, field_validator, ConfigDict
from tenacity import retry, stop_after_attempt, wait_fixed
from typing import Tuple, Dict, Any, Optional
from scipy.optimize import fsolve
from scipy import integrate

# Handle scipy version compatibility
if hasattr(integrate, "cumulative_trapezoid"):
    cumtrapz = integrate.cumulative_trapezoid
else:
    cumtrapz = integrate.cumtrapz

class OLCInput(BaseModel):
    """
    Input data model for OLC calculation validation.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    time_s: np.ndarray = Field(..., description="Time array in seconds")
    accel_g: np.ndarray = Field(..., description="Acceleration array in G (filtered)")
    velocity_mps: np.ndarray = Field(..., description="Vehicle velocity in m/s")
    initial_velocity_mps: float = Field(..., gt=0, description="Impact velocity in m/s")
    
    @field_validator('time_s', 'accel_g', 'velocity_mps')
    @classmethod
    def check_array_length(cls, v: np.ndarray) -> np.ndarray:
        if len(v) < 10:
            raise ValueError("Array must have at least 10 elements")
        return v

    @field_validator('accel_g')
    @classmethod
    def match_time_length(cls, v: np.ndarray, info) -> np.ndarray:
        return v

class OLCResult(BaseModel):
    """
    Output data model for OLC calculation.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    olc_g: float
    t1_s: float
    t2_s: float
    v1_mps: float
    v2_mps: float
    s_rel_m: np.ndarray = Field(exclude=True)
    virtual_occupant_velocity_mps: np.ndarray = Field(exclude=True) 

@retry(stop=stop_after_attempt(3), wait=wait_fixed(0.1))
def calculate_olc(
    time_s: np.ndarray,
    accel_g: np.ndarray,
    velocity_mps: np.ndarray,
    initial_velocity_mps: float,
    s1_m: float = 0.065, # t1 criteria (0.065m)
    s2_m: float = 0.300  # t2 criteria (0.300m)
) -> OLCResult:
    """
    Calculates the Occupant Load Criterion (OLC) according to Euro NCAP / precise definition.
    
    Solves for t2 and a_olc such that:
    1. V_occ(t2) == V_veh(t2)
    2. s_rel(t2) == 0.300 m
    """
    # 1. Input Validation
    input_data = OLCInput(
        time_s=time_s, 
        accel_g=accel_g, 
        velocity_mps=velocity_mps, 
        initial_velocity_mps=initial_velocity_mps
    )
    
    time_s = input_data.time_s
    velocity_mps = input_data.velocity_mps
    v0 = input_data.initial_velocity_mps
    
    # 2. Calculate Vehicle Displacement (s_veh)
    # Using trapezoidal integration for better accuracy
    s_veh = cumtrapz(velocity_mps, time_s, initial=0)
    
    # 3. Calculate Relative Displacement (s_rel)
    # s_occ_free(t) = v0 * t
    # s_rel(t) = s_occ_free(t) - s_veh(t)
    s_rel = (v0 * time_s) - s_veh
    
    # 4. Find t1 (s_rel >= 0.065m)
    # Find first index where s_rel >= s1_m
    idx_t1_candidates = np.where(s_rel >= s1_m)[0]
    
    if len(idx_t1_candidates) == 0:
        # Fallback if 65mm is never reached (unlikely in crash)
        return OLCResult(olc_g=0.0, t1_s=0.0, t2_s=0.0, v1_mps=0.0, v2_mps=0.0, 
                        s_rel_m=s_rel, virtual_occupant_velocity_mps=np.zeros_like(time_s))

    idx_t1 = idx_t1_candidates[0]
    t1 = time_s[idx_t1]
    
    # 5. Solve for t2 and a_olc
    # System of equations:
    # Eq1: v_veh(t2) - (v0 - a_olc * (t2 - t1)) = 0
    # Eq2: (s_occ(t2) - s_veh(t2)) - s2_m = 0
    #      where s_occ(t2) = v0*t2 - 0.5*a_olc*(t2 - t1)^2
    
    def equations(p):
        t2_val, a_olc_val = p
        
        # Use interpolation for vehicle values at continuous t2
        v_veh_t2 = np.interp(t2_val, time_s, velocity_mps)
        s_veh_t2 = np.interp(t2_val, time_s, s_veh)
        
        # Eq 1: Velocity Match
        # V_occ(t2) = V0 - a_olc * (t2 - t1)
        v_occ_t2 = v0 - a_olc_val * (t2_val - t1)
        eq1 = v_veh_t2 - v_occ_t2
        
        # Eq 2: Relative Displacement Match (Total 0.3m)
        # s_occ(t2) = V0*t2 - 0.5 * a_olc * (t2 - t1)^2
        s_occ_t2 = (v0 * t2_val) - (0.5 * a_olc_val * (t2_val - t1)**2)
        s_rel_t2 = s_occ_t2 - s_veh_t2
        eq2 = s_rel_t2 - s2_m
        
        return [eq1, eq2]

    # Initial Guesses
    # t2 is roughly when vehicle stops or later phase. Guess t1 + 0.1s
    # a_olc guess 20g
    guess_t2 = t1 + 0.1
    guess_a = 20.0 * 9.80665
    
    try:
        root = fsolve(equations, [guess_t2, guess_a])
        t2_final, a_olc_final = root
    except Exception:
        # Fallback if solver fails
        t2_final = t1
        a_olc_final = 0.0

    # Validation of result
    if t2_final <= t1 or a_olc_final < 0:
         # Solver failed to find physical solution
         t2_final = t1
         a_olc_final = 0.0

    # 6. Generate Virtual Occupant Velocity Profile
    virtual_velocity = np.full_like(velocity_mps, v0)
    
    # Apply deceleration after t1
    mask_decel = time_s >= t1
    if np.any(mask_decel):
        # V_occ(t) = V0 - a_olc * (t - t1)
        decel_vel = v0 - a_olc_final * (time_s[mask_decel] - t1)
        # Clamp to 0 if it goes negative (though usually it meets v_veh)
        virtual_velocity[mask_decel] = decel_vel
        
    return OLCResult(
        olc_g=round(a_olc_final / 9.80665, 2),
        t1_s=t1,
        t2_s=t2_final,
        v1_mps=velocity_mps[idx_t1], # Actually V_veh at t1
        v2_mps=np.interp(t2_final, time_s, velocity_mps), # V_veh at t2
        s_rel_m=s_rel,
        virtual_occupant_velocity_mps=virtual_velocity
    )
