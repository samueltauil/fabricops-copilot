from __future__ import annotations

from pathlib import Path

from fabricops.config import load_configuration
from fabricops.live import FabricRestClient, HttpResponse
from fabricops.live_provision import provision_live

CONFIG = Path("config/examples/synthetic-healthcare/project.yml")
GROUPS = {
    "fabric-platform-admins": "g-admin",
    "care-data-engineers": "g-eng",
    "care-operations-consumers": "g-view",
}
CAPS = {"shared-nonprod": "cap-np", "production": "cap-p"}


class FakeFabric:
    def __init__(self) -> None:
        self.workspaces: list[dict] = []
        self.roles: dict[str, list[dict]] = {}

    def __call__(self, method, url, headers, body):
        import json

        path = url.split("/v1", 1)[1]
        data = json.loads(body) if body else {}
        if method == "GET" and path == "/workspaces":
            return HttpResponse(200, {}, {"value": self.workspaces})
        if method == "POST" and path == "/workspaces":
            ws = {
                "id": f"ws{len(self.workspaces)}",
                "displayName": data["displayName"],
                "type": "Workspace",
                "capacityId": data["capacityId"],
            }
            self.workspaces.append(ws)
            return HttpResponse(201, {}, ws)
        if path.endswith("/roleAssignments"):
            wid = path.split("/")[2]
            if method == "GET":
                return HttpResponse(200, {}, {"value": self.roles.get(wid, [])})
            self.roles.setdefault(wid, []).append(
                {"principal": {"id": data["principal"]["id"]}, "role": data["role"]}
            )
            return HttpResponse(201, {}, {})
        raise AssertionError(f"{method} {path}")


def test_live_provision_preview_then_apply_is_idempotent() -> None:
    config = load_configuration(CONFIG)
    fake = FakeFabric()
    client = FabricRestClient(lambda: "t", transport=fake)

    preview = provision_live(client, config, GROUPS, CAPS, apply=False)
    assert fake.workspaces == []
    assert preview["environments"][0]["actions"][0]["action"] == "create"

    provision_live(client, config, GROUPS, CAPS, apply=True)
    assert len(fake.workspaces) == 3

    rerun = provision_live(client, config, GROUPS, CAPS, apply=True)
    actions = {a["action"] for e in rerun["environments"] for a in e["actions"]}
    assert actions == {"no-op"}
    assert len(fake.workspaces) == 3
