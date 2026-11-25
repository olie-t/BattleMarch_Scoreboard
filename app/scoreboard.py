from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.display import format_faction
from app.models import ArmyList, League, Match, Player, PlayerRoundScore, Round


WIN_LEAGUE_POINTS = 3
DRAW_LEAGUE_POINTS = 2
BYE_LEAGUE_POINTS = 2
LOSS_LEAGUE_POINTS = 1
PAINTING_PROGRESS_POINTS = 1
FULLY_PAINTED_POINTS = 1

def GetRoundPointLimit(db: Session, round_id: int):
    round_item = db.get(Round, round_id)
    if round_item is None:
        return None
    return round_item.points_limit

def current_league(db: Session) -> Optional[League]:
    return db.scalar(select(League).order_by(League.id.desc()))


def optional_score(value: str) -> Optional[int]:
    if not value.strip():
        return None
    return int(value)


def build_leaderboard(db: Session, league_id: int) -> tuple[List[Round], List[dict]]:
    rounds = list(
        db.scalars(
            select(Round)
            .where(Round.league_id == league_id)
            .order_by(Round.number)
        )
    )
    players = list(
        db.scalars(
            select(Player)
            .where(Player.league_id == league_id)
            .order_by(Player.name)
        )
    )
    matches = list(
        db.scalars(
            select(Match)
            .join(Round)
            .where(Round.league_id == league_id)
            .order_by(Match.round_id)
        )
    )
    score_rows = list(
        db.scalars(
            select(PlayerRoundScore)
            .join(Round)
            .where(Round.league_id == league_id)
        )
    )
    army_lists = list(
        db.scalars(
            select(ArmyList)
            .join(Round)
            .where(Round.league_id == league_id)
            .order_by(ArmyList.player_id, ArmyList.created_at.desc(), ArmyList.id.desc())
        )
    )

    matches_by_player_and_round = {}
    for match in matches:
        matches_by_player_and_round.setdefault((match.player_one_id, match.round_id), []).append(match)
        matches_by_player_and_round.setdefault((match.player_two_id, match.round_id), []).append(match)

    score_by_player_and_round = {
        (score.player_id, score.round_id): score
        for score in score_rows
    }
    faction_by_player_id = {}
    for army_list in army_lists:
        faction_by_player_id.setdefault(army_list.player_id, army_list.faction)

    standings = []
    for player in players:
        round_points = {}
        total_league_points = 0
        total_victory_points = 0
        for round_item in rounds:
            player_matches = matches_by_player_and_round.get((player.id, round_item.id), [])
            score_row = score_by_player_and_round.get((player.id, round_item.id))
            round_result = calculate_round_score(player.id, player_matches, score_row, db)
            round_points[round_item.number] = round_result["league_points"]
            total_league_points += round_result["league_points"]
            total_victory_points += round_result["victory_points"]

        standings.append(
            {
                "player": player,
                "round_points": round_points,
                "total_points": total_league_points,
                "total_league_points": total_league_points,
                "total_victory_points": total_victory_points,
                "faction": faction_by_player_id.get(player.id),
                "faction_display": format_faction(faction_by_player_id.get(player.id)),
            }
        )
    standings.sort(
        key=lambda standing: (
            -standing["total_league_points"],
            -standing["total_victory_points"],
            standing["player"].name,
        )
    )
    return rounds, standings


def calculate_round_score(
    player_id: int,
    matches: List[Match],
    score: Optional[PlayerRoundScore],
    db: Session,
) -> dict:
    battle_result = "No match scheduled"
    victory_points = 0
    best_result_points = 0
    best_game = None
    completed_games = []

    for match in matches:
        game_result = calculate_game_result(player_id, match, db)
        if game_result["battle_result"] == "Pending":
            continue
        completed_games.append(game_result)
        if is_better_game_result(game_result, best_game):
            best_result_points = game_result["result_points"]
            victory_points = game_result["victory_points"]
            best_game = game_result

    if best_game is not None:
        battle_result = best_game["battle_result"]
    elif matches:
        battle_result = "Pending"

    if score is not None and score.is_bye and BYE_LEAGUE_POINTS > best_result_points:
        battle_result = "Bye"
        best_result_points = BYE_LEAGUE_POINTS
        victory_points = 0

    painting_points = PAINTING_PROGRESS_POINTS if score is not None and score.painting_progress else 0
    fully_painted_points = FULLY_PAINTED_POINTS if score is not None and score.fully_painted else 0

    return {
        "battle_result": battle_result,
        "victory_points": victory_points,
        "result_points": best_result_points,
        "painting_points": painting_points,
        "fully_painted_points": fully_painted_points,
        "league_points": best_result_points + painting_points + fully_painted_points,
        "completed_games": completed_games,
    }


