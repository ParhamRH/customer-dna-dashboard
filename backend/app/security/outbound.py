"""Guard for server-side requests to customer-supplied URLs (webhooks, AI provider base URLs).

Without it, a workspace administrator could point a webhook at the platform's own internal
network (database admin ports, cloud metadata endpoints, other containers) and use the worker
as a proxy. Private, loopback, link-local and other non-public addresses are refused unless the
host is explicitly allow-listed (e.g. ``n8n`` inside Docker Compose) or private targets are
allowed for development. The check runs when the URL is saved *and* right before each request,
so a DNS name that later resolves somewhere private is caught too.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.config import get_settings


class OutboundUrlError(ValueError):
    pass


def _allow_private() -> bool:
    s = get_settings()
    return s.outbound_allow_private if s.outbound_allow_private is not None else not s.is_production


def check_outbound_url(url: str) -> str:
    """Return the URL if the platform may call it; raise OutboundUrlError otherwise."""
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise OutboundUrlError("URL must be an absolute http(s) URL")
    if parts.username or parts.password:
        raise OutboundUrlError("URL must not contain credentials; use the secret field instead")
    host = parts.hostname.lower().rstrip(".")
    s = get_settings()
    if host in {h.lower() for h in s.outbound_allowed_hosts} or _allow_private():
        return url
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise OutboundUrlError(f"host {host!r} cannot be resolved") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise OutboundUrlError(f"host {host!r} resolves to a non-public address ({ip}); "
                                   "allow it with BDNA_OUTBOUND_ALLOWED_HOSTS if this is intended")
    return url
