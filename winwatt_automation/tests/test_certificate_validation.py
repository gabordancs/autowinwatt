import json
from pathlib import Path

from winwatt_automation.certificates.validation import validate_native_readback


def test_readback_validation_compares_counts_geometry_and_loss(tmp_path: Path) -> None:
    model = {"project": {"heated_area_m2": 10, "heated_volume_m3": 30}, "boundaries": [
        {"area_m2": 4, "winwatt_type": "külső fal", "azimuth_deg": 90, "heat_loss_wk": 2},
    ]}
    model_path = tmp_path / "model.json"; model_path.write_text(json.dumps(model), encoding="utf-8")
    xml = tmp_path / "readback.xml"; xml.write_text("""<WinWatt32Project><WinWatt32Building/><WinWatt32Panel/><WinWatt32Room><Area>10</Area><CalculatedVolume>30</CalculatedVolume><Boundary><A>4</A><Type>külső fal</Type><Compass>90</Compass><U>0.5</U></Boundary></WinWatt32Room></WinWatt32Project>""", encoding="utf-8")
    report = validate_native_readback(model_path, xml)
    assert report["counts"] == {"buildings": 1, "zones": 0, "rooms": 1, "structures": 1, "boundaries": 1, "layer_rows": 0, "expected_layer_rows": 0}
    assert report["totals"]["transmission_wk"]["absolute"] == 0
