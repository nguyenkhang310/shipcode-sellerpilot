"""Security headers and defensive network utilities for ShipCode SellerPilot.
Follows Cloudflare security-audit-skill guidelines (CLIENT-SIDE.md, WEB-PROTOCOL-AND-AUTH.md).
"""
import ipaddress
import socket
from urllib.parse import urlparse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback IPv4
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata (AWS/GCP/Azure)
    ipaddress.ip_network("::1/128"),          # Loopback IPv6
    ipaddress.ip_network("fc00::/7"),         # Unique Local IPv6
    ipaddress.ip_network("fe80::/10"),        # Link-Local IPv6
]

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces standard defensive HTTP headers to neutralize Clickjacking, MIME sniffing, and framing."""
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("X-XSS-Protection", "1; mode=block")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

def is_safe_external_url(url: str) -> bool:
    """Validates that a URL does not target loopback, private RFC1918, or metadata service IP ranges.
    Adheres to Cloudflare WEB-PROTOCOL-AND-AUTH.md SSRF hunting criteria.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        # Attempt DNS resolution to inspect resolved IP addresses
        ip_addresses = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in ip_addresses:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            for network in BLOCKED_IP_NETWORKS:
                if ip_obj in network:
                    return False
        return True
    except Exception:
        return False
