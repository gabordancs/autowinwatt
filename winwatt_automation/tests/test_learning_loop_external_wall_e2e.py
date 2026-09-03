from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from winwatt_automation.experiments import ExperimentRunner
from winwatt_automation.knowledge import ExperimentSpec, Hypothesis, KnowledgeStatus, KnowledgeStore


pytestmark = pytest.mark.skipif(os.environ.get("WINWATT_E2E") != "1", reason="set WINWATT_E2E=1 to run WinWatt sandbox E2E tests")


def test_external_wall_x_learning_lifecycle_e2e(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    capability = "room.boundary.external_wall.x_m"
    name = f"Learning wall {uuid4().hex[:8]}"
    spec = ExperimentSpec.model_validate({
        "hypothesis_id": "hyp_external_wall_x_e2e", "target_capability": capability,
        "change": {"entity": name, "to": 1.37}, "observe": ["ui_readback", "save_reopen"],
    })
    store = KnowledgeStore(tmp_path / "knowledge.json", root / "data" / "capabilities" / "room_capabilities.json")
    assert store.get_concept(capability) is None
    store.store_hypothesis(Hypothesis(
        hypothesis_id=spec.hypothesis_id, target_capability=capability,
        semantic_guess="External-wall X geometry in metres", confidence=0.72,
    ))
    result = ExperimentRunner(output_dir=root / "data" / "runtime_maps" / "learning_loop_e2e").run(spec, root / "tests" / "testwwp.wwp")
    store.store_experiment_result(result)
    assert result.success, result.model_dump_json(indent=2)
    assert result.actual == pytest.approx(1.37)
    concept = store.promote_to_verified(capability, result)
    assert concept.status is KnowledgeStatus.VERIFIED
    assert store.get_hypothesis(spec.hypothesis_id).status is KnowledgeStatus.VERIFIED
