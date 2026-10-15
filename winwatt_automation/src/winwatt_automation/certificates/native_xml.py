"""Deterministic native XML compiler from a reviewed certificate model.

The model is deliberately explicit (rooms, structures, layers, boundaries).
PDF extraction never calls this compiler directly: geometry must first be
reviewed or be produced by a deterministic plan parser.
"""
from __future__ import annotations
import copy
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from .geometry import is_vertical_wall, wall_geometry_issues, xy_area

PANEL_TYPES={
    "külső fal":("OutsideWall",0),
    "lábazati fal":("OutsideWall",0),
    # WinWatt 9.60 native exports use the FloorISO record for the ISO 13370
    # floor editor.  That schema contains both ISOFloor and ISOWall fields;
    # using Roof1 is normalized back to an ordinary roof and loses the ground
    # heat-loss calculation.  Ground-wall use is verified by a dedicated
    # sandbox import/readback before promotion to a real reconstruction.
    "talajjal érintkező fal (ISO 13370)":("FloorISO",25),
    "talajon fekvő padló":("FloorISO",26),
    "padló (talajra fektetett ISO 13370)":("FloorISO",26),
    "külső tető":("Roof1",3),
    "tető":("Roof1",3),
    "tetőablak":("OutsideWindow",10),
    "felülvilágító":("OutsideWindow",10),
    "külső ablak":("OutsideWindow",10),
    "ablak (külső, fa vagy PVC)":("OutsideWindow",10),
    "külső ajtó/kapu":("OutsideDoor",12),
    "ajtó (külső)":("OutsideDoor",12),
}
def _set(node:ET.Element,name:str,value:object)->None:
    """Set a direct XML field and collapse legacy duplicate field nodes.

    Several older WinWatt exports contain the same direct field twice.  The
    program imports the final occurrence, so merely changing the first one
    leaves the former project value active.  Keep exactly one direct field.
    """
    matches = [child for child in list(node) if child.tag == name]
    child = matches[0] if matches else ET.SubElement(node, name)
    for duplicate in matches[1:]:
        node.remove(duplicate)
    child.text=str(value)
def _header(node:ET.Element,name:str,path:str,id_:int)->None:
    head=node.find("ItemHeader") or ET.SubElement(node,"ItemHeader")
    _set(head,"ItemName",name);_set(head,"ItemPath",path);_set(head,"ID",id_)
def _kind(value:str)->str:
    return PANEL_TYPES.get(value,("OutsideWall",0))[0]


