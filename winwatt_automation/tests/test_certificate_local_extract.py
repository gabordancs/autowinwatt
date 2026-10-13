from winwatt_automation.certificates.local_extract import candidate_material_lines, extract_known_values


def test_material_candidates_exclude_bare_dimension_rows() -> None:
    pages = [
        "PVC 60 mm-es 3 kamrás\nszélesség = 70 mm\n15,6 m\n77.000 m\n"
        "x méret: 0,9 m\ny méret: 2,4 m\n[kWh/m\n"
    ]
    assert candidate_material_lines(pages) == ["PVC 60 mm-es 3 kamrás"]


def test_known_values_support_current_winwatt_certificate_labels() -> None:
    values = extract_known_values([
        "Hasznos alapterület: 64.37 m2\n"
        "Összesített energetikai jellemző: 46.40 kWh/m2a\n"
        "Fajlagos széndioxid kibocsátás: 10.11 kg/m2a\n"
        "Épület felület-térfogat aránya: 0.671 m2/m3\n"
        "Fajlagos hőveszteségtényező: 0.571 W/m3K\n"
    ])
    assert {item.key: item.value for item in values} == {
        "useful_floor_area_m2": 64.37,
        "area_volume_ratio_m2_m3": 0.671,
        "summaries_energy_rating_kwh_m2a": 46.4,
        "co2_kg_m2a": 10.11,
        "heat_loss_factor_w_m3k": 0.571,
    }
