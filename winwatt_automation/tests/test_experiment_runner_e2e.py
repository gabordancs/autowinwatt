from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from winwatt_automation.experiments import ExperimentRunner
from winwatt_automation.knowledge import ExperimentSpec, KnowledgeStatus, KnowledgeStore


pytestmark = pytest.mark.skipif(os.environ.get("WINWATT_E2E") != "1", reason="set WINWATT_E2E=1 to run WinWatt sandbox E2E tests")


def test_room_area_experiment_save_reopen_e2e(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "tests" / "testwwp.wwp"
    name = f"Knowledge area {uuid4().hex[:8]}"
    spec = ExperimentSpec.model_validate({
        "hypothesis_id": "hyp_room_area_e2e", "target_capability": "room.area_m2",
        "change": {"entity": name, "to": 31.7}, "observe": ["ui_readback", "save_reopen"],
    })
    result = ExperimentRunner(output_dir=root / "data" / "runtime_maps" / "experiments_e2e").run(spec, source)
    assert result.success, result.model_dump_json(indent=2)
    assert result.actual == pytest.approx(31.7)
    assert result.roundtrip_verified
    store = KnowledgeStore(tmp_path / "knowledge.json", root / "data" / "capabilities" / "room_capabilities.json")
    store.store_experiment_result(result)
    concept = store.promote_to_verified("room.area_m2", result)
    assert concept.status is KnowledgeStatus.VERIFIED
