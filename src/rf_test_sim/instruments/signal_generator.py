from rf_test_sim.instruments.visa_session import ScpiInstrument


class SignalGenerator(ScpiInstrument):
    def configure(self, frequency_hz: float, power_dbm: float) -> None:
        self.set_value(f"FREQ {frequency_hz:.11e}")
        self.set_value(f"POW {power_dbm:.11e}")

    def output(self, enabled: bool) -> None:
        self.set_value(f"OUTP {int(enabled)}")

    def state(self) -> tuple[float, float, bool]:
        return self.number("FREQ?"), self.number("POW?"), self.flag("OUTP?")
