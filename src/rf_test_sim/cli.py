import argparse
import json
import logging
import os
import signal
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType

from rf_test_sim.config import load_config
from rf_test_sim.delivery import deliver
from rf_test_sim.domain import Execution, Verdict
from rf_test_sim.errors import ConfigurationError, StorageError
from rf_test_sim.persistence.artifacts import read_artifact
from rf_test_sim.persistence.mongodb import MongoRepository
from rf_test_sim.persistence.protocols import RunRepository
from rf_test_sim.simulation.bench import SimulationBench
from rf_test_sim.workflow import execute


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Simulated CW RF acceptance testing")
    commands = root.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="execute a measurement run")
    run.add_argument("--config", type=Path, required=True)
    replay = commands.add_parser("replay", help="persist an existing recovery artifact")
    replay.add_argument("artifact", type=Path)
    for command in (run, replay):
        command.add_argument("--output", type=Path, default=Path("artifacts"))
        command.add_argument(
            "--offline", action="store_true", help="generate a local-source report"
        )
    return root


def interrupt_run(signal_number: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def main(arguments: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    options = parser().parse_args(arguments)
    signal.signal(signal.SIGTERM, interrupt_run)
    try:
        uri = os.environ.get("MONGODB_URI")
        if not options.offline and not uri:
            raise ConfigurationError("set MONGODB_URI or select --offline")
        if options.command == "run":
            config = load_config(options.config)
            document = execute(config, SimulationBench).document()
        else:
            document = read_artifact(options.artifact)
        factory: Callable[[], RunRepository] | None = None
        if not options.offline:

            def mongo_repository() -> RunRepository:
                return MongoRepository(
                    uri or "", os.environ.get("MONGODB_DATABASE", "rf_sim")
                )

            factory = mongo_repository
        result = deliver(document, options.output, factory)
        print(
            json.dumps(
                {
                    "run_id": document["run_id"],
                    "verdict": document["verdict"],
                    "execution": document["execution"],
                    "persistence": result.persistence,
                    "report": result.report,
                    "artifact": str(result.artifact),
                }
            )
        )
        if result.errors:
            return 3
        if document["execution"] == Execution.ABORTED:
            return 130
        if document["execution"] != Execution.COMPLETED:
            return 3
        return 0 if document["verdict"] == Verdict.PASS else 1
    except ConfigurationError as error:
        logging.error("configuration: %s", error)
        return 2
    except (OSError, StorageError):
        logging.error("artifact or storage operation failed")
        return 3
    except KeyboardInterrupt:
        logging.error("delivery or configuration interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
