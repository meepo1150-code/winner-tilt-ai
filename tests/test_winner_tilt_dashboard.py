import copy
import json
import pytest
from winner_tilt.dashboard import DEFAULT_INPUTS, build_dashboard_view_model, load_dashboard_inputs, repo_path


def test_dashboard_loads_required_inputs():
    loaded = load_dashboard_inputs()
    assert set(loaded) == set(DEFAULT_INPUTS)
    assert loaded["portfolio"].data["holdings"]
    assert loaded["portfolio"].path == DEFAULT_INPUTS["portfolio"]


def test_dashboard_rejects_absolute_paths():
    with pytest.raises(ValueError, match="repository-relative"):
        repo_path("/mnt/data/not-allowed.json")


def test_dashboard_view_model_is_read_only_and_labeled():
    loaded = load_dashboard_inputs()
    before = copy.deepcopy({k: v.data for k, v in loaded.items()})
    vm = build_dashboard_view_model(loaded)
    assert vm["status"]["dashboard_mode"] == "READ_ONLY_PRESENTATION_ONLY"
    assert len(vm["holdings"]) == 15
    assert len(vm["reserves"]) == 15
    assert any("not investment evidence" in w for w in vm["status"]["warnings"])
    assert before == {k: v.data for k, v in loaded.items()}


def test_dashboard_fails_closed_on_missing_required_field(tmp_path):
    for name, rel in DEFAULT_INPUTS.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads((repo_path(rel)).read_text())
        if name == "portfolio":
            data.pop("holdings")
        target.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields: holdings"):
        load_dashboard_inputs(root=tmp_path)
