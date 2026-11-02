from typing import Protocol

from rf_test_sim.domain import Observation


class MessageResource(Protocol):
    def query(self, command: str, /) -> str: ...

    def write(self, command: str, /) -> int: ...

    def close(self) -> None: ...


class MeasurementBench(Protocol):
    @property
    def identities(self) -> dict[str, str]: ...

    def measure(self, frequency_hz: float, power_dbm: float) -> Observation: ...

    def close(self) -> list[dict[str, str]]: ...
