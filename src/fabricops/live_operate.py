from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fabricops.config import ProjectConfiguration
from fabricops.insights import health_snapshot
from fabricops.live import FabricRestClient, _alias

JOB_TYPES = {"DataPipeline": "Pipeline", "Notebook": "RunNotebook"}
RUNNING = {"NotStarted", "InProgress"}
FAILED = {"Failed", "Cancelled"}


class OperateError(RuntimeError):
    pass


class _MemoryStore:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    def load(self) -> dict[str, Any]:
        return self._state


def _latest_first(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(instances, key=lambda i: str(i.get("startTimeUtc") or ""), reverse=True)


def _job_state(instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse job history into the status/attempts shape that insights.py consumes."""
    ordered = _latest_first(instances)
    if not ordered:
        return {"status": "unknown", "attempts": 0}
    latest = str(ordered[0].get("status", ""))
    if latest in RUNNING:
        return {"status": "running", "attempts": 0}
    if latest in FAILED:
        attempts = 0
        for instance in ordered:
            if str(instance.get("status")) not in FAILED:
                break
            attempts += 1
        return {"status": "failed", "attempts": attempts}
    if latest == "Completed":
        return {"status": "succeeded", "attempts": 0}
    return {"status": "unknown", "attempts": 0}


def _health_class(entry: dict[str, Any]) -> str:
    status = entry["status"]
    if status == "failed":
        return "failed-actionable" if entry["retry_eligible"] else "failed-manual"
    if status == "succeeded":
        return "healthy"
    return "unknown"


def operate_live(
    client: FabricRestClient,
    config: ProjectConfiguration,
    run: bool = False,
    retry: bool = False,
    environment: str = "dev",
) -> dict[str, Any]:
    """Read job health for the dev workspace; trigger jobs only when ``run``/``retry`` are set."""
    environments = config.spec["environments"]
    if environment not in environments:
        raise OperateError(f"Environment {environment} is not configured")
    name = str(environments[environment]["workspaceName"]).casefold()
    workspace = next(
        (
            w
            for w in client.list_workspaces()
            if w.get("type") == "Workspace" and str(w.get("displayName", "")).casefold() == name
        ),
        None,
    )
    if workspace is None:
        raise OperateError(f"Workspace missing for {environment}; run provision-live first")
    workspace_id = str(workspace["id"])
    fabric_items = {
        str(i.get("displayName", "")).casefold(): i
        for i in client.list_items(workspace_id)
        if i.get("type") in JOB_TYPES
    }
    monitored = config.spec.get("monitoring", {}).get("items", [])
    mapped: dict[str, dict[str, Any]] = {}
    for configured in monitored:
        target = str(configured.get("fabricItem", configured["name"])).casefold()
        if target in fabric_items:
            mapped[configured["name"]] = fabric_items[target]

    actions: list[dict[str, Any]] = []

    def collect() -> dict[str, list[dict[str, Any]]]:
        return {
            n: client.list_job_instances(workspace_id, str(item["id"])) for n, item in mapped.items()
        }

    def snapshot(history: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        state = {"jobs": {n: _job_state(h) for n, h in history.items()}}
        return health_snapshot(config, _MemoryStore(state))

    history = collect()
    health = snapshot(history)
    by_name = {entry["name"]: entry for entry in health["items"]}
    triggered: set[str] = set()
    if run or retry:
        for monitored_name, item in mapped.items():
            entry = by_name[monitored_name]
            job_type = JOB_TYPES[str(item["type"])]
            record = {"item": monitored_name, "itemType": item["type"], "jobType": job_type}
            if entry["status"] == "running":
                actions.append({**record, "action": "skipped", "reason": "Job is already running"})
            elif run:
                instance_id = client.run_item_job(workspace_id, str(item["id"]), job_type)
                triggered.add(monitored_name)
                actions.append(
                    {
                        **record,
                        "action": "triggered",
                        "reason": "On-demand run",
                        "jobInstanceHash": _alias(instance_id) if instance_id else None,
                    }
                )
            elif entry["retry_eligible"]:
                instance_id = client.run_item_job(workspace_id, str(item["id"]), job_type)
                triggered.add(monitored_name)
                actions.append(
                    {
                        **record,
                        "action": "retried",
                        "reason": entry["retry_reason"],
                        "attempt": _job_state(history[monitored_name])["attempts"] + 1,
                        "jobInstanceHash": _alias(instance_id) if instance_id else None,
                    }
                )
            else:
                actions.append({**record, "action": "skipped", "reason": entry["retry_reason"]})
        if triggered:
            history = collect()
            health = snapshot(history)
            by_name = {entry["name"]: entry for entry in health["items"]}

    items = []
    for configured in monitored:
        monitored_name = configured["name"]
        entry = by_name[monitored_name]
        item = mapped.get(monitored_name)
        latest = _latest_first(history.get(monitored_name, []))[:1]
        items.append(
            {
                "name": monitored_name,
                "owner": entry["owner"],
                "dataProduct": entry["data_product"],
                "fabricItemType": item["type"] if item else None,
                "fabricItemHash": _alias(str(item["id"])) if item else None,
                "health": _health_class(entry) if item else "unknown",
                "latestJobStatus": str(latest[0].get("status")) if latest else None,
                "latestJobStartUtc": latest[0].get("startTimeUtc") if latest else None,
                "latestJobEndUtc": latest[0].get("endTimeUtc") if latest else None,
                "latestJobFailureCode": _failure_code(latest[0]) if latest else None,
                "jobInstanceCount": len(history.get(monitored_name, [])),
                "retryEligible": entry["retry_eligible"] if item else False,
                "note": entry["retry_reason"] if item else "No matching Fabric item in workspace",
            }
        )
    monitored_ids = {str(i["id"]) for i in mapped.values()}
    unmonitored = [
        {"name": i["displayName"], "type": i["type"], "itemHash": _alias(str(i["id"]))}
        for i in fabric_items.values()
        if str(i["id"]) not in monitored_ids
    ]
    summary: dict[str, int] = {}
    for item in items:
        summary[item["health"]] = summary.get(item["health"], 0) + 1
    return {
        "mode": "run" if run else "retry" if retry else "preview",
        "environment": environment,
        "workspaceIdHash": _alias(workspace_id),
        "summary": summary,
        "items": items,
        "unmonitoredItems": unmonitored,
        "actions": actions,
    }


def render_morning_report(report: dict[str, Any]) -> str:
    lines = [
        "# Morning operations report",
        "",
        f"- Environment: {report['environment']} (workspace `{report['workspaceIdHash']}`)",
        f"- Mode: {report['mode']}",
        "- Summary: "
        + (", ".join(f"{k}={v}" for k, v in sorted(report["summary"].items())) or "no monitored items"),
        "",
        "## Monitored items",
        "",
        "| Item | Owner | Health | Latest job | Retry eligible | Note |",
        "|---|---|---|---|---|---|",
    ]
    for item in report["items"]:
        lines.append(
            f"| {item['name']} | {item['owner']} | {item['health']} | "
            f"{item['latestJobStatus'] or 'none'} | {item['retryEligible']} | {item['note']} |"
        )
    lines += ["", "## Actions", ""]
    lines += [
        f"- {a['item']}: {a['action']} ({a['reason']})" for a in report["actions"]
    ] or ["- None (read-only)"]
    lines += ["", "## Unmonitored job-capable items", ""]
    lines += [
        f"- {u['name']} ({u['type']}, `{u['itemHash']}`)" for u in report["unmonitoredItems"]
    ] or ["- None"]
    return "\n".join(lines) + "\n"


def write_operate_report(output: Path, report: dict[str, Any]) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "live-operate.json"
    md_path = output / "morning-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_morning_report(report), encoding="utf-8")
    return [json_path, md_path]


def _failure_code(instance: dict[str, Any]) -> str | None:
    reason = instance.get("failureReason")
    if isinstance(reason, dict):
        code = reason.get("errorCode")
        return str(code) if code else None
    return None
