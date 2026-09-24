from pathlib import Path

from winwatt_automation.e2e_review.wall_overlay import WallOverlay


ROOT=Path(__file__).resolve().parents[1]


def test_delceg_wall_overlay_reuses_model_xy_labels():
    overlay=WallOverlay.load(ROOT/"data"/"e2e"/"delceg_wall_overlay.json")
    labels=overlay.labels_for_pdf("É02_TERVEZETT FÖLDSZINTI ALAPRAJZ_végl.pdf")
    assert len(labels)==16
    b10a=next(label for label in labels if label.room_code=="B10a")
    assert b10a.lines[0].startswith("B10a | A=")
    assert any("X×Y=" in line for line in b10a.lines[1:])


def test_overlay_only_matches_the_configured_plan():
    overlay=WallOverlay.load(ROOT/"data"/"e2e"/"delceg_wall_overlay.json")
    assert overlay.labels_for_pdf("unrelated.pdf")==[]
