from copy import deepcopy
from typing import Any

from rf_test_sim.errors import StorageError
from rf_test_sim.persistence.artifacts import validate_document


class MemoryRepository:
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    def save(self, document: dict[str, Any]) -> None:
        document = validate_document(document)
        run_id = document["run_id"]
        if run_id in self._documents and self._documents[run_id] != document:
            raise StorageError("run ID already contains different results")
        self._documents[run_id] = deepcopy(document)

    def load(self, run_id: str) -> dict[str, Any]:
        try:
            return deepcopy(self._documents[run_id])
        except KeyError as error:
            raise StorageError("run not found") from error

    def close(self) -> None:
        pass
