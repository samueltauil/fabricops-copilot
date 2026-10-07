from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from fabricops.config import load_configuration
from fabricops.live import FabricRestClient, HttpResponse, LiveConfigurationError
from fabricops.live_govern import (
    govern_live,
    inject_demo_drift,
    render_markdown,
    revert_demo_drift,
)

CONFIG = Path("config/examples/synthetic-healthcare/project.yml")
GROUPS = {
    "fabric-platform-admins": "aaaaaaaa-0000-0000-0000-000000000001",
    "care-data-engineers": "aaaaaaaa-0000-0000-0000-000000000002",
    "care-operations-consumers": "aaaaaaaa-0000-0000-0000-000000000003",
}
CAPS = {"shared-nonprod": "cap-nonprod", "production": "cap-prod"}
EXTRA = "bbbbbbbb-0000-0000-0000-00000000beef"


def notebook_payload(text: str) -> dict:
    payload = base64.b64encode(text.encode()).decode()
    return {"definition": {"parts": [{"path": "a.ipynb", "payload": payload}]}}


class FakeFabric:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.workspaces = []
        self.roles: dict[str, list[dict]] = {}
        self.items: dict[str, list[dict]] = {}
        self.notebook_text = "ENVIRONMENT = 'x'"
        for n in ("dev", "test", "prod"):
            wid = f"ws-{n}"
            cap = "cap-prod" if n == "prod" else "cap-nonprod"
            self.workspaces.append(
                {"id": wid, "displayName": f"fab-northwind-care-{n}", "type": "Workspace",
                 "capacityId": cap}
            )
            self.roles[wid] = [
                {"id": g, "principal": {"id": g, "type": "Group"}, "role": r}
                for g, r in zip(GROUPS.values(), ("Admin", "Contributor", "Viewer"), strict=True)
            ]
            self.items[wid] = [
                {"id": f"{wid}-{t}", "displayName": f"care_{t.lower()}", "type": t}
                for t in ("Lakehouse", "Notebook", "DataPipeline")
            ]

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        path = url.split("/v1", 1)[1]
        if path == "/workspaces":
            return HttpResponse(200, {}, {"value": self.workspaces})
        parts = path.split("/")
        wid = parts[2]
        if parts[3] == "items" and len(parts) == 4:
            return HttpResponse(200, {}, {"value": self.items[wid]})
        if parts[3] == "items" and parts[5] == "getDefinition":
            return HttpResponse(200, {}, notebook_payload(self.notebook_text))
        if parts[3] == "roleAssignments":
            if method == "GET":
                return HttpResponse(200, {}, {"value": self.roles[wid]})
            if method == "POST":
                data = json.loads(body)
                self.roles[wid].append(
                    {"id": data["principal"]["id"], "principal": data["principal"],
                     "role": data["role"]}
                )
                return HttpResponse(201, {}, {})
            if method == "DELETE":
                self.roles[wid] = [r for r in self.roles[wid] if r["id"] != parts[4]]
                return HttpResponse(200, {}, {})
        raise AssertionError(path)


def run(fake: FakeFabric) -> dict:
    client = FabricRestClient(lambda: "t", transport=fake)
    return govern_live(client, load_configuration(CONFIG), GROUPS, CAPS)


def categories(report: dict) -> set[str]:
    return {f["category"] for f in report["findings"]}


def test_clean_report_is_readonly() -> None:
    fake = FakeFabric()
    report = run(fake)
    assert report["status"] == "clean"
    assert report["driftCount"] == 0
    assert {m for m, u in fake.calls if "getDefinition" not in u} == {"GET"}


def test_detects_all_drift_kinds_and_sanitizes() -> None:
    fake = FakeFabric()
    fake.workspaces.pop(1)
    fake.workspaces[1]["capacityId"] = "cap-nonprod"
    fake.roles["ws-prod"].pop(0)
    fake.roles["ws-prod"].append({"id": EXTRA, "principal": {"id": EXTRA, "type": "User"},
                                  "role": "Admin"})
    fake.items["ws-prod"].pop(0)
    fake.notebook_text = "source fab-northwind-care-dev"
    report = run(fake)
    assert categories(report) == {
        "workspace-missing", "capacity-mismatch", "role-missing", "role-unexpected",
        "item-missing", "dev-reference",
    }
    text = json.dumps(report) + render_markdown(report)
    for raw in (EXTRA, *GROUPS.values(), "ws-prod", "cap-prod"):
        assert raw not in text
    severities = [f["severity"] for f in report["findings"]]
    assert severities[0] == "critical"
    assert all(f["remediation"] for f in report["findings"])


def test_dev_reference_not_flagged_in_dev() -> None:
    fake = FakeFabric()
    fake.notebook_text = "fab-northwind-care-dev"
    report = run(fake)
    assert {f["environment"] for f in report["findings"]} == {"test", "prod"}


def test_inject_requires_mutation_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FABRICOPS_ALLOW_LIVE_MUTATION", raising=False)
    client = FabricRestClient(lambda: "t", transport=FakeFabric())
    with pytest.raises(LiveConfigurationError):
        inject_demo_drift(client, load_configuration(CONFIG))


def test_inject_skips_without_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABRICOPS_ALLOW_LIVE_MUTATION", "1")
    monkeypatch.delenv("FABRICOPS_DRIFT_DEMO_PRINCIPAL", raising=False)
    fake = FakeFabric()
    result = inject_demo_drift(FabricRestClient(lambda: "t", transport=fake), load_configuration(CONFIG))
    assert result["applied"] is False
    assert all(m == "GET" for m, _ in fake.calls)


def test_inject_then_revert_only_touches_demo_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABRICOPS_ALLOW_LIVE_MUTATION", "1")
    monkeypatch.setenv("FABRICOPS_DRIFT_DEMO_PRINCIPAL", EXTRA)
    fake = FakeFabric()
    config = load_configuration(CONFIG)
    client = FabricRestClient(lambda: "t", transport=fake)
    assert inject_demo_drift(client, config)["applied"] is True
    assert "role-unexpected" in categories(run(fake))
    assert revert_demo_drift(client, config)["applied"] is True
    assert run(fake)["status"] == "clean"
    deletes = [u for m, u in fake.calls if m == "DELETE"]
    assert len(deletes) == 1 and deletes[0].endswith(f"/roleAssignments/{EXTRA}")
