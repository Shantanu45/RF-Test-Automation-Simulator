from collections.abc import Iterator

import pytest

from rf_test_sim.config import RunConfig
from rf_test_sim.simulation.bench import SimulationBench


@pytest.fixture
def bench() -> Iterator[SimulationBench]:
    instance = SimulationBench(RunConfig())
    try:
        yield instance
    finally:
        assert instance.close() == []
