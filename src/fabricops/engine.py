from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fabricops.config import ProjectConfiguration
from fabricops.models import Change, Plan, Resource
from fabricops.resources import resources_for
from fabricops.state import StateStore


class PlanError(RuntimeError):
    pass


class Planner:
    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def create(self, config: ProjectConfiguration, use_case: str, mode: str = "mock") -> Plan:
        state = self.state_store.load()
        actual = state.get("resources", {})
        changes = [self._diff(resource, actual.get(resource.key)) for resource in resources_for(config, use_case)]
        findings = _policy_findings(config, changes)
        return Plan(
            plan_version="1",
            operation_id=str(uuid.uuid4()),
            use_case=use_case,
            mode=mode,
            config_hash=config.config_hash,
            created_at=datetime.now(UTC).isoformat(),
            changes=changes,
            policy_findings=findings,
        )

    @staticmethod
    def _diff(resource: Resource, actual: dict[str, Any] | None) -> Change:
        if actual is None:
            return Change(resource, "create", "Resource is absent")
        if actual.get("kind") != resource.kind or actual.get("properties") != resource.properties:
            return Change(resource, "update", "Actual properties differ from approved configuration")
        return Change(resource, "no-op", "Actual state matches approved configuration")


class Executor:
    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def apply(self, config: ProjectConfiguration, plan: Plan) -> dict[str, Any]:
        if config.config_hash != plan.config_hash:
            raise PlanError("Plan is stale: configuration hash changed")
        if plan.policy_findings:
            raise PlanError("Plan has policy findings and cannot be applied")
        if plan.mode != "mock":
            raise PlanError("Live adapter is not configured; run capability preflight first")
        state = self.state_store.load()
        resources = state.setdefault("resources", {})
        applied = 0
        for change in plan.changes:
            if change.action in {"blocked", "manual"}:
                raise PlanError(f"Plan contains non-applicable action for {change.resource.key}")
            if change.action in {"create", "update"}:
                resources[change.resource.key] = {
                    "kind": change.resource.kind,
                    "properties": change.resource.properties,
                    "lastOperationId": plan.operation_id,
                }
                applied += 1
        self.state_store.save(state)
        verification = self.verify(plan)
        return {
            "operationId": plan.operation_id,
            "applied": applied,
            "verified": verification["verified"],
            "resourceCount": verification["resourceCount"],
        }

    def verify(self, plan: Plan) -> dict[str, Any]:
        state = self.state_store.load().get("resources", {})
        failures = []
        for change in plan.changes:
            actual = state.get(change.resource.key)
            if actual is None or actual.get("properties") != change.resource.properties:
                failures.append(change.resource.key)
        return {
            "verified": not failures,
            "resourceCount": len(plan.changes),
            "failures": failures,
        }


def write_plan(plan: Plan, output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{plan.use_case}-plan.json"
    markdown_path = directory / f"{plan.use_case}-plan.md"
    json_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        f"# FabricOps {plan.use_case.title()} Plan",
        "",
        f"- Operation: `{plan.operation_id}`",
        f"- Mode: `{plan.mode}`",
        f"- Configuration hash: `{plan.config_hash[:12]}...`",
        "",
        "## Summary",
        "",
    ]
    for action, count in sorted(plan.summary().items()):
        lines.append(f"- **{action}**: {count}")
    if plan.policy_findings:
        lines.extend(["", "## Policy findings", ""])
        lines.extend(f"- {finding}" for finding in plan.policy_findings)
    lines.extend(["", "## Changes", ""])
    for change in plan.changes:
        lines.append(
            f"- `{change.action}` **{change.resource.kind}** `{change.resource.key}` - {change.reason}"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def load_plan(path: str | Path) -> Plan:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    changes = [
        Change(
            Resource(
                key=item["key"],
                kind=item["kind"],
                properties=item["properties"],
                depends_on=tuple(item.get("dependsOn", [])),
            ),
            item["action"],
            item["reason"],
        )
        for item in raw["changes"]
    ]
    return Plan(
        plan_version=raw["plan_version"],
        operation_id=raw["operation_id"],
        use_case=raw["use_case"],
        mode=raw["mode"],
        config_hash=raw["config_hash"],
        created_at=raw["created_at"],
        changes=changes,
        policy_findings=raw.get("policy_findings", []),
    )


def _policy_findings(config: ProjectConfiguration, changes: list[Change]) -> list[str]:
    findings: list[str] = []
    names: set[str] = set()
    for environment, values in config.spec["environments"].items():
        workspace_name = values["workspaceName"].lower()
        if workspace_name in names:
            findings.append(f"Workspace name is duplicated: {values['workspaceName']}")
        names.add(workspace_name)
        if environment == "prod" and "dev" in workspace_name:
            findings.append("Production workspace name contains a development reference")
    direct_admins = [
        change
        for change in changes
        if change.resource.kind == "WorkspaceRoleAssignment"
        and change.resource.properties["role"] == "Admin"
        and "@" in change.resource.properties["groupRef"]
    ]
    if direct_admins:
        findings.append("Direct user administrators are forbidden; use an Entra group reference")
    return findings

