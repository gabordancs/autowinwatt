from pathlib import Path

from winwatt_automation.certificates.materials import load_catalog, match_by_name, match_material


def test_local_catalog_match_and_air_gap(tmp_path: Path) -> None:
    catalog_path = tmp_path / "materials.xml"
    catalog_path.write_text(
        """<?xml version='1.0' encoding='utf-8'?><WinWatt32Project>
        <WinWatt32Material><ItemHeader><ItemName>cementvakolat</ItemName><ItemPath>Falazat</ItemPath><ID>7</ID></ItemHeader><Density>1700</Density><ThermalCond>0.72</ThermalCond><HeatCapacity>0.88</HeatCapacity></WinWatt32Material>
        </WinWatt32Project>""", encoding="utf-8"
    )
    catalog = load_catalog(catalog_path)
    matched = match_by_name("cementvakolat", catalog)
    assert matched.status == "catalog"
    assert matched.candidate and matched.candidate.material_id == "7"
    assert match_by_name("zart legreteg", catalog).status == "special"
    assert match_material("cementvakolat", catalog, lambda_wmk=0.72, density_kgm3=1700).status == "catalog"
    assert match_material("cementvakolat", catalog, lambda_wmk=0.03).status == "review"


def test_family_hint_does_not_dilute_an_exact_catalogue_name(tmp_path: Path) -> None:
    catalog_path = tmp_path / "materials.xml"
    catalog_path.write_text(
        """<?xml version='1.0' encoding='utf-8'?><WinWatt32Project>
        <WinWatt32Material><ItemHeader><ItemName>kavicsfeltöltés</ItemName><ItemPath>Feltöltések</ItemPath><ID>343</ID></ItemHeader><Density>1800</Density><ThermalCond>0.35</ThermalCond><HeatCapacity>0.84</HeatCapacity></WinWatt32Material>
        </WinWatt32Project>""", encoding="utf-8"
    )
    decision = match_material(
        "Kavicsfeltöltés", load_catalog(catalog_path), family="talajon fekvő szerkezet",
        lambda_wmk=0.35, density_kgm3=1800, heat_capacity_kjkgk=0.84,
    )
    assert decision.status == "catalog"
    assert decision.candidate and decision.candidate.material_id == "343"
