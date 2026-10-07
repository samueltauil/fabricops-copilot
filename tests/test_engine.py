from __future__ import annotations

from pathlib import Path

import pytest

from fabricops.config import load_configuration
from fabricops.engine import Executor, PlanError, Planner
from fabricops.state import StateStore

CONFIG = Path("config/examples/synthetic-healthcare/project.yml")


def test_mock_apply_is_idempotent(tmp_path: Path) -> None:
    config = load_configuration(CONFIG)
    store = StateStore(tmp_path / "state.json")
    first = Planner(store).create(config, "all")
    result = Executor(store).apply(config, first)
    second = Planner(store).create(config, "all")

    assert result["verified"] is True
    assert first.summary()["create"] > 0
    assert second.summary() == {"no-op": len(second.changes)}


def test_stale_plan_is_rejected(tmp_path: Path) -> None:
    config = load_configuration(CONFIG)
    store = StateStore(tmp_path / "state.json")
    plan = Planner(store).create(config, "provision")
    object.__setattr__(config, "config_hash", "changed")

    with pytest.raises(PlanError, match="stale"):
        Executor(store).apply(config, plan)


def test_direct_user_admin_is_rejected(tmp_path: Path) -> None:
    raw = CONFIG.read_text(encoding="utf-8").replace(
        "fabric-platform-admins", "person@example.com"
    )
    changed = tmp_path / "project.yml"
    changed.write_text(raw, encoding="utf-8")
    config = load_configuration(changed)
    plan = Planner(StateStore(tmp_path / "state.json")).create(config, "provision")

    assert "Direct user administrators" in plan.policy_findings[0]

