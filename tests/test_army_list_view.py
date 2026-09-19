from pathlib import Path

import pytest

from app.army_list_import import import_army_list, parse_old_world_builder_text
from app.army_list_view import render_army_list
from app.database import SessionLocal
from app.models import ArmyList, Player, Round, League
from scripts.seed import seed_database


def test_render_standard_text_import_totals_unit_costs() -> None:
    parsed = parse_old_world_builder_text(
        "Gorzags Gang [393 pts]\n"
        "Warhammer: The Old World, Orc & Goblin Tribes, Battle March\n"
        "\n"
        "++ Characters [85 pts] ++\n"
        "\n"
        "Night Goblin Oddgit [85 pts]\n"
        "- Hand weapon\n"
        "- Wizard [Level 2 Wizard]\n"
        "\n"
        "---\n"
    )
    league = League(name="Test League")
    player = Player(name="Alys", league=league)
    round_item = Round(number=1, points_limit=1000, league=league)
    army_list = ArmyList(
        player=player,
        round=round_item,
        name=parsed.name,
        points=parsed.points,
        faction=parsed.faction,
        data=parsed.data,
    )

    view = render_army_list(army_list)
    unit = view["sections"][0]["units"][0]

    assert unit["name"] == "Night Goblin Oddgit"
    assert unit["total_cost"] == 85
    assert "Hand weapon" in unit["options"]
    assert unit["special_rules"] == []
    assert unit["command"] == []


def test_render_army_list_includes_selected_choices_only() -> None:
    league = League(name="Test League")
    player = Player(name="Alys", league=league)
    round_item = Round(number=1, points_limit=1000, league=league)
    army_list = ArmyList(
        player=player,
        round=round_item,
        name="Ng1 2",
        points=400,
        faction="orc-and-goblin-tribes",
        data={
            "characters": [
                {
                    "name_en": "Night Goblin Oddgit",
                    "points": 55,
                    "command": [{"name_en": "General", "active": False}],
                    "equipment": [
                        {"name_en": "Hand weapon", "active": True},
                        {"name_en": "Great weapon", "active": False},
                    ],
                    "options": [
                        {
                            "name_en": "Wizard",
                            "active": True,
                            "options": [
                                {"name_en": "Level 1 Wizard", "points": 0, "active": False},
                                {"name_en": "Level 2 Wizard", "points": 30, "active": True},
                            ],
                        }
                    ],
                    "mounts": [{"name_en": "On foot", "active": True}],
                    "specialRules": {"name_en": "Fear of Elves, Warband"},
                }
            ],
            "core": [],
            "special": [],
            "rare": [],
            "mercenaries": [],
            "allies": [],
        },
    )

    view = render_army_list(army_list)
    unit = view["sections"][0]["units"][0]
    section_labels = [section["label"] for section in view["sections"]]

    assert section_labels == ["Characters", "Core"]
    assert unit["equipment"] == ["Hand weapon"]
    assert unit["options"] == ["Wizard: Level 2 Wizard"]
    assert unit["mounts"] == ["On foot"]
    assert unit["command"] == []
    assert unit["special_rules"] == ["Fear of Elves", "Warband"]
    assert unit["base_total"] == 55
    assert unit["total_cost"] == 85
    assert unit["upgrade_costs"] == [
        {
            "category": "Options",
            "name": "Wizard: Level 2 Wizard",
            "points": 30,
            "per_model": False,
            "total": 30,
        }
    ]
    assert "Great weapon" not in unit["equipment"]


def test_render_real_old_world_builder_export_has_units() -> None:
    export_path = Path("/Users/olie.thomas/Downloads/ng1-2.owb.json")
    if not export_path.exists():
        pytest.skip("Sample Old World Builder export is not available")

    seed_database()
    with SessionLocal() as db:
        army_list = import_army_list(
            db,
            player_id=1,
            round_id=1,
            json_text=export_path.read_text(),
        )

        view = render_army_list(army_list)

        sections = {section["label"]: section["units"] for section in view["sections"]}
        assert view["faction_display"] == "Orc And Goblin Tribes"
        assert len(sections["Characters"]) == 2
        assert len(sections["Core"]) == 2
        assert len(sections["Special"]) == 1
        assert sections["Characters"][0]["name"] == "Night Goblin Oddgit"
        assert "Wizard: Level 2 Wizard" in sections["Characters"][0]["options"]
        assert sections["Core"][0]["base_total"] == 60
        assert sections["Core"][0]["total_cost"] == 77
        assert sections["Core"][1]["base_total"] == 42
        assert sections["Core"][1]["total_cost"] == 56
        assert sections["Core"][1]["upgrade_costs"] == [
            {
                "category": "Equipment",
                "name": "Hand weapons, Shortbows",
                "points": 1,
                "per_model": True,
                "total": 14,
            }
        ]


def test_render_optional_sections_when_present() -> None:
    league = League(name="Test League")
    player = Player(name="Alys", league=league)
    round_item = Round(number=1, points_limit=1000, league=league)
    army_list = ArmyList(
        player=player,
        round=round_item,
        name="Optional Sections",
        points=300,
        faction="test-faction",
        data={
            "characters": [],
            "core": [],
            "special": [],
            "rare": [{"name_en": "Rare Unit", "points": 50, "strength": 1}],
            "mercenaries": [{"name_en": "Mercenary Unit", "points": 30, "strength": 2}],
            "allies": [{"name_en": "Allied Unit", "points": 10, "strength": 3}],
        },
    )

    view = render_army_list(army_list)
    sections = {section["label"]: section["units"] for section in view["sections"]}

    assert "Special" not in sections
    assert sections["Rare"][0]["name"] == "Rare Unit"
    assert sections["Mercenaries"][0]["name"] == "Mercenary Unit"
    assert sections["Allies"][0]["name"] == "Allied Unit"