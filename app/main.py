from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Union

from fastapi import Depends, FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.army_list_import import ArmyListImportError, import_army_list
from app.army_list_view import render_army_list
from app.auth import SESSION_KEY, authenticate_admin, require_admin, secure_cookies_enabled, session_secret
from app.database import Base, engine, get_db
from app.models import ArmyList, League, Match, Player, Round


BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if auto_create_tables_enabled():
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Battle March", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    session_cookie="battle_march_session",
    same_site="lax",
    https_only=secure_cookies_enabled(),
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def current_league(db: Session) -> Optional[League]:
    return db.scalar(select(League).order_by(League.id.desc()))


def optional_score(value: str) -> Optional[int]:
    if not value.strip():
        return None
    return int(value)


def auto_create_tables_enabled() -> bool:
    if os.environ.get("BATTLE_MARCH_AUTO_CREATE_TABLES") is not None:
        return os.environ["BATTLE_MARCH_AUTO_CREATE_TABLES"].lower() in {"1", "true", "yes", "on"}
    return os.environ.get("BATTLE_MARCH_ENV") != "production"


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


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"title": "Battle March"},
    )


@app.get("/players", response_class=HTMLResponse)
def player_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = current_league(db)
    rounds, players = ([], []) if league is None else build_leaderboard(db, league.id)
    return templates.TemplateResponse(
        request=request,
        name="players.html",
        context={"league": league, "rounds": rounds, "players": players},
    )


@app.get("/players/{player_id}", response_class=HTMLResponse)
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


@app.get("/rounds", response_class=HTMLResponse)
def round_list(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = current_league(db)
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


@app.get("/rounds/{round_id}", response_class=HTMLResponse)
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


@app.get("/army-lists/{army_list_id}", response_class=HTMLResponse)
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


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"error": None},
    )


@app.post("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request, password: str = Form(...)) -> Response:
    if authenticate_admin(password):
        request.session.clear()
        request.session[SESSION_KEY] = True
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"error": "Invalid admin password."},
        status_code=400,
    )


@app.post("/admin/logout")
def admin_logout(request: Request, _: None = Depends(require_admin)) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, _: None = Depends(require_admin)) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="admin/home.html")


