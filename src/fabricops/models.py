from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Action = Literal["create", "update", "no-op", "blocked", "manual"]


@dataclass(frozen=True)
class Resource:
    key: str
    kind: str
    properties: dict[str, Any]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Change:
    resource: Resource
    action: Action
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.resource.key,
            "kind": self.resource.kind,
            "properties": self.resource.properties,
            "dependsOn": list(self.resource.depends_on),
            "action": self.action,
            "reason": self.reason,
        }


@dataclass
class Plan:
    plan_version: str
    operation_id: str
    use_case: str
    mode: str
    config_hash: str
    created_at: str
    changes: list[Change] = field(default_factory=list)
    policy_findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["changes"] = [change.to_dict() for change in self.changes]
        result["summary"] = self.summary()
        return result

    def summary(self) -> dict[str, int]:
        values: dict[str, int] = {}
        for change in self.changes:
            values[change.action] = values.get(change.action, 0) + 1
        return values

