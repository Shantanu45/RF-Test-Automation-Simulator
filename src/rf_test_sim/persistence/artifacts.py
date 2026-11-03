import hashlib
import json
import os
import tempfile
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from rf_test_sim.config import parse_config
from rf_test_sim.domain import PointResult, RunRecord, finite
from rf_test_sim.errors import StorageError

MAX_DOCUMENT_BYTES = 12 * 1024 * 1024


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.dumps(document, allow_nan=False, sort_keys=True)
        normalized = json.loads(payload)
        if not isinstance(normalized, dict):
            raise ValueError("document must be a mapping")
        if len(payload.encode()) > MAX_DOCUMENT_BYTES:
            raise ValueError("run document exceeds size bound")
        if normalized["schema_version"] != 1:
            raise ValueError("unsupported schema")
        if not isinstance(normalized["run_id"], str):
            raise ValueError("run_id must be a string")
        if str(UUID(normalized["run_id"])) != normalized["run_id"]:
            raise ValueError("run_id must be a canonical UUID")
        if normalized["execution"] not in ("COMPLETED", "ERROR", "ABORTED"):
            raise ValueError("invalid execution state")
        if normalized["verdict"] not in ("PASS", "FAIL", "NOT_EVALUATED"):
            raise ValueError("invalid verdict")
        required = (
            "started_at",
            "finished_at",
            "dut_id",
            "config",
            "config_hash",
            "instruments",
            "points",
            "errors",
            "software_version",
            "model_version",
            "seed",
            "assumptions",
        )
        if any(key not in normalized for key in required):
            raise ValueError("missing run fields")
        if not isinstance(normalized["points"], list):
            raise ValueError("points must be a list")
        if set(normalized) != {item.name for item in fields(RunRecord)}:
            raise ValueError("unexpected run fields")
        config = parse_config(normalized["config"])
        expected_hash = hashlib.sha256(
            json.dumps(normalized["config"], sort_keys=True).encode()
        ).hexdigest()
        if (
            normalized["config_hash"] != expected_hash
            or normalized["dut_id"] != config.dut_id
        ):
            raise ValueError("configuration provenance mismatch")
        for name in ("started_at", "finished_at"):
            if datetime.fromisoformat(normalized[name]).utcoffset() is None:
                raise ValueError("timestamps must include timezone")
        expected_count = len(config.frequencies_hz) * len(config.powers_dbm)
        if len(normalized["points"]) > expected_count:
            raise ValueError("too many point records")
        for index, point in enumerate(normalized["points"]):
            if not isinstance(point, dict) or set(point) != {
                item.name for item in fields(PointResult)
            }:
                raise ValueError("invalid point fields")
            if point["point_id"] != index:
                raise ValueError("point sequence mismatch")
            for name in (
                "frequency_hz",
                "generator_power_dbm",
                "bandwidth_hz",
                "dut_input_dbm",
                "analyzer_carrier_dbm",
                "analyzer_noise_dbm",
                "dut_output_dbm",
                "gain_db",
                "snr_db",
            ):
                if point[name] is not None:
                    finite(name, point[name])
            if point["verdict"] not in ("PASS", "FAIL", "NOT_EVALUATED"):
                raise ValueError("invalid point verdict")
            if point["execution"] not in ("COMPLETED", "ERROR", "ABORTED"):
                raise ValueError("invalid point execution")
        if normalized["verdict"] == "PASS":
            if (
                normalized["execution"] != "COMPLETED"
                or len(normalized["points"]) != expected_count
                or any(point["verdict"] != "PASS" for point in normalized["points"])
            ):
                raise ValueError("incomplete run cannot pass")
        return normalized
    except (ValueError, TypeError, KeyError) as error:
        raise StorageError("invalid or oversized run document") from error


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, document: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(document, indent=2, allow_nan=False) + "\n")


def read_artifact(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise StorageError("artifact exceeds size bound")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("artifact is not a mapping")
        return validate_document(document)
    except (ValueError, TypeError) as error:
        raise StorageError("invalid recovery artifact") from error
