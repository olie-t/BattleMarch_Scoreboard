from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.army_list_import import ArmyListImportError, import_army_list
from app.auth import require_admin
from app.database import get_db
from app.models import ArmyList, League, Match, Player, PlayerRoundScore, Round
from app.scoreboard import current_league, optional_score
from app.templating import templates


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def all_leagues(db: Session) -> list[League]:
    return list(db.scalars(select(League).order_by(League.name)))


def selected_league(db: Session, league_id: Optional[int]) -> Optional[League]:
    if league_id is not None:
        return db.get(League, league_id)
    return current_league(db)


def league_players(db: Session, league_id: int) -> list[Player]:
    return list(db.scalars(select(Player).where(Player.league_id == league_id).order_by(Player.name)))


def league_rounds(db: Session, league_id: int) -> list[Round]:
    return list(db.scalars(select(Round).where(Round.league_id == league_id).order_by(Round.number)))


def league_matches(db: Session, league_id: int) -> list[Match]:
    return list(
        db.scalars(
            select(Match)
            .join(Round)
            .where(Round.league_id == league_id)
            .order_by(Round.number, Match.id)
        )
    )


def league_admin_context(db: Session, league_id: Optional[int]) -> dict:
    league = selected_league(db, league_id)
    return {"leagues": all_leagues(db), "league": league}


def league_redirect(path: str, league: Optional[League]) -> RedirectResponse:
    if league is None:
        return RedirectResponse(path, status_code=303)
    return RedirectResponse(f"{path}?league_id={league.id}", status_code=303)


def match_admin_context(db: Session, league_id: Optional[int] = None, error: Optional[str] = None) -> dict:
    context = league_admin_context(db, league_id)
    league = context["league"]
    context.update(
        {
            "rounds": [] if league is None else league_rounds(db, league.id),
            "players": [] if league is None else league_players(db, league.id),
            "matches": [] if league is None else league_matches(db, league.id),
            "error": error,
        }
    )
    return context


def match_edit_context(db: Session, match: Match, error: Optional[str] = None) -> dict:
    league = match.round.league
    return {
        "match": match,
        "rounds": league_rounds(db, league.id),
        "players": league_players(db, league.id),
        "error": error,
    }


def army_list_admin_context(
    db: Session,
    league_id: Optional[int] = None,
    error: Optional[str] = None,
    army_list: Optional[ArmyList] = None,
) -> dict:
    context = league_admin_context(db, league_id)
    league = context["league"]
    context.update(
        {
            "players": [] if league is None else league_players(db, league.id),
            "rounds": [] if league is None else league_rounds(db, league.id),
            "army_lists": [] if league is None else list(
                db.scalars(
                    select(ArmyList)
                    .join(Round)
                    .where(Round.league_id == league.id)
                    .order_by(ArmyList.created_at.desc(), ArmyList.id.desc())
                )
            ),
            "error": error,
            "army_list": army_list,
        }
    )
    return context


def match_players_belong_to_round_league(db: Session, round_id: int, player_one_id: int, player_two_id: int) -> bool:
    round_item = db.get(Round, round_id)
    player_one = db.get(Player, player_one_id)
    player_two = db.get(Player, player_two_id)
    if round_item is None or player_one is None or player_two is None:
        return False
    return player_one.league_id == round_item.league_id and player_two.league_id == round_item.league_id


def delete_league_data(db: Session, league: League) -> None:
    round_ids = [round_item.id for round_item in league.rounds]
    player_ids = [player.id for player in league.players]

    if round_ids:
        db.execute(delete(Match).where(Match.round_id.in_(round_ids)))
        db.execute(delete(ArmyList).where(ArmyList.round_id.in_(round_ids)))
        db.execute(delete(PlayerRoundScore).where(PlayerRoundScore.round_id.in_(round_ids)))
        db.execute(delete(Round).where(Round.id.in_(round_ids)))

    if player_ids:
        db.execute(delete(ArmyList).where(ArmyList.player_id.in_(player_ids)))
        db.execute(delete(PlayerRoundScore).where(PlayerRoundScore.player_id.in_(player_ids)))
        db.execute(delete(Player).where(Player.id.in_(player_ids)))

    db.delete(league)


