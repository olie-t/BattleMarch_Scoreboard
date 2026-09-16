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

    match_by_player_and_round = {}
    for match in matches:
        match_by_player_and_round[(match.player_one_id, match.round_id)] = match
        match_by_player_and_round[(match.player_two_id, match.round_id)] = match

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
            match = match_by_player_and_round.get((player.id, round_item.id))
            score_row = score_by_player_and_round.get((player.id, round_item.id))
            round_result = calculate_round_score(player.id, match, score_row)
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
    match: Optional[Match],
    score: Optional[PlayerRoundScore],
) -> dict:
    battle_result = "No match scheduled"
    victory_points = 0
    result_points = 0

    if score is not None and score.is_bye:
        battle_result = "Bye"
        result_points = BYE_LEAGUE_POINTS
    elif match is not None:
        is_player_one = match.player_one_id == player_id
        player_victory_points = match.player_one_score if is_player_one else match.player_two_score
        opponent_victory_points = match.player_two_score if is_player_one else match.player_one_score

        if player_victory_points is None or opponent_victory_points is None:
            battle_result = "Pending"
        else:
            victory_points = player_victory_points
            if player_victory_points == opponent_victory_points:
                battle_result = "Draw"
                result_points = DRAW_LEAGUE_POINTS
            elif player_victory_points > opponent_victory_points:
                battle_result = "Win"
                result_points = WIN_LEAGUE_POINTS
            else:
                battle_result = "Loss"
                result_points = LOSS_LEAGUE_POINTS

    painting_points = PAINTING_PROGRESS_POINTS if score is not None and score.painting_progress else 0
    fully_painted_points = FULLY_PAINTED_POINTS if score is not None and score.fully_painted else 0

    return {
        "battle_result": battle_result,
        "victory_points": victory_points,
        "result_points": result_points,
        "painting_points": painting_points,
        "fully_painted_points": fully_painted_points,
        "league_points": result_points + painting_points + fully_painted_points,
    }


def build_match_row(match: Match) -> dict:
    if match.player_one_score is None or match.player_two_score is None:
        result = "Pending"
    elif match.player_one_score == match.player_two_score:
        result = "Draw"
    elif match.player_one_score > match.player_two_score:
        result = f"{match.player_one.name} won"
    else:
        result = f"{match.player_two.name} won"

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
    matches_by_round_id = {match.round_id: match for match in matches}
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
        match = matches_by_round_id.get(round_item.id)
        round_score = score_by_round_id.get(round_item.id)
        opponent = None
        victory_score = "Not played"
        result = "No match scheduled"

        if round_score is not None and round_score.is_bye:
            result = "Bye"
            victory_score = "Bye"
        elif match is not None:
            is_player_one = match.player_one_id == player.id
            opponent = match.player_two if is_player_one else match.player_one
            player_score = match.player_one_score if is_player_one else match.player_two_score
            opponent_score = match.player_two_score if is_player_one else match.player_one_score

            if player_score is None or opponent_score is None:
                victory_score = "Not entered"
                result = "Pending"
            else:
                victory_score = f"{player_score}-{opponent_score}"
                if player_score == opponent_score:
                    result = "Draw"
                elif player_score > opponent_score:
                    result = "Win"
                else:
                    result = "Loss"
        calculated_score = calculate_round_score(player.id, match, round_score)

        round_results.append(
            {
                "round": round_item,
                "opponent": opponent,
                "score": victory_score,
                "victory_score": victory_score,
                "result": result,
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
