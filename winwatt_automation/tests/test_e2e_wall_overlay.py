from pathlib import Path

from winwatt_automation.e2e_review.wall_overlay import WallOverlay, WallOverlayLabel, layout_outside_labels


ROOT=Path(__file__).resolve().parents[1]


def test_delceg_wall_overlay_reuses_model_xy_labels():
    overlay=WallOverlay.load(ROOT/"data"/"e2e"/"delceg_wall_overlay.json")
    labels=overlay.labels_for_pdf("É02_TERVEZETT FÖLDSZINTI ALAPRAJZ_végl.pdf")
    assert len(labels)>16  # room summaries plus individual vertical walls
    b10a_room=next(label for label in labels if label.room_code=="B10a" and label.target_x_ratio is None)
    b10a_wall=next(label for label in labels if label.room_code=="B10a" and label.target_x_ratio is not None)
    assert b10a_room.lines[0].startswith("B10a | A=")
    assert "x (alaprajzi falhossz)" in b10a_wall.lines[1]
    assert "y (fal magassága)" in b10a_wall.lines[2]
    assert (b10a_wall.target_x_ratio,b10a_wall.target_y_ratio)!=(b10a_wall.x_ratio,b10a_wall.y_ratio)


def test_overlay_only_matches_the_configured_plan():
    overlay=WallOverlay.load(ROOT/"data"/"e2e"/"delceg_wall_overlay.json")
    assert overlay.labels_for_pdf("unrelated.pdf")==[]


def test_labels_move_to_margin_without_overlap():
    labels=[WallOverlayLabel(.2,.1,("one","two"),"A"),WallOverlayLabel(.2,.11,("one","two"),"B"),WallOverlayLabel(.8,.1,("one","two"),"C")]
    placed=layout_outside_labels(labels,1000,1000,line_height=20,width_for_lines=lambda lines:100)
    left=sorted((item for item in placed if item.side=="left"),key=lambda item:item.rect_y)
    assert all(item.rect_x==18 for item in left)
    assert left[0].rect_y+left[0].height < left[1].rect_y
    right=next(item for item in placed if item.side=="right")
    assert right.rect_x+right.width==982
