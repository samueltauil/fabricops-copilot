from __future__ import annotations

import json
from pathlib import Path

from fabricops.reports import write_evidence


def test_evidence_uses_allowlist(tmp_path: Path) -> None:
    json_path, _ = write_evidence(
        tmp_path,
        "run",
        {
            "operationId": "123",
            "outcome": "succeeded",
            "token": "must-not-appear",
            "rawCustomerData": "must-not-appear",
        },
    )
    evidence = json.loads(json_path.read_text(encoding="utf-8"))

    assert evidence["operationId"] == "123"
    assert "token" not in evidence
    assert "rawCustomerData" not in evidence

