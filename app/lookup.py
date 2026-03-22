import json
from pathlib import Path

# Load properties.json once at module level
_properties_path = Path(__file__).parent.parent / "data" / "properties.json"
with open(_properties_path, "r") as f:
    _data = json.load(f)


def get_general() -> dict:
    """Return general policies dict."""
    return _data.get("general", {})


def get_building(building_id: str) -> dict:
    """Return building dict (excluding 'units' key) or {} if not found."""
    buildings = _data.get("buildings", {})
    if building_id not in buildings:
        return {}

    # Create a copy and remove the 'units' key
    building = buildings[building_id].copy()
    building.pop("units", None)
    return building


def get_unit(building_id: str, unit_id: str) -> dict:
    """Return unit dict or {} if building or unit not found."""
    buildings = _data.get("buildings", {})
    if building_id not in buildings:
        return {}

    units = buildings[building_id].get("units", {})
    return units.get(unit_id, {})


def get_all_buildings() -> list[str]:
    """Return list of all building_id keys."""
    return list(_data.get("buildings", {}).keys())


def get_units_for_building(building_id: str) -> list[str]:
    """Return list of unit_id keys for a building, or [] if not found."""
    buildings = _data.get("buildings", {})
    if building_id not in buildings:
        return []

    return list(buildings[building_id].get("units", {}).keys())


PUBLIC_UNIT_FIELDS = {
    "suite_name", "description", "room_type",
    "max_pax", "price_per_night", "floor",
    "extra_beds_available", "extra_bed_fee",
}


def get_all_units_public() -> list[dict]:
    """Return public fields for every unit across all buildings."""
    units = []
    for building_id, building in _data.get("buildings", {}).items():
        for unit_id, unit in building.get("units", {}).items():
            entry = {k: v for k, v in unit.items() if k in PUBLIC_UNIT_FIELDS}
            entry["building_id"] = building_id
            entry["unit_id"] = unit_id
            units.append(entry)
    return units
