from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectConfiguration:
    path: Path
    raw: dict[str, Any]
    config_hash: str

    @property
    def customer(self) -> str:
        return str(self.raw["metadata"]["customer"])

    @property
    def project(self) -> str:
        return str(self.raw["metadata"]["project"])

    @property
    def spec(self) -> dict[str, Any]:
        return self.raw["spec"]


def load_configuration(path: str | Path) -> ProjectConfiguration:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigurationError(f"Configuration not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigurationError("Configuration root must be a mapping")
    _validate(raw)
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return ProjectConfiguration(
        path=config_path,
        raw=raw,
        config_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _validate(raw: dict[str, Any]) -> None:
    allowed = {"apiVersion", "kind", "metadata", "spec"}
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigurationError(f"Unknown root fields: {', '.join(sorted(unknown))}")
    if raw.get("apiVersion") != "fabricops/v1alpha1":
        raise ConfigurationError("apiVersion must be fabricops/v1alpha1")
    if raw.get("kind") != "FabricProject":
        raise ConfigurationError("kind must be FabricProject")
    metadata = raw.get("metadata")
    spec = raw.get("spec")
    if not isinstance(metadata, dict) or not metadata.get("customer") or not metadata.get("project"):
        raise ConfigurationError("metadata.customer and metadata.project are required")
    if not isinstance(spec, dict):
        raise ConfigurationError("spec must be a mapping")
    environments = spec.get("environments")
    if not isinstance(environments, dict) or not environments:
        raise ConfigurationError("spec.environments must contain at least one environment")
    for name, environment in environments.items():
        if not isinstance(environment, dict):
            raise ConfigurationError(f"Environment {name} must be a mapping")
        for field in ("workspaceName", "capacityRef"):
            if not environment.get(field):
                raise ConfigurationError(f"Environment {name} requires {field}")
    access = spec.get("access", {})
    if not isinstance(access, dict):
        raise ConfigurationError("spec.access must be a mapping")
    monitoring = spec.get("monitoring", {})
    if monitoring and not isinstance(monitoring.get("items", []), list):
        raise ConfigurationError("spec.monitoring.items must be a list")

