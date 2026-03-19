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
