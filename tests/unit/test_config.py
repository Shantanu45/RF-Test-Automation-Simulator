from pathlib import Path

import pytest

from rf_test_sim.config import RunConfig, VisaConfig, load_config
from rf_test_sim.errors import ConfigurationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        "typo: 3",
        "model: {gaim_db: 20}",
        "frequencies_hz: []",
        "powers_dbm: [0]",
        "bandwidth_hz: .nan",
        "visa: {timeout_ms: true}",
        "dut_id: 12",
        "gain_limit: {lower: 22, upper: 20}",
        "frequencies_hz: null",
        "model: {noise_figure_db: -1}",
        "span_hz: 1",
        "[]",
        "",
    ],
)
def test_invalid_configuration(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_snapshot_has_explicit_units() -> None:
    snapshot = RunConfig().snapshot()
    assert snapshot["frequencies_hz"] == [1e9]
    assert snapshot["model"]["gain_db"] == 20


def test_reject_wrong_terminators() -> None:
    with pytest.raises(ConfigurationError):
        VisaConfig(write_termination="\r\n")
