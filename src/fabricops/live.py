from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
FABRIC_BASE_URL = "https://api.fabric.microsoft.com/v1"


class LiveConfigurationError(RuntimeError):
    pass


class FabricApiError(RuntimeError):
    def __init__(self, status: int, code: str, correlation_id: str | None = None) -> None:
        message = f"Fabric API request failed with HTTP {status} ({code})"
        if correlation_id:
            message += f"; correlation ID: {correlation_id}"
        super().__init__(message)
        self.status = status
        self.code = code
        self.correlation_id = correlation_id


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: dict[str, Any]


Transport = Callable[[str, str, dict[str, str], bytes | None], HttpResponse]


class FabricRestClient:
    def __init__(
        self,
        token_provider: Callable[[], str],
        transport: Transport | None = None,
        max_attempts: int = 4,
    ) -> None:
        self.token_provider = token_provider
        self.transport = transport or _urllib_transport
        self.max_attempts = max_attempts

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self._get_all("/workspaces", "value")

    def list_items(self, workspace_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"/workspaces/{workspace_id}/items", "value")

    def create_item(
        self, workspace_id: str, name: str, item_type: str, definition: dict[str, Any] | None = None
    ) -> None:
        payload: dict[str, Any] = {"displayName": name, "type": item_type}
        if definition:
            payload["definition"] = definition
        try:
            self._request("POST", f"{FABRIC_BASE_URL}/workspaces/{workspace_id}/items", payload)
        except FabricApiError as error:
            if error.status != 409:
                raise

    def create_workspace(self, name: str, capacity_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"displayName": name}
        if capacity_id:
            payload["capacityId"] = capacity_id
        return self._request("POST", f"{FABRIC_BASE_URL}/workspaces", payload).body

    def assign_to_capacity(self, workspace_id: str, capacity_id: str) -> None:
        self._request(
            "POST",
            f"{FABRIC_BASE_URL}/workspaces/{workspace_id}/assignToCapacity",
            {"capacityId": capacity_id},
        )

    def add_role_assignment(self, workspace_id: str, group_id: str, role: str) -> None:
        self._request(
            "POST",
            f"{FABRIC_BASE_URL}/workspaces/{workspace_id}/roleAssignments",
            {"principal": {"id": group_id, "type": "Group"}, "role": role},
        )

    def list_role_assignments(self, workspace_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"/workspaces/{workspace_id}/roleAssignments", "value")

    def add_principal_role(
        self, workspace_id: str, principal_id: str, principal_type: str, role: str
    ) -> None:
        self._request(
            "POST",
            f"{FABRIC_BASE_URL}/workspaces/{workspace_id}/roleAssignments",
            {"principal": {"id": principal_id, "type": principal_type}, "role": role},
        )

    def delete_role_assignment(self, workspace_id: str, role_assignment_id: str) -> None:
        self._request(
            "DELETE",
            f"{FABRIC_BASE_URL}/workspaces/{workspace_id}/roleAssignments/{role_assignment_id}",
        )

    def get_item_definition(self, workspace_id: str, item_id: str) -> dict[str, Any]:
        url = f"{FABRIC_BASE_URL}/workspaces/{workspace_id}/items/{item_id}/getDefinition"
        headers = {"Authorization": f"Bearer {self.token_provider()}", "Content-Type": "application/json"}
        response = self.transport("POST", url, headers, None)
        if response.status >= 400:
            raise FabricApiError(
                response.status,
                str(response.body.get("errorCode", "RequestFailed")),
                _correlation_id(response.headers),
            )
        location = {k.lower(): v for k, v in response.headers.items()}.get("location")
        if response.status == 202 and location:
            for _ in range(30):
                time.sleep(min(int(response.headers.get("Retry-After", "2")), 30))
                state = self._request("GET", location).body.get("status")
                if state == "Succeeded":
                    return self._request("GET", location.rstrip("/") + "/result").body
                if state in {"Failed", "Canceled"}:
                    raise FabricApiError(500, f"LongRunningOperation{state}")
            raise FabricApiError(504, "LongRunningOperationTimeout")
        return response.body

    def list_job_instances(self, workspace_id: str, item_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"/workspaces/{workspace_id}/items/{item_id}/jobs/instances", "value")

    def run_item_job(self, workspace_id: str, item_id: str, job_type: str) -> str | None:
        """Start an on-demand job without waiting; returns the new job instance ID if known."""
        url = (
            f"{FABRIC_BASE_URL}/workspaces/{workspace_id}/items/{item_id}"
            f"/jobs/instances?jobType={job_type}"
        )
        response = self._request("POST", url, poll=False)
        location = {k.lower(): v for k, v in response.headers.items()}.get("location", "")
        return location.rstrip("/").rsplit("/", 1)[-1] or None

    def _get_all(self, path: str, value_key: str) -> list[dict[str, Any]]:
        url = f"{FABRIC_BASE_URL}{path}"
        values: list[dict[str, Any]] = []
        while url:
            response = self._request("GET", url)
            page = response.body.get(value_key, [])
            if not isinstance(page, list):
                raise FabricApiError(response.status, "InvalidResponseShape")
            values.extend(item for item in page if isinstance(item, dict))
            continuation = response.body.get("continuationUri")
            url = continuation if isinstance(continuation, str) and continuation else ""
        return values

    def _request(
        self, method: str, url: str, payload: dict[str, Any] | None = None, poll: bool = True
    ) -> HttpResponse:
        headers = {
            "Authorization": f"Bearer {self.token_provider()}",
            "Content-Type": "application/json",
        }
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.transport(method, url, headers, body)
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if attempt < self.max_attempts:
                    time.sleep(min(2**attempt, 15))
                    continue
                raise FabricApiError(503, "ConnectionFailed") from None
            if response.status < 400:
                return self._finish(response) if poll else response
            if (response.status == 429 or response.status >= 500) and attempt < self.max_attempts:
                delay = min(int(response.headers.get("Retry-After", "1")), 30)
                time.sleep(delay)
                continue
            error = response.body.get("errorCode", "RequestFailed")
            correlation = _correlation_id(response.headers)
            raise FabricApiError(response.status, str(error), correlation)
        raise FabricApiError(503, "RetryExhausted")


    def _finish(self, response: HttpResponse) -> HttpResponse:
        location = {k.lower(): v for k, v in response.headers.items()}.get("location")
        if response.status != 202 or not location:
            return response
        for _ in range(30):
            time.sleep(min(int(response.headers.get("Retry-After", "2")), 30))
            polled = self._request("GET", location)
            state = str(polled.body.get("status", "Succeeded"))
            if state == "Succeeded":
                return polled
            if state in {"Failed", "Canceled"}:
                raise FabricApiError(500, f"LongRunningOperation{state}")
        raise FabricApiError(504, "LongRunningOperationTimeout")


