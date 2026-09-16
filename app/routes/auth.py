from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import SESSION_KEY, authenticate_admin, require_admin
from app.templating import templates


router = APIRouter(prefix="/admin")


@router.get("/login", response_class=HTMLResponse)
def admin_login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html",
        context={"error": None},
    )


@router.post("/login", response_class=HTMLResponse)
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


@router.post("/logout")
def admin_logout(request: Request, _: None = Depends(require_admin)) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
