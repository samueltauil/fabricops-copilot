from __future__ import annotations

import json
from pathlib import Path

import pytest

from fabricops.config import load_configuration
from fabricops.live import FabricRestClient, HttpResponse
from fabricops.live_deploy import DeploymentError, deploy_live

CONFIG = Path("config/examples/synthetic-healthcare/project.yml")


class FakeFabric:
    def __init__(self) -> None:
        self.items: dict[str, list[dict]] = {}
        self.workspaces = [
            {"id": f"ws-{n}", "displayName": f"fab-northwind-care-{n}", "type": "Workspace"}
            for n in ("dev", "test", "prod")
        ]

    def __call__(self, method, url, headers, body):
        path = url.split("/v1", 1)[1]
        if path == "/workspaces":
            return HttpResponse(200, {}, {"value": self.workspaces})
        workspace_id = path.split("/")[2]
        if method == "GET":
            return HttpResponse(200, {}, {"value": self.items.get(workspace_id, [])})
        data = json.loads(body)
        self.items.setdefault(workspace_id, []).append(
            {"displayName": data["displayName"], "type": data["type"]}
        )
        return HttpResponse(201, {}, {})


def test_deploy_is_idempotent() -> None:
    fake = FakeFabric()
    client = FabricRestClient(lambda: "t", transport=fake)
    config = load_configuration(CONFIG)

    deploy_live(client, config, apply=True)
    rerun = deploy_live(client, config, apply=True)

    assert all(len(items) == 3 for items in fake.items.values())
    assert {a["action"] for e in rerun["environments"] for a in e["actions"]} == {"no-op"}


def test_unsupported_item_blocks(tmp_path: Path) -> None:
    raw = CONFIG.read_text(encoding="utf-8").replace("- DataPipeline", "- Report")
    changed = tmp_path / "project.yml"
    changed.write_text(raw, encoding="utf-8")
    client = FabricRestClient(lambda: "t", transport=FakeFabric())

    with pytest.raises(DeploymentError, match="Unsupported"):
        deploy_live(client, load_configuration(changed), apply=False)
