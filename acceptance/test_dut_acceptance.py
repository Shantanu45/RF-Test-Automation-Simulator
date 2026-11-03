"""Engineering acceptance: a configured out-of-limit DUT must fail this suite."""

import os
from pathlib import Path

import pytest

from rf_test_sim.config import load_config
from rf_test_sim.domain import Execution, Verdict
from rf_test_sim.simulation.bench import SimulationBench
from rf_test_sim.workflow import execute

pytestmark = pytest.mark.acceptance


def test_configured_dut_meets_limits() -> None:
    config = load_config(
        Path(os.environ.get("RF_ACCEPTANCE_CONFIG", "configs/demo.yaml"))
    )
    result = execute(config, SimulationBench)
    assert result.execution == Execution.COMPLETED, result.errors
    assert result.verdict == Verdict.PASS, result.points
