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

    assert by_name["Darius Vale"]["round_points"] == {1: 10, 2: 0, 3: 14}
    assert by_name["Darius Vale"]["total_points"] == 24
    assert by_name["Alys Emberfall"]["round_points"] == {1: 15, 2: 8, 3: 0}
    assert by_name["Alys Emberfall"]["total_points"] == 23


def test_players_without_scored_matches_have_zero_points() -> None:
    _, standings = seeded_standings()

    hugo = next(standing for standing in standings if standing["player"].name == "Hugo Redwyne")

    assert hugo["round_points"] == {1: 0, 2: 0, 3: 0}
    assert hugo["total_points"] == 0


def test_standings_are_sorted_by_total_points() -> None:
    _, standings = seeded_standings()

    assert [standing["player"].name for standing in standings[:3]] == [
        "Darius Vale",
        "Alys Emberfall",
        "Celia Thorn",
    ]