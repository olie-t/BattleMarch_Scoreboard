import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal
from app.main import app
from app.models import League, Match, Player, Round
from app.scoreboard import (
    build_leaderboard,
    build_match_row,
    build_player_detail,
    calculate_game_result,
)
from scripts.seed import seed_database


@pytest.mark.parametrize(
    "points_limit, score_one, score_two, result_one, result_two, points_one, points_two",
    [
        (1000, 500, 500, "Draw", "Draw", 2, 2),
        (1000, 599, 500, "Draw", "Draw", 2, 2),
        (1000, 600, 500, "Draw", "Draw", 2, 2),
        (1000, 500, 600, "Draw", "Draw", 2, 2),
        (1000, 601, 500, "Win", "Loss", 3, 1),
        (1000, 500, 601, "Loss", "Win", 1, 3),
        (1250, 625, 500, "Draw", "Draw", 2, 2),
        (1250, 626, 500, "Win", "Loss", 3, 1),
        (1001, 600, 500, "Draw", "Draw", 2, 2),
        (1001, 601, 500, "Win", "Loss", 3, 1),
        (1000, 0, 0, "Draw", "Draw", 2, 2),
        (1000, None, 500, "Pending", "Pending", 0, 0),
        (1000, 500, None, "Pending", "Pending", 0, 0),
        (1000, None, None, "Pending", "Pending", 0, 0),
        (0, 600, 500, "Pending", "Pending", 0, 0),
    ],
)
def test_draw_margin_is_consistent_across_results_and_standings(
    points_limit, score_one, score_two, result_one, result_two, points_one, points_two
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        league = League(name="Draw margin league")
        player_one = Player(name="Alys", league=league)
        player_two = Player(name="Borin", league=league)
        round_item = Round(number=1, points_limit=points_limit, league=league)
        match = Match(
            round=round_item,
            player_one=player_one,
            player_two=player_two,
            player_one_score=score_one,
            player_two_score=score_two,
        )
        db.add(match)
        db.commit()

        if result_one == "Win":
            expected_match_result = "Alys won"
        elif result_two == "Win":
            expected_match_result = "Borin won"
        else:
            expected_match_result = result_one
        assert build_match_row(match, db)["result"] == expected_match_result

        _, standings = build_leaderboard(db, league.id)
        standings_by_player = {row["player"].id: row for row in standings}
        for player, expected_result, expected_points in (
            (player_one, result_one, points_one),
            (player_two, result_two, points_two),
        ):
            game = calculate_game_result(player.id, match, db)
            assert game["battle_result"] == expected_result
            assert game["result_points"] == expected_points
            detail = build_player_detail(db, player)
            assert detail["round_results"][0]["result"] == expected_result
            assert detail["total_league_points"] == expected_points
            assert standings_by_player[player.id]["total_league_points"] == expected_points
    engine.dispose()


def test_round_page_displays_draw_for_unequal_scores_at_margin() -> None:
    seed_database()
    with SessionLocal() as db:
        match = db.get(Match, 1)
        match.player_one_score = 600
        match.player_two_score = 500
        round_id = match.round_id
        db.commit()

    response = TestClient(app).get(f"/rounds/{round_id}")

    assert response.status_code == 200
    assert "Draw" in response.text
    assert "Alys Emberfall won" not in response.text
    assert "Borin Oakshield won" not in response.text
