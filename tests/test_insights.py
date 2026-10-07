from __future__ import annotations

import json
from pathlib import Path

from fabricops.config import load_configuration
from fabricops.engine import Executor, Planner
from fabricops.insights import drift_snapshot, health_snapshot
from fabricops.state import StateStore

CONFIG = Path("config/examples/synthetic-healthcare/project.yml")


def test_drift_is_empty_after_apply(tmp_path: Path) -> None:
    config = load_configuration(CONFIG)
    store = StateStore(tmp_path / "state.json")
    Executor(store).apply(config, Planner(store).create(config, "all"))

    assert drift_snapshot(config, store)["summary"] == {
        "missing": 0,
        "changed": 0,
        "unexpected": 0,
    }


def test_retry_requires_explicit_policy_and_failure(tmp_path: Path) -> None:
    config = load_configuration(CONFIG)
    store = StateStore(tmp_path / "state.json")
    store.save(
        {
            "resources": {},
            "jobs": {
                "ingest-operational-events": {"status": "failed", "attempts": 0},
                "publish-care-unit-metrics": {"status": "failed", "attempts": 0},
            },
        }
    )

    report = health_snapshot(config, store)
    items = {item["name"]: item for item in report["items"]}

    assert items["ingest-operational-events"]["retry_eligible"] is True
    assert items["publish-care-unit-metrics"]["retry_eligible"] is False
    assert "deny-by-default" in items["publish-care-unit-metrics"]["retry_reason"]


def test_missing_telemetry_is_unknown_not_healthy(tmp_path: Path) -> None:
    config = load_configuration(CONFIG)
    report = health_snapshot(config, StateStore(tmp_path / "state.json"))

    assert report["summary"] == {"unknown": 2}
    assert all(item["status"] == "unknown" for item in report["items"])


def test_drift_detects_changed_resource(tmp_path: Path) -> None:
    config = load_configuration(CONFIG)
    store = StateStore(tmp_path / "state.json")
    Executor(store).apply(config, Planner(store).create(config, "all"))
    state = store.load()
    first_key = next(iter(state["resources"]))
    state["resources"][first_key]["properties"] = {"tampered": True}
    store.save(state)

    report = drift_snapshot(config, store)

    assert report["summary"]["changed"] == 1
    assert json.dumps(report)
