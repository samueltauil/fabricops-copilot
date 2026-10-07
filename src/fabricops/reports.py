from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ALLOWED_EVENT_FIELDS = {
    "operationId",
    "useCase",
    "outcome",
    "applied",
    "verified",
    "resourceCount",
    "correlationId",
}


def write_evidence(
    output_dir: str | Path, name: str, event: dict[str, Any]
) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe = {key: event[key] for key in ALLOWED_EVENT_FIELDS if key in event}
    safe["recordedAt"] = datetime.now(UTC).isoformat()
    json_path = directory / f"{name}.json"
    markdown_path = directory / f"{name}.md"
    json_path.write_text(json.dumps(safe, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(
        "# FabricOps Evidence\n\n"
        + "\n".join(f"- **{key}**: `{value}`" for key, value in sorted(safe.items()))
        + "\n",
        encoding="utf-8",
    )
    return json_path, markdown_path
