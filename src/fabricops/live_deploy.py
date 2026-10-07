from __future__ import annotations

import base64
import json
from typing import Any

from fabricops.config import ProjectConfiguration
from fabricops.live import FabricRestClient

SUPPORTED_ITEMS = {"Lakehouse", "Notebook", "DataPipeline"}


class DeploymentError(RuntimeError):
    pass


def _notebook_definition(environment: str, dev_markers: list[str]) -> dict[str, Any]:
    source = [
        "# Synthetic healthcare operations starter (no patient data)\n",
        f"ENVIRONMENT = '{environment}'\n",
        "print(f'Care operations starter running in {ENVIRONMENT}')\n",
    ]
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": [
            {
                "cell_type": "code",
                "source": source,
                "execution_count": None,
                "outputs": [],
                "metadata": {},
            }
        ],
        "metadata": {"language_info": {"name": "python"}},
    }
    text = json.dumps(notebook)
    if environment != "dev" and any(marker in text.lower() for marker in dev_markers):
        raise DeploymentError(f"Development reference found in {environment} package")
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return {
        "format": "ipynb",
        "parts": [
            {"path": "artifact.content.ipynb", "payload": payload, "payloadType": "InlineBase64"}
        ],
    }


def deploy_live(
    client: FabricRestClient, config: ProjectConfiguration, apply: bool
) -> dict[str, Any]:
    deployment = config.spec.get("deployment", {})
    items = list(deployment.get("items", ["Lakehouse", "Notebook", "DataPipeline"]))
    unsupported = [item for item in items if item not in SUPPORTED_ITEMS]
    if unsupported:
        raise DeploymentError(f"Unsupported item types: {', '.join(unsupported)}")
    workspaces = {
        str(w.get("displayName", "")).casefold(): w
        for w in client.list_workspaces()
        if w.get("type") == "Workspace"
    }
    environments = config.spec["environments"]
    dev_markers = [environments["dev"]["workspaceName"].lower()] if "dev" in environments else []
    prefix = deployment.get("namePrefix", "care")
    results: list[dict[str, Any]] = []
    for environment, values in environments.items():
        workspace = workspaces.get(values["workspaceName"].casefold())
        if workspace is None:
            raise DeploymentError(f"Workspace missing for {environment}; run provision-live first")
        existing = {
            (str(i.get("type")), str(i.get("displayName", "")).casefold())
            for i in client.list_items(str(workspace["id"]))
        }
        actions = []
        for item_type in items:
            name = f"{prefix}_{item_type.lower()}"
            definition = (
                _notebook_definition(environment, dev_markers) if item_type == "Notebook" else None
            )
            if (item_type, name.casefold()) in existing:
                actions.append({"item": name, "type": item_type, "action": "no-op"})
                continue
            actions.append({"item": name, "type": item_type, "action": "create"})
            if apply:
                client.create_item(str(workspace["id"]), name, item_type, definition)
        results.append({"environment": environment, "actions": actions})
    return {"applied": apply, "environments": results}
