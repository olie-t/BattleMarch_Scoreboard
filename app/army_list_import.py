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

    def next_nonblank(start: int) -> int:
        index = start
        while index < total_lines and not lines[index].strip():
            index += 1
        return index

    index = next_nonblank(0)
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

    index = next_nonblank(index)
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

    index = next_nonblank(index)
    if index < total_lines and lines[index].strip() == "===":
        index += 1

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

        if not stripped:
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


def parse_old_world_builder_export(text: str) -> ParsedArmyList:
    if text.lstrip().startswith("{"):
        return parse_old_world_builder_json(text)
    return parse_old_world_builder_text(text)


def import_army_list(
    db: Session,
    player_id: int,
    round_id: int,
    json_text: str,
) -> ArmyList:
    parsed = parse_old_world_builder_export(json_text)
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