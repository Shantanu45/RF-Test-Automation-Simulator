"""Measurement records. All power values are dBm unless named otherwise."""

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from rf_test_sim.errors import ConfigurationError


def finite(name: str, value: float) -> None:
    try:
        valid = (
            not isinstance(value, bool) and isinstance(value, int | float) and math.isfinite(value)
        )
    except OverflowError:
        valid = False
    if not valid:
        raise ConfigurationError(f"{name} must be a finite number")


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class Execution(StrEnum):
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    ABORTED = "ABORTED"


@dataclass(frozen=True)
class Limit:
    lower: float | None = None
    upper: float | None = None
    guard_band: float = 0.0

    def __post_init__(self) -> None:
        finite("guard_band", self.guard_band)
        for name, value in asdict(self).items():
            if value is not None:
                finite(name, value)
        if self.lower is None and self.upper is None:
            raise ConfigurationError("a limit needs at least one bound")
        if self.guard_band < 0:
            raise ConfigurationError("guard_band cannot be negative")
        if self.lower is not None and self.upper is not None:
            if self.lower + self.guard_band > self.upper - self.guard_band:
                raise ConfigurationError("limit bounds overlap after guard band")


@dataclass(frozen=True)
class LimitResult:
    metric: str
    value: float | None
    lower: float | None
    upper: float | None
    guard_band: float
    margin_db: float | None
    verdict: Verdict
    units: str = "dB"
    comparison: str = "inclusive; guard band applied inward"


def evaluate(metric: str, value: float | None, limit: Limit) -> LimitResult:
    margin = None
    verdict = Verdict.NOT_EVALUATED
    if value is not None and math.isfinite(value):
        margins = []
        if limit.lower is not None:
            margins.append(value - limit.lower - limit.guard_band)
        if limit.upper is not None:
            margins.append(limit.upper - limit.guard_band - value)
        margin = min(margins)
        verdict = Verdict.PASS if margin >= 0 else Verdict.FAIL
    return LimitResult(metric, value, limit.lower, limit.upper, limit.guard_band, margin, verdict)


@dataclass(frozen=True)
class Observation:
    frequency_hz: float
    generator_power_dbm: float
    carrier_dbm: float | None
    noise_dbm: float
    bandwidth_hz: float
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("frequency_hz", "generator_power_dbm", "noise_dbm", "bandwidth_hz"):
            finite(name, getattr(self, name))
        if self.carrier_dbm is not None:
            finite("carrier_dbm", self.carrier_dbm)
        if self.frequency_hz <= 0 or self.bandwidth_hz <= 0:
            raise ConfigurationError("observation frequency and bandwidth must be positive")


@dataclass(frozen=True)
class PointResult:
    point_id: int
    frequency_hz: float
    generator_power_dbm: float
    bandwidth_hz: float
    dut_input_dbm: float | None = None
    analyzer_carrier_dbm: float | None = None
    analyzer_noise_dbm: float | None = None
    dut_output_dbm: float | None = None
    gain_db: float | None = None
    snr_db: float | None = None
    limits: tuple[LimitResult, ...] = ()
    verdict: Verdict = Verdict.NOT_EVALUATED
    execution: Execution = Execution.COMPLETED
    unavailable_reason: str | None = None
    errors: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    started_at: str
    finished_at: str
    dut_id: str
    config: dict[str, Any]
    config_hash: str
    instruments: dict[str, str]
    points: tuple[PointResult, ...]
    verdict: Verdict
    execution: Execution
    errors: tuple[dict[str, str], ...] = ()
    schema_version: int = 1
    software_version: str = "0.1.0"
    model_version: str = "linear-thermal-v1"
    seed: int | None = None
    assumptions: tuple[str, ...] = field(
        default=(
            "50-ohm matched CW system; generator power is calibrated available power",
            "DUT input power inferred using configured input cable loss",
            "SNR uses analyzer-plane noise integrated over equivalent noise bandwidth",
            "Linear amplifier; phase noise, modulation and distortion excluded",
        )
    )

    def document(self) -> dict[str, Any]:
        return asdict(self)
