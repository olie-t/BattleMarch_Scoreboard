import json
from dataclasses import dataclass
from typing import Any

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


def import_army_list(
    db: Session,
    player_id: int,
    round_id: int,
    json_text: str,
) -> ArmyList:
    parsed = parse_old_world_builder_json(json_text)
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