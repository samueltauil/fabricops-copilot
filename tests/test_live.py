from __future__ import annotations

from fabricops.live import FabricRestClient, HttpResponse, discover_configured_workspaces


def test_workspace_discovery_paginates_and_masks_ids() -> None:
    responses = iter(
        [
            HttpResponse(
                200,
                {},
                {
                    "value": [
                        {
                            "id": "workspace-secret-id",
                            "displayName": "fab-demo-dev",
                            "type": "Workspace",
                            "capacityId": "capacity-nonprod",
                        }
                    ],
                    "continuationUri": "https://api.fabric.microsoft.com/v1/workspaces?page=2",
                },
            ),
            HttpResponse(200, {}, {"value": []}),
        ]
    )

    def transport(method, url, headers, body):
        assert method == "GET"
        assert headers["Authorization"] == "Bearer token"
        return next(responses)

    workspaces = FabricRestClient(lambda: "token", transport=transport).list_workspaces()
    report = discover_configured_workspaces(
        {"dev": {"workspaceName": "fab-demo-dev", "capacityRef": "shared-nonprod"}},
        workspaces,
        {"shared-nonprod": "capacity-nonprod"},
    )

    item = report["configuredWorkspaces"][0]
    assert item["status"] == "found"
    assert item["capacityMatches"] is True
    assert item["workspaceIdHash"] != "workspace-secret-id"


def test_transient_error_is_retried(monkeypatch) -> None:
    calls = 0

    def transport(method, url, headers, body):
        nonlocal calls
        calls += 1
        if calls == 1:
            return HttpResponse(429, {"Retry-After": "0"}, {"errorCode": "Throttled"})
        return HttpResponse(200, {}, {"value": []})

    client = FabricRestClient(lambda: "token", transport=transport)

    assert client.list_workspaces() == []
    assert calls == 2

