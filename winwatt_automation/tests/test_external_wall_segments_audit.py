from scripts.audit_external_wall_segments import audit


def test_marks_aggregate_r5_and_preserves_b10a_separate_segments():
    model = {"rooms": [
        {"name": "B03 - Nappali"},
        {"name": "B10a - Földszinti gardrób"},
    ], "boundaries": [
        {"room": "B03 - Nappali", "structure": "B R5 új külső fal - tervrétegrend", "name": "B03 wall", "area_m2": 1, "azimuth_deg": 0},
        {"room": "B10a - Földszinti gardrób", "structure": "B R5 új külső fal - tervrétegrend", "name": "B10a top", "area_m2": 2, "azimuth_deg": 36},
        {"room": "B10a - Földszinti gardrób", "structure": "B R5 új külső fal - tervrétegrend", "name": "B10a right", "area_m2": 3, "azimuth_deg": 126},
    ]}
    result = audit(model)
    assert result["counts"] == {"rooms": 2, "single_r5": 1, "separate_r5": 1, "multi_wall_candidates": 1}
    assert result["rooms"][0]["status"] == "multiple_wall_candidate_requires_measurement"
    assert result["rooms"][1]["status"] == "separate_segments_present"
