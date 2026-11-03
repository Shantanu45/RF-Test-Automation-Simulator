from dataclasses import replace

import pytest

from rf_test_sim.config import ModelConfig, RunConfig
from rf_test_sim.domain import Execution, Verdict
from rf_test_sim.errors import InstrumentError
from rf_test_sim.simulation.bench import SimulationBench
from rf_test_sim.workflow import execute

pytestmark = pytest.mark.sim


def test_generator_changes_propagate_to_analyzer(bench: SimulationBench) -> None:
    first = bench.measure(1e9, -30)
    second = bench.measure(1.1e9, -20)
    assert first.carrier_dbm == -10
    assert second.carrier_dbm == 0
    assert second.frequency_hz == 1.1e9
    assert second.noise_dbm == pytest.approx(-88.975187, abs=0.00001)
    assert bench.analyzer.number("READ:CARR?") == 0


@pytest.mark.parametrize("power,carrier", [(-21, -1), (-20, 0), (-19, 1)])
def test_single_digit_carrier_powers(
    bench: SimulationBench, power: float, carrier: float
) -> None:
    assert bench.measure(1e9, power).carrier_dbm == carrier


def test_rf_off_invalidates_previous_reading(bench: SimulationBench) -> None:
    bench.measure(1e9, -30)
    bench.generator.output(False)
    assert bench.acquire().carrier_dbm is None
    assert bench.analyzer.read()[0] is None


def test_independent_simulators_and_close(bench: SimulationBench) -> None:
    bench.measure(1e9, -20)
    other = SimulationBench(RunConfig())
    try:
        assert other.generator.state() == (1e9, -30, False)
        other.measure(9e8, -40)
        assert bench.generator.state() == (1e9, -20, True)
    finally:
        assert other.close() == []
    assert bench.close() == []
    assert bench.close() == []
    with pytest.raises(InstrumentError, match="closed"):
        bench.acquire()


@pytest.mark.parametrize(
    "model,verdict",
    [
        (ModelConfig(), Verdict.PASS),
        (ModelConfig(gain_db=17), Verdict.FAIL),
        (ModelConfig(noise_figure_db=20), Verdict.FAIL),
    ],
)
def test_dut_outcomes_are_software_regressions(
    model: ModelConfig, verdict: Verdict
) -> None:
    result = execute(replace(RunConfig(), model=model), SimulationBench)
    assert result.execution == Execution.COMPLETED
    assert result.verdict == verdict
    assert result.errors == ()


def test_full_sweep() -> None:
    config = RunConfig(frequencies_hz=(9e8, 1e9, 1.1e9), powers_dbm=(-30, -20))
    result = execute(config, SimulationBench)
    assert result.verdict == Verdict.PASS
    assert len(result.points) == 6
    assert all(point.gain_db == 20 for point in result.points)


def test_unknown_scpi_is_rejected(bench: SimulationBench) -> None:
    with pytest.raises(InstrumentError):
        bench.generator.query("UNKNOWN?")


def test_configuration_failure_does_not_leave_stale_measurement(
    bench: SimulationBench,
) -> None:
    bench.measure(1e9, -30)
    with pytest.raises(InstrumentError):
        bench.measure(2e12, -30)
    assert bench.analyzer.read()[0] is None
