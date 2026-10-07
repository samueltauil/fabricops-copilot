from __future__ import annotations

import os
from typing import Any

from fabricops.config import ProjectConfiguration
from fabricops.live import FabricApiError, FabricRestClient, LiveConfigurationError

ROLE_NAMES = {
    "adminGroupRef": "Admin",
    "memberGroupRef": "Member",
    "contributorGroupRef": "Contributor",
    "viewerGroupRef": "Viewer",
}
CAPACITY_ENV = {"shared-nonprod": "FABRIC_CAPACITY_NONPROD", "production": "FABRIC_CAPACITY_PROD"}


def reference_env_name(ref: str) -> str:
    return "FABRIC_REF_" + ref.upper().replace("-", "_")


def resolve_references(config: ProjectConfiguration) -> tuple[dict[str, str], dict[str, str]]:
    groups: dict[str, str] = {}
    for ref in config.spec.get("access", {}).values():
        value = os.getenv(reference_env_name(ref))
        if not value:
            raise LiveConfigurationError(f"Missing environment variable {reference_env_name(ref)}")
        groups[ref] = value
    capacities: dict[str, str] = {}
    for values in config.spec["environments"].values():
        ref = values["capacityRef"]
        value = os.getenv(CAPACITY_ENV.get(ref, reference_env_name(ref)))
        if not value:
            raise LiveConfigurationError(f"Missing capacity mapping for {ref}")
        capacities[ref] = value
    return groups, capacities


def provision_live(
    client: FabricRestClient,
    config: ProjectConfiguration,
    groups: dict[str, str],
    capacities: dict[str, str],
    apply: bool,
) -> dict[str, Any]:
    workspaces = {
        str(w.get("displayName", "")).casefold(): w
        for w in client.list_workspaces()
        if w.get("type") == "Workspace"
    }
    results: list[dict[str, Any]] = []
    for environment, values in config.spec["environments"].items():
        name = values["workspaceName"]
        capacity_id = capacities[values["capacityRef"]]
        actual = workspaces.get(name.casefold())
        actions: list[dict[str, str]] = []
        workspace_id = str(actual["id"]) if actual else ""
        if actual is None:
            actions.append({"resource": "workspace", "action": "create"})
            if apply:
                workspace_id = str(client.create_workspace(name, capacity_id)["id"])
        elif actual.get("capacityId") != capacity_id:
            actions.append({"resource": "capacity", "action": "update"})
            if apply:
                client.assign_to_capacity(workspace_id, capacity_id)
        else:
            actions.append({"resource": "workspace", "action": "no-op"})
        existing = _existing_roles(client, workspace_id) if workspace_id else set()
        for key, ref in config.spec.get("access", {}).items():
            role = ROLE_NAMES.get(key, key)
            pair = (groups[ref].lower(), role)
            if pair in existing:
                actions.append({"resource": f"role/{role}", "action": "no-op"})
                continue
            actions.append({"resource": f"role/{role}", "action": "create"})
            if apply and workspace_id:
                try:
                    client.add_role_assignment(workspace_id, groups[ref], role)
                except FabricApiError as error:
                    if error.status != 409:
                        raise
        results.append({"environment": environment, "workspaceName": name, "actions": actions})
    return {"applied": apply, "environments": results}


def _existing_roles(client: FabricRestClient, workspace_id: str) -> set[tuple[str, str]]:
    return {
        (str(item.get("principal", {}).get("id", "")).lower(), str(item.get("role", "")))
        for item in client.list_role_assignments(workspace_id)
    }
