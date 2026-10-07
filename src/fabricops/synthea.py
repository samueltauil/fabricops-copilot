from __future__ import annotations

import csv
import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

JAR_URL = (
    "https://github.com/synthetichealth/synthea/releases/download/"
    "master-branch-latest/synthea-with-dependencies.jar"
)
TABLES = ("patients", "encounters", "conditions", "observations", "organizations", "providers")


class SyntheaError(RuntimeError):
    pass


def synthea_settings(spec: dict[str, Any]) -> dict[str, Any]:
    values = {"seed": 42, "population": 25, "state": "Massachusetts", "city": "Boston"}
    values.update(spec.get("synthea", {}))
    values["population"] = int(values["population"])
    values["seed"] = int(values["seed"])
    if not 1 <= values["population"] <= 1000:
        raise SyntheaError("synthea.population must be between 1 and 1000")
    return values


def ensure_jar(tools_dir: Path) -> Path:
    jar = tools_dir / "synthea-with-dependencies.jar"
    if jar.exists():
        return jar
    if shutil.which("java") is None:
        raise SyntheaError("Java 11 or later is required to run Synthea")
    tools_dir.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(JAR_URL, jar)
    return jar


def generate(settings: dict[str, Any], output_dir: Path, tools_dir: Path) -> dict[str, Any]:
    jar = ensure_jar(tools_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    command = [
        "java", "-jar", str(jar),
        "-s", str(settings["seed"]),
        "-p", str(settings["population"]),
        "--exporter.baseDirectory", str(output_dir),
        "--exporter.csv.export", "true",
        "--exporter.fhir.export", "false",
        "--exporter.hospital.fhir.export", "false",
        "--exporter.practitioner.fhir.export", "false",
        str(settings["state"]), str(settings["city"]),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    if result.returncode != 0:
        raise SyntheaError(f"Synthea failed with exit code {result.returncode}")
    return summarize(output_dir)


def summarize(output_dir: Path) -> dict[str, Any]:
    csv_dir = output_dir / "csv"
    counts: dict[str, int] = {}
    digest = hashlib.sha256()
    for table in TABLES:
        path = csv_dir / f"{table}.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            counts[table] = max(sum(1 for _ in csv.reader(handle)) - 1, 0)
        digest.update(path.read_bytes())
    if not counts.get("patients"):
        raise SyntheaError("Synthea produced no patient records")
    return {"tableRowCounts": counts, "datasetHash": digest.hexdigest()[:16], "synthetic": True}