def calculate_game_result(player_id: int, match: Match, db: Session) -> dict:
    is_player_one = match.player_one_id == player_id
    opponent = match.player_two if is_player_one else match.player_one
    player_victory_points = match.player_one_score if is_player_one else match.player_two_score
    opponent_victory_points = match.player_two_score if is_player_one else match.player_one_score

    round_point_limit = GetRoundPointLimit(db, match.round_id)

    if round_point_limit is None or round_point_limit == 0:
        return {
            "opponent": opponent,
            "victory_score": "Not entered",
            "battle_result": "Pending",
            "victory_points": 0,
            "result_points": 0,
        }       

    if player_victory_points is None or opponent_victory_points is None:
        return {
            "opponent": opponent,
            "victory_score": "Not entered",
            "battle_result": "Pending",
            "victory_points": 0,
            "result_points": 0,
        }

    if abs(player_victory_points - opponent_victory_points) * 10 <= round_point_limit:
        battle_result = "Draw"
        result_points = DRAW_LEAGUE_POINTS
    elif player_victory_points > opponent_victory_points:
        battle_result = "Win"
        result_points = WIN_LEAGUE_POINTS
    else:
        battle_result = "Loss"
        result_points = LOSS_LEAGUE_POINTS

    return {
        "opponent": opponent,
        "victory_score": f"{player_victory_points}-{opponent_victory_points}",
        "battle_result": battle_result,
        "victory_points": player_victory_points,
        "result_points": result_points,
    }


def is_better_game_result(candidate: dict, current_best: Optional[dict]) -> bool:
    if current_best is None:
        return True
    if candidate["result_points"] != current_best["result_points"]:
        return candidate["result_points"] > current_best["result_points"]
    return candidate["victory_points"] > current_best["victory_points"]


def build_match_row(match: Match, db: Session) -> dict:
    game_result = calculate_game_result(match.player_one_id, match, db)
    if game_result["battle_result"] == "Win":
        result = f"{match.player_one.name} won"
    elif game_result["battle_result"] == "Loss":
        result = f"{match.player_two.name} won"
    else:
        result = game_result["battle_result"]

    return {"match": match, "result": result}


def build_player_detail(db: Session, player: Player) -> dict:
    rounds, standings = build_leaderboard(db, player.league_id)
    standing = next(row for row in standings if row["player"].id == player.id)
    matches = list(
        db.scalars(
            select(Match)
            .where((Match.player_one_id == player.id) | (Match.player_two_id == player.id))
            .order_by(Match.round_id)
        )
    )
    matches_by_round_id = {}
    for match in matches:
        matches_by_round_id.setdefault(match.round_id, []).append(match)
    army_lists = list(
        db.scalars(
            select(ArmyList)
            .where(ArmyList.player_id == player.id)
            .order_by(ArmyList.round_id, ArmyList.created_at.desc(), ArmyList.id.desc())
        )
    )
    army_lists_by_round_id = {}
    for army_list in army_lists:
        army_lists_by_round_id.setdefault(army_list.round_id, army_list)
    score_rows = list(
        db.scalars(
            select(PlayerRoundScore)
            .where(PlayerRoundScore.player_id == player.id)
        )
    )
    score_by_round_id = {score.round_id: score for score in score_rows}

    round_results = []
    for round_item in rounds:
        player_matches = matches_by_round_id.get(round_item.id, [])
        round_score = score_by_round_id.get(round_item.id)
        games = [calculate_game_result(player.id, match, db) for match in player_matches]
        calculated_score = calculate_round_score(player.id, player_matches, round_score, db)
        victory_score = "Not played"
        if games:
            victory_score = "; ".join(game["victory_score"] for game in games)
        elif round_score is not None and round_score.is_bye:
            victory_score = "Bye"

        round_results.append(
            {
                "round": round_item,
                "opponent": games[0]["opponent"] if len(games) == 1 else None,
                "games": games,
                "score": victory_score,
                "victory_score": victory_score,
                "result": calculated_score["battle_result"],
                "army_list": army_lists_by_round_id.get(round_item.id),
                "points": calculated_score["league_points"],
                "league_points": calculated_score["league_points"],
                "victory_points": calculated_score["victory_points"],
                "result_points": calculated_score["result_points"],
                "painting_points": calculated_score["painting_points"],
                "fully_painted_points": calculated_score["fully_painted_points"],
            }
        )

    return {
        "player": player,
        "faction": standing["faction"],
        "faction_display": standing["faction_display"],
        "total_points": standing["total_points"],
        "total_league_points": standing["total_league_points"],
        "total_victory_points": standing["total_victory_points"],
        "round_results": round_results,
    }



