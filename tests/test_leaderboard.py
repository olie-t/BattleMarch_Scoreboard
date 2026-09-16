from sqlalchemy import select

from app.database import SessionLocal
from app.main import build_leaderboard
from app.models import League
from scripts.seed import seed_database


def seeded_standings():
    seed_database()
    with SessionLocal() as db:
        league = db.scalar(select(League))
        return build_leaderboard(db, league.id)


def test_seeded_round_points_and_totals() -> None:
    rounds, standings = seeded_standings()

    assert [round_item.number for round_item in rounds] == [1, 2, 3]
    by_name = {standing["player"].name: standing for standing in standings}

    assert by_name["Darius Vale"]["round_points"] == {1: 2, 2: 0, 3: 4}
    assert by_name["Darius Vale"]["total_league_points"] == 6
    assert by_name["Darius Vale"]["total_victory_points"] == 24
    assert by_name["Alys Emberfall"]["round_points"] == {1: 4, 2: 1, 3: 0}
    assert by_name["Alys Emberfall"]["total_league_points"] == 5
    assert by_name["Alys Emberfall"]["total_victory_points"] == 23


def test_best_game_result_counts_for_round_league_points() -> None:
    _, standings = seeded_standings()
    by_name = {standing["player"].name: standing for standing in standings}

    assert by_name["Alys Emberfall"]["round_points"][1] == 4
    assert by_name["Alys Emberfall"]["total_victory_points"] == 23


def test_victory_points_come_from_best_game_result_only() -> None:
    _, standings = seeded_standings()
    by_name = {standing["player"].name: standing for standing in standings}

    assert by_name["Alys Emberfall"]["total_victory_points"] == 23
    assert by_name["Darius Vale"]["total_victory_points"] == 24


def test_players_without_scored_matches_have_zero_points() -> None:
    _, standings = seeded_standings()

    hugo = next(standing for standing in standings if standing["player"].name == "Hugo Redwyne")

    assert hugo["round_points"] == {1: 0, 2: 0, 3: 0}
    assert hugo["total_league_points"] == 0
    assert hugo["total_victory_points"] == 0


def test_byes_and_painting_awards_count_as_league_points() -> None:
    _, standings = seeded_standings()
    by_name = {standing["player"].name: standing for standing in standings}

    assert by_name["Gwen Hearthward"]["round_points"] == {1: 0, 2: 2, 3: 0}
    assert by_name["Gwen Hearthward"]["total_league_points"] == 2
    assert by_name["Borin Oakshield"]["round_points"][1] == 2


def test_standings_are_sorted_by_total_points() -> None:
    _, standings = seeded_standings()

    assert [standing["player"].name for standing in standings[:3]] == [
        "Darius Vale",
        "Alys Emberfall",
        "Celia Thorn",
    ]