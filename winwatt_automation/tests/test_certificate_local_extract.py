from winwatt_automation.certificates.local_extract import candidate_material_lines


def test_material_candidates_exclude_bare_dimension_rows() -> None:
    pages = ["PVC 60 mm-es 3 kamrás\nszélesség = 70 mm\n15,6 m\n77.000 m\n"]
    assert candidate_material_lines(pages) == ["PVC 60 mm-es 3 kamrás"]
