from pathlib import Path

from winwatt_automation.e2e_review.material_resolution import resolve_layers


def test_local_catalog_is_used_before_new_material(tmp_path: Path):
    catalog=tmp_path/"catalog.xml"
    catalog.write_text("""<?xml version='1.0'?><Root><WinWatt32Material><ItemHeader><ItemName>Monolit vasbeton födémszerkezet</ItemName><ID>17</ID><ItemPath>Anyagok</ItemPath></ItemHeader><ThermalCond>1.7</ThermalCond><Density>2400</Density><HeatCapacity>0.88</HeatCapacity></WinWatt32Material></Root>""",encoding="utf-8")
    layers,decisions,warnings=resolve_layers([{"structure":"R8","sequence":5,"name":"Monolit vasbeton födémszerkezet"}],catalog)
    assert decisions[0]["status"]=="catalog" and not warnings
    assert layers[0]["catalog_material_id"]=="17" and layers[0]["lambda_wmk"]==1.7


def test_unmatched_material_remains_review_not_new(tmp_path: Path):
    catalog=tmp_path/"catalog.xml"; catalog.write_text("<Root/>",encoding="utf-8")
    _,decisions,warnings=resolve_layers([{"structure":"R1","sequence":1,"name":"Kerámia tetőcserép fedés"}],catalog)
    assert decisions[0]["status"]=="review" and warnings
