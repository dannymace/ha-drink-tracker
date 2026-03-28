"""FastAPI entrypoint."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import can_access_dashboard, is_ingress_request
from .service import DrinkTrackerService
from .settings import load_settings

settings = load_settings()
service = DrinkTrackerService(settings)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

app = FastAPI(title="Drink Tracker")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret())


@app.on_event("startup")
def startup() -> None:
    service.start()


@app.on_event("shutdown")
def shutdown() -> None:
    service.shutdown()


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(service.health())


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    if not can_access_dashboard(request, settings):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    context = service.dashboard_context(str(request.base_url).rstrip("/"))
    context["request"] = request
    context["using_ingress"] = is_ingress_request(request)
    context["dashboard_auth_enabled"] = bool(settings.dashboard.password)
    return templates.TemplateResponse(request, "dashboard.html", context)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "dashboard_auth_enabled": bool(settings.dashboard.password),
            "username": settings.dashboard.username,
        },
    )


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    if settings.dashboard.password and username == settings.dashboard.username and password == settings.dashboard.password:
        request.session["direct_dashboard_authed"] = True
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login?error=1", status_code=status.HTTP_302_FOUND)


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.post("/daily")
async def save_daily(
    request: Request,
    entry_date: str = Form(...),
    drinks: str = Form(""),
    status_value: str = Form(..., alias="status"),
    note: str = Form(""),
) -> RedirectResponse:
    _ensure_dashboard_access(request)
    parsed_date = date.fromisoformat(entry_date)
    parsed_drinks = int(drinks) if drinks.strip() else None
    service.upsert_daily_entry(parsed_date, parsed_drinks, status_value, note)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@app.post("/weekly-goals")
async def save_weekly_goals(
    request: Request,
    week_start: str = Form(...),
    weekly_drinks: int = Form(...),
    weekly_dry_days: int = Form(...),
    monday: int = Form(...),
    tuesday: int = Form(...),
    wednesday: int = Form(...),
    thursday: int = Form(...),
    friday: int = Form(...),
    saturday: int = Form(...),
    sunday: int = Form(...),
) -> RedirectResponse:
    _ensure_dashboard_access(request)
    service.upsert_weekly_goal(
        date.fromisoformat(week_start),
        {
            "weekly_drinks": weekly_drinks,
            "weekly_dry_days": weekly_dry_days,
            "monday": monday,
            "tuesday": tuesday,
            "wednesday": wednesday,
            "thursday": thursday,
            "friday": friday,
            "saturday": saturday,
            "sunday": sunday,
        },
    )
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@app.post("/admin/send-daily")
def trigger_daily_prompt(request: Request) -> RedirectResponse:
    _ensure_dashboard_access(request)
    service.send_daily_prompt()
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@app.post("/admin/send-weekly")
def trigger_weekly_summary(request: Request) -> RedirectResponse:
    _ensure_dashboard_access(request)
    service.send_weekly_summary()
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@app.post("/admin/recalculate")
def recalculate(request: Request) -> RedirectResponse:
    _ensure_dashboard_access(request)
    service.recalculate_all()
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@app.post("/webhooks/bluebubbles/{secret}")
async def bluebubbles_webhook(secret: str, payload: dict) -> JSONResponse:
    if secret != settings.ensure_webhook_secret():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown webhook")
    return JSONResponse(service.process_bluebubbles_webhook(payload))


def _ensure_dashboard_access(request: Request) -> None:
    if not can_access_dashboard(request, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
