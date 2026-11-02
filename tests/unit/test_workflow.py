from dataclasses import replace

import pytest

from rf_test_sim.config import ModelConfig, RunConfig
from rf_test_sim.domain import Execution, Observation, Verdict
from rf_test_sim.measurements import calculate
from rf_test_sim.workflow import execute

pytestmark = pytest.mark.unit


class FailingBench:
    identities = {"generator": "test", "analyzer": "test"}

    def __init__(self, *, cleanup_error: bool = False) -> None:
        self.closed = False
        self.count = 0
        self.cleanup_error = cleanup_error

    def measure(self, frequency_hz: float, power_dbm: float) -> Observation:
        self.count += 1
        if self.count == 2:
            raise TimeoutError("simulated timeout")
        return Observation(frequency_hz, power_dbm, -10, -89, 1e6)

    def close(self) -> list[dict[str, str]]:
        self.closed = True
        if self.cleanup_error:
            return [{"type": "CleanupError", "message": "RF off failed"}]
        return []


def test_partial_sweep_cannot_pass_and_closes() -> None:
    bench = FailingBench()
    config = RunConfig(frequencies_hz=(9e8, 1e9, 1.1e9))
    result = execute(config, lambda _: bench)
    assert bench.closed
    assert len(result.points) == 2
    assert result.points[0].verdict == Verdict.PASS
    assert result.points[1].execution == Execution.ERROR
    assert result.verdict == Verdict.NOT_EVALUATED
    assert result.execution == Execution.ERROR


def test_cleanup_error_prevents_overall_pass() -> None:
    bench = FailingBench(cleanup_error=True)
    result = execute(RunConfig(), lambda _: bench)
    assert result.execution == Execution.ERROR
    assert result.verdict == Verdict.NOT_EVALUATED
    assert result.errors[0]["type"] == "CleanupError"


def test_interruption_is_recorded() -> None:
    def interrupted(_: RunConfig) -> FailingBench:
        raise KeyboardInterrupt

    result = execute(RunConfig(), interrupted)
    assert result.execution == Execution.ABORTED
    assert result.verdict == Verdict.NOT_EVALUATED


def test_absent_carrier_cannot_pass() -> None:
    config = RunConfig()
    point = calculate(0, Observation(1e9, -30, None, -89, 1e6, "RF off"), config)
    assert point.gain_db is None and point.snr_db is None
    assert point.verdict == Verdict.NOT_EVALUATED


def test_raw_and_corrected_reference_planes() -> None:
    config = replace(RunConfig(), model=ModelConfig(input_loss_db=2, output_loss_db=3))
    point = calculate(0, Observation(1e9, -30, -15, -90, 1e6), config)
    assert point.dut_input_dbm == -32
    assert point.dut_output_dbm == -12
    assert point.gain_db == 20
    assert point.snr_db == 75
