"""Read-only dashboard data loading and view-model helpers for Winner Tilt AI.

This module intentionally performs presentation-only transformations. It does
not call or alter scoring, portfolio, research, or backtest business logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = {
    "score": Path("reports/winner-tilt-prototype-score-run-v1.0.json"),
    "portfolio": Path("reports/winner-tilt-prototype-portfolio-run-v1.0.json"),
    "backtest": Path("reports/winner-tilt-m5-prototype-backtest-run-v1.0.json"),
    "research": Path("reports/winner-tilt-research-prototype-run-v1.0.json"),
    "events": Path("reports/winner-tilt-m6-prototype-events-v1.0.json"),
}

REQUIRED = {
    "score": ["results"],
    "portfolio": ["as_of_date", "holdings", "reserves", "dca_allocation", "portfolio_summary"],
    "backtest": ["validation_status", "metrics", "benchmark_metrics", "relative_metrics", "integrity_validation"],
    "research": ["run_status", "non_interference", "accepted_events"],
    "events": ["events"],
}

@dataclass(frozen=True)
class DashboardInput:
    name: str
    path: Path
    data: dict
    size_bytes: int
    modified_at_utc: str
    synthetic: bool


def repo_path(relative: str | Path, root: Path = REPO_ROOT) -> Path:
    path = Path(relative)
    if path.is_absolute():
        raise ValueError(f"Dashboard paths must be repository-relative: {relative}")
    return (root / path).resolve()


def _load_json(name: str, relative_path: Path, root: Path) -> DashboardInput:
    path = repo_path(relative_path, root)
    if not path.exists():
        raise FileNotFoundError(f"Missing required dashboard input '{name}': {relative_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Dashboard input '{name}' must be a JSON object")
    missing = [field for field in REQUIRED[name] if field not in data]
    if missing:
        raise ValueError(f"Dashboard input '{name}' missing required fields: {', '.join(missing)}")
    stat = path.stat()
    text = json.dumps(data).lower()
    return DashboardInput(
        name=name,
        path=relative_path,
        data=data,
        size_bytes=stat.st_size,
        modified_at_utc=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        synthetic="synthetic" in text or "validation_only" in text,
    )


def load_dashboard_inputs(root: Path = REPO_ROOT, inputs: dict[str, Path] = DEFAULT_INPUTS) -> dict[str, DashboardInput]:
    return {name: _load_json(name, rel, root) for name, rel in inputs.items()}


def _pct(value: float | int | None) -> float | None:
    return None if value is None else round(float(value) * 100, 4)


def build_dashboard_view_model(loaded: dict[str, DashboardInput], *, stale_after_days: int = 7) -> dict:
    now = datetime.now(timezone.utc)
    portfolio = loaded["portfolio"].data
    score = loaded["score"].data
    backtest = loaded["backtest"].data
    research = loaded["research"].data

    freshness = []
    warnings = []
    for item in loaded.values():
        modified = datetime.fromisoformat(item.modified_at_utc)
        age_days = (now - modified).days
        stale = age_days > stale_after_days
        if item.synthetic:
            warnings.append(f"{item.name} contains synthetic/prototype or validation-only data; not investment evidence.")
        if stale:
            warnings.append(f"{item.name} input is stale: modified {age_days} days ago.")
        freshness.append({"name": item.name, "path": str(item.path), "modified_at_utc": item.modified_at_utc, "size_bytes": item.size_bytes, "stale": stale, "synthetic": item.synthetic})

    non_interference = research.get("non_interference", {})
    if any(non_interference.get(k) for k in ("scoring_modified", "portfolio_modified", "backtest_modified", "dca_modified")):
        raise ValueError("Research run is not presentation-safe: non-interference flags indicate modifications")

    holdings = sorted(portfolio["holdings"], key=lambda r: r.get("portfolio_rank", 999))[:15]
    reserves = sorted(portfolio["reserves"], key=lambda r: r.get("reserve_rank", r.get("overall_rank", 999)))[:15]
    dca = portfolio["dca_allocation"]
    score_rows = sorted(score["results"], key=lambda r: r.get("overall_rank") or 999)[:30]

    return {
        "status": {
            "dashboard_mode": "READ_ONLY_PRESENTATION_ONLY",
            "portfolio_as_of_date": portfolio["as_of_date"],
            "research_status": research["run_status"],
            "backtest_validation_status": backtest["validation_status"],
            "warnings": sorted(set(warnings)),
        },
        "holdings": [{**h, "weight_pct": _pct(h.get("weight")), "dca_allocation": dca.get(h["security_id"], 0)} for h in holdings],
        "reserves": reserves,
        "scores": score_rows,
        "concentration": portfolio["portfolio_summary"],
        "backtest": {"metrics": backtest["metrics"], "benchmark_metrics": backtest["benchmark_metrics"], "relative_metrics": backtest["relative_metrics"], "integrity_validation": backtest["integrity_validation"]},
        "research": {"non_interference": non_interference, "events": research["accepted_events"]},
        "freshness": freshness,
    }
