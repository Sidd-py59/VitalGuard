"""
VitalGuard — Deterministic Risk Scoring Engine
Computes a 0–100 risk score from vital signs.
Levels: LOW (0-30), MODERATE (31-60), HIGH (61-80), CRITICAL (81-100)
"""

from dataclasses import dataclass, field
from typing import Literal

from simulator import VitalSigns

RiskLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


@dataclass
class RiskAssessment:
    score: int
    level: RiskLevel
    contributing_factors: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "level": self.level,
            "contributing_factors": self.contributing_factors,
            "summary": self.summary,
        }


THRESHOLDS = {
    "heart_rate": {
        "warning_high": 100,
        "critical_high": 140,
        "warning_low": 55,
        "critical_low": 40,
    },
    "spo2": {
        "warning_low": 94,
        "critical_low": 88,
    },
    "temperature": {
        "warning_high": 37.8,
        "critical_high": 39.5,
        "warning_low": 35.5,
        "critical_low": 34.5,
    },
    "hrv": {
        "warning_low": 20,
        "critical_low": 10,
    },
}


def compute_risk(vitals: VitalSigns) -> RiskAssessment:
    """Compute a composite risk score from vital signs."""
    score = 0
    factors: list[str] = []

    hr = vitals.heart_rate
    hr_thresh = THRESHOLDS["heart_rate"]
    if hr >= hr_thresh["critical_high"]:
        score += 30
        factors.append(f"Heart rate critically high ({hr:.0f} bpm)")
    elif hr >= hr_thresh["warning_high"]:
        score += 15
        factors.append(f"Heart rate elevated ({hr:.0f} bpm)")
    elif hr <= hr_thresh["critical_low"]:
        score += 30
        factors.append(f"Heart rate critically low ({hr:.0f} bpm)")
    elif hr <= hr_thresh["warning_low"]:
        score += 15
        factors.append(f"Heart rate low ({hr:.0f} bpm)")

    spo2 = vitals.spo2
    spo2_thresh = THRESHOLDS["spo2"]
    if spo2 <= spo2_thresh["critical_low"]:
        score += 35
        factors.append(f"SpO2 critically low ({spo2:.1f}%)")
    elif spo2 <= spo2_thresh["warning_low"]:
        score += 18
        factors.append(f"SpO2 below normal ({spo2:.1f}%)")

    temp = vitals.temperature
    temp_thresh = THRESHOLDS["temperature"]
    if temp >= temp_thresh["critical_high"]:
        score += 25
        factors.append(f"Temperature critically high ({temp:.1f}°C)")
    elif temp >= temp_thresh["warning_high"]:
        score += 12
        factors.append(f"Temperature elevated ({temp:.1f}°C)")
    elif temp <= temp_thresh["critical_low"]:
        score += 25
        factors.append(f"Temperature critically low ({temp:.1f}°C)")
    elif temp <= temp_thresh["warning_low"]:
        score += 12
        factors.append(f"Temperature below normal ({temp:.1f}°C)")

    hrv = vitals.hrv
    hrv_thresh = THRESHOLDS["hrv"]
    if hrv <= hrv_thresh["critical_low"]:
        score += 20
        factors.append(f"HRV critically low ({hrv:.1f} ms) — high stress/autonomic dysfunction")
    elif hrv <= hrv_thresh["warning_low"]:
        score += 10
        factors.append(f"HRV reduced ({hrv:.1f} ms)")

    abnormal_count = len(factors)
    if abnormal_count >= 3:
        score = int(score * 1.3)
        factors.append("⚠ Multiple vitals abnormal — compounding risk applied")
    elif abnormal_count == 2:
        score = int(score * 1.15)

    score = max(0, min(100, score))

    if score >= 81:
        level: RiskLevel = "CRITICAL"
    elif score >= 61:
        level = "HIGH"
    elif score >= 31:
        level = "MODERATE"
    else:
        level = "LOW"

    summary = (
        "All vitals within normal range. No concerns detected."
        if not factors
        else f"Risk score {score}/100 ({level}). Issues: {'; '.join(factors)}"
    )

    return RiskAssessment(
        score=score,
        level=level,
        contributing_factors=factors,
        summary=summary,
    )
