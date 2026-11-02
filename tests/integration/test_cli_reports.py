import json
import os
import subprocess
import sys
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import pytest

from rf_test_sim.config import RunConfig
from rf_test_sim.delivery import deliver
from rf_test_sim.reporting.renderer import render
from rf_test_sim.simulation.bench import SimulationBench
from rf_test_sim.workflow import execute

pytestmark = pytest.mark.sim


def test_package_data_present() -> None:
    package = files("rf_test_sim")
    assert package.joinpath("simulation/instruments.yaml").is_file()
    assert package.joinpath("reporting/templates/run.html").is_file()


def test_report_escaping_and_json_agreement(tmp_path: Path) -> None:
    config = replace(RunConfig(), dut_id='<script>alert("DUT")</script>')
    document = execute(config, SimulationBench).document()
    result = deliver(document, tmp_path, None)
    html = (tmp_path / f"{document['run_id']}.report.html").read_text(encoding="utf-8")
    payload = json.loads((tmp_path / f"{document['run_id']}.report.json").read_text())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert payload["run"]["dut_id"] == config.dut_id
    assert payload["run"]["points"][0]["gain_db"] == 20
    assert "local recovery artifact (offline)" in html
    assert result.report == "GENERATED"


def test_sweep_charts_are_in_report(tmp_path: Path) -> None:
    config = RunConfig(frequencies_hz=(9e8, 1e9))
    document = execute(config, SimulationBench).document()
    _, html_path = render(document, tmp_path, "local")
    html = html_path.read_text()
    assert "gain_db versus frequency" in html
    assert "snr_db versus frequency" in html
    assert "<polyline" in html


def test_installed_cli_outside_repository(tmp_path: Path) -> None:
    config = tmp_path / "demo.yaml"
    config.write_text("{}", encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "rf_test_sim.cli",
            "run",
            "--config",
            str(config),
            "--offline",
            "--output",
            str(tmp_path / "output"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["verdict"] == "PASS"
    assert result["persistence"] == "LOCAL_ONLY"


def test_cli_requires_explicit_storage_choice(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment.pop("MONGODB_URI", None)
    process = subprocess.run(
        [sys.executable, "-m", "rf_test_sim.cli", "run", "--config", "missing.yaml"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == 2
