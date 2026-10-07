from __future__ import annotations

import base64
import binascii
import hashlib
import os
from typing import Any

from fabricops.config import ProjectConfiguration
from fabricops.live import FabricRestClient, LiveConfigurationError
from fabricops.live_provision import ROLE_NAMES

DEMO_PRINCIPAL_ENV = "FABRICOPS_DRIFT_DEMO_PRINCIPAL"
DEMO_PRINCIPAL_TYPE_ENV = "FABRICOPS_DRIFT_DEMO_PRINCIPAL_TYPE"
ALLOWED_PRINCIPALS_ENV = "FABRICOPS_GOVERN_ALLOWED_PRINCIPALS"
DEMO_ROLE = "Viewer"
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _hash(value: str) -> str:
    return hashlib.sha256(value.lower().encode("utf-8")).hexdigest()[:12]


def _finding(
    environment: str, category: str, severity: str, detail: str, remediation: str
) -> dict[str, str]:
    return {
        "environment": environment,
        "category": category,
        "severity": severity,
        "detail": detail,
        "remediation": remediation,
    }


def _definition_text(definition: dict[str, Any]) -> str:
    chunks: list[str] = []
    for part in definition.get("definition", definition).get("parts", []):
        payload = part.get("payload", "")
        try:
            chunks.append(base64.b64decode(payload).decode("utf-8", errors="ignore"))
        except (binascii.Error, ValueError):
            continue
    return "\n".join(chunks).lower()


def govern_live(
    client: FabricRestClient,
    config: ProjectConfiguration,
    groups: dict[str, str],
    capacities: dict[str, str],
) -> dict[str, Any]:
    environments = config.spec["environments"]
    deployment = config.spec.get("deployment", {})
    prefix = deployment.get("namePrefix", "care")
    item_types = list(deployment.get("items", ["Lakehouse", "Notebook", "DataPipeline"]))
    dev_markers = [environments["dev"]["workspaceName"].lower()] if "dev" in environments else []
    allowed = {
        v.strip().lower() for v in os.getenv(ALLOWED_PRINCIPALS_ENV, "").split(",") if v.strip()
    }
    workspaces = {
        str(w.get("displayName", "")).casefold(): w
        for w in client.list_workspaces()
        if w.get("type") == "Workspace"
    }
    findings: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    for environment, values in environments.items():
        actual = workspaces.get(values["workspaceName"].casefold())
        summary: dict[str, Any] = {
            "environment": environment,
            "workspaceExists": actual is not None,
            "workspaceIdHash": _hash(str(actual["id"])) if actual else None,
        }
        if actual is None:
            findings.append(
                _finding(
                    environment,
                    "workspace-missing",
                    "critical",
                    "Configured workspace does not exist.",
                    "Run provision-live (preview, then --apply) to create it.",
                )
            )
            summaries.append(summary)
            continue
        workspace_id = str(actual["id"])
        expected_capacity = capacities.get(values["capacityRef"], "")
        capacity_ok = bool(expected_capacity) and (
            str(actual.get("capacityId", "")).lower() == expected_capacity.lower()
        )
        summary["capacityMatches"] = capacity_ok
        if not capacity_ok:
            findings.append(
                _finding(
                    environment,
                    "capacity-mismatch",
                    "high",
                    f"Workspace is not assigned to the expected capacity ref "
                    f"'{values['capacityRef']}'.",
                    "Review, then run provision-live --apply to reassign capacity.",
                )
            )
        _check_roles(client, workspace_id, environment, config, groups, allowed, findings, summary)
        items = client.list_items(workspace_id)
        _check_items(
            client, workspace_id, environment, prefix, item_types, dev_markers, items, findings, summary
        )
        summaries.append(summary)
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["environment"], f["category"]))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}
    return {
        "mode": "live-readonly",
        "driftCount": len(findings),
        "severityCounts": counts,
        "status": "clean" if not findings else "drift-detected",
        "environments": summaries,
        "findings": findings,
        "remediationPolicy": "Report only. No remediation is applied automatically.",
    }


