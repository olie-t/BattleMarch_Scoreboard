import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.army_list_import import ArmyListImportError, import_army_list, parse_army_list_export
from app.army_list_view import render_army_list
from app.database import SessionLocal
from app.models import ArmyList
from scripts.seed import seed_database
from tests.test_admin import authenticated_client


@pytest.fixture
def rankings_export():
    return json.loads((Path(__file__).parent / "fixtures" / "old_world_rankings.json").read_text())


def test_rankings_example_preserves_units_choices_and_original_export(rankings_export):
    parsed = parse_army_list_export(json.dumps(rankings_export), total_points=598)

    assert parsed.name == "Elf n Safety"
    assert parsed.points == 598
    assert parsed.points != rankings_export["pointsLimit"]
    assert parsed.faction == "high-elf-realms"
    assert parsed.data["source_export"] == rankings_export
    assert len(parsed.data["unclassified"]) == 4
    assert len(parsed.data["special"]) == 1

    army_list = ArmyList(name=parsed.name, points=parsed.points, faction=parsed.faction, data=parsed.data)
    view = render_army_list(army_list)
    assert view["faction_display"] == "High Elf Realms"
    sections = {section["label"]: section["units"] for section in view["sections"]}
    assert set(sections) == {"Special", "Category not provided"}
    sea_guard, noble, chariot, shadow_warriors = sections["Category not provided"]
    assert sea_guard["name"] == "Lothern Sea Guard"
    assert sea_guard["strength"] == 15
    assert sea_guard["options"] == [
        "Light Armour", "Hand Weapons Thrusting Spears Warbows", "Warbows",
        "Shields", "Sea Master", "Standard Bearer",
    ]
    assert sea_guard["traits"] == ["Banner Of Swirling Wind"]
    assert noble["traits"] == ["Sea Guard"]
    assert "General" in noble["options"]
    assert chariot["name"] == "Lion Chariot Of Chrace"
    assert shadow_warriors["strength"] == 5
    assert sections["Special"][0]["name"] == "Lothern Skycutters"
    assert "Eagle Eye Bolt Thrower" in sections["Special"][0]["options"]
    for units in sections.values():
        for unit in units:
            assert unit["points"] is None
            assert unit["base_total"] is None
            assert unit["total_cost"] is None
            assert unit["upgrade_costs"] == []


@pytest.mark.parametrize("points", [None, -1, True, 598.5, "598"])
def test_rankings_requires_manual_non_negative_integer_total(rankings_export, points):
    with pytest.raises(ArmyListImportError, match="actual total army points"):
        parse_army_list_export(json.dumps(rankings_export), total_points=points)


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("name", " ", "name"),
        ("factionId", "tow/", "factionId"),
        ("factionId", "other/high-elf-realms", "factionId"),
        ("ruleset", None, "The Old World"),
        ("ruleset", {"gameSystemId": "warhammer-40000"}, "The Old World"),
        ("units", {}, "units array"),
        ("units", [None], "JSON object"),
    ],
)
def test_rankings_rejects_invalid_export_fields(rankings_export, key, value, message):
    rankings_export[key] = value
    with pytest.raises(ArmyListImportError, match=message):
        parse_army_list_export(json.dumps(rankings_export), total_points=598)


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("quantity", 0, "quantity"),
        ("quantity", True, "quantity"),
        ("quantity", "15", "quantity"),
        ("unitEntryId", "", "unitEntryId"),
        ("categoryOverride", "invented", "categoryOverride"),
        ("categoryOverride", [], "categoryOverride"),
        ("selectedOptions", {}, "arrays"),
        ("selectedOptions", [None], "selected option"),
        ("selectedOptions", [{"groupId": "equipment"}], "optionId"),
        ("traitIds", None, "arrays"),
        ("traitIds", [None], "traitId"),
    ],
)
def test_rankings_rejects_invalid_units(rankings_export, key, value, message):
    rankings_export["units"][0][key] = value
    with pytest.raises(ArmyListImportError, match=message):
        parse_army_list_export(json.dumps(rankings_export), total_points=598)


def test_admin_imports_rankings_and_public_page_shows_unknown_costs(monkeypatch, rankings_export):
    seed_database()
    client = authenticated_client(monkeypatch)
    response = client.post("/admin/army-lists", data={
        "player_id": "1", "round_id": "1",
        "json_text": json.dumps(rankings_export), "total_points": "598",
    })
    assert response.status_code == 200
    assert "Imported" in response.text
    with SessionLocal() as db:
        army_list = db.scalar(select(ArmyList).where(ArmyList.player_id == 1, ArmyList.round_id == 1))
        assert army_list.points == 598
        assert army_list.data["source_export"] == rankings_export
        army_list_id = army_list.id

    response = client.get(f"/army-lists/{army_list_id}")
    assert response.status_code == 200
    assert "Elf n Safety" in response.text
    assert "High Elf Realms" in response.text
    assert "598" in response.text
    assert "Category not provided" in response.text
    assert response.text.count("Total unit cost: Not provided") == 5
    assert "Lothern Sea Guard" in response.text
    assert "Banner Of Swirling Wind" in response.text
    assert "Sea Guard" in response.text
    assert "None" not in response.text
    assert "No selected upgrades with additional points." not in response.text

    response = client.get("/players/1")
    assert f'href="/army-lists/{army_list_id}"' in response.text
    assert "High Elf Realms" in client.get("/players").text


@pytest.mark.parametrize("points", ["", "-1", "invalid", "598.5"])
def test_admin_invalid_total_preserves_export_and_creates_no_list(monkeypatch, rankings_export, points):
    seed_database()
    client = authenticated_client(monkeypatch)
    response = client.post("/admin/army-lists", data={
        "player_id": "2", "round_id": "2",
        "json_text": json.dumps(rankings_export), "total_points": points,
    })
    assert response.status_code == 400
    assert "Elf n Safety" in response.text
    assert 'option value="2" selected' in response.text
    with SessionLocal() as db:
        assert db.scalar(select(ArmyList)) is None


def test_reimport_rankings_updates_existing_list(rankings_export):
    seed_database()
    with SessionLocal() as db:
        original = import_army_list(db, 1, 1, json.dumps(rankings_export), total_points=598)
        original_id = original.id
        rankings_export["name"] = "Updated Elf n Safety"
        rankings_export["units"][0]["quantity"] = 16
        updated = import_army_list(db, 1, 1, json.dumps(rankings_export), total_points=610)
        assert updated.id == original_id
        assert updated.name == "Updated Elf n Safety"
        assert updated.points == 610
        assert updated.data["unclassified"][0]["strength"] == 16
        assert len(list(db.scalars(select(ArmyList)))) == 1
