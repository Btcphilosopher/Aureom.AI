"""
Engine audio mix parameters derived from live drivetrain telemetry: layer
blend weights (idle/load/redline/turbo-flutter) and pitch, exactly the
kind of RPM-driven layered engine sound model real racing games use.
Headless engine -> this produces the numeric mix an audio backend would
consume, not actual sound.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_horizon_engine.utils.config import DrivetrainSpec, EngineCurve


@dataclass
class EngineAudioMix:
    pitch_ratio: float          # relative to a 1.0 reference sample pitch
    load_layer_weight: float    # 0..1, throttle/load layer blend
    idle_layer_weight: float
    redline_layer_weight: float
    turbo_flutter: float        # 0..1, off-throttle turbo blow-off intensity
    is_electric_whine: bool


def compute_engine_audio(engine: EngineCurve, drivetrain: DrivetrainSpec, rpm: float,
                          throttle: float, prev_throttle: float) -> EngineAudioMix:
    rpm_frac = max(0.0, min(1.0, (rpm - engine.idle_rpm) / max(1.0, engine.redline_rpm - engine.idle_rpm)))
    pitch = 0.55 + 1.35 * rpm_frac

    idle_weight = max(0.0, 1.0 - rpm_frac * 3.0)
    redline_weight = max(0.0, (rpm_frac - 0.85) / 0.15)
    load_weight = max(0.0, min(1.0, throttle)) * (1.0 - idle_weight)

    lifted_hard = (prev_throttle - throttle) > 0.35
    flutter = 0.8 if (lifted_hard and rpm_frac > 0.4 and not drivetrain.is_electric) else 0.0

    return EngineAudioMix(
        pitch_ratio=round(pitch, 3), load_layer_weight=round(load_weight, 3),
        idle_layer_weight=round(idle_weight, 3), redline_layer_weight=round(redline_weight, 3),
        turbo_flutter=flutter, is_electric_whine=drivetrain.is_electric,
    )
