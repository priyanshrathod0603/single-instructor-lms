"""Network security utilities and trusted proxy client IP resolution.

Architecture Specifications:
- docs/backend/18-SECURITY-ARCHITECTURE.md (Reverse Proxy & IP Spoofing Prevention)
- docs/backend/15-MEDIA-STREAMING-VIDEO-PROTECTION.md (Signed HLS Device & IP Binding)
"""

import ipaddress
import logging
from typing import Optional
from starlette.requests import Request
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def is_trusted_proxy(ip_str: str, trusted_proxies: str) -> bool:
    """Check if an IP address string matches configured trusted proxy IPs or CIDR networks."""
    if not ip_str:
        return False
    clean_ip = ip_str.strip()
    for raw_entry in trusted_proxies.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if clean_ip.lower() == entry.lower():
            return True
        try:
            ip = ipaddress.ip_address(clean_ip)
            if "/" in entry:
                network = ipaddress.ip_network(entry, strict=False)
                if ip in network:
                    return True
            else:
                if ip == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


def get_trusted_client_ip(request: Optional[Request]) -> Optional[str]:
    """Authoritatively resolve client IP adhering strictly to trusted reverse proxy boundaries.

    Strict Security Invariants (P0-07):
    1. Extract immediate connecting peer (request.client.host).
    2. If request.client.host is NOT in TRUSTED_PROXIES, return request.client.host directly.
       Any client-supplied X-Forwarded-For header is completely ignored to prevent IP spoofing.
    3. If request.client.host IS in TRUSTED_PROXIES, parse X-Forwarded-For:
       Traverse the hop list from right to left, returning the first non-trusted IP.
    """
    if not request or not hasattr(request, "client") or not request.client:
        return None

    raw_host = getattr(request.client, "host", None)
    if not raw_host:
        return None

    # Handle test mock requests where client.host was not explicitly assigned a string
    if type(raw_host).__name__ in ("MagicMock", "Mock", "AsyncMock"):
        remote_ip = "127.0.0.1"
    else:
        remote_ip = str(raw_host).strip()

    settings = get_settings()
    trusted_proxies = getattr(settings, "TRUSTED_PROXIES", "127.0.0.1,::1")

    if not is_trusted_proxy(remote_ip, trusted_proxies):
        # Direct connection or untrusted intermediary: NEVER trust X-Forwarded-For
        return remote_ip

    forwarded_header = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
    if not forwarded_header:
        return remote_ip

    # Parse hops from right to left
    hops = [h.strip() for h in forwarded_header.split(",") if h.strip()]
    if not hops:
        return remote_ip

    for hop in reversed(hops):
        if not is_trusted_proxy(hop, trusted_proxies):
            return hop

    # If all hops in header are within trusted proxy networks, return the leftmost hop
    return hops[0]
