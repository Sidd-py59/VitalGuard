"""
VitalGuard — Simulated Wearable Data Generator
Produces realistic heart_rate, spo2, temperature, hrv readings.
Supports scenario modes: normal, mild_anomaly, critical_emergency, auto.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ScenarioMode = Literal["normal", "mild_anomaly", "critical_emergency", "auto"]

AUTO_CYCLE: list[tuple[ScenarioMode, int]] = [
    ("normal", 20),
    ("mild_anomaly", 15),
    ("critical_emergency", 10),
]


@dataclass
class VitalSigns:
    heart_rate: float
    spo2: float
    temperature: float
    hrv: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        def r1(v: float) -> float:
            return float(int(v * 10 + 0.5) / 10)

        return {
            "heart_rate": r1(self.heart_rate),
            "spo2": r1(self.spo2),
            "temperature": r1(self.temperature),
            "hrv": r1(self.hrv),
            "timestamp": self.timestamp,
        }


class WearableSimulator:
    """Generates simulated wearable vital sign data."""

    def __init__(self):
        self.mode: ScenarioMode = "normal"
        self._transition_steps = 0
        self._current_vitals = self._generate_normal()
        self._auto_ticks = 0
        self._auto_stage = 0
        self._auto_stage_ticks = 0
        self._auto_internal_mode: ScenarioMode = "normal"

    def set_mode(self, mode: ScenarioMode):
        """Switch scenario mode."""
        self.mode = mode
        self._transition_steps = 5
        if mode == "auto":
            self._auto_ticks = 0
            self._auto_stage = 0
            self._auto_stage_ticks = 0
            self._auto_internal_mode = AUTO_CYCLE[0][0]

    def _generate_normal(self) -> VitalSigns:
        return VitalSigns(
            heart_rate=random.uniform(65, 85),
            spo2=random.uniform(96, 99),
            temperature=random.uniform(36.3, 37.0),
            hrv=random.uniform(30, 60),
        )

    def _generate_mild_anomaly(self) -> VitalSigns:
        """Multiple vitals slightly off — triggers high risk (>60) to book doctor automatically."""
        base = self._generate_normal()
        base.heart_rate = random.uniform(105, 120)       # warning high
        base.spo2 = random.uniform(91, 94)               # warning low
        base.temperature = random.uniform(37.9, 38.5)    # warning high
        base.hrv = random.uniform(15, 19)                # warning low
        return base

    def _generate_critical(self) -> VitalSigns:
        """Multiple vitals severely abnormal — triggers emergency."""
        return VitalSigns(
            heart_rate=random.uniform(140, 190),
            spo2=random.uniform(75, 88),
            temperature=random.uniform(39.0, 41.0),
            hrv=random.uniform(3, 10),
        )

    def _tick_auto(self):
        """Advance the auto simulation cycle, looping indefinitely."""
        self._auto_stage_ticks += 1
        _stage_name, stage_duration = AUTO_CYCLE[self._auto_stage]

        if self._auto_stage_ticks >= stage_duration:
            self._auto_stage = (self._auto_stage + 1) % len(AUTO_CYCLE)
            self._auto_stage_ticks = 0
            self._auto_internal_mode = AUTO_CYCLE[self._auto_stage][0]
            self._transition_steps = 6

    def _lerp(self, current: float, target: float, alpha: float) -> float:
        return current + (target - current) * alpha

    def generate(self) -> VitalSigns:
        """Generate the next set of vital signs based on current mode."""
        if self.mode == "auto":
            self._tick_auto()
            active_mode = self._auto_internal_mode
        else:
            active_mode = self.mode

        if active_mode == "normal":
            target = self._generate_normal()
        elif active_mode == "mild_anomaly":
            target = self._generate_mild_anomaly()
        elif active_mode == "critical_emergency":
            target = self._generate_critical()
        else:
            target = self._generate_normal()

        if self._transition_steps > 0:
            alpha = 1.0 / self._transition_steps
            self._transition_steps -= 1
        else:
            alpha = 0.3

        self._current_vitals = VitalSigns(
            heart_rate=self._lerp(self._current_vitals.heart_rate, target.heart_rate, alpha),
            spo2=self._lerp(self._current_vitals.spo2, target.spo2, alpha),
            temperature=self._lerp(self._current_vitals.temperature, target.temperature, alpha),
            hrv=self._lerp(self._current_vitals.hrv, target.hrv, alpha),
        )

        return self._current_vitals