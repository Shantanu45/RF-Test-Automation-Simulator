from rf_test_sim.errors import InstrumentError
from rf_test_sim.instruments.visa_session import ScpiInstrument


class SpectrumAnalyzer(ScpiInstrument):
    def configure(self, center_hz: float, span_hz: float, bandwidth_hz: float) -> None:
        self.set_value(f"FREQ:CENT {center_hz:.11e}")
        self.set_value(f"FREQ:SPAN {span_hz:.11e}")
        self.set_value(f"BAND {bandwidth_hz:.11e}")

    def settings(self) -> tuple[float, float, float]:
        return self.number("FREQ:CENT?"), self.number("FREQ:SPAN?"), self.number("BAND?")

    def trigger(self) -> None:
        if self.query("INIT") != "OK" or not self.flag("*OPC?"):
            raise InstrumentError("acquisition did not complete")

    def read(self) -> tuple[float | None, float]:
        carrier = self.number("READ:CARR?") if self.flag("READ:VALID?") else None
        return carrier, self.number("READ:NOISE?")
