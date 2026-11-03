from typing import Any

import pytest

from rf_test_sim.config import RunConfig
from rf_test_sim.errors import InstrumentError
from rf_test_sim.simulation.bench import SimulationBench

pytestmark = pytest.mark.sim


def test_partial_setup_attempts_rf_off_and_closes_every_resource(
    monkeypatch: Any,
) -> None:
    events: list[str] = []

    class Resource:
        def __init__(self, name: str) -> None:
            self.name = name

        def query(self, command: str) -> str:
            events.append(f"{self.name}:{command}")
            if command == "*IDN?":
                return (
                    "RF-SIM,GENERATOR,1,1"
                    if self.name == "generator"
                    else "WRONG,MODEL,1,1"
                )
            return "OK"

        def close(self) -> None:
            events.append(f"close:{self.name}")

    class Manager:
        def open_resource(self, address: str, **kwargs: Any) -> Resource:
            return Resource("generator" if "generator" in address else "analyzer")

        def close(self) -> None:
            events.append("close:manager")

    monkeypatch.setattr(
        "rf_test_sim.simulation.bench.pyvisa.ResourceManager", lambda _: Manager()
    )
    with pytest.raises(InstrumentError, match="identity"):
        SimulationBench(RunConfig())
    assert "generator:OUTP 0" in events
    assert "close:analyzer" in events
    assert "close:generator" in events
    assert events[-1] == "close:manager"


def test_actual_terminator_mismatch_times_out(bench: SimulationBench) -> None:
    from rf_test_sim.errors import InstrumentTimeout

    resource = bench.generator.resource
    previous_timeout = resource.timeout
    resource.timeout = 50
    resource.write_termination = "\r"
    try:
        with pytest.raises((InstrumentTimeout, InstrumentError)):
            bench.generator.number("FREQ?")
    finally:
        resource.timeout = previous_timeout
        resource.write_termination = "\n"
        resource.write_raw(b"\n")
        resource.read()
        assert bench.generator.number("FREQ?") == 1e9
