# RF Test Automation Simulator

A Python CW amplifier test bench using real PyVISA sessions backed by PyVISA-sim. It sweeps generator frequency/power, applies a linear amplifier and thermal-noise model, reads simulated analyzer measurements, evaluates gain/SNR limits, saves the run to MongoDB, and renders HTML/JSON reports.

## Run with Docker Compose

Install Docker Engine/Desktop with Compose v2 and Linux containers. From this directory:

```powershell
docker compose build simulator
docker compose run --rm simulator
```

Compose starts MongoDB, waits for its health check, then runs the application. Reports and recovery artifacts appear in `artifacts/`. MongoDB data resides in the `mongo-data` named volume. Neither database exposes a host port. The included database is a local development service on an isolated internal network; configure authentication and secrets before deployment to shared infrastructure.

The app runs as UID 10001. On Linux, make the bind-mounted `artifacts/` directory writable by this UID before running. On Docker Desktop, the shared workspace normally supplies write access.

```powershell
docker compose --profile test build tests
docker compose --profile test run --rm tests
docker compose down
```

The test service runs linting, type checking, pytest regressions, and the demonstration DUT acceptance suite. It uses a separate, disposable `mongo-test` service with an in-memory data volume. Each database test also creates a unique temporary database. Test XML and coverage are written to `artifacts/`. `docker compose --profile test down` also stops the test database; adding `--volumes` deletes the application database permanently.

To run without a database, override the command and disable dependency startup:

```powershell
docker compose run --rm --no-deps simulator run --config /app/configs/demo.yaml --output /artifacts --offline
```

## Configuration and acceptance

Edit `configs/demo.yaml` or add a YAML file under `configs/`, which is mounted read-only in the container:

```powershell
docker compose run --rm simulator run --config /app/configs/my_dut.yaml --output /artifacts
```

Unknown keys, nonfinite values, invalid limits, unsupported resources, and sweep points outside the model's frequency/linear-input ranges are rejected. Frequencies and equivalent noise bandwidth are Hz; powers are dBm; gain/loss/noise figure/SNR are dB; temperatures are kelvin. All limits are demonstration settings requiring engineering approval for an actual DUT.

The sweep is the Cartesian product of `frequencies_hz` and `powers_dbm`, capped at 10000 points. `gain_limit` and `snr_limit` accept `lower`, `upper`, and `guard_band`. Boundaries are inclusive after applying the guard band inward. Decisions use stored values before display formatting; instrument replies use 12 significant figures.

`model` defines flat gain, noise figure, linear input limits, cable losses/temperature, source temperature, and optional analyzer noise density in dBm/Hz. `analyzer_noise_dbm_hz: null` selects an ideal analyzer. Noise figure references 290 K. Passive cables add thermal noise as well as attenuating power. With the nominal 1 GHz / -30 dBm / 1 MHz case, carrier power is -10 dBm, noise is approximately -88.975187 dBm, gain is 20 dB, and SNR is 78.975187 dB.

DUT input power is inferred from generator power minus input cable loss. DUT output power corrects the analyzer carrier for output cable loss. SNR is measured at the analyzer plane, including output cable and analyzer noise. Source thermal noise remains present when RF carrier output is disabled. There is no carrier in that state, so gain and SNR are unavailable. The model excludes phase noise, mismatch, compression, modulation, and distortion. It is deterministic; `seed` is null because no random variation is implemented.

## Results, failure recovery, and exit codes

Each run produces:

- `<run-id>.json`: atomic recovery record containing full configuration, hash, instrument identity, measurements, limits, assumptions, timestamps, errors, and versions.
- `<run-id>.status.json`: persistence/report status tracked separately from RF acceptance.
- `<run-id>.report.html` and `.report.json`: human/machine reports, including gain/SNR frequency plots for sweeps.

The application writes and flushes the recovery record before contacting MongoDB. A successful database save is reloaded before report generation. Offline reports identify their local source explicitly. MongoDB saves are idempotent: replaying the same run does not duplicate it, and different content with the same ID is rejected. Records are bounded to 12 MiB, below the MongoDB document limit.

On storage failure, use the retained artifact after restoring MongoDB:

```powershell
docker compose run --rm simulator replay /artifacts/REPLACE-WITH-RUN-ID.json --output /artifacts
```

