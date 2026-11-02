class ConfigurationError(ValueError):
    """Configuration does not satisfy the measurement contract."""


class InstrumentError(RuntimeError):
    """Instrument communication or response validation failed."""


class InstrumentTimeout(InstrumentError):
    """A bounded instrument operation timed out."""


class StorageError(RuntimeError):
    """A run could not be saved or retrieved."""
