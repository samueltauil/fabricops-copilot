from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fabricops.config import ProjectConfiguration
from fabricops.resources import resources_for
from fabricops.state import StateStore


@dataclass(frozen=True)
class HealthItem:
    name: str
    owner: str
    data_product: str
    status: str
    freshness_minutes: int
    retry_eligible: bool
    retry_reason: str


def health_snapshot(config: ProjectConfiguration, store: StateStore) -> dict[str, Any]:
    state = store.load()
    jobs = state.get("jobs", {})
    items: list[HealthItem] = []
    for configured in config.spec.get("monitoring", {}).get("items", []):
        job = jobs.get(configured["name"], {})
        status = job.get("status", "unknown")
        retryable = bool(configured.get("retryable", False))
        attempts = int(job.get("attempts", 0))
        maximum = int(configured.get("maxAttempts", 0))
        running = status == "running"
        eligible = status == "failed" and retryable and attempts < maximum and not running
        if status == "unknown":
            reason = "No telemetry is available for this monitored item"
        elif status != "failed":
            reason = "Job is not failed"
        elif not retryable:
            reason = "Retry policy is deny-by-default"
        elif attempts >= maximum:
            reason = "Retry attempt limit reached"
        elif running:
            reason = "Job is already running"
        else:
            reason = "Explicit policy permits an approval-gated retry"
        items.append(
            HealthItem(
                name=configured["name"],
                owner=configured["owner"],
                data_product=configured.get("dataProduct", config.project),
                status=status,
                freshness_minutes=int(configured.get("freshnessMinutes", 60)),
                retry_eligible=eligible,
                retry_reason=reason,
            )
        )
    return {
        "summary": _status_counts(items),
        "items": [asdict(item) for item in items],
        "telemetryMode": "mock",
    }


def drift_snapshot(config: ProjectConfiguration, store: StateStore) -> dict[str, Any]:
    actual = store.load().get("resources", {})
    desired = {resource.key: resource for resource in resources_for(config, "all")}
    missing = sorted(key for key in desired if key not in actual)
    changed = sorted(
        key
        for key, resource in desired.items()
        if key in actual
        and (
            actual[key].get("kind") != resource.kind
            or actual[key].get("properties") != resource.properties
        )
    )
    unexpected = sorted(key for key in actual if key not in desired)
    return {
        "mode": "report-only",
        "summary": {
            "missing": len(missing),
            "changed": len(changed),
            "unexpected": len(unexpected),
        },
        "missing": missing,
        "changed": changed,
        "unexpected": unexpected,
    }


def _status_counts(items: list[HealthItem]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        summary[item.status] = summary.get(item.status, 0) + 1
    return summary
