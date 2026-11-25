import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArmyList, Player, Round


class ArmyListImportError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedArmyList:
    name: str
    points: int
    faction: str
    data: dict[str, Any]


# Matches "<optional count> <name> [<points> pts]", used for both the list's
# top-level name/points header line and individual unit lines.
_NAME_POINTS_RE = re.compile(r"^(?:(?P<count>\d+)\s+)?(?P<name>.+?)\s*\[(?P<points>\d+)\s*pts\]\s*$")
_SECTION_HEADER_RE = re.compile(r"^\+\+\s*(?P<label>.+?)\s*\[\d+\s*pts\]\s*\+\+$")
_BULLET_RE = re.compile(r"^-\s+(?P<text>.+)$")

_SECTION_KEY_ALIASES = {
    "characters": "characters",
    "core": "core",
    "special": "special",
    "rare": "rare",
    "mercenaries": "mercenaries",
    "mercenary": "mercenaries",
    "allies": "allies",
}


def _normalize_section_key(label: str) -> Optional[str]:
    tokens = label.strip().lower().split()
    if tokens and tokens[-1] == "units":
        tokens = tokens[:-1]
    return _SECTION_KEY_ALIASES.get(" ".join(tokens))


def _is_divider_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) == {"="}


def parse_old_world_builder_json(json_text: str) -> ParsedArmyList:
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise ArmyListImportError(f"Invalid JSON: {error.msg}") from error

    if not isinstance(data, dict):
        raise ArmyListImportError("Old World Builder export must be a JSON object.")

    if data.get("game") != "the-old-world":
        raise ArmyListImportError("JSON must be an Old World Builder export for The Old World.")

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ArmyListImportError("Army list is missing a valid top-level name.")

    points = data.get("points")
    if not isinstance(points, int):
        raise ArmyListImportError("Army list is missing a valid top-level points value.")

    faction = data.get("army") or data.get("armyComposition")
    if not isinstance(faction, str) or not faction.strip():
        raise ArmyListImportError("Army list is missing a valid top-level army/faction value.")

    return ParsedArmyList(
        name=name.strip(),
        points=points,
        faction=faction.strip(),
        data=data,
    )


def parse_old_world_builder_text(text: str) -> ParsedArmyList:
    lines = text.splitlines()
    total_lines = len(lines)

    def skip_ignorable(start: int) -> int:
        index = start
        while index < total_lines and (not lines[index].strip() or _is_divider_line(lines[index])):
            index += 1
        return index

    index = skip_ignorable(0)
    if index >= total_lines:
        raise ArmyListImportError("Text export is empty.")

    name_match = _NAME_POINTS_RE.match(lines[index].strip())
    if name_match is None:
        raise ArmyListImportError("Text export is missing a valid list name and points header.")
    name = name_match.group("name").strip()
    if not name:
        raise ArmyListImportError("Army list is missing a valid top-level name.")
    points = int(name_match.group("points"))
    index += 1

    index = skip_ignorable(index)
    if index >= total_lines:
        raise ArmyListImportError("Text export is missing the game/faction header line.")
    header_parts = [part.strip() for part in lines[index].strip().split(",")]
    if not header_parts[0].startswith("Warhammer: The Old World"):
        raise ArmyListImportError("Text export must be an Old World Builder export for The Old World.")
    if len(header_parts) < 2 or not header_parts[1]:
        raise ArmyListImportError("Army list is missing a valid top-level army/faction value.")
    faction = header_parts[1]
    composition = header_parts[2] if len(header_parts) > 2 and header_parts[2] else None
    index += 1

    index = skip_ignorable(index)

    sections: dict[str, list[dict[str, Any]]] = {}
    current_section: Optional[str] = None
    current_unit: Optional[dict[str, Any]] = None
    current_unit_total = 0

    def flush_unit() -> None:
        nonlocal current_unit, current_unit_total
        if current_unit is not None:
            current_unit["options"].append(
                {"name_en": "Unit total cost", "active": True, "points": current_unit_total, "perModel": False}
            )
            sections[current_section].append(current_unit)
            current_unit = None
            current_unit_total = 0

    while index < total_lines:
        stripped = lines[index].strip()
        index += 1

        if not stripped or _is_divider_line(stripped):
            continue
        if stripped == "---":
            break

        section_match = _SECTION_HEADER_RE.match(stripped)
        if section_match:
            flush_unit()
            key = _normalize_section_key(section_match.group("label"))
            if key is None:
                raise ArmyListImportError(f"Unrecognized army list section: {section_match.group('label')!r}.")
            current_section = key
            sections.setdefault(key, [])
            continue

        bullet_match = _BULLET_RE.match(stripped)
        if bullet_match:
            if current_unit is None:
                raise ArmyListImportError(f"Found a selection line before any unit was declared: {stripped!r}.")
            current_unit["options"].append(
                {"name_en": bullet_match.group("text"), "active": True, "points": 0, "perModel": False}
            )
            continue

        unit_match = _NAME_POINTS_RE.match(stripped)
        if unit_match:
            if current_section is None:
                raise ArmyListImportError(f"Found a unit entry before any section header: {stripped!r}.")
            flush_unit()
            current_unit = {
                "name_en": unit_match.group("name").strip(),
                "strength": int(unit_match.group("count")) if unit_match.group("count") else 1,
                "points": 0,
                "options": [],
            }
            current_unit_total = int(unit_match.group("points"))
            continue

        raise ArmyListImportError(f"Could not parse army list line: {stripped!r}.")

    flush_unit()

    if not sections:
        raise ArmyListImportError("Text export does not contain any army list sections.")

    data: dict[str, Any] = {
        "game": "the-old-world",
        "name": name,
        "points": points,
        "army": faction,
        **sections,
    }
    if composition:
        data["armyComposition"] = composition

    return ParsedArmyList(name=name, points=points, faction=faction, data=data)