def _required_number(source: dict, name: str, structure_name: str) -> float:
    value = source.get(name)
    if value is None:
        raise ValueError(
            f"Ground-contact structure {structure_name!r} requires explicit PDF-backed {name}"
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Ground-contact structure {structure_name!r} has invalid {name}: {value!r}")
    return number


def _apply_ground_iso_fields(panel: ET.Element, structure: dict) -> None:
    """Populate ISO 13370 inputs explicitly; never retain template operands."""
    structure_type = str(structure.get("type") or "")
    if structure_type not in {
        "talajon fekvő padló",
        "padló (talajra fektetett ISO 13370)",
        "talajjal érintkező fal (ISO 13370)",
    }:
        return
    name = str(structure.get("name") or structure_type)
    u_value = _required_number(structure, "u_layer", name)
    earth_lambda = _required_number(structure, "earth_lambda_w_mk", name)
    floor_level = _required_number(structure, "floor_level_m", name)
    _set(panel, "k", u_value)
    _set(panel, "EarthLambda", earth_lambda)
    _set(panel, "FloorLevel", floor_level)
    _set(panel, "Rse", _required_number(structure, "rse_m2k_w", name))
    _set(panel, "Rsi", _required_number(structure, "rsi_m2k_w", name))
    modifier = structure.get("u_modifier_percent")
    if modifier is not None:
        modifier_node = panel.find("kModifier")
        if modifier_node is None:
            modifier_node = ET.SubElement(panel, "kModifier", {"ModifierMode": "Percent"})
        modifier_node.set("ModifierMode", "Percent")
        modifier_node.text = str(float(modifier))
    if structure_type == "talajjal érintkező fal (ISO 13370)":
        _set(panel, "WallU", u_value)
        _set(panel, "FloorWidth", 0)
        _set(panel, "WallHeight", abs(floor_level))
        _set(panel, "ISOCorrectionMode", 0)
        wall = panel.find("ISOWall")
        if wall is None:
            wall = ET.SubElement(panel, "ISOWall")
        wall.set("WallU", str(u_value))
        wall.set("FloorU", str(_required_number(structure, "floor_u_value", name)))
        wall.set("EarthLambda", str(earth_lambda))
        wall.set("FloorLevel", str(floor_level))
        return
    area = _required_number(structure, "iso_area_m2", name)
    perimeter = _required_number(structure, "iso_perimeter_m", name)
    wall_floor_psi = _required_number(structure, "wall_floor_psi_w_mk", name)
    _set(panel, "BaseWidth", _required_number(structure, "base_width_m", name))
    _set(panel, "ISOCorrectionMode", 0)
    iso_floor = panel.find("ISOFloor")
    if iso_floor is None:
        iso_floor = ET.SubElement(panel, "ISOFloor")
    for field, value in (
        ("Area", area),
        ("Perimeter", perimeter),
        ("AverageU", u_value),
        ("PlinthWallU", 0),
        ("WallFloorPszi", wall_floor_psi),
    ):
        iso_floor.set(field, str(value))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_text(element: ET.Element, name: str) -> str | None:
    return next(
        ((child.text or "").strip() for child in element if _local_name(child.tag) == name),
        None,
    )


def _room_identity_map(root: ET.Element) -> tuple[dict[str, tuple[str, str]], dict[tuple[str, str], str]]:
    """Index rooms by export ID and by their stable WinWatt path/name identity."""
    by_id: dict[str, tuple[str, str]] = {}
    by_identity: dict[tuple[str, str], str] = {}
    for room in (node for node in root if _local_name(node.tag) == "WinWatt32Room"):
        header = next((child for child in room if _local_name(child.tag) == "ItemHeader"), None)
        if header is None:
            raise ValueError("WinWatt32Room has no ItemHeader")
        room_id = _direct_text(header, "ID")
        identity = (_direct_text(header, "ItemPath") or "", _direct_text(header, "ItemName") or "")
        if not room_id or not identity[1]:
            raise ValueError(f"Room has incomplete identity: id={room_id!r}, identity={identity!r}")
        if room_id in by_id:
            raise ValueError(f"Duplicate room ID: {room_id}")
        if identity in by_identity:
            raise ValueError(f"Duplicate room path/name identity: {identity!r}")
        by_id[room_id] = identity
        by_identity[identity] = room_id
    return by_id, by_identity


def rebase_room_area_ids(source_path: Path, readback_path: Path, target_path: Path) -> dict:
    """Rewrite ETZone room references to IDs assigned by a WinWatt import.

    WinWatt assigns fresh ItemHeader/ID values during complete-project import,
    but this version leaves ETZone/RoomAreaItem references at their exported
    values.  A discovery import provides the deterministic assigned IDs.  The
    stable ItemPath + ItemName pair bridges the two exports without guessing.
    """
    source_tree = ET.parse(source_path)
    source_root = source_tree.getroot()
    readback_root = ET.parse(readback_path).getroot()
    source_by_id, source_by_identity = _room_identity_map(source_root)
    _, readback_by_identity = _room_identity_map(readback_root)
    if source_by_identity.keys() != readback_by_identity.keys():
        missing = sorted(source_by_identity.keys() - readback_by_identity.keys())
        extra = sorted(readback_by_identity.keys() - source_by_identity.keys())
        raise ValueError(f"Room identity sets differ; missing={missing[:5]!r}, extra={extra[:5]!r}")
    old_to_new = {
        old_id: readback_by_identity[identity]
        for old_id, identity in source_by_id.items()
    }
    references = 0
    changed = 0
    unresolved: set[str] = set()
    for node in source_root.iter():
        if _local_name(node.tag) != "RoomAreaItem":
            continue
        references += 1
        old_id = node.attrib.get("ID")
        new_id = old_to_new.get(old_id or "")
        if new_id is None:
            unresolved.add(old_id or "")
            continue
        if new_id != old_id:
            node.set("ID", new_id)
            changed += 1
    if unresolved:
        raise ValueError(f"Unresolved RoomAreaItem IDs: {sorted(unresolved)!r}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(source_tree, space="  ")
    source_tree.write(target_path, encoding="utf-8", xml_declaration=True)
    return {
        "source": str(source_path),
        "readback": str(readback_path),
        "target": str(target_path),
        "rooms": len(source_by_id),
        "references": references,
        "changed_references": changed,
    }


def _explicit_glass_ratio(structure: dict) -> float | None:
    """Read only an explicitly stated glazing ratio from reviewed source data."""
    direct = structure.get("glass_ratio_percent")
    if direct is not None:
        return float(direct)
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:üvegezési|uvegezesi)", str(structure.get("note") or ""), re.I)
    return float(match.group(1).replace(",", ".")) if match else None


def _building_specs(model: dict) -> list[dict]:
    """Return explicit source buildings, retaining the former one-building model."""
    explicit = model.get("buildings")
    if explicit:
        return list(explicit)
    project = model["project"]
    return [{"name": project["name"], "address": project.get("address", "")}]


def _boundary_gradient(boundary: dict) -> float:
    if boundary.get("inclination_deg") is not None:
        return float(boundary["inclination_deg"])
    if str(boundary.get("inclination") or "").casefold() == "vertical":
        return 90.0
    return 90.0 if boundary.get("slope") == "függőleges" else (
        45.0 if boundary.get("slope") == "45°" else 0.0
    )


def _boundary_u(boundary: dict) -> float:
    direct = boundary.get("u_effective")
    if direct is None:
        direct = boundary.get("u")
    if direct is None:
        direct = boundary.get("u_layer")
    if direct is not None:
        return float(direct)
    psi = boundary.get("linear_transmittance_w_mk")
    if psi is None:
        psi = boundary.get("psi")
    if psi is not None and boundary.get("length_m") is not None and boundary.get("area_m2"):
        return float(psi) * float(boundary["length_m"]) / float(boundary["area_m2"])
    return 0.0


def _native_integer(value: object, field: str) -> int:
    """Serialize a native integer field without engineering-value rounding."""
    number = float(value)
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"WinWatt native {field} must be an exact integer, got {value!r}")
    return int(number)


