from typing import List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import ArmyList, League, Match, Player, Round


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
    round_score_expressions = {}
    for round_item in rounds:
        round_score_expressions[round_item.number] = func.coalesce(
            func.sum(
                case(
                    (
                        (Match.round_id == round_item.id)
                        & (Match.player_one_id == Player.id),
                        Match.player_one_score,
                    ),
                    (
                        (Match.round_id == round_item.id)
                        & (Match.player_two_id == Player.id),
                        Match.player_two_score,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label(f"round_{round_item.number}_points")

    total_points = sum(round_score_expressions.values())
    latest_faction = (
        select(ArmyList.faction)
        .where(ArmyList.player_id == Player.id)
        .order_by(ArmyList.created_at.desc(), ArmyList.id.desc())
        .limit(1)
        .scalar_subquery()
    )

    query = (
        select(
            Player,
            *round_score_expressions.values(),
            total_points.label("total_points"),
            latest_faction.label("faction"),
        )
        .outerjoin(Match, (Match.player_one_id == Player.id) | (Match.player_two_id == Player.id))
        .where(Player.league_id == league_id)
        .group_by(Player.id)
        .order_by(
            total_points.desc(),
            Player.name,
        )
    )
    rows = db.execute(query).all()
    standings = []
    for row in rows:
        standings.append(
            {
                "player": row[0],
                "round_points": {
                    round_item.number: row[index + 1]
                    for index, round_item in enumerate(rounds)
                },
                "total_points": row[len(rounds) + 1],
                "faction": row[len(rounds) + 2],
            }
        )
    return rounds, standings


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

    round_results = []
    for round_item in rounds:
        match = matches_by_round_id.get(round_item.id)
        opponent = None
        score = "Not played"
        result = "No match scheduled"

        if match is not None:
            is_player_one = match.player_one_id == player.id
            opponent = match.player_two if is_player_one else match.player_one
            player_score = match.player_one_score if is_player_one else match.player_two_score
            opponent_score = match.player_two_score if is_player_one else match.player_one_score

            if player_score is None or opponent_score is None:
                score = "Not entered"
                result = "Pending"
            else:
                score = f"{player_score}-{opponent_score}"
                if player_score == opponent_score:
                    result = "Draw"
                elif player_score > opponent_score:
                    result = "Win"
                else:
                    result = "Loss"

        round_results.append(
            {
                "round": round_item,
                "opponent": opponent,
                "score": score,
                "result": result,
                "army_list": army_lists_by_round_id.get(round_item.id),
                "points": standing["round_points"][round_item.number],
            }
        )

    return {
        "player": player,
        "faction": standing["faction"],
        "total_points": standing["total_points"],
        "round_results": round_results,
    }
