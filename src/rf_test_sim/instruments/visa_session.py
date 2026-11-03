import math

from pyvisa import constants
from pyvisa.errors import VisaIOError

from rf_test_sim.errors import InstrumentError, InstrumentTimeout
from rf_test_sim.instruments.protocols import MessageResource


class ScpiInstrument:
    def __init__(self, resource: MessageResource, expected_identity: str) -> None:
        self.resource = resource
        self.identity = self.query("*IDN?")
        if not self.identity.startswith(expected_identity + ","):
            raise InstrumentError("unexpected instrument identity")

    def query(self, command: str) -> str:
        try:
            response = self.resource.query(command).strip()
        except VisaIOError as error:
            if error.error_code == constants.StatusCode.error_timeout:
                raise InstrumentTimeout(
                    f"timeout during {command.split()[0]}"
                ) from error
            raise InstrumentError(
                f"VISA failure during {command.split()[0]}"
            ) from error
        if not response or response == "ERROR":
            raise InstrumentError(f"invalid response to {command.split()[0]}")
        return response

    def set_value(self, command: str) -> None:
        if self.query(command) != "OK":
            raise InstrumentError(f"setter rejected: {command.split()[0]}")

    def number(self, command: str) -> float:
        try:
            value = float(self.query(command))
        except ValueError as error:
            raise InstrumentError(f"nonnumeric response to {command}") from error
        if not math.isfinite(value):
            raise InstrumentError(f"nonfinite response to {command}")
        return value

    def flag(self, command: str) -> bool:
        response = self.query(command)
        if response not in ("0", "1"):
            raise InstrumentError(f"invalid boolean response to {command}")
        return response == "1"
