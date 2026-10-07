from __future__ import annotations

import pytest

from fabricops.synthea import SyntheaError, summarize, synthea_settings


def test_settings_defaults_and_limits() -> None:
    assert synthea_settings({})["seed"] == 42
    with pytest.raises(SyntheaError):
        synthea_settings({"synthea": {"population": 5000}})


def test_summary_reports_counts_only(tmp_path) -> None:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    (csv_dir / "patients.csv").write_text("Id,FIRST\n1,Jane\n2,John\n", encoding="utf-8")

    report = summarize(tmp_path)

    assert report["tableRowCounts"] == {"patients": 2}
    assert "Jane" not in str(report)


def test_empty_dataset_fails(tmp_path) -> None:
    (tmp_path / "csv").mkdir()
    with pytest.raises(SyntheaError):
        summarize(tmp_path)
