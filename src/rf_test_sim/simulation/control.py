from rf_test_sim.instruments.visa_session import ScpiInstrument
from rf_test_sim.rf_model import ModelReading


class SimulationControl:
    """Private bench control port; these commands are never hardware SCPI."""

    def __init__(self, analyzer: ScpiInstrument) -> None:
        self.analyzer = analyzer

    def invalidate(self) -> None:
        self.analyzer.set_value("SIM:VALID 0")

    def load(self, reading: ModelReading) -> None:
        self.invalidate()
        self.analyzer.set_value(f"SIM:NOISE {reading.noise_dbm:.11e}")
        if reading.carrier_dbm is not None:
            self.analyzer.set_value(f"SIM:CARR {reading.carrier_dbm:.11e}")
            self.analyzer.set_value("SIM:VALID 1")
