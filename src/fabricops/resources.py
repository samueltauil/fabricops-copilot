from __future__ import annotations

from collections.abc import Iterable

from fabricops.config import ProjectConfiguration
from fabricops.models import Resource


def resources_for(config: ProjectConfiguration, use_case: str) -> list[Resource]:
    builders = {
        "provision": _provision,
        "deploy": _deploy,
        "operate": _operate,
        "govern": _govern,
        "accelerate": _accelerate,
    }
    if use_case == "all":
        resources: list[Resource] = []
        for builder in builders.values():
            resources.extend(builder(config))
        return _unique(resources)
    if use_case not in builders:
        raise ValueError(f"Unknown use case: {use_case}")
    return builders[use_case](config)


def _provision(config: ProjectConfiguration) -> list[Resource]:
    resources: list[Resource] = []
    access = config.spec.get("access", {})
    template = config.spec.get("template", "healthcare-rti-starter")
    for environment, values in config.spec["environments"].items():
        prefix = f"{config.customer}/{config.project}/{environment}"
        workspace_key = f"{prefix}/workspace"
        resources.append(
            Resource(
                key=workspace_key,
                kind="Workspace",
                properties={"name": values["workspaceName"], "environment": environment},
            )
        )
        resources.append(
            Resource(
                key=f"{prefix}/capacity",
                kind="CapacityAssignment",
                properties={"capacityRef": values["capacityRef"]},
                depends_on=(workspace_key,),
            )
        )
        for role, group_ref in sorted(access.items()):
            resources.append(
                Resource(
                    key=f"{prefix}/role/{role}",
                    kind="WorkspaceRoleAssignment",
                    properties={"groupRef": group_ref, "role": _role_name(role)},
                    depends_on=(workspace_key,),
                )
            )
        resources.append(
            Resource(
                key=f"{prefix}/starter/{template}",
                kind="StarterTemplate",
                properties={"template": template, "version": "1"},
                depends_on=(workspace_key,),
            )
        )
    return resources


def _deploy(config: ProjectConfiguration) -> list[Resource]:
    package = config.spec.get("deployment", {}).get("package", "healthcare-operations")
    items = config.spec.get("deployment", {}).get(
        "items", ["Lakehouse", "Notebook", "DataPipeline"]
    )
    resources: list[Resource] = []
    for environment, values in config.spec["environments"].items():
        workspace_key = f"{config.customer}/{config.project}/{environment}/workspace"
        for item in items:
            resources.append(
                Resource(
                    key=f"{config.customer}/{config.project}/{environment}/item/{item.lower()}",
                    kind="FabricItem",
                    properties={
                        "itemType": item,
                        "package": package,
                        "targetWorkspace": values["workspaceName"],
                        "environment": environment,
                    },
                    depends_on=(workspace_key,),
                )
            )
    return resources


def _operate(config: ProjectConfiguration) -> list[Resource]:
    resources: list[Resource] = []
    for item in config.spec.get("monitoring", {}).get("items", []):
        name = item["name"]
        resources.append(
            Resource(
                key=f"{config.customer}/{config.project}/monitor/{name}",
                kind="MonitoringPolicy",
                properties={
                    "owner": item["owner"],
                    "freshnessMinutes": item.get("freshnessMinutes", 60),
                    "retryable": bool(item.get("retryable", False)),
                    "maxAttempts": item.get("maxAttempts", 0),
                    "dataProduct": item.get("dataProduct", config.project),
                },
            )
        )
    return resources


def _govern(config: ProjectConfiguration) -> list[Resource]:
    return [
        Resource(
            key=f"{config.customer}/{config.project}/governance/baseline",
            kind="GovernancePolicy",
            properties={
                "mode": "report-only",
                "forbidDirectUserAdmin": True,
                "requireCapacityAssignment": True,
                "detectDevReferencesInProd": True,
            },
        )
    ]


def _accelerate(config: ProjectConfiguration) -> list[Resource]:
    resources: list[Resource] = []
    for workload in config.spec.get("accelerators", ["rti", "fabric-iq", "ontology", "agent"]):
        resources.append(
            Resource(
                key=f"{config.customer}/{config.project}/accelerator/{workload}",
                kind="WorkloadAccelerator",
                properties={
                    "workload": workload,
                    "mode": "automated" if workload == "rti" else "capability-probe",
                    "syntheticDataOnly": True,
                },
            )
        )
    return resources


def _role_name(config_key: str) -> str:
    names = {
        "adminGroupRef": "Admin",
        "contributorGroupRef": "Contributor",
        "memberGroupRef": "Member",
        "viewerGroupRef": "Viewer",
    }
    return names.get(config_key, config_key)


def _unique(resources: Iterable[Resource]) -> list[Resource]:
    values: dict[str, Resource] = {}
    for resource in resources:
        values[resource.key] = resource
    return list(values.values())
