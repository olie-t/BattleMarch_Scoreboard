from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.army_list_import import ArmyListImportError, import_army_list
from app.auth import require_admin
from app.database import get_db
from app.models import ArmyList, League, Match, Player, PlayerRoundScore, Round
from app.scoreboard import current_league, optional_score
from app.templating import templates


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("", response_class=HTMLResponse)
def admin_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="admin/home.html")


@router.get("/leagues", response_class=HTMLResponse)
def admin_leagues(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    leagues = list(db.scalars(select(League).order_by(League.id.desc())))
    return templates.TemplateResponse(
        request=request,
        name="admin/leagues.html",
        context={"leagues": leagues},
    )


@router.post("/leagues")
def admin_create_league(name: str = Form(...), db: Session = Depends(get_db)) -> RedirectResponse:
    db.add(League(name=name.strip()))
    db.commit()
    return RedirectResponse("/admin/leagues", status_code=303)


@router.get("/leagues/{league_id}/edit", response_class=HTMLResponse)
def admin_edit_league_form(
    league_id: int,
    request: Request,
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


@router.post("/leagues/{league_id}/edit")
def admin_update_league(
    league_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    league = db.get(League, league_id)
    if league is not None:
        league.name = name.strip()
        db.commit()
    return RedirectResponse("/admin/leagues", status_code=303)


@router.get("/players", response_class=HTMLResponse)
def admin_players(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = current_league(db)
    players = [] if league is None else list(
        db.scalars(select(Player).where(Player.league_id == league.id).order_by(Player.name))
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/players.html",
        context={"league": league, "players": players},
    )


@router.post("/players")
def admin_create_player(name: str = Form(...), db: Session = Depends(get_db)) -> RedirectResponse:
    league = current_league(db)
    if league is not None:
        db.add(Player(name=name.strip(), league_id=league.id))
        db.commit()
    return RedirectResponse("/admin/players", status_code=303)


@router.get("/players/{player_id}/edit", response_class=HTMLResponse)
def admin_edit_player_form(
    player_id: int,
    request: Request,
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


@router.post("/players/{player_id}/edit")
def admin_update_player(
    player_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    player = db.get(Player, player_id)
    if player is not None:
        player.name = name.strip()
        db.commit()
    return RedirectResponse("/admin/players", status_code=303)


@router.get("/rounds", response_class=HTMLResponse)
def admin_rounds(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    league = current_league(db)
    rounds = [] if league is None else list(
        db.scalars(select(Round).where(Round.league_id == league.id).order_by(Round.number))
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/rounds.html",
        context={"league": league, "rounds": rounds},
    )


@router.post("/rounds")
def admin_create_round(
    number: int = Form(...),
    points_limit: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    league = current_league(db)
    if league is not None:
        db.add(Round(number=number, points_limit=points_limit, league_id=league.id))
        db.commit()
    return RedirectResponse("/admin/rounds", status_code=303)


@router.get("/rounds/{round_id}/edit", response_class=HTMLResponse)
def admin_edit_round_form(
    round_id: int,
    request: Request,
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


@router.post("/rounds/{round_id}/edit")
def admin_update_round(
    round_id: int,
    number: int = Form(...),
    points_limit: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    round_item = db.get(Round, round_id)
    if round_item is not None:
        round_item.number = number
        round_item.points_limit = points_limit
        db.commit()
    return RedirectResponse("/admin/rounds", status_code=303)


@router.get("/rounds/{round_id}/scores", response_class=HTMLResponse)
def admin_round_scores(
    round_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    round_item = db.get(Round, round_id)
    if round_item is None:
        return HTMLResponse("Round not found", status_code=404)
    players = list(db.scalars(select(Player).where(Player.league_id == round_item.league_id).order_by(Player.name)))
    scores = list(db.scalars(select(PlayerRoundScore).where(PlayerRoundScore.round_id == round_id)))
    scores_by_player_id = {score.player_id: score for score in scores}
    return templates.TemplateResponse(
        request=request,
        name="admin/round_scores.html",
        context={"round_item": round_item, "players": players, "scores_by_player_id": scores_by_player_id},
    )


@router.post("/rounds/{round_id}/scores")
async def admin_update_round_scores(
    round_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    round_item = db.get(Round, round_id)
    if round_item is None:
        return RedirectResponse("/admin/rounds", status_code=303)

    form = await request.form()
    players = list(db.scalars(select(Player).where(Player.league_id == round_item.league_id).order_by(Player.name)))
    scores = list(db.scalars(select(PlayerRoundScore).where(PlayerRoundScore.round_id == round_id)))
    scores_by_player_id = {score.player_id: score for score in scores}

    for player in players:
        score = scores_by_player_id.get(player.id)
        if score is None:
            score = PlayerRoundScore(player_id=player.id, round_id=round_id)
            db.add(score)
        score.is_bye = f"bye_{player.id}" in form
        score.painting_progress = f"painting_progress_{player.id}" in form
        score.fully_painted = f"fully_painted_{player.id}" in form

    db.commit()
    return RedirectResponse(f"/admin/rounds/{round_id}/scores", status_code=303)


@router.get("/matches", response_class=HTMLResponse)
def admin_matches(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
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


@router.post("/matches", response_class=HTMLResponse)
def admin_create_match(
    request: Request,
    round_id: int = Form(...),
    player_one_id: int = Form(...),
    player_two_id: int = Form(...),
    player_one_score: str = Form(""),
    player_two_score: str = Form(""),
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


@router.get("/matches/{match_id}/edit", response_class=HTMLResponse)
def admin_edit_match_form(
    match_id: int,
    request: Request,
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


@router.post("/matches/{match_id}/edit", response_class=HTMLResponse)
def admin_update_match(
    match_id: int,
    request: Request,
    round_id: int = Form(...),
    player_one_id: int = Form(...),
    player_two_id: int = Form(...),
    player_one_score: str = Form(""),
    player_two_score: str = Form(""),
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


@router.post("/matches/{match_id}/scores", response_class=HTMLResponse)
def admin_update_match_scores(
    match_id: int,
    request: Request,
    player_one_score: str = Form(""),
    player_two_score: str = Form(""),
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


@router.get("/army-lists", response_class=HTMLResponse)
def admin_army_lists(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    players = list(db.scalars(select(Player).order_by(Player.name)))
    rounds = list(db.scalars(select(Round).order_by(Round.number)))
    army_lists = list(db.scalars(select(ArmyList).order_by(ArmyList.created_at.desc(), ArmyList.id.desc())))
    return templates.TemplateResponse(
        request=request,
        name="admin/army_lists.html",
        context={"players": players, "rounds": rounds, "army_lists": army_lists, "error": None, "army_list": None},
    )


@router.post("/army-lists", response_class=HTMLResponse)
def admin_import_army_list(
    request: Request,
    player_id: int = Form(...),
    round_id: int = Form(...),
    json_text: str = Form(...),
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
