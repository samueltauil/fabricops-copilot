from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    status: str
    mechanism: str
    note: str


def get_capabilities(mode: str) -> list[Capability]:
    live_note = "Requires tenant preflight" if mode == "live" else "Simulated by local adapter"
    return [
        Capability("workspace.create", "supported", "Fabric REST API", live_note),
        Capability("workspace.capacity", "supported", "Fabric REST API", live_note),
        Capability("workspace.roles", "supported", "Fabric REST API", live_note),
        Capability("item.deploy", "conditional", "fabric-cicd/item definitions", "Varies by item type"),
        Capability("job.history", "supported", "Job Scheduler API", live_note),
        Capability("job.retry", "conditional", "Job Scheduler API", "Deny by default; job policy required"),
        Capability("governance.scan", "conditional", "Scanner/activity APIs", "Admin setup required"),
        Capability("rti.deploy", "conditional", "Fabric APIs", "Validate item and capacity support"),
        Capability("fabric-iq.deploy", "preview", "Capability probe", "Assisted path may be required"),
        Capability("ontology.deploy", "preview", "Capability probe", "Assisted path may be required"),
        Capability("agent.deploy", "preview", "Capability probe", "Assisted path may be required"),
    ]


def capabilities_dict(mode: str) -> list[dict[str, str]]:
    return [asdict(capability) for capability in get_capabilities(mode)]

