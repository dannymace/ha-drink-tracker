"""Dashboard authentication helpers."""

from __future__ import annotations

from fastapi import Request

from .settings import Settings


def is_ingress_request(request: Request) -> bool:
    return bool(
        request.headers.get("X-Ingress-Path")
        or request.headers.get("X-HA-Ingress")
        or request.headers.get("X-Hassio-Key")
    )


def can_access_dashboard(request: Request, settings: Settings) -> bool:
    if is_ingress_request(request):
        return True
    if not settings.dashboard.password:
        return False
    return bool(request.session.get("direct_dashboard_authed"))

