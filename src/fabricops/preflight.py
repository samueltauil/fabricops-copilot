from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from fabricops.capabilities import capabilities_dict


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: str
    detail: str


def live_preflight() -> dict[str, object]:
    checks = [
        _required("FABRIC_TENANT_ID", "Fabric tenant"),
        _required("FABRIC_CLIENT_ID", "Federated application/client"),
        _required("FABRIC_CAPACITY_NONPROD", "Nonproduction capacity mapping"),
        _required("FABRIC_CAPACITY_PROD", "Production capacity mapping"),
        PreflightCheck(
            "credentialStrategy",
            "configured" if _credential_available() else "missing",
            "DefaultAzureCredential" if _credential_available() else "No OIDC/managed identity signal",
        ),
    ]
    ready = all(check.status == "configured" for check in checks)
    return {
        "readyForLiveDiscovery": ready,
        "readyForLiveMutation": False,
        "checks": [asdict(check) for check in checks],
        "capabilities": capabilities_dict("live"),
        "note": (
            "Live mutation remains disabled until tenant API support, identity permissions, "
            "group mappings, and sandbox verification are confirmed."
        ),
    }


def _required(name: str, label: str) -> PreflightCheck:
    value = os.getenv(name)
    return PreflightCheck(name, "configured" if value else "missing", label)


def _credential_available() -> bool:
    names = (
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "IDENTITY_ENDPOINT",
        "AZURE_FEDERATED_TOKEN_FILE",
        "AZURE_CLIENT_SECRET",
        "FABRICOPS_ALLOW_AZURE_CLI",
    )
    return any(os.getenv(name) for name in names)

