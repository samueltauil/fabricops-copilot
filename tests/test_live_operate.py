from __future__ import annotations

import json
from pathlib import Path

from fabricops.config import load_configuration
from fabricops.live import FabricRestClient, HttpResponse
from fabricops.live_operate import operate_live, render_morning_report, write_operate_report

CONFIG = Path("config/examples/synthetic-healthcare/project.yml")


class FakeFabric:
    def __init__(self, statuses: list[str]) -> None:
        self.jobs = [
            {"id": f"job-{n}", "status": s, "startTimeUtc": f"2026-01-01T00:0{n}:00Z"}
            for n, s in enumerate(statuses)
        ]
        self.posts: list[str] = []

    def __call__(self, method, url, headers, body):
        path = url.split("/v1", 1)[1]
        if path == "/workspaces":
            return HttpResponse(
                200, {}, {"value": [{"id": "ws-dev", "displayName": "fab-northwind-care-dev", "type": "Workspace"}]}
            )
        if path == "/workspaces/ws-dev/items":
            return HttpResponse(
                200,
                {},
                {
                    "value": [
                        {"id": "pipe-1", "displayName": "care_datapipeline", "type": "DataPipeline"},
                        {"id": "nb-1", "displayName": "care_notebook", "type": "Notebook"},
                    ]
                },
            )
        if method == "POST":
            self.posts.append(path)
            return HttpResponse(202, {"Location": "https://x/v1/jobs/instances/new-job"}, {})
        if path == "/workspaces/ws-dev/items/pipe-1/jobs/instances":
            return HttpResponse(200, {}, {"value": self.jobs})
        raise AssertionError(path)


def _run(statuses, **kwargs):
    fake = FakeFabric(statuses)
    client = FabricRestClient(lambda: "t", transport=fake)
    return fake, operate_live(client, load_configuration(CONFIG), **kwargs)


def test_preview_is_read_only_and_unknown_without_jobs() -> None:
    fake, report = _run([])
    assert fake.posts == []
    assert report["items"][0]["health"] == "unknown"
    assert report["items"][1]["note"] == "No matching Fabric item in workspace"
    assert report["unmonitoredItems"][0]["type"] == "Notebook"


def test_healthy_and_run_triggers_pipeline() -> None:
    fake, report = _run(["Completed"], run=True)
    assert fake.posts == ["/workspaces/ws-dev/items/pipe-1/jobs/instances?jobType=Pipeline"]
    assert report["actions"][0]["action"] == "triggered"
    assert report["items"][0]["health"] == "healthy"


def test_run_skipped_when_already_running() -> None:
    fake, report = _run(["InProgress"], run=True)
    assert fake.posts == []
    assert report["actions"][0]["action"] == "skipped"


def test_retry_when_allowed_and_bounded() -> None:
    fake, report = _run(["Failed"], retry=True)
    assert report["actions"][0]["action"] == "retried"
    assert len(fake.posts) == 1
    fake, report = _run(["Failed", "Failed"], retry=True)
    assert fake.posts == []
    assert report["items"][0]["health"] == "failed-manual"


def test_report_has_no_raw_ids(tmp_path: Path) -> None:
    _, report = _run(["Failed"], retry=True)
    paths = write_operate_report(tmp_path, report)
    text = "".join(p.read_text(encoding="utf-8") for p in paths)
    for raw in ("ws-dev", "pipe-1", "nb-1", "new-job"):
        assert raw not in text
    assert json.loads(paths[0].read_text(encoding="utf-8"))["workspaceIdHash"]
    assert "Morning operations report" in render_morning_report(report)
