"""Trusted reverse proxy helpers."""

from __future__ import annotations

import ipaddress

from ruzsite.settings import get_settings


def is_trusted_proxy_host(host: str | None) -> bool:
    """Return whether a host matches a configured proxy address or network."""
    if not host:
        return False

    settings = get_settings()
    for trusted_value in settings.trusted_proxy_ips:
        if trusted_value == host:
            return True

        try:
            address = ipaddress.ip_address(host)
            network = ipaddress.ip_network(trusted_value, strict=False)
        except ValueError:
            continue

        if address in network:
            return True

    return False