@app.get("/admin/leagues", response_class=HTMLResponse)
def admin_leagues(
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    leagues = list(db.scalars(select(League).order_by(League.id.desc())))
    return templates.TemplateResponse(
        request=request,
        name="admin/leagues.html",
        context={"leagues": leagues},
    )


@app.post("/admin/leagues")
def admin_create_league(
    name: str = Form(...),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    db.add(League(name=name.strip()))
    db.commit()
    return RedirectResponse("/admin/leagues", status_code=303)


@app.get("/admin/leagues/{league_id}/edit", response_class=HTMLResponse)
def admin_edit_league_form(
    league_id: int,
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    league = db.get(League, league_id)
    if league is None:
        return HTMLResponse("League not found", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="admin/league_edit.html",
        context={"league": league},
    )


@app.post("/admin/leagues/{league_id}/edit")
def admin_update_league(
    league_id: int,
    name: str = Form(...),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    league = db.get(League, league_id)
    if league is not None:
        league.name = name.strip()
        db.commit()
    return RedirectResponse("/admin/leagues", status_code=303)


@app.get("/admin/players", response_class=HTMLResponse)
def admin_players(
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    league = current_league(db)
    players = [] if league is None else list(
        db.scalars(select(Player).where(Player.league_id == league.id).order_by(Player.name))
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/players.html",
        context={"league": league, "players": players},
    )


@app.post("/admin/players")
def admin_create_player(
    name: str = Form(...),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    league = current_league(db)
    if league is not None:
        db.add(Player(name=name.strip(), league_id=league.id))
        db.commit()
    return RedirectResponse("/admin/players", status_code=303)


@app.get("/admin/players/{player_id}/edit", response_class=HTMLResponse)
def admin_edit_player_form(
    player_id: int,
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    player = db.get(Player, player_id)
    if player is None:
        return HTMLResponse("Player not found", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="admin/player_edit.html",
        context={"player": player},
    )


@app.post("/admin/players/{player_id}/edit")
def admin_update_player(
    player_id: int,
    name: str = Form(...),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    player = db.get(Player, player_id)
    if player is not None:
        player.name = name.strip()
        db.commit()
    return RedirectResponse("/admin/players", status_code=303)


@app.get("/admin/rounds", response_class=HTMLResponse)
def admin_rounds(
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    league = current_league(db)
    rounds = [] if league is None else list(
        db.scalars(select(Round).where(Round.league_id == league.id).order_by(Round.number))
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/rounds.html",
        context={"league": league, "rounds": rounds},
    )


@app.post("/admin/rounds")
def admin_create_round(
    number: int = Form(...),
    points_limit: int = Form(...),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    league = current_league(db)
    if league is not None:
        db.add(Round(number=number, points_limit=points_limit, league_id=league.id))
        db.commit()
    return RedirectResponse("/admin/rounds", status_code=303)


@app.get("/admin/rounds/{round_id}/edit", response_class=HTMLResponse)
def admin_edit_round_form(
    round_id: int,
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    round_item = db.get(Round, round_id)
    if round_item is None:
        return HTMLResponse("Round not found", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="admin/round_edit.html",
        context={"round_item": round_item},
    )


@app.post("/admin/rounds/{round_id}/edit")
def admin_update_round(
    round_id: int,
    number: int = Form(...),
    points_limit: int = Form(...),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    round_item = db.get(Round, round_id)
    if round_item is not None:
        round_item.number = number
        round_item.points_limit = points_limit
        db.commit()
    return RedirectResponse("/admin/rounds", status_code=303)


@app.get("/admin/matches", response_class=HTMLResponse)
def admin_matches(
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    league = current_league(db)
    rounds = [] if league is None else list(
        db.scalars(select(Round).where(Round.league_id == league.id).order_by(Round.number))
    )
    players = [] if league is None else list(
        db.scalars(select(Player).where(Player.league_id == league.id).order_by(Player.name))
    )
    matches = list(db.scalars(select(Match).join(Round).order_by(Round.number, Match.id)))
    return templates.TemplateResponse(
        request=request,
        name="admin/matches.html",
        context={"league": league, "rounds": rounds, "players": players, "matches": matches, "error": None},
    )


@app.post("/admin/matches", response_class=HTMLResponse)
def admin_create_match(
    request: Request,
    round_id: int = Form(...),
    player_one_id: int = Form(...),
    player_two_id: int = Form(...),
    player_one_score: str = Form(""),
    player_two_score: str = Form(""),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    if player_one_id == player_two_id:
        return admin_matches_with_error(request, db, "A match needs two different players.")
    db.add(
        Match(
            round_id=round_id,
            player_one_id=player_one_id,
            player_two_id=player_two_id,
            player_one_score=optional_score(player_one_score),
            player_two_score=optional_score(player_two_score),
        )
    )
    db.commit()
    return RedirectResponse("/admin/matches", status_code=303)


def admin_matches_with_error(request: Request, db: Session, error: str) -> HTMLResponse:
    league = current_league(db)
    rounds = [] if league is None else list(
        db.scalars(select(Round).where(Round.league_id == league.id).order_by(Round.number))
    )
    players = [] if league is None else list(
        db.scalars(select(Player).where(Player.league_id == league.id).order_by(Player.name))
    )
    matches = list(db.scalars(select(Match).join(Round).order_by(Round.number, Match.id)))
    return templates.TemplateResponse(
        request=request,
        name="admin/matches.html",
        context={"league": league, "rounds": rounds, "players": players, "matches": matches, "error": error},
        status_code=400,
    )


@app.get("/admin/matches/{match_id}/edit", response_class=HTMLResponse)
def admin_edit_match_form(
    match_id: int,
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)
    league = match.round.league
    rounds = list(db.scalars(select(Round).where(Round.league_id == league.id).order_by(Round.number)))
    players = list(db.scalars(select(Player).where(Player.league_id == league.id).order_by(Player.name)))
    return templates.TemplateResponse(
        request=request,
        name="admin/match_edit.html",
        context={"match": match, "rounds": rounds, "players": players, "error": None},
    )


@app.post("/admin/matches/{match_id}/edit", response_class=HTMLResponse)
def admin_update_match(
    match_id: int,
    request: Request,
    round_id: int = Form(...),
    player_one_id: int = Form(...),
    player_two_id: int = Form(...),
    player_one_score: str = Form(""),
    player_two_score: str = Form(""),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)
    if player_one_id == player_two_id:
        league = match.round.league
        rounds = list(db.scalars(select(Round).where(Round.league_id == league.id).order_by(Round.number)))
        players = list(db.scalars(select(Player).where(Player.league_id == league.id).order_by(Player.name)))
        return templates.TemplateResponse(
            request=request,
            name="admin/match_edit.html",
            context={"match": match, "rounds": rounds, "players": players, "error": "A match needs two different players."},
            status_code=400,
        )
    match.round_id = round_id
    match.player_one_id = player_one_id
    match.player_two_id = player_two_id
    match.player_one_score = optional_score(player_one_score)
    match.player_two_score = optional_score(player_two_score)
    db.commit()
    return RedirectResponse("/admin/matches", status_code=303)


@app.post("/admin/matches/{match_id}/scores", response_class=HTMLResponse)
def admin_update_match_scores(
    match_id: int,
    request: Request,
    player_one_score: str = Form(""),
    player_two_score: str = Form(""),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)

    match.player_one_score = optional_score(player_one_score)
    match.player_two_score = optional_score(player_two_score)
    db.commit()
    db.refresh(match)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="admin/match_row.html",
            context={"match": match},
        )
    return RedirectResponse("/admin/matches", status_code=303)


@app.get("/admin/army-lists", response_class=HTMLResponse)
def admin_army_lists(
    request: Request,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    players = list(db.scalars(select(Player).order_by(Player.name)))
    rounds = list(db.scalars(select(Round).order_by(Round.number)))
    army_lists = list(db.scalars(select(ArmyList).order_by(ArmyList.created_at.desc(), ArmyList.id.desc())))
    return templates.TemplateResponse(
        request=request,
        name="admin/army_lists.html",
        context={"players": players, "rounds": rounds, "army_lists": army_lists, "error": None, "army_list": None},
    )


@app.post("/admin/army-lists", response_class=HTMLResponse)
def admin_import_army_list(
    request: Request,
    player_id: int = Form(...),
    round_id: int = Form(...),
    json_text: str = Form(...),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    players = list(db.scalars(select(Player).order_by(Player.name)))
    rounds = list(db.scalars(select(Round).order_by(Round.number)))
    try:
        army_list = import_army_list(db, player_id, round_id, json_text)
        error = None
    except ArmyListImportError as import_error:
        army_list = None
        error = str(import_error)
    army_lists = list(db.scalars(select(ArmyList).order_by(ArmyList.created_at.desc(), ArmyList.id.desc())))
    return templates.TemplateResponse(
        request=request,
        name="admin/army_lists.html",
        context={"players": players, "rounds": rounds, "army_lists": army_lists, "error": error, "army_list": army_list},
        status_code=400 if error else 200,
    )


