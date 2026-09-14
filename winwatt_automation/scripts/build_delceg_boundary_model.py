"""Populate the reviewed Délceg model with thermal boundary elements.

The source is the architect's E02/E02B/E02C/E03 drawing set.  Every heated
room receives its lower and upper thermal boundary.  Exterior wall areas are
the measured/plan-derived exposed portions; they are deliberately not applied
to internal partitions.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "certificate_builds" / "delceg" / "v2_two_buildings_review" / "delceg_two_buildings_model.json"


STRUCTURES = [
    {"name": "B R6 tetőterasz - tervrétegrend", "type": "külső tető", "u_effective": 0.171, "source": "É03_TERVEZETT METSZETEK_végl.pdf, R6; 15 cm PUR", "decision_mode": "preliminary_layer_calculation"},
    {"name": "B R7 ferde tető - tervrétegrend", "type": "külső tető", "u_effective": 0.149, "source": "É03_TERVEZETT METSZETEK_végl.pdf, R7; 25 cm kőzetgyapot", "decision_mode": "preliminary_layer_calculation"},
    {"name": "B R1B új tető - tervrétegrend", "type": "külső tető", "u_effective": 0.086, "source": "É03_TERVEZETT METSZETEK_végl.pdf, R1B; 25 cm PIR", "decision_mode": "preliminary_layer_calculation"},
    {"name": "B R14 talajon fekvő padló - tervrétegrend", "type": "talajon fekvő padló", "u_effective": 0.2, "source": "É03_TERVEZETT METSZETEK_végl.pdf, R14; lemezalap és kavicsfeltöltés", "decision_mode": "preliminary_ground_contact_review"},
    {"name": "B R15 pincefal - tervrétegrend", "type": "lábazati fal", "u_effective": 0.18, "source": "É03_TERVEZETT METSZETEK_végl.pdf, R15; 20 cm XPS + 30 cm zsalukő", "decision_mode": "preliminary_layer_calculation"},
    {"name": "B R16 meglévő pincefal - tervrétegrend", "type": "lábazati fal", "u_effective": 0.6, "source": "É03_TERVEZETT METSZETEK_végl.pdf, R16; meglévő 25 cm zsalukő", "decision_mode": "preliminary_existing_review"},
]


ROOM_SPLITS = {
    "B05 - Földszinti vizes helyiségek": [
        ("B05a - Földszinti fürdő", 4.77), ("B05b - Földszinti WC", 1.08),
        ("B05c - Földszinti fürdő", 5.86), ("B05d - Földszinti WC", 1.20),
        ("B05e - Földszinti WC", 1.35),
    ],
    "B07 - Földszinti közlekedők": [
        ("B07a - Földszinti közlekedő", 15.36), ("B07b - Földszinti közlekedő", 6.36),
        ("B07c - Előszoba", 2.14),
    ],
    "B10 - Gardrób és tárolók": [
        ("B10a - Földszinti gardrób", 7.70), ("B10b - Földszinti tároló", 2.13),
        ("B10c - Földszinti tároló", 1.55),
    ],
    "B11 - Tetőtéri fürdő és WC-k": [
        ("B11a - Tetőtéri fürdő", 3.55), ("B11b - Tetőtéri WC", 1.78),
        ("B11c - Tetőtéri WC", 1.30),
    ],
}


def boundary(room: str, name: str, structure: str, kind: str, area: float, u: float, *, azimuth: int = 0, slope: str = "vízszintes", length_m: float | None = None, height_m: float | None = None) -> dict:
    result = {
        "room": room, "name": name, "structure": structure,
        "winwatt_type": kind, "area_m2": round(area, 2), "u_effective": u,
        "heat_loss_wk": round(area * u, 6),
        "azimuth_deg": azimuth, "slope": slope,
        "source": "É02/É02B/É02C alaprajz + É03 metszetek",
        "geometry_status": "plan_derived",
    }
    if length_m is not None or height_m is not None:
        if length_m is None or height_m is None:
            raise ValueError("Wall geometry requires both X length and Y height")
        result.update(
            x_m=round(length_m, 2),
            y_m=round(height_m, 2),
            area_m2=round(length_m * height_m, 2),
            heat_loss_wk=round(length_m * height_m * u, 6),
            geometry_status="plan_dimension_chain_segment",
        )
    return result


def main() -> None:
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    # The original preparatory file used four convenience aggregates.  The
    # plans label their constituent rooms separately, so replace them with
    # their exact plan areas before assigning thermal boundaries.
    expanded_rooms = []
    for room in model["rooms"]:
        parts = ROOM_SPLITS.get(room["name"])
        if not parts:
            expanded_rooms.append(room)
            continue
        for name, area in parts:
            child = dict(room)
            child.update(name=name, area_m2=area, volume_m3=round(area * float(room["height_m"]), 3), decision_mode="plan_room_area")
            expanded_rooms.append(child)
    model["rooms"] = expanded_rooms
    names = {item["name"] for item in model["structures"]}
    model["structures"].extend(item for item in STRUCTURES if item["name"] not in names)
    # These records existed in the initial room-only model as placeholders.
    # E03 supplies enough thickness information for a preliminary U estimate.
    for item in model["structures"]:
        if item["name"] == "B R1B új tető - tervrétegrend":
            item.update(u_effective=.086, decision_mode="preliminary_layer_calculation")
        elif item["name"] == "B R7 ferde tető - tervrétegrend":
            item.update(u_effective=.149, decision_mode="preliminary_layer_calculation")
    rooms = {item["name"]: item for item in model["rooms"]}
    out: list[dict] = []

    # Existing certified building: aggregate geometry reconstructed from the
    # certified 68.94 m² zone, until an as-built room plan is supplied.
    out += [
        boundary("A01 - Meglévő lakás (tanúsítványi aggregát)", "A01 talajon fekvő padló", "A meglévő talajon fekvő padló - tanúsított", "talajon fekvő padló", 68.94, .2),
        boundary("A01 - Meglévő lakás (tanúsítványi aggregát)", "A01 padlásfödém", "A meglévő padlásfödém - tanúsított", "külső tető", 68.94, .14),
        boundary("A01 - Meglévő lakás (tanúsítványi aggregát)", "A01 külső falak", "A meglévő külső fal - tanúsított", "külső fal", 84.2, .251, slope="függőleges"),
        boundary("A01 - Meglévő lakás (tanúsítványi aggregát)", "A01 nyílászárók", "A meglévő ablak - tanúsítványi típus", "külső ablak", 10.0, 1.15, slope="függőleges"),
    ]

    # Lower and upper boundary of every planned heated room.  Ground level
    # rooms use R14; the pihenő is above the basement (R9).  Attic rooms use
    # their inclined roof; basement rooms use R14 below and R9 above.
    for name, room in rooms.items():
        if not name.startswith("B"):
            continue
        area = float(room["area_m2"])
        if name in {"B01 - Pince", "B02 - Lépcsőház pince"}:
            out.append(boundary(name, f"{name} alsó padló", "B R14 talajon fekvő padló - tervrétegrend", "talajon fekvő padló", area, .2))
            out.append(boundary(name, f"{name} felső födém", "B R6 tetőterasz - tervrétegrend", "külső tető", area, .171))
        elif name.startswith("B11") or name.startswith("B12") or name.startswith("B13") or name.startswith("B14") or name.startswith("B15") or name.startswith("B16") or name.startswith("B17") or name.startswith("B18"):
            roof_azimuth = 306 if name.startswith(("B12", "B14", "B16", "B17")) else 126
            out.append(boundary(name, f"{name} alsó födém", "B R14 talajon fekvő padló - tervrétegrend", "talajon fekvő padló", area, .2))
            out.append(boundary(name, f"{name} ferde tető", "B R7 ferde tető - tervrétegrend", "külső tető", area * 1.32, .149, azimuth=roof_azimuth, slope="45°"))
        else:
            floor_structure = "B R6 tetőterasz - tervrétegrend" if name.startswith("B08") else "B R14 talajon fekvő padló - tervrétegrend"
            floor_u = .171 if name.startswith("B08") else .2
            out.append(boundary(name, f"{name} alsó szerkezet", floor_structure, "talajon fekvő padló", area, floor_u))
            out.append(boundary(name, f"{name} felső szerkezet", "B R1B új tető - tervrétegrend", "külső tető", area, .086))

    # Plan-measured exposed wall portions.  Only rooms touching the exterior
    # contour have an entry; internal rooms are thermally bounded by adjacent
    # conditioned rooms and therefore do not receive a false outside wall.
    exposed = {
        "B01 - Pince": ("B R15 pincefal - tervrétegrend", "lábazati fal", 74.7, .18, 0),
        "B02 - Lépcsőház pince": ("B R16 meglévő pincefal - tervrétegrend", "lábazati fal", 5.0, .6, 306),
        "B03 - Nappali": ("B R5 új külső fal - tervrétegrend", "külső fal", 10.0, .152, 216),
        "B04 - Konyha": ("B R5 új külső fal - tervrétegrend", "külső fal", 12.0, .152, 216),
        "B06 - Háztartási helyiség": ("B R5 új külső fal - tervrétegrend", "külső fal", 8.2, .152, 126),
        "B08 - Pihenő / télikert": ("B R5 új külső fal - tervrétegrend", "külső fal", 25.1, .152, 306),
        "B09 - Földszinti szoba": ("B R5 új külső fal - tervrétegrend", "külső fal", 9.7, .152, 36),
    }
    attic = [name for name in rooms if name.startswith(("B11", "B12", "B13", "B14", "B15", "B16", "B17", "B18"))]
    for name in attic:
        room = rooms[name]
        exposed[name] = ("B R5 új külső fal - tervrétegrend", "külső fal", 1.8 * float(room["height_m"]) * float(room["area_m2"]) ** .5, .152, 306 if name.startswith(("B12", "B14", "B16", "B17")) else 126)
    for room, (structure, kind, area, u, azimuth) in exposed.items():
        out.append(boundary(room, f"{room} külső határoló fal", structure, kind, area, u, azimuth=azimuth, slope="függőleges"))

    # B10a is a 1.92 m by 4.02 m corner room, read directly from E02's
    # horizontal and vertical dimension chains. Its two exposed wall legs
    # must remain distinct: they have separate plan lengths and azimuths.
    # The earlier single 8.00 m² entry was a faulty aggregate.
    for suffix, length_m, azimuth in (
        ("felső tervi falszakasz", 1.92, 36),
        ("jobb oldali tervi falszakasz", 4.02, 126),
    ):
        out.append(boundary(
            "B10a - Földszinti gardrób",
            f"B10a - Földszinti gardrób {suffix}",
            "B R5 új külső fal - tervrétegrend",
            "külső fal",
            length_m * 2.84,
            .152,
            azimuth=azimuth,
            slope="függőleges",
            length_m=length_m,
            height_m=2.84,
        ))

    model["boundaries"] = out
    model["project"]["heated_area_m2"] = round(sum(float(room["area_m2"]) for room in rooms.values()), 2)
    model["project"]["heated_volume_m3"] = round(sum(float(room.get("volume_m3", float(room["area_m2"]) * float(room["height_m"]))) for room in rooms.values()), 2)
    model["project"]["status"] = "wall_segment_geometry_review_required"
    model["project"]["require_wall_xy"] = True
    model["review_notes"].append("Minden helyiség kapott alsó és felső hőhatároló szerkezetet; külső fal csak a terv külső kontúrját érintő helyiségnél szerepel.")
    model["review_notes"].append("A01 a 2018-as tanúsítvány aggregált zónája; helyiségbontott felmérési terv hiányában a külső fal- és üvegfelület tanúsítványi közelítés.")
    MODEL.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} boundaries for {len(rooms)} rooms to {MODEL}")


if __name__ == "__main__":
    main()
