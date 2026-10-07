from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fabricops.config import ProjectConfiguration
from fabricops.live import FabricApiError, FabricRestClient, LiveConfigurationError
from fabricops.live_deploy import STARTER_NOTEBOOK_VERSION, build_notebook_definition
from fabricops.synthea import generate, summarize, synthea_settings

STORAGE_SCOPE = "https://storage.azure.com/.default"
ONELAKE_BASE_URL = "https://onelake.dfs.fabric.microsoft.com"
UPLOAD_TABLES = ("patients", "encounters", "observations")
CHUNK_SIZE = 4 * 1024 * 1024
DEFAULT_RTI_NAME = "rti-care-ops"

DfsTransport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, str]]]


def storage_token_provider() -> str:
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as error:
        raise LiveConfigurationError(
            'Live accelerate requires the optional dependency: pip install -e ".[live]"'
        ) from error
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return credential.get_token(STORAGE_SCOPE).token


def _urllib_dfs_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> tuple[int, dict[str, str]]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, dict(response.headers.items())
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items())


class OneLakeFiles:
    def __init__(
        self, token_provider: Callable[[], str], transport: DfsTransport | None = None
    ) -> None:
        self.token_provider = token_provider
        self.transport = transport or _urllib_dfs_transport

    def _call(self, method: str, url: str, body: bytes | None = None) -> tuple[int, dict[str, str]]:
        headers = {"Authorization": f"Bearer {self.token_provider()}", "x-ms-version": "2023-11-03"}
        if body is not None:
            headers["Content-Length"] = str(len(body))
        return self.transport(method, url, headers, body)

    def size(self, url: str) -> int | None:
        status, headers = self._call("HEAD", url)
        if status == 404:
            return None
        if status >= 400:
            raise FabricApiError(status, "OneLakeHeadFailed")
        lowered = {k.lower(): v for k, v in headers.items()}
        return int(lowered.get("content-length", "-1"))

    def upload(self, url: str, data: bytes) -> None:
        status, _ = self._call("PUT", f"{url}?resource=file&overwrite=true")
        if status >= 400:
            raise FabricApiError(status, "OneLakeCreateFailed")
        for position in range(0, len(data), CHUNK_SIZE):
            chunk = data[position : position + CHUNK_SIZE]
            status, _ = self._call("PATCH", f"{url}?action=append&position={position}", chunk)
            if status >= 400:
                raise FabricApiError(status, "OneLakeAppendFailed")
        status, _ = self._call("PATCH", f"{url}?action=flush&position={len(data)}")
        if status >= 400:
            raise FabricApiError(status, "OneLakeFlushFailed")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _find(items: list[dict[str, Any]], item_type: str, name: str) -> dict[str, Any] | None:
    for item in items:
        if item.get("type") == item_type and str(item.get("displayName", "")).casefold() == (
            name.casefold()
        ):
            return item
    return None


def _ensure_rti_item(
    client: FabricRestClient,
    workspace_id: str,
    items: list[dict[str, Any]],
    item_type: str,
    name: str,
    apply: bool,
) -> dict[str, Any]:
    if _find(items, item_type, name):
        return {"type": item_type, "item": name, "action": "no-op"}
    if not apply:
        return {"type": item_type, "item": name, "action": "create"}
    try:
        client._request(
            "POST",
            f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items",
            {"displayName": name, "type": item_type},
        )
    except FabricApiError as error:
        if error.status == 409:
            return {"type": item_type, "item": name, "action": "no-op"}
        return {
            "type": item_type,
            "item": name,
            "action": "manual/unsupported",
            "httpStatus": error.status,
            "errorCode": error.code,
        }
    return {"type": item_type, "item": name, "action": "created"}


