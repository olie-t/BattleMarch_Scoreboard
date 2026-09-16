import json

import pytest
from sqlalchemy import select

from app.army_list_import import ArmyListImportError, import_army_list, parse_old_world_builder_json
from app.database import SessionLocal
from app.models import ArmyList, League, Player, Round
from scripts.seed import seed_database


VALID_EXPORT = {
    "name": "Ng1 2",
    "game": "the-old-world",
    "points": 400,
    "army": "orc-and-goblin-tribes",
    "characters": [],
    "core": [],
    "special": [],
    "rare": [],
}


def test_parse_valid_old_world_builder_json() -> None:
    parsed = parse_old_world_builder_json(json.dumps(VALID_EXPORT))

    assert parsed.name == "Ng1 2"
    assert parsed.points == 400
    assert parsed.faction == "orc-and-goblin-tribes"
    assert parsed.data == VALID_EXPORT


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(ArmyListImportError, match="Invalid JSON"):
        parse_old_world_builder_json("not json")


def test_parse_rejects_wrong_game() -> None:
    export = dict(VALID_EXPORT, game="warhammer-40000")

    with pytest.raises(ArmyListImportError, match="The Old World"):
        parse_old_world_builder_json(json.dumps(export))


def test_import_army_list_associates_player_round_and_stores_data() -> None:
    seed_database()
    with SessionLocal() as db:
        player = db.scalar(select(Player).where(Player.name == "Alys Emberfall"))
        round_item = db.scalar(select(Round).where(Round.number == 1))

        army_list = import_army_list(
            db,
            player_id=player.id,
            round_id=round_item.id,
            json_text=json.dumps(VALID_EXPORT),
        )

        assert army_list.player_id == player.id
        assert army_list.round_id == round_item.id
        assert army_list.name == "Ng1 2"
        assert army_list.points == 400
        assert army_list.faction == "orc-and-goblin-tribes"
        assert army_list.data == VALID_EXPORT
        assert db.scalar(select(ArmyList).where(ArmyList.id == army_list.id)) is not None


def test_import_rejects_player_and_round_from_different_leagues() -> None:
    seed_database()
    with SessionLocal() as db:
        player = db.scalar(select(Player).where(Player.name == "Alys Emberfall"))
        other_league = League(name="Other League")
        other_round = Round(number=1, points_limit=1000, league=other_league)
        db.add(other_league)
        db.commit()

        with pytest.raises(ArmyListImportError, match="same league"):
            import_army_list(
                db,
                player_id=player.id,
                round_id=other_round.id,
                json_text=json.dumps(VALID_EXPORT),
            )