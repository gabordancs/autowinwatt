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
