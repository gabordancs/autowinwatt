from pathlib import Path

from openpyxl import Workbook

from winwatt_automation.e2e_review.evidence_fusion import RoomStamp, TopologyCell, match_room_stamp
from winwatt_automation.e2e_review.geometry_calibration import DimensionAnchor, calibrate, pixels_to_meters
from winwatt_automation.e2e_review.golden import build_fixture_manifest


def test_calibration_requires_consistent_dimension_chain():
    calibration=calibrate([DimensionAnchor("a",100,2),DimensionAnchor("b",200,4.02)])
    assert calibration.status=="accepted"
    assert round(pixels_to_meters(50,calibration),3)==1.002
    conflict=calibrate([DimensionAnchor("a",100,2),DimensionAnchor("b",100,3)])
    assert conflict.status=="conflict"


def test_room_stamp_cell_fusion_is_explainable():
    stamp=RoomStamp("FSZ-01","NAPPALI",24.17,(4,4,6,6),("stamp",))
    inside=TopologyCell("cell-a",((0,0),(10,0),(10,10),(0,10)),24.2,("geometry",))
    outside=TopologyCell("cell-b",((30,30),(40,30),(40,40),(30,40)),24.1,())
    result=match_room_stamp(stamp,[outside,inside])
    assert result.cell_id=="cell-a" and result.status=="accepted" and result.area_residual_percent<1
    assert result.evidence_ids==("geometry","stamp")


def test_golden_manifest_does_not_claim_approved_geometry(tmp_path: Path):
    workbook=tmp_path/"input.xlsx"; book=Workbook(); sheet=book.active; sheet.title="Helyiségek"; sheet.append(["Helyiségkód","Helyiség","Alapterület [m²]","PDF-forrás"]); sheet.append(["FSZ-01","NAPPALI","24,17","É-02"]); book.save(workbook)
    pdf_root=tmp_path/"pdf"; pdf_root.mkdir(); (pdf_root/"É02.pdf").write_bytes(b"pdf-source")
    manifest=build_fixture_manifest(workbook,pdf_root,tmp_path/"manifest.json")
    assert manifest["fixture_status"]=="needs_human_approved_geometry"
    assert manifest["candidate_inventory"]["total"]==2
