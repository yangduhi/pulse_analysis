"""
Signal processing engine compliant with SAE J211.
Uses known_impact_velocity (if provided) for precise Dynamic Crush calculation.
"""

import numpy as np
from scipy import signal, integrate
from src.analysis.core import CrashSignal


class SignalProcessor:
    """신호 처리 전용 클래스"""

    @staticmethod
    def process(
        time_s: np.ndarray,
        raw_g: np.ndarray,
        cfc: int = 60,
        known_impact_velocity_mps: float = None,
        auto_polarity_flip: bool = True, # 옵션으로 분리
        is_rear_impact: bool = False     # 충돌 모드 고려
    ) -> CrashSignal:
        
        # 1. 데이터 검증 및 초기화
        if len(time_s) < 10:
            raise ValueError("Data too short")

        dt = time_s[1] - time_s[0]
        fs = 1.0 / dt

        # 2. CFC 필터링 (SAE J211)
        filtered_g = SignalProcessor.apply_cfc_filter(raw_g, fs, cfc)

        # 3. [Bias Removal] 수정된 로직
        # 1단계: 초기 20ms의 중앙값(Median)으로 1차 보정
        n_init = int(0.020 * fs)
        n_init = min(n_init, len(filtered_g) // 10) # 데이터가 짧을 경우 안전장치
        
        initial_bias = np.median(filtered_g[:n_init])
        
        # 2단계: 정밀 보정 (Trigger 전 가장 평탄한 구간 탐색)
        # Trigger 탐색 (임시로 1차 보정된 데이터 사용)
        temp_g = filtered_g - initial_bias
        trigger_threshold = 0.5
        trigger_indices = np.where(np.abs(temp_g) > trigger_threshold)[0]
        
        final_offset = initial_bias # 기본값

        trigger_idx = 0 # Initialize for later scope usage
        
        if len(trigger_indices) > 0:
            trigger_idx = trigger_indices[0]
            
            # 탐색 범위: Trigger 5ms 전부터 최대 50ms 전까지
            margin = int(0.005 * fs)
            window_len = int(0.010 * fs)
            search_end = max(0, trigger_idx - margin)
            search_start = max(0, search_end - int(0.050 * fs))

            if search_end - search_start > window_len:
                best_var = float('inf')
                
                # 윈도우 슬라이딩하며 분산이 최소인 구간 찾기
                for i in range(search_start, search_end - window_len + 1):
                    # *중요*: 원본 filtered_g에서 구간을 추출해야 실제 DC Offset을 알 수 있음
                    window = filtered_g[i : i + window_len]
                    curr_var = np.var(window)
                    
                    if curr_var < best_var:
                        best_var = curr_var
                        # 분산이 최소인 구간의 평균이 가장 신뢰할 수 있는 Bias
                        final_offset = np.mean(window) 
                
                # 만약 최소 분산이 너무 크다면(노이즈가 심함), 초기 Bias 유지
                if best_var > 0.1: 
                    final_offset = initial_bias

        # 최종 Bias 적용
        filtered_g_corrected = filtered_g - final_offset
        accel_mps2 = filtered_g_corrected * 9.80665

        # 4. [Polarity Correction] 수정된 로직
        # 전방 충돌인데 평균 가속도가 양수(가속)라면 뒤집기
        # 후방 충돌(is_rear_impact=True)일 경우 로직 건너뜀
        if auto_polarity_flip and not is_rear_impact:
             # Trigger 이후 충돌 구간의 평균 확인
            check_end = min(len(accel_mps2), trigger_idx + int(0.1 * fs)) if len(trigger_indices) > 0 else len(accel_mps2)
            check_start = trigger_indices[0] if len(trigger_indices) > 0 else 0
            
            segment_mean = np.mean(accel_mps2[check_start:check_end])
            
            if segment_mean > 0: # 감속이어야 하는데 양수라면
                accel_mps2 = -accel_mps2
                filtered_g_corrected = -filtered_g_corrected

        # 5. [Physics Correction] T0 탐색 및 초기화
        # 감속(-0.5g) 시작점 탐색
        threshold_acc = -0.5 * 9.80665
        t0_candidates = np.where(accel_mps2 < threshold_acc)[0]
        
        start_idx = 0
        if len(t0_candidates) > 0:
            first_cross = t0_candidates[0]
            # Cross 지점에서 뒤로 가며 Zero-Crossing(혹은 local max) 찾기
            lookback_limit = max(0, first_cross - int(0.020 * fs))
            # 구간 내에서 0에 가장 가까운 지점(절대값 최소)
            local_segment = np.abs(accel_mps2[lookback_limit:first_cross+1])
            local_min_rel_idx = np.argmin(local_segment)
            start_idx = lookback_limit + local_min_rel_idx
            
        # T0 이전 데이터 0으로 강제 (Pre-impact noise 제거)
        accel_mps2[:start_idx] = 0.0
        filtered_g_corrected[:start_idx] = 0.0 # Corrected data also needs zeroing
        
        # 6. 적분 (Velocity & Displacement)
        initial_v = known_impact_velocity_mps if known_impact_velocity_mps is not None else 0.0
        
        # scipy 적분 함수 호환성
        integ_func = getattr(integrate, "cumulative_trapezoid", integrate.cumtrapz)
        
        velocity_mps = np.full_like(time_s, initial_v)
        # T0 이후부터 적분 수행
        if start_idx < len(time_s) - 1:
            delta_v = integ_func(accel_mps2[start_idx:], time_s[start_idx:], initial=0)
            velocity_mps[start_idx:] = initial_v + delta_v

        # 차량 정지 시점(Rebound 시작점) 탐색
        # 속도가 0 이하로 떨어지거나, 다시 증가하는(Rebound) 지점 등 정의 필요
        # 여기서는 속도가 0 이하가 되는 첫 지점으로 정의
        stop_indices = np.where(velocity_mps[start_idx:] <= 0)[0]
        end_idx = len(time_s) - 1
        
        if len(stop_indices) > 0:
            end_idx = start_idx + stop_indices[0]
            # 물리적으로 정지 후에는 변위 고정
            velocity_mps[end_idx+1:] = 0.0

        displacement_m = np.zeros_like(time_s)
        if start_idx < end_idx:
            delta_s = integ_func(velocity_mps[start_idx:end_idx+1], time_s[start_idx:end_idx+1], initial=0)
            displacement_m[start_idx:end_idx+1] = delta_s
            displacement_m[end_idx+1:] = delta_s[-1] # 최종 변위 유지

        return CrashSignal(
            time_ms=time_s * 1000,
            raw_accel_g=raw_g,
            filtered_accel_g=filtered_g_corrected,
            velocity_kph=velocity_mps * 3.6,
            displacement_m=displacement_m,
            sample_rate=fs,
            impact_start_index=start_idx
        )

    @staticmethod
    def apply_cfc_filter(data: np.ndarray, fs: float, cfc: int) -> np.ndarray:
        # Cutoff Frequency Calculation
        if cfc == 60:
            cutoff = 100.0
        elif cfc == 180:
            cutoff = 300.0
        else:
            cutoff = cfc * 1.667

        nyq = 0.5 * fs
        normal_cutoff = np.clip(cutoff / nyq, 0, 0.99) # 안전하게 clip 사용

        b, a = signal.butter(2, normal_cutoff, btype="low", analog=False)
        return signal.filtfilt(b, a, data)