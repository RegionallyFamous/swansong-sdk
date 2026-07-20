"""Deterministic comparisons between SwanSong resource reports."""

from __future__ import annotations

from typing import Mapping


REPORT_SCHEMA = "swansong-budget-diff-report-v1"
DEFAULT_METRICS = (
    "romBytes",
    "linkedInternalRamBytes",
    "linkedMonoAreaBytes",
    "linkedColorAreaBytes",
    "sourceAssetBytes",
    "generatedTileBytes",
    "audioBytes",
    "uniqueTiles",
)


class BudgetHistoryError(RuntimeError):
    pass


def _number(report: Mapping[str, object], key: str) -> int | None:
    value = report.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BudgetHistoryError(f"resource report field {key} must be a non-negative integer or null")
    return value


def compare_resource_reports(current: Mapping[str, object], baseline: Mapping[str, object], *,
                             allowed_increase: Mapping[str, int] | None = None,
                             metrics: tuple[str, ...] = DEFAULT_METRICS) -> dict[str, object]:
    limits = dict(allowed_increase or {})
    unknown = sorted(set(limits) - set(metrics))
    if unknown:
        raise BudgetHistoryError("unknown budget metrics: " + ", ".join(unknown))
    comparisons: list[dict[str, object]] = []
    regressions: list[str] = []
    for key in metrics:
        before = _number(baseline, key)
        after = _number(current, key)
        maximum = limits.get(key)
        if maximum is not None and (not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0):
            raise BudgetHistoryError(f"allowed increase for {key} must be a non-negative integer")
        comparable = before is not None and after is not None
        delta = after - before if comparable else None
        regression = comparable and maximum is not None and delta > maximum
        if regression:
            regressions.append(key)
        comparisons.append({
            "metric": key,
            "baseline": before,
            "current": after,
            "delta": delta,
            "allowedIncrease": maximum,
            "comparable": comparable,
            "regression": regression,
        })
    return {
        "schema": REPORT_SCHEMA,
        "project": current.get("project"),
        "baselineProject": baseline.get("project"),
        "comparisons": comparisons,
        "regressions": regressions,
        "ok": not regressions,
    }
