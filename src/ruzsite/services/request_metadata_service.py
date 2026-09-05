"""Proxy-aware request metadata helpers."""

from __future__ import annotations

import ipaddress

from fastapi import Request

from ruzsite.services.proxy_service import is_trusted_proxy_host
from ruzsite.settings import get_settings


def _split_header_values(header_value: str | None) -> tuple[str, ...]:
    """Split a comma-separated proxy header into normalized values."""
    if not header_value:
        return ()
    return tuple(part.strip() for part in header_value.split(",") if part.strip())


def _is_ip_or_network(value: str) -> bool:
    """Return whether the value is a valid IP address or CIDR network."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError:
            return False
    return True


def get_effective_client_ip(request: Request) -> str:
    """Resolve the best client IP, honoring trusted forwarding headers."""
    peer_ip = request.client.host if request.client else None
    forwarded_for = _split_header_values(request.headers.get("x-forwarded-for"))
    if forwarded_for and is_trusted_proxy_host(peer_ip):
        return forwarded_for[0]
    if peer_ip:
        return peer_ip
    return "unknown"


def get_uvicorn_forwarded_allow_ips() -> str:
    """Return a uvicorn-compatible forwarded-allow-ips string."""
    settings = get_settings()
    values = [value for value in settings.trusted_proxy_ips if _is_ip_or_network(value)]
    return ",".join(values)
