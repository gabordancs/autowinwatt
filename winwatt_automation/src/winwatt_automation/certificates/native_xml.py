"""Deterministic native XML compiler from a reviewed certificate model.

The model is deliberately explicit (rooms, structures, layers, boundaries).
PDF extraction never calls this compiler directly: geometry must first be
reviewed or be produced by a deterministic plan parser.
"""
from __future__ import annotations
import copy
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

PANEL_TYPES={"külső fal":("OutsideWall",0),"lábazati fal":("OutsideWall",0),"talajon fekvő padló":("Roof1",3),"külső tető":("Roof3",5),"tető":("Roof3",5),"tetőablak":("OutsideWindow",10),"felülvilágító":("OutsideWindow",10),"külső ablak":("OutsideWindow",10),"külső ajtó/kapu":("OutsideDoor",12)}
def _set(node:ET.Element,name:str,value:object)->None:
    # ElementTree leaf elements are false-y, so ``find(...) or`` silently
    # appended duplicate fields instead of updating existing template values.
    child = node.find(name)
    if child is None:
        child = ET.SubElement(node, name)
    child.text=str(value)
def _header(node:ET.Element,name:str,path:str,id_:int)->None:
    head=node.find("ItemHeader") or ET.SubElement(node,"ItemHeader")
    _set(head,"ItemName",name);_set(head,"ItemPath",path);_set(head,"ID",id_)
def _kind(value:str)->str:
    return PANEL_TYPES.get(value,("OutsideWall",0))[0]


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


def compile_native_xml(model_path:Path,template_path:Path,target:Path)->dict:
    model=json.loads(model_path.read_text(encoding="utf-8")); tree=ET.parse(template_path); root=tree.getroot()
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
        kind=_kind(structure.get("type","külső fal")); base=next((item for item in panels if item.attrib.get("Type")==kind),panels[0]); panel=copy.deepcopy(base)
        panel.attrib["Type"]=kind; layered=bool(by_layer[structure["name"]]); panel.attrib["Layered"]="Yes" if layered else "No";_header(panel,structure["name"],"Certificate\\Structures\\",next_id)
        _set(panel,"Type",structure.get("winwatt_use",structure.get("type",""))); _set(panel,"k",structure.get("u_effective") or structure.get("u_layer") or 0)
        glass_ratio = _explicit_glass_ratio(structure)
        if glass_ratio is not None:
            _set(panel, "GlassRatio", glass_ratio)
        for old in list(panel.findall("PanelLayer")):panel.remove(old)
        for layer in sorted(by_layer[structure["name"]],key=lambda item:item.get("sequence",0)):
            row=copy.deepcopy(layer_template);_set(row,"LayerName",layer["name"]);_set(row,"Thickness",float(layer.get("thickness_cm") or 0)/100);_set(row,"Density",layer.get("density_kgm3") or 1);_set(row,"ThermalCond",layer.get("lambda_wmk") or 9999);_set(row,"ThermalRes",layer.get("r") or 0);_set(row,"HeatCapacity",layer.get("heat_capacity_kjkgk") or 0);panel.append(row)
        root.append(panel);next_id+=1
    # A certificate template can contain dozens of unrelated ETZones.  Retain
    # only its minimal zone shape, then rebuild source-specific zones below.
    building_template=buildings[0]
    zone_template=copy.deepcopy(next(iter(building_template.findall("ETZone")), None))
    building_by_name: dict[str, tuple[ET.Element, int]] = {}
    for building_spec in _building_specs(model):
        building_name = str(building_spec["name"])
        if building_name in building_by_name:
            raise ValueError(f"Duplicate building name: {building_name}")
        building=copy.deepcopy(building_template)
        for old_zone in list(building.findall("ETZone")): building.remove(old_zone)
        _header(building,building_name,"Certificate\\",next_id)
        _set(building,"Description",building_spec.get("address", model["project"].get("address", "")))
        building_by_name[building_name]=(building,next_id)
        root.append(building);next_id+=1
    room_ids=[]
    for room_spec in model["rooms"]:
        building_name = str(room_spec.get("building") or next(iter(building_by_name)))
        if building_name not in building_by_name:
            raise ValueError(f"Room {room_spec['name']!r} refers to unknown building {building_name!r}")
        _, building_id = building_by_name[building_name]
        room=copy.deepcopy(rooms[0]);_header(room,room_spec["name"],"Certificate\\",next_id);_set(room,"Area",room_spec["area_m2"]);_set(room,"Height",room_spec["height_m"]);_set(room,"CalculatedVolume",room_spec.get("volume_m3",room_spec["area_m2"]*room_spec["height_m"]));_set(room,"GivedVolume",room_spec.get("volume_m3",room_spec["area_m2"]*room_spec["height_m"]));_set(room,"BuildingRefID",building_id)
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
            _,code=PANEL_TYPES[boundary["winwatt_type"]];sample=boundary_templates.get(str(code)) or next(iter(boundary_templates.values()));out=copy.deepcopy(sample);area=float(boundary["area_m2"]);_set(out,"Name",boundary["name"]);_set(out,"Type",code);_set(out,"x",area);_set(out,"y",1);_set(out,"A",area)
            # Ground-contact source tables frequently supply psi [W/mK] and
            # perimeter rather than U. Preserve the certified transmission
            # loss in WinWatt's area*U field without inventing material data.
            u=boundary.get("u_effective") or boundary.get("u")
            if u is None and boundary.get("psi") is not None and boundary.get("length_m") is not None and area:
                u=float(boundary["psi"])*float(boundary["length_m"])/area
            _set(out,"U",u or 0);_set(out,"Compass",boundary.get("azimuth_deg",0));_set(out,"Gradient",90 if boundary.get("slope")=="függőleges" else 45 if boundary.get("slope")=="45°" else 0);room.append(out)
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
    return {"xml":str(target),"buildings":len(building_by_name),"rooms":len(model["rooms"]),"structures":len(model["structures"]),"boundaries":len(model.get("boundaries",[]))}
