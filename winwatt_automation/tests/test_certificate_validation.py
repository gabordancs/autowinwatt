import json
from pathlib import Path

from winwatt_automation.certificates.validation import validate_native_readback


def test_readback_validation_compares_counts_geometry_and_loss(tmp_path: Path) -> None:
    model = {"project": {"heated_area_m2": 10, "heated_volume_m3": 30}, "rooms": [
        {"name": "Room", "temperature_c": 20, "air_change_h": 0.8},
    ], "boundaries": [
        {"area_m2": 4, "winwatt_type": "külső fal", "azimuth_deg": 90, "heat_loss_wk": 2},
    ]}
    model_path = tmp_path / "model.json"; model_path.write_text(json.dumps(model), encoding="utf-8")
    xml = tmp_path / "readback.xml"; xml.write_text("""<WinWatt32Project><WinWatt32Building/><WinWatt32Panel/><WinWatt32Room><ItemHeader><ItemName>Room</ItemName></ItemHeader><Area>10</Area><CalculatedVolume>30</CalculatedVolume><Heating><Temp>20</Temp><Filtration><AirChangeFact>0.8</AirChangeFact></Filtration></Heating><Cooling><Temp>26</Temp></Cooling><Boundary><A>4</A><Type>külső fal</Type><Compass>90</Compass><U>0.5</U></Boundary></WinWatt32Room></WinWatt32Project>""", encoding="utf-8")
    report = validate_native_readback(model_path, xml)
    assert report["counts"] == {"buildings": 1, "zones": 0, "rooms": 1, "structures": 1, "boundaries": 1, "layer_rows": 0, "expected_layer_rows": 0}
    assert report["totals"]["transmission_wk"]["absolute"] == 0
    assert report["room_conditions"]["Room"]["air_change_h"]["absolute"] == 0


def test_readback_uses_preserved_name_for_window_type_mapping(tmp_path: Path) -> None:
    model = {"project": {"heated_area_m2": 1, "heated_volume_m3": 1}, "boundaries": [
        {"name": "homlokzati ablak", "area_m2": 2, "winwatt_type": "külső ablak", "azimuth_deg": 180, "heat_loss_wk": 1},
    ]}
    model_path = tmp_path / "model.json"; model_path.write_text(json.dumps(model), encoding="utf-8")
    xml = tmp_path / "readback.xml"; xml.write_text("""<WinWatt32Project><WinWatt32Room><Area>1</Area><CalculatedVolume>1</CalculatedVolume><Boundary><Name>homlokzati ablak</Name><A>2</A><Type>10</Type><Compass>180</Compass><U>0.5</U></Boundary></WinWatt32Room></WinWatt32Project>""", encoding="utf-8")
    report = validate_native_readback(model_path, xml)
    assert report["surface_by_source_type_m2"]["külső ablak"]["actual"] == 2
    assert report["surface_by_azimuth_deg_m2"]["180"]["actual"] == 2


def test_readback_validates_explicit_rooflight_glazing_ratio(tmp_path: Path) -> None:
    model = {"project": {"heated_area_m2": 1, "heated_volume_m3": 1}, "structures": [
        {"name": "Felülvilágító", "note": "90% üvegezési arány"},
    ]}
    model_path = tmp_path / "model.json"; model_path.write_text(json.dumps(model), encoding="utf-8")
    xml = tmp_path / "readback.xml"; xml.write_text("""<WinWatt32Project><WinWatt32Panel><ItemHeader><ItemName>Felülvilágító</ItemName></ItemHeader><GlassRatio>90</GlassRatio></WinWatt32Panel></WinWatt32Project>""", encoding="utf-8")
    report = validate_native_readback(model_path, xml)
    assert report["opening_glass_ratio_percent"]["Felülvilágító"]["absolute"] == 0


def test_readback_compares_native_heating_and_hot_water_fields(tmp_path: Path) -> None:
    model = {
        "project": {"heated_area_m2": 32.8, "heated_volume_m3": 88.6},
        "systems": [
            {
                "name": "Gázkonvektor", "type": "heating", "served_area_m2": 32.8,
                "carrier": "földgáz", "generator_performance_factor": 1.4,
                "net_heat_kwh_a": 8154, "final_energy_kwh_a": 13698,
            },
            {
                "name": "Bojler", "type": "hot_water", "served_area_m2": 32.8,
                "carrier": "elektromos áram", "generator_performance_factor": 1,
                "net_demand_kwh_m2a": 25, "final_energy_kwh_a": 927,
                "storage_loss_percent": 13,
            },
        ],
    }
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")
    xml = tmp_path / "readback.xml"
    xml.write_text("""<WinWatt32Project><WinWatt32Building><EPBD>
      <HeatingEnergy>6486.1</HeatingEnergy>
      <WinWatt32HeatingSystemItem><Name>Gázkonvektor</Name><SystemArea>32.8</SystemArea>
        <EnergyConsumptions><ConsumptionTableItem Consumption="10897"/></EnergyConsumptions>
        <StokerItem><EnergySourceTypeDescription>földgáz</EnergySourceTypeDescription><Ck>1.4</Ck><CkDescription>Gázkonvektor</CkDescription></StokerItem>
      </WinWatt32HeatingSystemItem>
      <WinWatt32WaterHeatingSystemItem><Name>Bojler</Name><SystemArea>32.8</SystemArea>
        <EnergyConsumptions><ConsumptionTableItem Consumption="926.6"/></EnergyConsumptions>
        <StokerItem><EnergySourceTypeDescription>elektromos áram</EnergySourceTypeDescription><Ck>1</Ck><CkDescription>Elektromos</CkDescription></StokerItem>
        <qHMV>25</qHMV><qft>13</qft><qftDescription>fűtött térben</qftDescription>
        <qfvDescription>Nincs</qfvDescription><EcDescription>nincs segédenergia igény</EcDescription>
      </WinWatt32WaterHeatingSystemItem>
    </EPBD></WinWatt32Building></WinWatt32Project>""", encoding="utf-8")

    report = validate_native_readback(model_path, xml)

    assert report["mechanics_included"] is True
    assert report["system_readback"]["native_counts"]["heating"] == 1
    assert report["system_readback"]["native_counts"]["hot_water"] == 1
    assert report["system_readback"]["native_counts"]["cooling"] == 0
    heating, hot_water = report["system_readback"]["items"]
    assert heating["carrier"]["equal"] is True
    assert heating["net_heat_kwh_a"]["actual"] == 6486
    assert heating["net_heat_kwh_a"]["raw_actual"] == 6486.1
    assert heating["final_energy_kwh_a"]["absolute"] == -2801
    assert heating["final_energy_kwh_a"]["raw_actual"] == 10897
    assert hot_water["net_demand_kwh_m2a"]["absolute"] == 0
    assert hot_water["storage_loss_percent"]["absolute"] == 0
    assert hot_water["final_energy_kwh_a"]["absolute"] == 0
    assert hot_water["final_energy_kwh_a"]["raw_actual"] == 926.6
