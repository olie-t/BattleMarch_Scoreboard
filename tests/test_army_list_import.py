import json

import pytest
from sqlalchemy import select

from app.army_list_import import (
    ArmyListImportError,
    import_army_list,
    parse_old_world_builder_export,
    parse_old_world_builder_json,
    parse_old_world_builder_text,
)
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

STANDARD_TEXT_EXPORT = (
    "Gorzags Gang [393 pts]\n"
    "Warhammer: The Old World, Orc & Goblin Tribes, Battle March\n"
    "===\n"
    "\n"
    "++ Characters [119 pts] ++\n"
    "\n"
    "Night Goblin Oddgit [85 pts] \n"
    "- Hand weapon\n"
    "- Wizard [Level 2 Wizard]\n"
    "- On foot\n"
    "- Illusion\n"
    "\n"
    "Night Goblin Bigboss [34 pts] \n"
    "- Hand weapon\n"
    "- Great weapon\n"
    "- General\n"
    "- On foot\n"
    "\n"
    "++ Core Units [183 pts] ++\n"
    "\n"
    "20 Night Goblin Mob [127 pts] \n"
    "- Hand weapons\n"
    "- Shields\n"
    "- Boss (champion)\n"
    "- Standard bearer\n"
    "- Musician\n"
    "- 2x Fanatics [Fanatic ball & chain]\n"
    "\n"
    "14 Night Goblin Mob [56 pts] \n"
    "- Hand weapons\n"
    "- Shortbows\n"
    "\n"
    "++ Special Units [91 pts] ++\n"
    "\n"
    "7 Night Goblin Squig Hopper Mob [91 pts] \n"
    "- Hand weapons\n"
    "- Huge gobs (Squigs only)\n"
    "- Cavalry spears\n"
    "- Huge gobs (Squigs only)\n"
    "\n"
    "---\n"
    'Created with "Old World Builder"\n'
    "\n"
    "[https://old-world-builder.com]\n"
)


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


def test_parse_valid_old_world_builder_text() -> None:
    parsed = parse_old_world_builder_text(STANDARD_TEXT_EXPORT)

    assert parsed.name == "Gorzags Gang"
    assert parsed.points == 393
    assert parsed.faction == "Orc & Goblin Tribes"
    assert parsed.data["army"] == "Orc & Goblin Tribes"
    assert parsed.data["armyComposition"] == "Battle March"
    assert "rare" not in parsed.data

    characters = parsed.data["characters"]
    core = parsed.data["core"]
    special = parsed.data["special"]
    assert [unit["name_en"] for unit in characters] == ["Night Goblin Oddgit", "Night Goblin Bigboss"]
    assert [unit["name_en"] for unit in core] == ["Night Goblin Mob", "Night Goblin Mob"]
    assert [unit["name_en"] for unit in special] == ["Night Goblin Squig Hopper Mob"]

    oddgit = characters[0]
    assert oddgit["strength"] == 1
    option_names = [option["name_en"] for option in oddgit["options"]]
    assert option_names == ["Hand weapon", "Wizard [Level 2 Wizard]", "On foot", "Illusion", "Unit total cost"]
    assert oddgit["options"][-1]["points"] == 85

    big_mob = core[0]
    assert big_mob["strength"] == 20
    assert big_mob["options"][-1]["points"] == 127


def test_parse_text_rejects_wrong_game() -> None:
    text = STANDARD_TEXT_EXPORT.replace(
        "Warhammer: The Old World, Orc & Goblin Tribes, Battle March",
        "Warhammer 40,000, Orks, Combat Patrol",
    )

    with pytest.raises(ArmyListImportError, match="The Old World"):
        parse_old_world_builder_text(text)


def test_parse_text_rejects_unparseable_line() -> None:
    text = STANDARD_TEXT_EXPORT.replace("- Illusion\n", "not a valid selection or unit line\n")

    with pytest.raises(ArmyListImportError, match="Could not parse"):
        parse_old_world_builder_text(text)


def test_parse_old_world_builder_export_detects_format() -> None:
    assert parse_old_world_builder_export(json.dumps(VALID_EXPORT)) == parse_old_world_builder_json(
        json.dumps(VALID_EXPORT)
    )
    assert parse_old_world_builder_export(STANDARD_TEXT_EXPORT) == parse_old_world_builder_text(
        STANDARD_TEXT_EXPORT
    )


def test_import_army_list_accepts_standard_text_export() -> None:
    seed_database()
    with SessionLocal() as db:
        player = db.scalar(select(Player).where(Player.name == "Alys Emberfall"))
        round_item = db.scalar(select(Round).where(Round.number == 1))

        army_list = import_army_list(
            db,
            player_id=player.id,
            round_id=round_item.id,
            json_text=STANDARD_TEXT_EXPORT,
        )

        assert army_list.name == "Gorzags Gang"
        assert army_list.points == 393
        assert army_list.faction == "Orc & Goblin Tribes"
        assert len(army_list.data["core"]) == 2


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