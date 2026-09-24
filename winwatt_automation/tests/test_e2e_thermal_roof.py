from winwatt_automation.e2e_review.roof_geometry import RoofBoundaryCandidate, net_roof_area, polygon_area_3d
from winwatt_automation.e2e_review.thermal_envelope import BoundaryCandidate, classify_boundary


def test_boundary_requires_proven_xy_area_and_zone():
    good=classify_boundary(BoundaryCandidate("B1","FSZ-01","exterior","R5",4,2.8,11.2,("ev",),0.6))
    assert good.status=="accepted" and good.classification=="external_air"
    assert classify_boundary(BoundaryCandidate("B2","P-01","unknown","R15",4,2.8,11.2)).status=="unresolved"
    assert classify_boundary(BoundaryCandidate("B3","FSZ-01","exterior","R5",4,2.8,10)).classification=="xy_area_conflict"


def test_roof_area_uses_3d_plane_not_plan_area():
    # plan rectangle 4×3, rising 3 m across its 3 m width: actual area is 4*sqrt(18)
    polygon=((0,0,0),(4,0,0),(4,3,3),(0,3,3))
    gross=polygon_area_3d(polygon)
    assert round(gross,6)==round(4*(18**0.5),6)
    assert round(net_roof_area(RoofBoundaryCandidate("TT-01","roof-a",polygon,1.2)),6)==round(gross-1.2,6)