def _remove_template_system_items(building: ET.Element) -> int:
    """Remove semantic system instances inherited from a schema template.

    Native project XML stores building-system rows below ``EPBD``.  They are
    project data, not schema defaults, so copying them into a PDF-derived model
    would silently create systems that the source model did not request.
    Actual systems are added later by a dedicated, evidence-backed worker.
    """
    epbd = building.find("EPBD")
    if epbd is None:
        return 0
    removed = 0
    for child in list(epbd):
        if child.tag.startswith("WinWatt32") and child.tag.endswith("SystemItem"):
            epbd.remove(child)
            removed += 1
    return removed


def compile_native_xml(model_path:Path,template_path:Path,target:Path)->dict:
    model=json.loads(model_path.read_text(encoding="utf-8")); tree=ET.parse(template_path); root=tree.getroot()
    if model.get("project", {}).get("require_wall_xy"):
        issues = wall_geometry_issues(model)
        if issues:
            raise ValueError("Strict wall geometry required; unresolved walls:\n" + "\n".join(issues))
    panels=root.findall("WinWatt32Panel"); rooms=root.findall("WinWatt32Room"); buildings=root.findall("WinWatt32Building")
    if not panels or not rooms or not buildings: raise ValueError("Template must contain panel, room and building examples")
    layer_template=next((panel.find("PanelLayer") for panel in panels if panel.find("PanelLayer") is not None),None)
    if layer_template is None: raise ValueError("Template has no PanelLayer example")
    boundary_templates={b.findtext("Type"):b for room in rooms for b in room.findall("Boundary")}
    for node in list(root):
        if node.tag in {"WinWatt32Panel","WinWatt32Room","WinWatt32Building"}: root.remove(node)
    by_layer=defaultdict(list)
    for layer in model.get("layers",[]): by_layer[layer["structure"]].append(layer)
    by_room=defaultdict(list)
    for boundary in model.get("boundaries",[]): by_room[boundary["room"]].append(boundary)
    next_id=1
    for structure in model["structures"]:
        kind=_kind(structure.get("type","külső fal"))
        base=next((item for item in panels if item.attrib.get("Type")==kind),None)
        if base is None:
            raise ValueError(
                f"Template has no native {kind!r} panel record required by "
                f"structure {structure['name']!r}; refusing to mutate an "
                "incompatible panel schema"
            )
        panel=copy.deepcopy(base)
        panel.attrib["Type"]=kind; layered=bool(by_layer[structure["name"]]); panel.attrib["Layered"]="Yes" if layered else "No";_header(panel,structure["name"],"Certificate\\Structures\\",next_id)
        _set(panel,"Type",structure.get("winwatt_use",structure.get("type",""))); _set(panel,"k",structure.get("u_effective") or structure.get("u_layer") or 0)
        # These three values are printed explicitly in the source calculation
        # PDF and materially affect the monthly gain-utilisation calculation.
        # Never retain unrelated template values when the PDF supplies them.
        for native_tag, model_key in (
            ("Mass", "specific_mass_kg_m2"),
            ("HeatMass", "specific_heat_mass_kg_m2"),
            ("HeatCapacity", "specific_heat_capacity_kj_m2k"),
        ):
            if structure.get(model_key) is not None:
                _set(panel, native_tag, _native_integer(structure[model_key], native_tag))
        _apply_ground_iso_fields(panel, structure)
        glass_ratio = _explicit_glass_ratio(structure)
        if glass_ratio is not None:
            _set(panel, "GlassRatio", glass_ratio)
        # Preserve the native template's child ordering.  The WinWatt importer
        # is order-sensitive in several project sections, so replacement
        # layers stay at the position occupied by the template layers.
        panel_children = list(panel)
        old_layers = list(panel.findall("PanelLayer"))
        layer_insert_index = min(
            (panel_children.index(old) for old in old_layers),
            default=panel_children.index(panel.find("LayeredPanel")) + 1,
        )
        for old in old_layers:
            panel.remove(old)
        for layer_offset, layer in enumerate(sorted(by_layer[structure["name"]],key=lambda item:item.get("sequence",0))):
            row=copy.deepcopy(layer_template);_set(row,"LayerName",layer["name"]);_set(row,"Thickness",float(layer.get("thickness_cm") or 0)/100);_set(row,"Density",layer.get("density_kgm3") or 1);_set(row,"ThermalCond",layer.get("lambda_wmk") or 9999);_set(row,"ThermalRes",layer.get("r") or 0);_set(row,"HeatCapacity",layer.get("heat_capacity_kjkgk") or 0);panel.insert(layer_insert_index + layer_offset, row)
        root.append(panel);next_id+=1
    # A certificate template can contain dozens of unrelated ETZones.  Retain
    # only its minimal zone shape, then rebuild source-specific zones below.
    building_template=buildings[0]
    zone_template=copy.deepcopy(next(iter(building_template.findall("ETZone")), None))
    building_by_name: dict[str, tuple[ET.Element, int]] = {}
    building_aliases: dict[str, str] = {}
    template_system_items_removed = 0
    for building_spec in _building_specs(model):
        building_name = str(building_spec["name"])
        if building_name in building_by_name:
            raise ValueError(f"Duplicate building name: {building_name}")
        building=copy.deepcopy(building_template)
        for old_zone in list(building.findall("ETZone")): building.remove(old_zone)
        template_system_items_removed += _remove_template_system_items(building)
        # UI-created WinWatt buildings live at the project root.  An invented
        # ``Certificate\\`` folder survives XML import textually but makes the
        # building editor's whole-building zone ignore otherwise valid rooms.
        _header(building,building_name,"",next_id)
        _set(building,"Description",building_spec.get("address", model["project"].get("address", "")))
        building_by_name[building_name]=(building,next_id)
        for reference in (building_name, str(building_spec.get("id") or "")):
            if not reference:
                continue
            previous = building_aliases.get(reference)
            if previous is not None and previous != building_name:
                raise ValueError(f"Duplicate building reference: {reference}")
            building_aliases[reference] = building_name
        root.append(building);next_id+=1
    room_ids=[]
    for room_spec in model["rooms"]:
        building_reference = str(room_spec.get("building") or next(iter(building_by_name)))
        building_name = building_aliases.get(building_reference, building_reference)
        if building_name not in building_by_name:
            raise ValueError(f"Room {room_spec['name']!r} refers to unknown building {building_name!r}")
        _, building_id = building_by_name[building_name]
        # Rooms created by WinWatt's own UI are also root items; membership is
        # carried by BuildingRefID, not by a synthetic ItemPath folder.
        room=copy.deepcopy(rooms[0]);_header(room,room_spec["name"],"",next_id);_set(room,"Area",room_spec["area_m2"]);_set(room,"Height",room_spec["height_m"]);_set(room,"CalculatedVolume",room_spec.get("volume_m3",room_spec["area_m2"]*room_spec["height_m"]));_set(room,"GivedVolume",room_spec.get("volume_m3",room_spec["area_m2"]*room_spec["height_m"]));_set(room,"BuildingRefID",building_id)
        # Room conditions are source-model inputs, not incidental template
        # defaults.  Cooling is retained from the version-specific template
        # unless an explicit source value is supplied.
        heating = room.find("Heating")
        if heating is not None and room_spec.get("temperature_c") is not None:
            _set(heating, "Temp", room_spec["temperature_c"])
        filtration = heating.find("Filtration") if heating is not None else None
        if filtration is not None and room_spec.get("air_change_h") is not None:
            _set(filtration, "AirChangeFact", room_spec["air_change_h"])
        cooling = room.find("Cooling")
        if cooling is not None and room_spec.get("summer_temperature_c") is not None:
            _set(cooling, "Temp", room_spec["summer_temperature_c"])
        for old in list(room.findall("Boundary")):room.remove(old)
        for boundary in by_room[room_spec["name"]]:
            _,code=PANEL_TYPES[boundary["winwatt_type"]];sample=boundary_templates.get(str(code)) or next(iter(boundary_templates.values()));out=copy.deepcopy(sample);area=float(boundary["area_m2"])
            # For plan-measured vertical walls, preserve the actual operands:
            # X=wall length, Y=wall height, A=X*Y. Legacy aggregate records
            # retain the area×1 fallback until their contour is measured.
            geometry = xy_area(boundary)
            x, y = (geometry[0], geometry[1]) if geometry is not None else (area, 1.0)
            _set(out,"Name",boundary["name"]);_set(out,"Type",code);_set(out,"x",x);_set(out,"y",y);_set(out,"A",area)
            # Ground-contact source tables frequently supply psi [W/mK] and
            # perimeter rather than U. Preserve the certified transmission
            # loss in WinWatt's area*U field without inventing material data.
            u=_boundary_u(boundary)
            _set(out,"U",u)
            _set(out,"Compass",_native_integer(boundary.get("azimuth_deg",0), "Compass"))
            _set(out,"Gradient",_native_integer(_boundary_gradient(boundary), "Gradient"))
            # Native room-boundary readbacks contain a second geometry block
            # at the end of every record. Its Name is the catalogue structure
            # reference, while the leading Name is the room-boundary label.
            # WinWatt drops the reference (and, for roofs, its orientation)
            # when the trailing block is absent.
            for field, value in (
                ("Name", boundary["structure"]), ("Type", code), ("x", x),
                ("y", y), ("A", area), ("U", u),
                ("Compass", _native_integer(boundary.get("azimuth_deg", 0), "Compass")),
                ("Gradient", _native_integer(_boundary_gradient(boundary), "Gradient")),
            ):
                child = ET.SubElement(out, field)
                child.text = str(value)
            room.append(out)
        root.append(room);room_ids.append((room_spec, next_id, building_name));next_id+=1
    if zone_template is not None:
        for room_spec, room_id, building_name in room_ids:
            zone=copy.deepcopy(zone_template)
            zone.set("Name", room_spec["name"]); zone.set("UseZones", "0")
            for old in list(zone.findall("RoomAreaItem")): zone.remove(old)
            ET.SubElement(zone, "RoomAreaItem", {"ID": str(room_id), "Area": str(room_spec["area_m2"])})
            doc=zone.find("ETZoneDoc")
            if doc is not None:
                doc.set("NettoArea", str(room_spec["area_m2"]));doc.set("Volume", str(room_spec.get("volume_m3", room_spec["area_m2"]*room_spec["height_m"])))
            building_by_name[building_name][0].append(zone)
    target.parent.mkdir(parents=True,exist_ok=True);ET.indent(tree,space="  ");tree.write(target,encoding="utf-8",xml_declaration=True)
    return {"xml":str(target),"buildings":len(building_by_name),"rooms":len(model["rooms"]),"structures":len(model["structures"]),"boundaries":len(model.get("boundaries",[])),"template_system_items_removed":template_system_items_removed}