def _sync_notebook(
    client: FabricRestClient,
    workspace_id: str,
    notebook: dict[str, Any] | None,
    lakehouse: dict[str, Any],
    lakehouse_name: str,
    dev_markers: list[str],
    apply: bool,
) -> dict[str, Any]:
    if notebook is None:
        return {"type": "Notebook", "action": "missing; run deploy-live first"}
    if notebook.get("description") == STARTER_NOTEBOOK_VERSION:
        return {"type": "Notebook", "action": "no-op"}
    if not apply:
        return {"type": "Notebook", "action": "update-definition"}
    definition = build_notebook_definition(
        "dev",
        dev_markers,
        {
            "lakehouseId": str(lakehouse["id"]),
            "lakehouseName": lakehouse_name,
            "workspaceId": workspace_id,
        },
    )
    base = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{notebook['id']}"
    try:
        client._request("POST", f"{base}/updateDefinition", {"definition": definition})
        client._request("PATCH", base, {"description": STARTER_NOTEBOOK_VERSION})
    except FabricApiError as error:
        return {
            "type": "Notebook",
            "action": "manual/unsupported",
            "httpStatus": error.status,
            "errorCode": error.code,
        }
    return {"type": "Notebook", "action": "updated"}


def _dataset(settings: dict[str, Any], data_dir: Path, tools_dir: Path, apply: bool) -> Path:
    if (data_dir / "csv" / "patients.csv").exists():
        return data_dir
    if not apply:
        return data_dir
    generate(settings, data_dir, tools_dir)
    return data_dir


def accelerate_live(
    client: FabricRestClient,
    onelake: OneLakeFiles,
    config: ProjectConfiguration,
    data_dir: Path,
    tools_dir: Path,
    apply: bool,
) -> dict[str, Any]:
    spec = config.spec
    environments = spec["environments"]
    dev_name = environments["dev"]["workspaceName"]
    workspace = next(
        (
            w
            for w in client.list_workspaces()
            if w.get("type") == "Workspace"
            and str(w.get("displayName", "")).casefold() == dev_name.casefold()
        ),
        None,
    )
    if workspace is None:
        raise LiveConfigurationError("Dev workspace missing; run provision-live first")
    workspace_id = str(workspace["id"])
    prefix = spec.get("deployment", {}).get("namePrefix", "care")
    rti_name = str(spec.get("rti", {}).get("name", DEFAULT_RTI_NAME))
    items = client.list_items(workspace_id)

    rti_actions = [
        _ensure_rti_item(client, workspace_id, items, "Eventhouse", rti_name, apply),
        _ensure_rti_item(client, workspace_id, items, "Eventstream", f"{rti_name}-stream", apply),
    ]
    if apply:
        items = client.list_items(workspace_id)
    kql_db = _find(items, "KQLDatabase", rti_name)
    rti_actions.append(
        {
            "type": "KQLDatabase",
            "item": rti_name,
            "action": "present (default database)" if kql_db else "pending/not found",
        }
    )

    lakehouse_name = f"{prefix}_lakehouse"
    lakehouse = _find(items, "Lakehouse", lakehouse_name)
    uploads: list[dict[str, Any]] = []
    notebook_action: dict[str, Any]
    dataset: dict[str, Any] | None = None
    if lakehouse is None:
        uploads.append({"action": "skipped", "reason": "lakehouse missing; run deploy-live first"})
        notebook_action = {"type": "Notebook", "action": "skipped; lakehouse missing"}
    else:
        settings = synthea_settings(spec)
        source = _dataset(settings, data_dir, tools_dir, apply)
        have_data = (source / "csv" / "patients.csv").exists()
        if have_data:
            dataset = summarize(source)
        for table in UPLOAD_TABLES:
            path = source / "csv" / f"{table}.csv"
            if not path.exists():
                uploads.append({"table": table, "action": "skipped", "reason": "no local csv"})
                continue
            data = path.read_bytes()
            url = (
                f"{ONELAKE_BASE_URL}/{workspace_id}/{lakehouse['id']}/Files/synthea/{table}.csv"
            )
            remote = onelake.size(url)
            entry: dict[str, Any] = {
                "table": table,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest()[:12],
            }
            if remote == len(data):
                entry["action"] = "no-op"
            else:
                entry["action"] = "upload" if not apply else "uploaded"
                if apply:
                    onelake.upload(url, data)
            uploads.append(entry)
        notebook = _find(items, "Notebook", f"{prefix}_notebook")
        notebook_action = _sync_notebook(
            client,
            workspace_id,
            notebook,
            lakehouse,
            lakehouse_name,
            [dev_name.lower()],
            apply,
        )
    return {
        "applied": apply,
        "workspaceIdHash": _digest(workspace_id),
        "realTimeIntelligence": rti_actions,
        "syntheaUpload": uploads,
        "starterNotebook": notebook_action,
        "dataset": dataset,
    }
