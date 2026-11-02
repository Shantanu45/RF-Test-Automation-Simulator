import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from itertools import product
from uuid import uuid4

from rf_test_sim.config import RunConfig
from rf_test_sim.domain import Execution, PointResult, RunRecord, Verdict
from rf_test_sim.instruments.protocols import MeasurementBench
from rf_test_sim.measurements import calculate

logger = logging.getLogger(__name__)


def execute(config: RunConfig, bench_factory: Callable[[RunConfig], MeasurementBench]) -> RunRecord:
    started = datetime.now(UTC).isoformat()
    run_id = str(uuid4())
    snapshot = config.snapshot()
    config_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    points: list[PointResult] = []
    errors: list[dict[str, str]] = []
    identities: dict[str, str] = {}
    execution = Execution.COMPLETED
    bench = None
    try:
        bench = bench_factory(config)
        identities = bench.identities
        for point_id, (frequency, power) in enumerate(
            product(config.frequencies_hz, config.powers_dbm)
        ):
            logger.info("run=%s point=%s acquiring", run_id, point_id)
            try:
                points.append(calculate(point_id, bench.measure(frequency, power), config))
            except Exception as error:
                detail = {"type": type(error).__name__, "message": "point acquisition failed"}
                points.append(
                    PointResult(
                        point_id,
                        frequency,
                        power,
                        config.bandwidth_hz,
                        execution=Execution.ERROR,
                        errors=(detail,),
                    )
                )
                raise
    except KeyboardInterrupt:
        execution = Execution.ABORTED
        errors.append({"type": "KeyboardInterrupt", "message": "run interrupted"})
    except Exception as error:
        execution = Execution.ERROR
        errors.append({"type": type(error).__name__, "message": "measurement execution failed"})
        logger.error("run=%s failed: %s", run_id, type(error).__name__)
    finally:
        if bench is not None:
            try:
                cleanup_errors = bench.close()
            except Exception as error:
                cleanup_errors = [{"type": type(error).__name__, "message": "bench cleanup failed"}]
            errors.extend(cleanup_errors)
            if cleanup_errors and execution == Execution.COMPLETED:
                execution = Execution.ERROR
    expected_count = len(config.frequencies_hz) * len(config.powers_dbm)
    verdict = Verdict.NOT_EVALUATED
    if execution == Execution.COMPLETED and len(points) == expected_count:
        if all(point.verdict == Verdict.PASS for point in points):
            verdict = Verdict.PASS
        elif all(point.verdict != Verdict.NOT_EVALUATED for point in points):
            verdict = Verdict.FAIL
    return RunRecord(
        run_id,
        started,
        datetime.now(UTC).isoformat(),
        config.dut_id,
        snapshot,
        config_hash,
        identities,
        tuple(points),
        verdict,
        execution,
        tuple(errors),
    )
