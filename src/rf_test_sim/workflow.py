"""coordinates a complete test run: it requests measurements, handles failures, closes the bench, and returns a record of what happened"""

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

"""
Args:
    config: the test settings, including frequencies, powers, bandwidth, and acceptance limits.
    bench_factory: a callable that creates the measurement bench using those settings.
"""
def execute(config: RunConfig, bench_factory: Callable[[RunConfig], MeasurementBench]) -> RunRecord:
    # for traceability
    started = datetime.now(UTC).isoformat()
    run_id = str(uuid4())           #Gives this run a unique identifier
    snapshot = config.snapshot()    #Keeps a serializable copy of the settings
    config_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()         #Provides a fingerprint of those settings, The hash helps detect configuration changes. It does not prove that the measurements are correct.

    # creates empty collections for measurement points, errors, and instrument identities
    points: list[PointResult] = []
    errors: list[dict[str, str]] = []
    identities: dict[str, str] = {}
    execution = Execution.COMPLETED
    bench = None
    try:
        #Creating SimulationBench opens the virtual instruments and prepares them for use
        bench = bench_factory(config)
        identities = bench.identities

        #Measure every frequency/power combination
        #produces:
        #| point_id | Frequency | Input power |
        #|---|  ---  |  ---    |
        #| 0 | 1 GHz | −30 dBm |
        #| 1 | 1 GHz | −20 dBm |
        #| 2 | 2 GHz | −30 dBm |
        #| 3 | 2 GHz | −20 dBm |
        for point_id, (frequency, power) in enumerate(
            product(config.frequencies_hz, config.powers_dbm)
        ):
            logger.info("run=%s point=%s acquiring", run_id, point_id)
            try:
                #Read this from the inside outward:
                #1. bench.measure(...) configures the instruments and returns an Observation containing readings.
                #2. calculate(...) converts those readings into gain, SNR, and limit decisions.
                #3. points.append(...) retains the resulting PointResult.
                points.append(calculate(point_id, bench.measure(frequency, power), config))
            except Exception as error:
                #If instrument communication or calculation raises an exception, the function:
                #- Creates a point containing the requested frequency, power, and bandwidth.
                #- Marks that point’s execution as ERROR.
                #- Adds a generic error description.
                #- Uses raise to pass the exception to the outer handler.
                #This preserves both earlier successful measurements and the location where the sweep failed. Acquisition stops at that first execution error.
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
    #Distinguish interruption from failure
    except KeyboardInterrupt:
        execution = Execution.ABORTED
        errors.append({"type": "KeyboardInterrupt", "message": "run interrupted"})
    #This handles ordinary failures
    except Exception as error:
        execution = Execution.ERROR
        errors.append({"type": type(error).__name__, "message": "measurement execution failed"})
        logger.error("run=%s failed: %s", run_id, type(error).__name__)
    #Always attempt cleanup
    finally:
        if bench is not None:
            try:
                cleanup_errors = bench.close()
            except Exception as error:
                cleanup_errors = [{"type": type(error).__name__, "message": "bench cleanup failed"}]
            errors.extend(cleanup_errors)
            if cleanup_errors and execution == Execution.COMPLETED:
                execution = Execution.ERROR

    #The function only assigns an overall PASS or FAIL if execution completed and every expected point was collected.
    #| Condition                                           | Overall verdict |
    #|                        ---                          |        ---      |
    #| Every point passed                                  |        PASS     |
    #| Every point has a decision, and at least one failed |        FAIL     |
    #| Execution failed, was interrupted, or a required decision is unavailable | NOT_EVALUATED |
    expected_count = len(config.frequencies_hz) * len(config.powers_dbm)
    verdict = Verdict.NOT_EVALUATED
    if execution == Execution.COMPLETED and len(points) == expected_count:
        if all(point.verdict == Verdict.PASS for point in points):
            verdict = Verdict.PASS
        elif all(point.verdict != Verdict.NOT_EVALUATED for point in points):
            verdict = Verdict.FAIL

    #Finally, the function builds a RunRecord containing the identifiers, timestamps, configuration, instrument identities, points, verdict, execution state, and errors.
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
