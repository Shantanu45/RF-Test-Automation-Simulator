from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rf_test_sim.persistence.artifacts import atomic_json, validate_document
from rf_test_sim.persistence.protocols import RunRepository
from rf_test_sim.reporting.renderer import render


@dataclass(frozen=True)
class DeliveryResult:
    artifact: Path
    status_path: Path
    persistence: str
    report: str
    errors: tuple[dict[str, str], ...]


def deliver(
    document: dict[str, Any],
    output: Path,
    repository_factory: Callable[[], RunRepository] | None,
    renderer: Callable[..., Any] = render,
) -> DeliveryResult:
    document = validate_document(document)
    artifact = output / f"{document['run_id']}.json"
    atomic_json(artifact, document)
    status_path = output / f"{document['run_id']}.status.json"
    status: dict[str, Any] = {
        "run_id": document["run_id"],
        "persistence": "LOCAL_ONLY",
        "report": "PENDING",
        "errors": [],
    }
    atomic_json(status_path, status)
    repository = None
    saved = document
    source = "local recovery artifact (offline)"
    try:
        if repository_factory is not None:
            repository = repository_factory()
            repository.save(document)
            saved = repository.load(document["run_id"])
            source = "MongoDB readback"
            status["persistence"] = "SAVED"
    except Exception as error:
        status["persistence"] = "ERROR"
        status["report"] = "NOT_GENERATED"
        status["errors"].append(
            {"type": type(error).__name__, "message": "persistence failed"}
        )
    finally:
        if repository is not None:
            try:
                repository.close()
            except Exception as error:
                status["persistence"] = "ERROR"
                status["errors"].append(
                    {"type": type(error).__name__, "message": "close failed"}
                )
    if status["persistence"] != "ERROR":
        try:
            renderer(saved, output, source)
            status["report"] = "GENERATED"
        except Exception as error:
            status["report"] = "ERROR"
            status["errors"].append(
                {"type": type(error).__name__, "message": "report failed"}
            )
    atomic_json(status_path, status)
    return DeliveryResult(
        artifact,
        status_path,
        status["persistence"],
        status["report"],
        tuple(status["errors"]),
    )
