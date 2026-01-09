"""
Signal processing engine compliant with SAE J211.
Uses known_impact_velocity (if provided) for precise Dynamic Crush calculation.
"""

import numpy as np
from scipy import signal, integrate
from src.analysis.core import CrashSignal


class SignalProcessor:
    """
    [최종 수정] Signal Processor V3
    1. Bias Search Window 축소 (30ms -> 10ms) 및 탐색 한계 축소 (40% -> 20%)
    2. T0 Fallback 로직 추가 (탐색 실패 시 Anchor 기준으로 강제 설정)
    """

    @staticmethod
    def process(
        time_s: np.ndarray,
        raw_g: np.ndarray,
        cfc: int = 60,
        known_impact_velocity_mps: float = None,
        search_window_ms: float = 10.0, # [수정] 윈도우 크기 축소 (충돌 전 짧은 구간 대응)
    ) -> CrashSignal:
        
        # 1. Basic Setup
        if len(time_s) < 10: raise ValueError("Data too short")
        dt = time_s[1] - time_s[0]
        fs = 1.0 / dt

        # 2. Filtering
        filtered_g = SignalProcessor.apply_cfc_filter(raw_g, fs, cfc)

        # 3. Bias Removal
        # [수정] 충돌 데이터 혼입 방지를 위해 탐색 비율을 20%로 제한
        final_bias = SignalProcessor.find_best_bias(
            filtered_g, fs, window_ms=search_window_ms, limit_ratio=0.2
        )
        corrected_g = filtered_g - final_bias
        accel_mps2 = corrected_g * 9.80665

        # 4. Anchor & Backtrack T0 Detection
        start_idx = SignalProcessor.find_impact_start_robust(
            accel_mps2, fs, anchor_g=-5.0, release_g=-0.5
        )
        
        # [Zero Padding] T0 이전 데이터 완전 소거
        accel_mps2[:start_idx] = 0.0
        corrected_g[:start_idx] = 0.0

        # 5. Integration (Velocity)
        initial_v = known_impact_velocity_mps if known_impact_velocity_mps is not None else 0.0
        integ_func = getattr(integrate, "cumulative_trapezoid", integrate.cumtrapz)
        
        velocity_mps = np.full_like(time_s, initial_v)
        if start_idx < len(time_s) - 1:
            delta_v = integ_func(accel_mps2[start_idx:], time_s[start_idx:], initial=0)
            velocity_mps[start_idx:] = initial_v + delta_v
            
        # Stop Detection
        stop_indices = np.where(velocity_mps[start_idx:] <= 0)[0]
        end_idx = len(time_s) - 1
        if len(stop_indices) > 0:
            end_idx = start_idx + stop_indices[0]
            velocity_mps[end_idx+1:] = 0.0

        # 6. Integration (Displacement)
        displacement_m = np.zeros_like(time_s)
        if start_idx < end_idx:
            delta_s = integ_func(velocity_mps[start_idx:end_idx+1], time_s[start_idx:end_idx+1], initial=0)
            displacement_m[start_idx:end_idx+1] = delta_s
            
            # [강제 보정] T0 이전 변위 0 처리
            displacement_m[:start_idx] = 0.0
            displacement_m[end_idx+1:] = displacement_m[end_idx]

        return CrashSignal(
            time_ms=time_s * 1000,
            raw_accel_g=raw_g,
            filtered_accel_g=corrected_g,
            velocity_kph=velocity_mps * 3.6,
            displacement_m=displacement_m,
            sample_rate=fs,
            impact_start_index=start_idx,
            bias_value=final_bias
        )

    @staticmethod
    def find_impact_start_robust(accel_mps2: np.ndarray, fs: float, anchor_g: float = -5.0, release_g: float = -0.5) -> int:
        anchor_val = anchor_g * 9.80665
        release_val = release_g * 9.80665
        
        # 1. Anchor 탐색
        hard_impact_indices = np.where(accel_mps2 < anchor_val)[0]
        
        if len(hard_impact_indices) == 0:
            # Anchor 미발견 시 (매우 약한 충돌) -> 기존 방식 Fallback
            fallback_indices = np.where(accel_mps2 < release_val)[0]
            return fallback_indices[0] if len(fallback_indices) > 0 else 0
            
        first_anchor_idx = hard_impact_indices[0]
        
        # 2. Backtrack
        pre_crash_segment = accel_mps2[:first_anchor_idx]
        safe_indices = np.where(pre_crash_segment > release_val)[0]
        
        if len(safe_indices) > 0:
            return safe_indices[-1] + 1
        else:
            # [Fallback] Backtrack 실패 (0ms까지 전부 -0.5g 이하인 경우)
            # 이는 Bias가 잘못되었을 확률이 높지만, 
            # 최소한 그래프가 0부터 시작하는 것은 막기 위해 Anchor 직전 20ms를 강제 T0로 잡음.
            fallback_ms = 20.0
            fallback_samples = int((fallback_ms / 1000.0) * fs)
            t0_fallback = max(0, first_anchor_idx - fallback_samples)
            return t0_fallback

    @staticmethod
    def find_best_bias(data: np.ndarray, fs: float, window_ms: float = 10.0, limit_ratio: float = 0.2) -> float:
        # [수정] 탐색 범위 제한 (limit_ratio: 0.4 -> 0.2)
        # v15494 처럼 충돌이 빨리 시작되는 경우를 위해 앞쪽 20%만 사용
        search_limit_idx = int(len(data) * limit_ratio)
        
        # 너무 짧으면 최소 50ms 확보 시도
        min_samples = int(0.05 * fs)
        if search_limit_idx < min_samples: 
            search_limit_idx = min(len(data), min_samples)
        
        target_data = data[:search_limit_idx]
        win_len = int((window_ms / 1000.0) * fs)
        if win_len < 3: win_len = 3
        
        if len(target_data) < win_len: return np.median(target_data)

        min_std = float('inf')
        best_mean = 0.0
        stride = max(1, win_len // 4)
        
        for i in range(0, len(target_data) - win_len, stride):
            segment = target_data[i : i + win_len]
            curr_std = np.std(segment)
            if curr_std < min_std:
                min_std = curr_std
                best_mean = np.mean(segment)
        
        # Bias 안전장치 (3g 이상은 비정상)
        if abs(best_mean) > 3.0: return 0.0
        return best_mean

    @staticmethod
    def apply_cfc_filter(data: np.ndarray, fs: float, cfc: int) -> np.ndarray:
        if cfc == 60: cutoff = 100.0
        elif cfc == 180: cutoff = 300.0
        else: cutoff = cfc * 1.667
        nyq = 0.5 * fs
        normal_cutoff = np.clip(cutoff / nyq, 0, 0.99)
        b, a = signal.butter(2, normal_cutoff, btype="low", analog=False)
        return signal.filtfilt(b, a, data)
