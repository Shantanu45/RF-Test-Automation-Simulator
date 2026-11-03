import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

from rf_test_sim.domain import Limit, finite
from rf_test_sim.errors import ConfigurationError

ConfigType = TypeVar("ConfigType")


def construct(record_type: type[ConfigType], values: Any) -> ConfigType:
    if not isinstance(values, dict):
        raise ConfigurationError(f"{record_type.__name__} must be a mapping")
    if not is_dataclass(record_type):
        raise TypeError("configuration record must be a dataclass")
    allowed = {item.name for item in fields(record_type)}
    if set(values) - allowed:
        raise ConfigurationError(
            f"unknown {record_type.__name__} keys: {set(values) - allowed}"
        )
    try:
        return cast(ConfigType, record_type(**values))
    except TypeError as error:
        raise ConfigurationError(f"invalid {record_type.__name__} fields") from error


@dataclass(frozen=True)
class ModelConfig:
    gain_db: float = 20.0
    noise_figure_db: float = 5.0
    frequency_min_hz: float = 1e8
    frequency_max_hz: float = 6e9
    input_min_dbm: float = -80.0
    input_max_dbm: float = -10.0
    input_loss_db: float = 0.0
    output_loss_db: float = 0.0
    temperature_k: float = 290.0
    source_temperature_k: float = 290.0
    analyzer_noise_dbm_hz: float | None = None

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value is not None or name != "analyzer_noise_dbm_hz":
                finite(name, value)
        for name in ("noise_figure_db", "input_loss_db", "output_loss_db"):
            if not 0 <= getattr(self, name) <= 100:
                raise ConfigurationError(f"{name} must be within 0..100 dB")
        if not -100 <= self.gain_db <= 100:
            raise ConfigurationError("gain_db must be within -100..100 dB")
        if not 1 <= self.frequency_min_hz <= self.frequency_max_hz <= 1e12:
            raise ConfigurationError("invalid frequency range")
        if not -200 <= self.input_min_dbm <= self.input_max_dbm <= 100:
            raise ConfigurationError("invalid linear input power range")
        if (
            not 0 < self.temperature_k <= 10000
            or not 0 < self.source_temperature_k <= 10000
        ):
            raise ConfigurationError(
                "temperatures must be within 0..10000 K, excluding zero"
            )
        if self.analyzer_noise_dbm_hz is not None:
            if not -300 <= self.analyzer_noise_dbm_hz <= 0:
                raise ConfigurationError(
                    "analyzer noise density must be within -300..0 dBm/Hz"
                )


@dataclass(frozen=True)
class VisaConfig:
    generator_resource: str = "TCPIP::generator::INSTR"
    analyzer_resource: str = "TCPIP::analyzer::INSTR"
    timeout_ms: int = 2000
    read_termination: str = "\n"
    write_termination: str = "\n"

    def __post_init__(self) -> None:
        if type(self.timeout_ms) is not int or not 1 <= self.timeout_ms <= 60000:
            raise ConfigurationError("timeout_ms must be an integer within 1..60000")
        if (self.generator_resource, self.analyzer_resource) != (
            "TCPIP::generator::INSTR",
            "TCPIP::analyzer::INSTR",
        ):
            raise ConfigurationError(
                "only the packaged simulator resources are supported"
            )
        if self.read_termination != "\n" or self.write_termination != "\n":
            raise ConfigurationError("packaged simulator requires newline terminators")


@dataclass(frozen=True)
class RunConfig:
    dut_id: str = "DEMO-AMP-001"
    frequencies_hz: tuple[float, ...] = (1e9,)
    powers_dbm: tuple[float, ...] = (-30.0,)
    bandwidth_hz: float = 1e6
    span_hz: float = 1e7
    model: ModelConfig = field(default_factory=ModelConfig)
    gain_limit: Limit = field(default_factory=lambda: Limit(19.0, 21.0))
    snr_limit: Limit = field(default_factory=lambda: Limit(70.0))
    visa: VisaConfig = field(default_factory=VisaConfig)

    def __post_init__(self) -> None:
        if not isinstance(self.dut_id, str) or not self.dut_id.strip():
            raise ConfigurationError("dut_id must be a nonempty string")
        for name in ("bandwidth_hz", "span_hz"):
            finite(name, getattr(self, name))
            if not 1e-6 <= getattr(self, name) <= 1e12:
                raise ConfigurationError(f"{name} must be within 1e-6..1e12 Hz")
        if self.span_hz < self.bandwidth_hz:
            raise ConfigurationError("span_hz must cover bandwidth_hz")
        if not self.frequencies_hz or not self.powers_dbm:
            raise ConfigurationError("sweep axes cannot be empty")
        if len(self.frequencies_hz) * len(self.powers_dbm) > 10000:
            raise ConfigurationError("sweep exceeds the 10000 point document limit")
        for frequency in self.frequencies_hz:
            finite("frequency_hz", frequency)
            if (
                not self.model.frequency_min_hz
                <= frequency
                <= self.model.frequency_max_hz
            ):
                raise ConfigurationError("frequency outside model range")
        for power in self.powers_dbm:
            finite("power_dbm", power)
            if not -200 <= power <= 100:
                raise ConfigurationError("generator power outside simulator range")
            dut_input = power - self.model.input_loss_db
            if not self.model.input_min_dbm <= dut_input <= self.model.input_max_dbm:
                raise ConfigurationError("DUT input power outside linear model range")

    def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), allow_nan=False))


def parse_config(values: Any) -> RunConfig:
    if not isinstance(values, dict):
        raise ConfigurationError("configuration must be a mapping")
    values = dict(values)
    for name, record_type in (
        ("model", ModelConfig),
        ("visa", VisaConfig),
        ("gain_limit", Limit),
        ("snr_limit", Limit),
    ):
        if name in values:
            values[name] = construct(record_type, values[name])
    for name in ("frequencies_hz", "powers_dbm"):
        if name in values:
            if not isinstance(values[name], list):
                raise ConfigurationError(f"{name} must be a list")
            values[name] = tuple(values[name])
    return construct(RunConfig, values)


def load_config(path: Path) -> RunConfig:
    import yaml

    try:
        return parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError("cannot read configuration YAML") from error