def delete_round_data(db: Session, round_item: Round) -> None:
    db.execute(delete(Match).where(Match.round_id == round_item.id))
    db.execute(delete(ArmyList).where(ArmyList.round_id == round_item.id))
    db.execute(delete(PlayerRoundScore).where(PlayerRoundScore.round_id == round_item.id))
    db.delete(round_item)


def delete_player_data(db: Session, player: Player) -> None:
    db.execute(delete(Match).where(or_(Match.player_one_id == player.id, Match.player_two_id == player.id)))
    db.execute(delete(ArmyList).where(ArmyList.player_id == player.id))
    db.execute(delete(PlayerRoundScore).where(PlayerRoundScore.player_id == player.id))
    db.delete(player)


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
    league = League(name=name.strip())
    db.add(league)
    db.commit()
    db.refresh(league)
    return league_redirect("/admin/players", league)


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


@router.post("/leagues/{league_id}/delete")
def admin_delete_league(league_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    league = db.get(League, league_id)
    if league is not None:
        delete_league_data(db, league)
        db.commit()
    return RedirectResponse("/admin/leagues", status_code=303)


@router.get("/players", response_class=HTMLResponse)
def admin_players(
    request: Request,
    league_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    context = league_admin_context(db, league_id)
    league = context["league"]
    context["players"] = [] if league is None else league_players(db, league.id)
    return templates.TemplateResponse(request=request, name="admin/players.html", context=context)


@router.post("/players")
def admin_create_player(
    name: str = Form(...),
    league_id: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    league = selected_league(db, league_id)
    if league is not None:
        db.add(Player(name=name.strip(), league_id=league.id))
        db.commit()
    return league_redirect("/admin/players", league)


@router.get("/players/{player_id}/edit", response_class=HTMLResponse)
def admin_edit_player_form(
    player_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    player = db.get(Player, player_id)
    if player is None:
        return HTMLResponse("Player not found", status_code=404)
    return templates.TemplateResponse(request=request, name="admin/player_edit.html", context={"player": player})


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
        return league_redirect("/admin/players", player.league)
    return RedirectResponse("/admin/players", status_code=303)


@router.post("/players/{player_id}/delete")
def admin_delete_player(player_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    player = db.get(Player, player_id)
    league = None if player is None else player.league
    if player is not None:
        delete_player_data(db, player)
        db.commit()
    return league_redirect("/admin/players", league)


@router.get("/rounds", response_class=HTMLResponse)
def admin_rounds(
    request: Request,
    league_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    context = league_admin_context(db, league_id)
    league = context["league"]
    context["rounds"] = [] if league is None else league_rounds(db, league.id)
    return templates.TemplateResponse(request=request, name="admin/rounds.html", context=context)


@router.post("/rounds")
def admin_create_round(
    number: int = Form(...),
    points_limit: int = Form(...),
    league_id: int = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    league = selected_league(db, league_id)
    if league is not None:
        db.add(Round(number=number, points_limit=points_limit, league_id=league.id))
        db.commit()
    return league_redirect("/admin/rounds", league)


@router.get("/rounds/{round_id}/edit", response_class=HTMLResponse)
def admin_edit_round_form(
    round_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    round_item = db.get(Round, round_id)
    if round_item is None:
        return HTMLResponse("Round not found", status_code=404)
    return templates.TemplateResponse(request=request, name="admin/round_edit.html", context={"round_item": round_item})


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
        return league_redirect("/admin/rounds", round_item.league)
    return RedirectResponse("/admin/rounds", status_code=303)


@router.post("/rounds/{round_id}/delete")
def admin_delete_round(round_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    round_item = db.get(Round, round_id)
    league = None if round_item is None else round_item.league
    if round_item is not None:
        delete_round_data(db, round_item)
        db.commit()
    return league_redirect("/admin/rounds", league)


@router.get("/rounds/{round_id}/scores", response_class=HTMLResponse)
def admin_round_scores(
    round_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    round_item = db.get(Round, round_id)
    if round_item is None:
        return HTMLResponse("Round not found", status_code=404)
    players = league_players(db, round_item.league_id)
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
    players = league_players(db, round_item.league_id)
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
def admin_matches(
    request: Request,
    league_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin/matches.html",
        context=match_admin_context(db, league_id=league_id),
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
    round_item = db.get(Round, round_id)
    league_id = None if round_item is None else round_item.league_id
    if player_one_id == player_two_id:
        return admin_matches_with_error(request, db, league_id, "A match needs two different players.")
    if not match_players_belong_to_round_league(db, round_id, player_one_id, player_two_id):
        return admin_matches_with_error(request, db, league_id, "Both players must belong to the selected round's league.")
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
    return league_redirect("/admin/matches", round_item.league if round_item else None)


def admin_matches_with_error(
    request: Request,
    db: Session,
    league_id: Optional[int],
    error: str,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin/matches.html",
        context=match_admin_context(db, league_id=league_id, error=error),
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
    return templates.TemplateResponse(request=request, name="admin/match_edit.html", context=match_edit_context(db, match))


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
        return templates.TemplateResponse(
            request=request,
            name="admin/match_edit.html",
            context=match_edit_context(db, match, error="A match needs two different players."),
            status_code=400,
        )
    if not match_players_belong_to_round_league(db, round_id, player_one_id, player_two_id):
        return templates.TemplateResponse(
            request=request,
            name="admin/match_edit.html",
            context=match_edit_context(db, match, error="Both players must belong to the selected round's league."),
            status_code=400,
        )
    match.round_id = round_id
    match.player_one_id = player_one_id
    match.player_two_id = player_two_id
    match.player_one_score = optional_score(player_one_score)
    match.player_two_score = optional_score(player_two_score)
    db.commit()
    return league_redirect("/admin/matches", match.round.league)


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

    return match_row_or_redirect(request, match)


@router.post("/matches/{match_id}/reset", response_class=HTMLResponse)
def admin_reset_match_scores(
    match_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    match = db.get(Match, match_id)
    if match is None:
        return HTMLResponse("Match not found", status_code=404)

    match.player_one_score = None
    match.player_two_score = None
    db.commit()
    db.refresh(match)

    return match_row_or_redirect(request, match)


@router.post("/matches/{match_id}/delete")
def admin_delete_match(match_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    match = db.get(Match, match_id)
    league = None if match is None else match.round.league
    if match is not None:
        db.delete(match)
        db.commit()
    return league_redirect("/admin/matches", league)


def match_row_or_redirect(request: Request, match: Match) -> Response:

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request=request, name="admin/match_row.html", context={"match": match})
    return league_redirect("/admin/matches", match.round.league)


@router.get("/army-lists", response_class=HTMLResponse)
def admin_army_lists(
    request: Request,
    league_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin/army_lists.html",
        context=army_list_admin_context(db, league_id=league_id),
    )


@router.post("/army-lists", response_class=HTMLResponse)
def admin_import_army_list(
    request: Request,
    player_id: int = Form(...),
    round_id: int = Form(...),
    json_text: str = Form(...),
    total_points: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    round_item = db.get(Round, round_id)
    league_id = None if round_item is None else round_item.league_id
    try:
        try:
            entered_points = int(total_points) if total_points.strip() else None
        except ValueError:
            raise ArmyListImportError("Total army points must be a non-negative whole number.")
        if entered_points is not None and entered_points < 0:
            raise ArmyListImportError("Total army points must be a non-negative whole number.")
        army_list = import_army_list(db, player_id, round_id, json_text, total_points=entered_points)
        error = None
        league_id = army_list.round.league_id
    except ArmyListImportError as import_error:
        army_list = None
        error = str(import_error)
    context = army_list_admin_context(db, league_id=league_id, error=error, army_list=army_list)
    if error:
        context.update(import_text=json_text, total_points=total_points, selected_player_id=player_id, selected_round_id=round_id)
    return templates.TemplateResponse(
        request=request,
        name="admin/army_lists.html",
        context=context,
        status_code=400 if error else 200,
    )


@router.post("/army-lists/{army_list_id}/delete")
def admin_delete_army_list(army_list_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    army_list = db.get(ArmyList, army_list_id)
    league = None if army_list is None else army_list.round.league
    if army_list is not None:
        db.delete(army_list)
        db.commit()
    return league_redirect("/admin/army-lists", league)
