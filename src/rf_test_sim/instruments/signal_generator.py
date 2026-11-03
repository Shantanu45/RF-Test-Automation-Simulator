""" It translates Python method calls into SCPI commands that the instrument understands."""

from rf_test_sim.instruments.visa_session import ScpiInstrument


class SignalGenerator(ScpiInstrument):
    #set frequency and power
    def configure(self, frequency_hz: float, power_dbm: float) -> None:
        self.set_value(f"FREQ {frequency_hz:.11e}")
        self.set_value(f"POW {power_dbm:.11e}")
    #switch the RF signal on or off
    def output(self, enabled: bool) -> None:
        self.set_value(f"OUTP {int(enabled)}")
    # read the current settings
    def state(self) -> tuple[float, float, bool]:
        return self.number("FREQ?"), self.number("POW?"), self.flag("OUTP?")