def _rankings_name(identifier: Any, label: str) -> str:
    if not isinstance(identifier, str) or not identifier.strip() or not identifier.strip().split("/")[-1]:
        raise ArmyListImportError(f"Old World Rankings export is missing a valid {label}.")
    return identifier.strip().split("/")[-1].replace("-", " ").title()


def _normalize_rankings_units(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    units = data.get("units")
    if not isinstance(units, list):
        raise ArmyListImportError("Old World Rankings export must contain a units array.")

    sections: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise ArmyListImportError("Each Old World Rankings unit must be a JSON object.")
        name = _rankings_name(unit.get("unitEntryId"), "unitEntryId")
        quantity = unit.get("quantity")
        if type(quantity) is not int or quantity <= 0:
            raise ArmyListImportError(f"{name} must have a positive integer quantity.")

        category = unit.get("categoryOverride")
        if category is None:
            section_key = "unclassified"
        elif isinstance(category, str) and _normalize_section_key(category):
            section_key = _normalize_section_key(category)
        else:
            raise ArmyListImportError(f"{name} has an unrecognized categoryOverride.")

        selected_options = unit.get("selectedOptions", [])
        traits = unit.get("traitIds", [])
        if not isinstance(selected_options, list) or not isinstance(traits, list):
            raise ArmyListImportError(f"{name} options and traits must be arrays.")
        options = []
        for option in selected_options:
            if not isinstance(option, dict):
                raise ArmyListImportError(f"{name} contains an invalid selected option.")
            options.append({
                "name_en": _rankings_name(option.get("optionId"), "optionId"),
                "active": True,
            })
        normalized_traits = [
            {"name_en": _rankings_name(trait, "traitId"), "active": True}
            for trait in traits
        ]
        sections.setdefault(section_key, []).append({
            "name_en": name,
            "strength": quantity,
            "points": None,
            "cost_unknown": True,
            "options": options,
            "traits": normalized_traits,
        })
    return sections


def parse_old_world_rankings_json(
    json_text: str, total_points: Optional[int] = None,
) -> ParsedArmyList:
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise ArmyListImportError(f"Invalid JSON: {error.msg}") from error
    if not isinstance(data, dict):
        raise ArmyListImportError("Old World Rankings export must be a JSON object.")
    ruleset = data.get("ruleset")
    if not isinstance(ruleset, dict) or ruleset.get("gameSystemId") != "the-old-world":
        raise ArmyListImportError("Old World Rankings export must be for The Old World.")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ArmyListImportError("Army list is missing a valid top-level name.")
    faction_id = data.get("factionId")
    if not isinstance(faction_id, str) or not faction_id.startswith("tow/"):
        raise ArmyListImportError("Old World Rankings export is missing a valid factionId.")
    _rankings_name(faction_id, "factionId")
    sections = _normalize_rankings_units(data)
    if type(total_points) is not int or total_points < 0:
        raise ArmyListImportError(
            "Enter the actual total army points for the Old World Rankings list. "
            "The export contains no unit costs or total cost; pointsLimit is only the army's limit."
        )
    faction = faction_id.split("/", 1)[1]
    normalized = {
        "game": "the-old-world",
        "source": "old-world-rankings",
        "name": name.strip(),
        "points": total_points,
        "army": faction,
        "source_export": data,
        **sections,
    }
    return ParsedArmyList(name=name.strip(), points=total_points, faction=faction, data=normalized)


def parse_army_list_export(text: str, total_points: Optional[int] = None) -> ParsedArmyList:
    if text.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise ArmyListImportError(f"Invalid JSON: {error.msg}") from error
        if isinstance(data, dict) and ("ruleset" in data or "factionId" in data):
            return parse_old_world_rankings_json(text, total_points=total_points)
        return parse_old_world_builder_json(text)
    return parse_old_world_builder_text(text)


def parse_old_world_builder_export(text: str) -> ParsedArmyList:
    return parse_army_list_export(text)


def import_army_list(
    db: Session,
    player_id: int,
    round_id: int,
    json_text: str,
    total_points: Optional[int] = None,
) -> ArmyList:
    parsed = parse_army_list_export(json_text, total_points=total_points)
    player = db.get(Player, player_id)
    if player is None:
        raise ArmyListImportError("Player does not exist.")

    round_item = db.get(Round, round_id)
    if round_item is None:
        raise ArmyListImportError("Round does not exist.")

    if player.league_id != round_item.league_id:
        raise ArmyListImportError("Player and round must belong to the same league.")

    army_list = db.scalar(
        select(ArmyList).where(
            ArmyList.player_id == player_id,
            ArmyList.round_id == round_id,
        )
    )
    if army_list is None:
        army_list = ArmyList(player_id=player_id, round_id=round_id, data=parsed.data)
        db.add(army_list)

    army_list.name = parsed.name
    army_list.points = parsed.points
    army_list.faction = parsed.faction
    army_list.data = parsed.data
    db.commit()
    db.refresh(army_list)
    return army_list
