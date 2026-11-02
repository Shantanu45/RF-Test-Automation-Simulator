import json
from pathlib import Path

import pytest

from rf_test_sim.config import RunConfig
from rf_test_sim.delivery import deliver
from rf_test_sim.errors import StorageError
from rf_test_sim.persistence.artifacts import read_artifact
from rf_test_sim.persistence.memory import MemoryRepository
from rf_test_sim.workflow import execute

pytestmark = pytest.mark.unit


def error_document() -> dict:
    def unavailable(_: RunConfig) -> None:
        raise RuntimeError("unavailable")

    return execute(RunConfig(), unavailable).document()


def test_storage_outage_keeps_replayable_artifact(tmp_path: Path) -> None:
    def unavailable() -> MemoryRepository:
        raise StorageError("database offline")

    result = deliver(error_document(), tmp_path, unavailable)
    assert result.persistence == "ERROR"
    assert result.report == "NOT_GENERATED"
    document = read_artifact(result.artifact)
    repository = MemoryRepository()
    replay = deliver(document, tmp_path, lambda: repository)
    assert replay.persistence == "SAVED"
    assert replay.report == "GENERATED"
    assert repository.load(document["run_id"]) == document


def test_report_failure_separate_from_measurement_and_storage(tmp_path: Path) -> None:
    def broken(*args: object) -> None:
        raise OSError("disk full")

    repository = MemoryRepository()
    result = deliver(error_document(), tmp_path, lambda: repository, renderer=broken)
    assert result.persistence == "SAVED"
    assert result.report == "ERROR"
    status = json.loads(result.status_path.read_text())
    assert status["errors"][0]["type"] == "OSError"
    assert read_artifact(result.artifact)["execution"] == "ERROR"


def test_idempotent_immutable_repository() -> None:
    repository = MemoryRepository()
    document = error_document()
    repository.save(document)
    repository.save(document)
    document["software_version"] = "different"
    with pytest.raises(StorageError, match="different"):
        repository.save(document)


def test_reject_invalid_artifact(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"schema_version": 1, "run_id": "../../escape"}', encoding="utf-8")
    with pytest.raises(StorageError):
        read_artifact(path)
