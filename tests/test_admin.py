import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import ArmyList, League, Match, Player, PlayerRoundScore, Round
from scripts.seed import seed_database
from tests.test_army_list_import import VALID_EXPORT


def authenticated_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("BATTLE_MARCH_ADMIN_PASSWORD_HASH", hash_password("secret"))
    client = TestClient(app)
    response = client.post(
        "/admin/login",
        data={"password": "secret"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    return client


def test_public_pages_do_not_require_admin_login() -> None:
    seed_database()
    client = TestClient(app)

    assert client.get("/players").status_code == 200
    assert client.get("/rounds").status_code == 200


def test_public_development_write_routes_are_removed() -> None:
    seed_database()
    client = TestClient(app)

    assert client.get("/dev/army-lists/import").status_code == 404
    assert client.post("/dev/army-lists/import").status_code == 404
    assert client.post("/leagues", data={"name": "Open Write"}).status_code == 405


def test_admin_pages_require_login() -> None:
    seed_database()
    client = TestClient(app)

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"

    response = client.get("/admin/leagues", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_login_and_logout(monkeypatch) -> None:
    seed_database()
    monkeypatch.setenv("BATTLE_MARCH_ADMIN_PASSWORD_HASH", hash_password("secret"))
    client = TestClient(app)

    bad_response = client.post("/admin/login", data={"password": "wrong"})
    assert bad_response.status_code == 400

    good_response = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    assert good_response.status_code == 303

    logout_response = client.post("/admin/logout", follow_redirects=False)
    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/admin/login"


def test_admin_pages_render(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    for path in ("/admin", "/admin/leagues", "/admin/players", "/admin/rounds", "/admin/matches", "/admin/army-lists"):
        response = client.get(path)
        assert response.status_code == 200


def test_admin_can_create_and_edit_first_league_from_empty_database(monkeypatch) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client = authenticated_client(monkeypatch)

    response = client.get("/admin/leagues")
    assert response.status_code == 200

    response = client.post("/admin/leagues", data={"name": "The First Muster"})
    assert response.status_code == 200

    with SessionLocal() as db:
        league = db.scalar(select(League).where(League.name == "The First Muster"))
        assert league is not None
        league_id = league.id

    response = client.post(f"/admin/leagues/{league_id}/edit", data={"name": "The First Muster Revised"})
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.scalar(select(League).where(League.name == "The First Muster Revised")) is not None


def test_admin_filters_players_by_selected_league(monkeypatch) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client = authenticated_client(monkeypatch)

    with SessionLocal() as db:
        old_world = League(name="Old World")
        combat_patrol = League(name="Combat Patrol")
        db.add_all([old_world, combat_patrol])
        db.flush()
        old_world_id = old_world.id
        combat_patrol_id = combat_patrol.id
        db.add(Player(name="Alys Emberfall", league_id=old_world_id))
        db.add(Player(name="Brother Cassian", league_id=combat_patrol_id))
        db.commit()

    response = client.get(f"/admin/players?league_id={old_world_id}")

    assert response.status_code == 200
    assert "Alys Emberfall" in response.text
    assert "Brother Cassian" not in response.text

    response = client.get(f"/admin/players?league_id={combat_patrol_id}")

    assert response.status_code == 200
    assert "Brother Cassian" in response.text
    assert "Alys Emberfall" not in response.text


def test_admin_can_add_and_edit_player(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    response = client.post("/admin/players", data={"name": "Iris Dawn", "league_id": "1"})
    assert response.status_code == 200

    with SessionLocal() as db:
        player = db.scalar(select(Player).where(Player.name == "Iris Dawn"))
        assert player is not None
        player_id = player.id

    response = client.post(f"/admin/players/{player_id}/edit", data={"name": "Iris Dawnblade"})
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.scalar(select(Player).where(Player.name == "Iris Dawnblade")) is not None


def test_admin_can_add_and_edit_round(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    response = client.post("/admin/rounds", data={"number": "4", "points_limit": "1750", "league_id": "1"})
    assert response.status_code == 200

    with SessionLocal() as db:
        round_item = db.scalar(select(Round).where(Round.number == 4))
        assert round_item is not None
        round_id = round_item.id

    response = client.post(
        f"/admin/rounds/{round_id}/edit",
        data={"number": "4", "points_limit": "2000"},
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        round_item = db.get(Round, round_id)
        assert round_item.points_limit == 2000


def test_admin_can_update_round_league_points(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    response = client.get("/admin/rounds/1/scores")
    assert response.status_code == 200

    response = client.post(
        "/admin/rounds/1/scores",
        data={
            "bye_8": "on",
            "painting_progress_8": "on",
            "fully_painted_8": "on",
        },
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        score = db.scalar(select(PlayerRoundScore).where(PlayerRoundScore.player_id == 8, PlayerRoundScore.round_id == 1))
        assert score is not None
        assert score.is_bye is True
        assert score.painting_progress is True
        assert score.fully_painted is True


def test_admin_can_add_match_and_edit_scores(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    response = client.post(
        "/admin/matches",
        data={
            "round_id": "3",
            "player_one_id": "7",
            "player_two_id": "8",
            "player_one_score": "",
            "player_two_score": "",
        },
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        match = db.scalar(select(Match).where(Match.player_one_id == 7, Match.player_two_id == 8))
        assert match is not None
        assert match.player_one_score is None
        match_id = match.id

    response = client.post(
        f"/admin/matches/{match_id}/edit",
        data={
            "round_id": "3",
            "player_one_id": "7",
            "player_two_id": "8",
            "player_one_score": "11",
            "player_two_score": "9",
        },
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        match = db.get(Match, match_id)
        assert match.player_one_score == 11
        assert match.player_two_score == 9


def test_admin_can_update_match_scores_with_htmx(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    with SessionLocal() as db:
        match = db.scalar(select(Match).where(Match.player_one_id == 5, Match.player_two_id == 6))
        assert match is not None
        match_id = match.id

    response = client.post(
        f"/admin/matches/{match_id}/scores",
        data={"player_one_score": "20", "player_two_score": "1"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert f'id="match-{match_id}"' in response.text
    assert 'value="20"' in response.text
    assert 'value="1"' in response.text

    with SessionLocal() as db:
        match = db.get(Match, match_id)
        assert match.player_one_score == 20
        assert match.player_two_score == 1

    leaderboard_response = client.get("/players")
    assert leaderboard_response.status_code == 200
    assert "Elara Moonbrook" in leaderboard_response.text
    assert ">20<" in leaderboard_response.text


def test_admin_can_reset_match_scores_with_htmx(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    with SessionLocal() as db:
        match = db.scalar(select(Match).where(Match.player_one_id == 1, Match.player_two_id == 2))
        assert match is not None
        match_id = match.id

    response = client.post(
        f"/admin/matches/{match_id}/reset",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert f'id="match-{match_id}"' in response.text
    assert f'action="/admin/matches/{match_id}/reset"' in response.text
    assert 'value="15"' not in response.text
    assert 'value="5"' not in response.text

    with SessionLocal() as db:
        match = db.get(Match, match_id)
        assert match.player_one_score is None
        assert match.player_two_score is None


def test_admin_can_delete_match(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    with SessionLocal() as db:
        match = db.scalar(select(Match).where(Match.player_one_id == 1, Match.player_two_id == 2))
        assert match is not None
        match_id = match.id

    response = client.post(f"/admin/matches/{match_id}/delete")
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(Match, match_id) is None


def test_admin_can_delete_army_list(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)
    client.post(
        "/admin/army-lists",
        data={"player_id": "1", "round_id": "1", "json_text": json.dumps(VALID_EXPORT)},
    )

    with SessionLocal() as db:
        army_list = db.scalar(select(ArmyList).where(ArmyList.player_id == 1, ArmyList.round_id == 1))
        assert army_list is not None
        army_list_id = army_list.id

    response = client.post(f"/admin/army-lists/{army_list_id}/delete")
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(ArmyList, army_list_id) is None


def test_admin_can_delete_player_and_dependent_rows(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)
    client.post(
        "/admin/army-lists",
        data={"player_id": "1", "round_id": "1", "json_text": json.dumps(VALID_EXPORT)},
    )

    response = client.post("/admin/players/1/delete")
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(Player, 1) is None
        assert db.scalar(select(Match).where((Match.player_one_id == 1) | (Match.player_two_id == 1))) is None
        assert db.scalar(select(ArmyList).where(ArmyList.player_id == 1)) is None
        assert db.scalar(select(PlayerRoundScore).where(PlayerRoundScore.player_id == 1)) is None


def test_admin_can_delete_round_and_dependent_rows(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)
    client.post(
        "/admin/army-lists",
        data={"player_id": "1", "round_id": "1", "json_text": json.dumps(VALID_EXPORT)},
    )

    response = client.post("/admin/rounds/1/delete")
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(Round, 1) is None
        assert db.scalar(select(Match).where(Match.round_id == 1)) is None
        assert db.scalar(select(ArmyList).where(ArmyList.round_id == 1)) is None
        assert db.scalar(select(PlayerRoundScore).where(PlayerRoundScore.round_id == 1)) is None


def test_admin_can_delete_league_and_dependent_rows(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)
    client.post(
        "/admin/army-lists",
        data={"player_id": "1", "round_id": "1", "json_text": json.dumps(VALID_EXPORT)},
    )

    response = client.post("/admin/leagues/1/delete")
    assert response.status_code == 200

    with SessionLocal() as db:
        assert db.get(League, 1) is None
        assert db.scalar(select(Player)) is None
        assert db.scalar(select(Round)) is None
        assert db.scalar(select(Match)) is None
        assert db.scalar(select(ArmyList)) is None
        assert db.scalar(select(PlayerRoundScore)) is None


def test_admin_can_import_army_list(monkeypatch) -> None:
    seed_database()
    client = authenticated_client(monkeypatch)

    response = client.post(
        "/admin/army-lists",
        data={
            "player_id": "1",
            "round_id": "1",
            "json_text": json.dumps(VALID_EXPORT),
        },
    )

    assert response.status_code == 200
    assert "Imported" in response.text

    with SessionLocal() as db:
        army_list = db.scalar(select(ArmyList).where(ArmyList.player_id == 1, ArmyList.round_id == 1))
        assert army_list is not None
        assert army_list.name == "Ng1 2"
