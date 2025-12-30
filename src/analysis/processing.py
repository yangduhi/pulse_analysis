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
    ) -> CrashSignal:
        """
        Raw Data -> Filtering -> Integration -> Physics Correction

        :param known_impact_velocity_mps: 메타데이터에서 가져온 실측 충돌 속도.
                                          이 값이 제공되면 적분 오차(Drift)가 획기적으로 줄어듭니다.
        """
        # 1. 데이터 검증
        if len(time_s) < 10:
            raise ValueError("Data too short")

        dt = time_s[1] - time_s[0]
        fs = 1.0 / dt

        # 2. CFC 필터링 (SAE J211)
        filtered_g = SignalProcessor.apply_cfc_filter(raw_g, fs, cfc)

        # [Bias Removal] 0점 보정
        pre_impact_mask = time_s < 0
        if np.any(pre_impact_mask):
            offset = np.mean(filtered_g[pre_impact_mask])
        else:
            offset = np.mean(filtered_g[:8])
        filtered_g = filtered_g - offset

        # 3. 단위 변환 (G -> m/s^2)
        accel_mps2 = filtered_g * 9.80665

        # 4. 1차 적분 (Delta V 계산)
        if hasattr(integrate, "cumulative_trapezoid"):
            integ_func = integrate.cumulative_trapezoid
        else:
            integ_func = integrate.cumtrapz

        delta_v_mps = integ_func(accel_mps2, time_s, initial=0)

        # [Physics Correction] 초기 속도(V0) 결정 로직
        if known_impact_velocity_mps:
            # Case A: 실측 속도가 있으면 그걸 믿음 (정확도 최상)
            v0 = known_impact_velocity_mps
        else:
            # Case B: 없으면 Delta V의 최댓값으로 추정 (Fallback)
            v0 = np.max(np.abs(delta_v_mps))

        # 실제 속도 프로파일 계산: V(t) = V0 - |Delta_V(t)|
        # (충돌 시 속도가 V0에서 0으로 줄어드는 물리 현상 반영)
        real_velocity_mps = v0 - np.abs(delta_v_mps)

        # 물리적 제약: 속도는 음수가 될 수 없음 (Rebound 이후 0 처리)
        real_velocity_mps = np.maximum(real_velocity_mps, 0)

        # [Safety Lock] 300ms 이후 적분 강제 중단 (Drift 방지)
        cutoff_idx = np.searchsorted(time_s, 0.3)
        if cutoff_idx < len(real_velocity_mps):
            real_velocity_mps[cutoff_idx:] = 0

        # 5. 2차 적분 (속도 -> 변위 = Dynamic Crush)
        displacement_m = integ_func(real_velocity_mps, time_s, initial=0)

        # [Free-Flight Correction] T=0 시점의 변위 오프셋 제거
        idx_t0 = np.argmin(np.abs(time_s))
        crush_m = displacement_m - displacement_m[idx_t0]
        crush_m[time_s < 0] = 0  # T<0 구간은 0으로 처리

        return CrashSignal(
            time_ms=time_s * 1000,
            raw_accel_g=raw_g,
            filtered_accel_g=filtered_g,
            velocity_kph=delta_v_mps * 3.6,  # 분석용으로는 Delta V 반환
            displacement_m=crush_m,  # 보정된 순수 찌그러짐
            sample_rate=fs,
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
        normal_cutoff = cutoff / nyq
        if normal_cutoff >= 1.0:
            normal_cutoff = 0.99

        b, a = signal.butter(2, normal_cutoff, btype="low", analog=False)
        return signal.filtfilt(b, a, data)