def default_token_provider() -> str:
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as error:
        raise LiveConfigurationError(
            'Live discovery requires the optional dependency: pip install -e ".[live]"'
        ) from error
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return credential.get_token(FABRIC_SCOPE).token


def discover_configured_workspaces(
    configured_environments: dict[str, dict[str, Any]],
    workspaces: list[dict[str, Any]],
    capacity_mapping: dict[str, str],
) -> dict[str, Any]:
    by_name = {
        str(workspace.get("displayName", "")).casefold(): workspace
        for workspace in workspaces
        if workspace.get("type") == "Workspace"
    }
    results = []
    for environment, configured in configured_environments.items():
        name = str(configured["workspaceName"])
        actual = by_name.get(name.casefold())
        expected_capacity = capacity_mapping.get(str(configured["capacityRef"]), "")
        actual_capacity = str(actual.get("capacityId", "")) if actual else ""
        results.append(
            {
                "environment": environment,
                "workspaceName": name,
                "status": "found" if actual else "missing",
                "workspaceIdHash": _alias(str(actual.get("id", ""))) if actual else None,
                "capacityMatches": bool(
                    actual and expected_capacity and actual_capacity == expected_capacity
                ),
            }
        )
    return {
        "workspaceCountVisibleToCaller": len(workspaces),
        "configuredWorkspaces": results,
    }


def _urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return HttpResponse(response.status, dict(response.headers.items()), parsed)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"errorCode": "NonJsonError"}
        return HttpResponse(error.code, dict(error.headers.items()), parsed)


def _alias(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _correlation_id(headers: dict[str, str]) -> str | None:
    lowered = {key.lower(): value for key, value in headers.items()}
    return lowered.get("requestid") or lowered.get("x-ms-request-id")