def _check_roles(
    client: FabricRestClient,
    workspace_id: str,
    environment: str,
    config: ProjectConfiguration,
    groups: dict[str, str],
    allowed: set[str],
    findings: list[dict[str, str]],
    summary: dict[str, Any],
) -> None:
    desired = {
        (groups[ref].lower(), ROLE_NAMES.get(key, key))
        for key, ref in config.spec.get("access", {}).items()
    }
    desired_principals = {p for p, _ in desired}
    actual = {
        (str(a.get("principal", {}).get("id", "")).lower(), str(a.get("role", "")))
        for a in client.list_role_assignments(workspace_id)
    }
    missing = sorted(desired - actual)
    unexpected = sorted(
        pair for pair in actual - desired if pair[0] not in allowed
    )
    summary["roleAssignments"] = {
        "desired": len(desired),
        "actual": len(actual),
        "missing": len(missing),
        "unexpected": len(unexpected),
    }
    for principal, role in missing:
        findings.append(
            _finding(
                environment,
                "role-missing",
                "high",
                f"Expected {role} assignment for principal {_hash(principal)} is absent.",
                "Run provision-live --apply to add the assignment.",
            )
        )
    for principal, role in unexpected:
        known = principal in desired_principals
        findings.append(
            _finding(
                environment,
                "role-unexpected",
                "high" if environment == "prod" or role == "Admin" else "medium",
                f"Principal {_hash(principal)} holds {role}"
                + (" (different role than desired)." if known else " and is not in desired access."),
                "Confirm with the workspace owner, then remove the assignment manually in "
                f"Fabric (or add its ref to {ALLOWED_PRINCIPALS_ENV} if approved).",
            )
        )


def _check_items(
    client: FabricRestClient,
    workspace_id: str,
    environment: str,
    prefix: str,
    item_types: list[str],
    dev_markers: list[str],
    items: list[dict[str, Any]],
    findings: list[dict[str, str]],
    summary: dict[str, Any],
) -> None:
    present = {(str(i.get("type")), str(i.get("displayName", "")).casefold()) for i in items}
    missing = 0
    for item_type in item_types:
        name = f"{prefix}_{item_type.lower()}"
        if (item_type, name.casefold()) not in present:
            missing += 1
            findings.append(
                _finding(
                    environment,
                    "item-missing",
                    "medium",
                    f"Starter item '{name}' ({item_type}) is absent.",
                    "Run deploy-live --apply to create it.",
                )
            )
    summary["starterItems"] = {"expected": len(item_types), "missing": missing}
    dev_refs = 0
    if environment != "dev" and dev_markers:
        for item in items:
            name = str(item.get("displayName", ""))
            text = name.lower()
            if item.get("type") == "Notebook":
                text += "\n" + _definition_text(client.get_item_definition(workspace_id, str(item["id"])))
            if any(marker in text for marker in dev_markers):
                dev_refs += 1
                findings.append(
                    _finding(
                        environment,
                        "dev-reference",
                        "critical" if environment == "prod" else "high",
                        f"{item.get('type')} item {_hash(str(item.get('id', '')))} "
                        "references the development workspace.",
                        "Redeploy the item from the promoted package with environment "
                        "parameters; do not edit prod items by hand.",
                    )
                )
    summary["devReferences"] = dev_refs


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Governance drift report (live, read-only)",
        "",
        f"- Status: **{report['status']}**",
        f"- Drift findings: {report['driftCount']}",
        "- Severity counts: "
        + ", ".join(f"{k}={v}" for k, v in report["severityCounts"].items()),
        f"- Policy: {report['remediationPolicy']}",
        "",
        "## Environments",
        "",
        "| Environment | Exists | Workspace ID hash | Capacity OK | Roles missing/unexpected"
        + " | Items missing | Dev refs |",
        "|---|---|---|---|---|---|---|",
    ]
    for env in report["environments"]:
        roles = env.get("roleAssignments", {})
        lines.append(
            f"| {env['environment']} | {env['workspaceExists']} | {env['workspaceIdHash']} "
            f"| {env.get('capacityMatches', 'n/a')} "
            f"| {roles.get('missing', 'n/a')}/{roles.get('unexpected', 'n/a')} "
            f"| {env.get('starterItems', {}).get('missing', 'n/a')} "
            f"| {env.get('devReferences', 'n/a')} |"
        )
    lines += ["", "## Findings", ""]
    if not report["findings"]:
        lines.append("No drift detected.")
    for f in report["findings"]:
        lines += [
            f"- **[{f['severity'].upper()}]** `{f['environment']}` {f['category']}: {f['detail']}",
            f"  - Remediation: {f['remediation']}",
        ]
    return "\n".join(lines) + "\n"


