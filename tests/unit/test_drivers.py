import pytest
from pyvisa import constants
from pyvisa.errors import VisaIOError

from rf_test_sim.errors import InstrumentError, InstrumentTimeout
from rf_test_sim.instruments.signal_generator import SignalGenerator

pytestmark = pytest.mark.unit


class ScriptedResource:
    def __init__(self, response: str = "OK") -> None:
        self.response = response
        self.commands: list[str] = []
        self.timeout = False

    def query(self, command: str) -> str:
        self.commands.append(command)
        if self.timeout:
            raise VisaIOError(constants.StatusCode.error_timeout)
        return "RF-SIM,GENERATOR,UNIT,1" if command == "*IDN?" else self.response

    def write(self, command: str) -> int:
        return len(command)

    def close(self) -> None:
        pass


def test_scpi_formatting() -> None:
    resource = ScriptedResource()
    driver = SignalGenerator(resource, "RF-SIM,GENERATOR")
    driver.configure(1e9, -30)
    driver.output(True)
    assert resource.commands == [
        "*IDN?",
        "FREQ 1.00000000000e+09",
        "POW -3.00000000000e+01",
        "OUTP 1",
    ]


@pytest.mark.parametrize("response", ["NaN", "inf", "garbage", "ERROR", ""])
def test_bad_response(response: str) -> None:
    driver = SignalGenerator(ScriptedResource(response), "RF-SIM,GENERATOR")
    with pytest.raises(InstrumentError):
        driver.number("POW?")


def test_timeout_classification_preserves_cause() -> None:
    resource = ScriptedResource()
    driver = SignalGenerator(resource, "RF-SIM,GENERATOR")
    resource.timeout = True
    with pytest.raises(InstrumentTimeout) as captured:
        driver.number("POW?")
    assert isinstance(captured.value.__cause__, VisaIOError)


def test_identity_mismatch() -> None:
    with pytest.raises(InstrumentError, match="identity"):
        SignalGenerator(ScriptedResource(), "OTHER,MODEL")