Replay never reacquires measurements. Report generation can also be retried with this command after a report error. Do not edit a stored artifact: changed content with an existing run ID conflicts with the database record. Preserve artifacts if a run fails; diagnostic errors deliberately omit connection strings/credentials.

| Exit code | Meaning |
| --- | --- |
| 0 | Completed and accepted; persistence/reporting succeeded (or explicit offline mode) |
| 1 | Completed but failed limits or required metrics unavailable |
| 2 | Invalid configuration/arguments or missing storage selection |
| 3 | Measurement, cleanup, storage, or report execution error |
| 130 | Interrupted run, when its artifacts were delivered successfully |

RF verdicts (`PASS`, `FAIL`, `NOT_EVALUATED`) are distinct from execution (`COMPLETED`, `ERROR`, `ABORTED`) and delivery state. An errored or incomplete sweep never passes. Acquisition stops on the first execution error and retains prior points plus the failed point. Teardown attempts RF off and closure of every opened resource, including partially opened benches.

## Local Python development

Python 3.12 and 3.13 are the supported targets; the Docker image uses 3.12. Use a virtual environment:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -c requirements.lock ".[dev]"
.venv/Scripts/rf-test run --config configs/demo.yaml --offline
.venv/Scripts/python -m pytest tests acceptance
.venv/Scripts/python -m ruff format src tests acceptance scripts
.venv/Scripts/python -m ruff check src tests acceptance scripts
.venv/Scripts/python -m mypy src
```

`requirements.lock` pins direct and transitive dependencies for the supported Python targets. It is consumed as a pip constraints file and needs no host VISA driver. Build-time setuptools is pinned separately in `pyproject.toml`. The Docker build, dependency checks, Ruff, mypy, and full 76-case suite have passed on Linux/Python 3.12 with real PyVISA-sim and MongoDB. CI additionally targets Windows and Python 3.13; those matrix runs have not been executed locally.

MongoDB tests skip locally unless `TEST_MONGODB_URI` explicitly enables them; unreachable configured databases fail rather than skip. Use a disposable MongoDB instance, never a production database. `MONGODB_URI` and optional `MONGODB_DATABASE` configure normal runs. Credentials belong in environment/secrets, not YAML or source control. No `.env` file is required for the provided isolated Compose setup.

`tests/` verifies software behavior, including correct rejection of bad DUTs. `acceptance/` asserts that a selected DUT actually passes and therefore fails for out-of-limit configurations:

```powershell
docker compose --profile test run --rm --entrypoint python tests -m pytest acceptance
docker compose --profile test run --rm -e RF_ACCEPTANCE_CONFIG=configs/my_dut.yaml --entrypoint python tests -m pytest acceptance
```

For a new acceptance config, rebuild the test image because its configuration files are copied at build time. CI covers Python 3.12/3.13 on Windows/Linux and a Compose job with real MongoDB. Build artifacts include the simulator YAML and escaped report template; an integration test invokes the installed package outside the project directory.

## Design and extension

`config.py` validates inputs; `domain.py`, `rf_model.py`, and `measurements.py` hold records and pure calculations. `workflow.py` executes the injected `MeasurementBench` interface. Instrument drivers own SCPI formatting/parsing, while `simulation/bench.py` owns resource lifecycle and acquisition coupling. `SimulationControl` injects RF-model measurements through dedicated `SIM:*` commands; the analyzer reads them through its normal measurement queries. No PyVISA-sim internals are modified. Each bench uses a unique temporary definition path to isolate backend state, and measurements run serially.

The SCPI profile is a deliberately small simulation contract, including acknowledged setters. It is not a physical vendor profile and does not implement a general reset/error queue. Physical instruments require new vendor drivers, acquisition synchronization, noise estimation and bandwidth corrections, calibration, and uncertainty/guard-band approval. They can be introduced through `MeasurementBench` without changing the RF decision or repository code.

`persistence/` implements in-memory and MongoDB repositories; `delivery.py` coordinates recovery/persistence/reporting. `reporting/` renders saved results with HTML escaping and inline SVG sweep plots, requiring no browser or plotting server. See `IMPLEMENTATION_PLAN.md` for the measurement contract and milestone acceptance criteria.
