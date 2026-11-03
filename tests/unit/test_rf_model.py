import math
from dataclasses import replace

import pytest

from rf_test_sim.config import ModelConfig
from rf_test_sim.domain import Limit, Verdict, evaluate
from rf_test_sim.errors import ConfigurationError
from rf_test_sim.rf_model import dbm_to_watts, simulate, watts_to_dbm

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("dbm,watts", [(0, 0.001), (30, 1), (-30, 0.000001)])
def test_power_conversions(dbm: float, watts: float) -> None:
    assert dbm_to_watts(dbm) == pytest.approx(watts, rel=1e-12)
    assert watts_to_dbm(watts) == pytest.approx(dbm, abs=1e-12)


def test_independent_thermal_reference() -> None:
    reading = simulate(ModelConfig(), 1e9, -30, 1e6)
    assert reading.carrier_dbm == -10
    assert reading.noise_dbm == pytest.approx(-88.975187, abs=0.00001)
    assert reading.carrier_dbm - reading.noise_dbm == pytest.approx(
        78.975187, abs=0.00001
    )


def test_tenfold_bandwidth_adds_ten_db_noise() -> None:
    narrow = simulate(ModelConfig(), 1e9, -30, 1e5)
    wide = simulate(ModelConfig(), 1e9, -30, 1e6)
    assert wide.noise_dbm - narrow.noise_dbm == pytest.approx(10, abs=1e-12)
    assert wide.carrier_dbm == narrow.carrier_dbm


def test_cable_noise_and_corrected_gain() -> None:
    model = ModelConfig(input_loss_db=2, output_loss_db=3)
    reading = simulate(model, 1e9, -30, 1e6)
    assert reading.carrier_dbm == -15
    assert reading.carrier_dbm + 3 - (-30 - 2) == 20
    expected_watts = (
        1.380649e-23 * 290 * 1e6 * 100 * 10**0.5 * 10**-0.3
        + 1.380649e-23 * 290 * 1e6 * (1 - 10**-0.3)
    )
    assert reading.noise_dbm == pytest.approx(10 * math.log10(expected_watts) + 30)


def test_analyzer_noise_added_in_linear_power() -> None:
    ideal = simulate(ModelConfig(), 1e9, -30, 1e6)
    noisy = simulate(
        ModelConfig(analyzer_noise_dbm_hz=ideal.noise_dbm - 60), 1e9, -30, 1e6
    )
    assert noisy.noise_dbm - ideal.noise_dbm == pytest.approx(3.01029995664)


def test_output_off_has_noise_but_no_carrier() -> None:
    reading = simulate(ModelConfig(), 1e9, -30, 1e6, output_enabled=False)
    assert reading.carrier_dbm is None
    assert math.isfinite(reading.noise_dbm)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True])
def test_reject_nonfinite_and_boolean_model_values(value: float) -> None:
    with pytest.raises(ConfigurationError):
        ModelConfig(gain_db=value)


@pytest.mark.parametrize("bandwidth", [0, -1, float("nan")])
def test_invalid_bandwidth(bandwidth: float) -> None:
    with pytest.raises(ConfigurationError):
        simulate(ModelConfig(), 1e9, -30, bandwidth)


def test_outside_linear_range() -> None:
    with pytest.raises(ConfigurationError):
        simulate(ModelConfig(), 1e9, 0, 1e6)


@pytest.mark.parametrize(
    "value,verdict",
    [
        (19, Verdict.PASS),
        (21, Verdict.PASS),
        (18.999999, Verdict.FAIL),
        (21.000001, Verdict.FAIL),
        (None, Verdict.NOT_EVALUATED),
        (float("nan"), Verdict.NOT_EVALUATED),
    ],
)
def test_inclusive_limits_without_rounding(
    value: float | None, verdict: Verdict
) -> None:
    assert evaluate("gain", value, Limit(19, 21)).verdict == verdict


def test_guard_bands_and_invalid_limits() -> None:
    limit = Limit(19, 21, 0.25)
    assert evaluate("gain", 19.25, limit).margin_db == 0
    assert evaluate("gain", 19.1, limit).verdict == Verdict.FAIL
    with pytest.raises(ConfigurationError):
        replace(limit, guard_band=2)
