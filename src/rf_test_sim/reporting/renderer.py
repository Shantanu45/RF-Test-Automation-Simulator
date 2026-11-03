from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined

from rf_test_sim.persistence.artifacts import (
    atomic_json,
    atomic_text,
    validate_document,
)


def sweep_series(document: dict[str, Any]) -> list[dict[str, Any]]:
    series = []
    powers = sorted({point["generator_power_dbm"] for point in document["points"]})
    for power in powers:
        points = sorted(
            (
                point
                for point in document["points"]
                if point["generator_power_dbm"] == power
            ),
            key=lambda point: point["frequency_hz"],
        )
        for metric in ("gain_db", "snr_db"):
            valid = [point for point in points if point[metric] is not None]
            if len(valid) < 2 or len({point["frequency_hz"] for point in valid}) < 2:
                continue
            frequencies = [point["frequency_hz"] for point in valid]
            values = [point[metric] for point in valid]
            low, high = min(values) - 1, max(values) + 1
            width = max(frequencies) - min(frequencies)
            coordinates = " ".join(
                f"{50 + 500 * (point['frequency_hz'] - min(frequencies)) / width:.3f},"
                f"{170 - 140 * (point[metric] - low) / (high - low):.3f}"
                for point in valid
            )
            series.append(
                {
                    "metric": metric,
                    "power": power,
                    "coordinates": coordinates,
                    "low": low,
                    "high": high,
                    "frequency_low": min(frequencies),
                    "frequency_high": max(frequencies),
                }
            )
    return series


def render(document: dict[str, Any], output: Path, source: str) -> tuple[Path, Path]:
    document = validate_document(document)
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    template = environment.from_string(
        files("rf_test_sim")
        .joinpath("reporting/templates/run.html")
        .read_text(encoding="utf-8")
    )
    html = template.render(run=document, source=source, series=sweep_series(document))
    stem = f"{document['run_id']}.report"
    json_path, html_path = output / f"{stem}.json", output / f"{stem}.html"
    atomic_json(json_path, {"report_source": source, "run": document})
    atomic_text(html_path, html)
    return json_path, html_path
