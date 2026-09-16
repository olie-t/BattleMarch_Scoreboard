from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.army_list_view import render_army_list
from app.database import get_db
from app.models import ArmyList, League, Match, Player, Round
from app.scoreboard import build_leaderboard, build_match_row, build_player_detail, current_league
from app.templating import templates


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"title": "Battle March"},
    )


@router.get("/players", response_class=HTMLResponse)
def player_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = current_league(db)
    return render_player_list(request, db, league)


@router.get("/leagues", response_class=HTMLResponse)
def league_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    leagues = list(db.scalars(select(League).order_by(League.name)))
    return templates.TemplateResponse(
        request=request,
        name="leagues.html",
        context={"leagues": leagues},
    )


@router.get("/leagues/{league_id}/players", response_class=HTMLResponse)
def league_player_list(league_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = db.get(League, league_id)
    if league is None:
        return HTMLResponse("League not found", status_code=404)
    return render_player_list(request, db, league)


def render_player_list(request: Request, db: Session, league: Optional[League]) -> HTMLResponse:
    rounds, players = ([], []) if league is None else build_leaderboard(db, league.id)
    return templates.TemplateResponse(
        request=request,
        name="players.html",
        context={"league": league, "rounds": rounds, "players": players},
    )


@router.get("/players/{player_id}", response_class=HTMLResponse)
def player_detail(
    player_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    player = db.scalar(select(Player).where(Player.id == player_id))
    if player is None:
        return HTMLResponse("Player not found", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="player_detail.html",
        context={"player_detail": build_player_detail(db, player)},
    )


@router.get("/rounds", response_class=HTMLResponse)
def round_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = current_league(db)
    return render_round_list(request, db, league)


@router.get("/leagues/{league_id}/rounds", response_class=HTMLResponse)
def league_round_list(league_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = db.get(League, league_id)
    if league is None:
        return HTMLResponse("League not found", status_code=404)
    return render_round_list(request, db, league)


def render_round_list(request: Request, db: Session, league: Optional[League]) -> HTMLResponse:
    rounds = [] if league is None else list(
        db.scalars(
            select(Round)
            .where(Round.league_id == league.id)
            .order_by(Round.number)
        )
    )
    return templates.TemplateResponse(
        request=request,
        name="rounds.html",
        context={"league": league, "rounds": rounds},
    )


@router.get("/rounds/{round_id}", response_class=HTMLResponse)
def round_detail(
    round_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    round_item = db.scalar(select(Round).where(Round.id == round_id))
    if round_item is None:
        return HTMLResponse("Round not found", status_code=404)

    matches = list(
        db.scalars(
            select(Match)
            .where(Match.round_id == round_id)
            .order_by(Match.id)
        )
    )
    return templates.TemplateResponse(
        request=request,
        name="round_detail.html",
        context={
            "round_item": round_item,
            "matches": [build_match_row(match) for match in matches],
        },
    )


@router.get("/army-lists/{army_list_id}", response_class=HTMLResponse)
def army_list_detail(
    army_list_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    army_list = db.get(ArmyList, army_list_id)
    if army_list is None:
        return HTMLResponse("Army list not found", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="army_list_detail.html",
        context={"view": render_army_list(army_list)},
    )
