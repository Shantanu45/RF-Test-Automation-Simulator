"""Think of it as the person operating the laboratory equipment: connecting instruments, choosing settings, taking readings, and switching everything off afterward"""
import logging
import shutil
import tempfile
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, cast

import pyvisa

from rf_test_sim.config import RunConfig
from rf_test_sim.domain import Observation
from rf_test_sim.errors import InstrumentError
from rf_test_sim.instruments.protocols import MessageResource
from rf_test_sim.instruments.signal_generator import SignalGenerator
from rf_test_sim.instruments.spectrum_analyzer import SpectrumAnalyzer
from rf_test_sim.rf_model import simulate
from rf_test_sim.simulation.control import SimulationControl

logger = logging.getLogger(__name__)

"""
Configures the signal generator
Configures the spectrum analyzer
Uses rf_model.py to predict the signal and noise
Returns the analyzer readings
"""
class SimulationBench:
    #It stores the configuration and prepares cleanup trackin
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self._stack = ExitStack()       #ExitStack is a cleanup organizer
        self._closed = False
        self._output_disable_attempted = False
        self._cleanup_errors: list[dict[str, str]] = []
        try:
            temporary = self._stack.enter_context(tempfile.TemporaryDirectory(prefix="rf-bench-"))
            resource = files("rf_test_sim").joinpath("simulation/instruments.yaml")
            with as_file(resource) as source:
                definition = Path(temporary) / "instruments.yaml"
                shutil.copyfile(source, definition)
            manager = pyvisa.ResourceManager(f"{definition}@sim")
            self._stack.callback(self._close_resource, manager)
            settings = config.visa
            generator_resource = manager.open_resource(
                settings.generator_resource,
                timeout=settings.timeout_ms,
                read_termination=settings.read_termination,
                write_termination=settings.write_termination,
            )
            self._stack.callback(self._close_resource, generator_resource)
            self.generator = SignalGenerator(
                cast(MessageResource, generator_resource), "RF-SIM,GENERATOR"
            )
            self._stack.callback(self._disable_output)
            analyzer_resource = manager.open_resource(
                settings.analyzer_resource,
                timeout=settings.timeout_ms,
                read_termination=settings.read_termination,
                write_termination=settings.write_termination,
            )
            self._stack.callback(self._close_resource, analyzer_resource)
            self.analyzer = SpectrumAnalyzer(
                cast(MessageResource, analyzer_resource), "RF-SIM,ANALYZER"
            )
            self.control = SimulationControl(self.analyzer)
            self.generator.output(False)
            self.control.invalidate()
        except BaseException as error:
            self._close_stack()
            for cleanup in self._cleanup_errors:
                error.add_note(f"cleanup failed: {cleanup['type']}")
            raise

    def _close_stack(self) -> None:
        try:
            self._stack.close()
        except Exception as error:
            self._cleanup_errors.append(
                {"type": type(error).__name__, "message": "bench context cleanup failed"}
            )

    def _close_resource(self, resource: Any) -> None:
        try:
            resource.close()
        except Exception as error:
            self._cleanup_errors.append({"type": type(error).__name__, "message": "close failed"})

    def _disable_output(self) -> None:
        if self._output_disable_attempted:
            return
        self._output_disable_attempted = True
        try:
            self.generator.output(False)
        except Exception as error:
            self._cleanup_errors.append({"type": type(error).__name__, "message": "RF off failed"})

    #identify the instruments
    @property
    def identities(self) -> dict[str, str]:
        return {"generator": self.generator.identity, "analyzer": self.analyzer.identity}

    #take a reading using the current settings
    def acquire(self) -> Observation:
        if self._closed:
            raise InstrumentError("bench is closed")
        self.control.invalidate()
        frequency, power, enabled = self.generator.state()
        center, span, bandwidth = self.analyzer.settings()
        if abs(frequency - center) > span / 2:
            raise InstrumentError("carrier outside analyzer span")

        #Calculate the simulated physical response
        reading = simulate(self.config.model, frequency, power, bandwidth, enabled)
        self.control.load(reading)
        self.analyzer.trigger()
        carrier, noise = self.analyzer.read()
        return Observation(
            frequency,
            power,
            carrier,
            noise,
            bandwidth,
            None if carrier is not None else "generator RF output is disabled",
        )

    #perform a measurement at requested settings
    def measure(self, frequency_hz: float, power_dbm: float) -> Observation:
        if self._closed:
            raise InstrumentError("bench is closed")
        self.control.invalidate()
        self.generator.configure(frequency_hz, power_dbm)
        self.generator.output(True)
        self.analyzer.configure(frequency_hz, self.config.span_hz, self.config.bandwidth_hz)
        result = self.acquire()
        if result.frequency_hz != frequency_hz or result.generator_power_dbm != power_dbm:
            raise InstrumentError("generator readback differs from requested settings")
        if result.bandwidth_hz != self.config.bandwidth_hz:
            raise InstrumentError("analyzer bandwidth readback differs from configuration")
        return result

    def close(self) -> list[dict[str, str]]:
        if not self._closed:
            self._closed = True
            self._disable_output()
            self._close_stack()
        return list(self._cleanup_errors)