def _demo_principal() -> tuple[str, str] | None:
    principal = os.getenv(DEMO_PRINCIPAL_ENV, "").strip()
    if not principal:
        return None
    return principal, os.getenv(DEMO_PRINCIPAL_TYPE_ENV, "User").strip() or "User"


def _prod_workspace_id(client: FabricRestClient, config: ProjectConfiguration) -> str | None:
    env = config.spec["environments"].get("prod")
    if env is None:
        return None
    for w in client.list_workspaces():
        if w.get("type") == "Workspace" and str(w.get("displayName", "")).casefold() == str(
            env["workspaceName"]
        ).casefold():
            return str(w["id"])
    return None


def inject_demo_drift(client: FabricRestClient, config: ProjectConfiguration) -> dict[str, Any]:
    if os.getenv("FABRICOPS_ALLOW_LIVE_MUTATION") != "1":
        raise LiveConfigurationError("--inject-demo-drift requires FABRICOPS_ALLOW_LIVE_MUTATION=1")
    demo = _demo_principal()
    if demo is None:
        return {"action": "inject", "applied": False, "message": f"Skipped: {DEMO_PRINCIPAL_ENV} not set."}
    workspace_id = _prod_workspace_id(client, config)
    if workspace_id is None:
        return {"action": "inject", "applied": False, "message": "Skipped: prod workspace missing."}
    principal, ptype = demo
    existing = {
        str(a.get("principal", {}).get("id", "")).lower()
        for a in client.list_role_assignments(workspace_id)
    }
    if principal.lower() in existing:
        return {
            "action": "inject",
            "applied": False,
            "message": "Skipped: demo principal already has an assignment.",
        }
    client.add_principal_role(workspace_id, principal, ptype, DEMO_ROLE)
    return {"action": "inject", "applied": True, "principalHash": _hash(principal), "role": DEMO_ROLE}


def revert_demo_drift(client: FabricRestClient, config: ProjectConfiguration) -> dict[str, Any]:
    if os.getenv("FABRICOPS_ALLOW_LIVE_MUTATION") != "1":
        raise LiveConfigurationError("--revert-demo-drift requires FABRICOPS_ALLOW_LIVE_MUTATION=1")
    demo = _demo_principal()
    if demo is None:
        return {"action": "revert", "applied": False, "message": f"Skipped: {DEMO_PRINCIPAL_ENV} not set."}
    workspace_id = _prod_workspace_id(client, config)
    if workspace_id is None:
        return {"action": "revert", "applied": False, "message": "Skipped: prod workspace missing."}
    principal = demo[0].lower()
    for assignment in client.list_role_assignments(workspace_id):
        if str(assignment.get("principal", {}).get("id", "")).lower() == principal:
            client.delete_role_assignment(workspace_id, str(assignment["id"]))
            return {"action": "revert", "applied": True, "principalHash": _hash(principal)}
    return {"action": "revert", "applied": False, "message": "Nothing to revert."}
