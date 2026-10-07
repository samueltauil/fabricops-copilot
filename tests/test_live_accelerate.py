from __future__ import annotations

import json
from pathlib import Path

from fabricops.config import load_configuration
from fabricops.live import FabricRestClient, HttpResponse
from fabricops.live_accelerate import OneLakeFiles, accelerate_live

CONFIG = Path("config/examples/synthetic-healthcare/project.yml")


class FakeFabric:
    def __init__(self, reject: set[str] | None = None) -> None:
        self.reject = reject or set()
        self.items = [
            {"id": "lh1", "displayName": "care_lakehouse", "type": "Lakehouse"},
            {"id": "nb1", "displayName": "care_notebook", "type": "Notebook"},
        ]
        self.definition_updates = 0

    def __call__(self, method, url, headers, body):
        path = url.split("/v1", 1)[1]
        if path == "/workspaces":
            return HttpResponse(
                200, {}, {"value": [{"id": "ws", "displayName": "fab-northwind-care-dev", "type": "Workspace"}]}
            )
        if method == "GET":
            return HttpResponse(200, {}, {"value": self.items})
        if path.endswith("/updateDefinition"):
            self.definition_updates += 1
            return HttpResponse(200, {}, {})
        if method == "PATCH":
            self.items[1]["description"] = json.loads(body)["description"]
            return HttpResponse(200, {}, {})
        data = json.loads(body)
        if data["type"] in self.reject:
            return HttpResponse(400, {}, {"errorCode": "UnsupportedItemType"})
        self.items.append({"id": data["displayName"], **data})
        if data["type"] == "Eventhouse":
            self.items.append({"id": "kql", "displayName": data["displayName"], "type": "KQLDatabase"})
        return HttpResponse(201, {}, {})


class FakeDfs:
    def __init__(self) -> None:
        self.files: dict[str, int] = {}

    def __call__(self, method, url, headers, body):
        base = url.split("?")[0]
        if method == "HEAD":
            if base in self.files:
                return 200, {"Content-Length": str(self.files[base])}
            return 404, {}
        if method == "PUT":
            self.files[base] = 0
        elif "action=append" in url:
            self.files[base] += len(body)
        return 200, {}


def _data(tmp_path: Path) -> Path:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    for name in ("patients", "encounters", "observations"):
        (csv_dir / f"{name}.csv").write_text("Id,FIRST\nsecret-id,Jane\n", encoding="utf-8")
    return tmp_path


def test_accelerate_is_idempotent_and_reports_no_raw_data(tmp_path: Path) -> None:
    fabric, dfs = FakeFabric(), FakeDfs()
    client = FabricRestClient(lambda: "t", transport=fabric)
    onelake = OneLakeFiles(lambda: "t", transport=dfs)
    config = load_configuration(CONFIG)
    data = _data(tmp_path)

    first = accelerate_live(client, onelake, config, data, tmp_path, apply=True)
    second = accelerate_live(client, onelake, config, data, tmp_path, apply=True)

    assert [a["action"] for a in first["realTimeIntelligence"]][:2] == ["created", "created"]
    assert {u["action"] for u in first["syntheaUpload"]} == {"uploaded"}
    assert len(dfs.files) == 3
    assert {a["action"] for a in second["realTimeIntelligence"][:2]} == {"no-op"}
    assert {u["action"] for u in second["syntheaUpload"]} == {"no-op"}
    assert second["starterNotebook"]["action"] == "no-op"
    assert fabric.definition_updates == 1
    assert "secret-id" not in json.dumps(first) and "Jane" not in json.dumps(first)


def test_preview_does_not_mutate(tmp_path: Path) -> None:
    fabric, dfs = FakeFabric(), FakeDfs()
    client = FabricRestClient(lambda: "t", transport=fabric)
    report = accelerate_live(
        client, OneLakeFiles(lambda: "t", transport=dfs), load_configuration(CONFIG),
        _data(tmp_path), tmp_path, apply=False,
    )

    assert report["realTimeIntelligence"][0]["action"] == "create"
    assert not dfs.files and fabric.definition_updates == 0 and len(fabric.items) == 2


def test_unsupported_item_reported_honestly(tmp_path: Path) -> None:
    client = FabricRestClient(lambda: "t", transport=FakeFabric(reject={"Eventstream"}))
    report = accelerate_live(
        client, OneLakeFiles(lambda: "t", transport=FakeDfs()), load_configuration(CONFIG),
        _data(tmp_path), tmp_path, apply=True,
    )

    assert report["realTimeIntelligence"][1]["action"] == "manual/unsupported"
    assert report["realTimeIntelligence"][0]["action"] == "created"
