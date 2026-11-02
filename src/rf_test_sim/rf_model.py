"""Linear CW model; noise powers are integrated over equivalent noise bandwidth."""

import math
from dataclasses import dataclass

from rf_test_sim.config import ModelConfig
from rf_test_sim.domain import finite
from rf_test_sim.errors import ConfigurationError

BOLTZMANN = 1.380649e-23
REFERENCE_TEMPERATURE_K = 290.0


def dbm_to_watts(power_dbm: float) -> float:
    finite("power_dbm", power_dbm)
    try:
        watts = 10 ** ((power_dbm - 30) / 10)
    except OverflowError as error:
        raise ConfigurationError("power cannot be represented in watts") from error
    if not math.isfinite(watts) or watts <= 0:
        raise ConfigurationError("power cannot be represented in watts")
    return watts


def watts_to_dbm(power_w: float) -> float:
    finite("power_w", power_w)
    if power_w <= 0:
        raise ConfigurationError("power_w must be positive")
    return 10 * math.log10(power_w) + 30


def cable_noise(noise_w: float, loss_db: float, temperature_k: float, bandwidth_hz: float) -> float:
    transmission = 10 ** (-loss_db / 10)
    return noise_w * transmission + BOLTZMANN * temperature_k * bandwidth_hz * (1 - transmission)


@dataclass(frozen=True)
class ModelReading:
    carrier_dbm: float | None
    noise_dbm: float


def simulate(
    model: ModelConfig,
    frequency_hz: float,
    power_dbm: float,
    bandwidth_hz: float,
    output_enabled: bool = True,
) -> ModelReading:
    for name, value in (
        ("frequency_hz", frequency_hz),
        ("power_dbm", power_dbm),
        ("bandwidth_hz", bandwidth_hz),
    ):
        finite(name, value)
    if not model.frequency_min_hz <= frequency_hz <= model.frequency_max_hz:
        raise ConfigurationError("frequency outside model range")
    if not 0 < bandwidth_hz <= 1e12:
        raise ConfigurationError("invalid equivalent noise bandwidth")
    dut_input = power_dbm - model.input_loss_db
    if not model.input_min_dbm <= dut_input <= model.input_max_dbm:
        raise ConfigurationError("DUT input outside linear model range")
    gain = 10 ** (model.gain_db / 10)
    noise_factor = 10 ** (model.noise_figure_db / 10)
    source_noise = BOLTZMANN * model.source_temperature_k * bandwidth_hz
    input_noise = cable_noise(source_noise, model.input_loss_db, model.temperature_k, bandwidth_hz)
    added_noise = BOLTZMANN * REFERENCE_TEMPERATURE_K * bandwidth_hz * (noise_factor - 1)
    output_noise = gain * (input_noise + added_noise)
    analyzer_noise = cable_noise(
        output_noise, model.output_loss_db, model.temperature_k, bandwidth_hz
    )
    if model.analyzer_noise_dbm_hz is not None:
        analyzer_noise += dbm_to_watts(model.analyzer_noise_dbm_hz) * bandwidth_hz
    carrier = dut_input + model.gain_db - model.output_loss_db if output_enabled else None
    return ModelReading(carrier, watts_to_dbm(analyzer_noise))
