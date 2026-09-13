"""Pure input validation for CLI callers; no core imports or DNS/network access."""

import ipaddress
import re
from urllib.parse import urlsplit

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))
METADATA = ipaddress.ip_address("169.254.169.254")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
NUMERIC_HOST = re.compile(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}", re.I)


def safe_slug(team: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", team.lower()).strip("-")
    return slug[:64].rstrip("-") or "team"


def validate_repo(repo: str | None) -> str | None:
    if repo is None:
        return None
    if not isinstance(repo, str) or REPO.fullmatch(repo) is None:
        raise ValueError("Repository must have the form owner/name")
    return repo


def validate_target(url: str, allow_remote: bool = False) -> str:
    if not isinstance(url, str) or not url or any(ord(c) <= 32 for c in url) or "\\" in url:
        raise ValueError("Target must be a valid HTTP(S) URL")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("Target must be a valid HTTP(S) URL") from None
    if (parsed.scheme not in {"http", "https"} or not host or port == 0
            or parsed.query or parsed.fragment):
        raise ValueError("Target must be a valid HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Target URL must not contain embedded credentials")
    host = host.lower().rstrip(".")
    if not host or "%" in host:
        raise ValueError("Target host is invalid")
    try:
        host = host.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError:
        raise ValueError("Target host is invalid") from None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address == METADATA:
        raise ValueError("Cloud metadata targets are not allowed")
    # Noncanonical numeric hosts may resolve as decimal, hex or octal IPv4 and
    # bypass the metadata restriction. Refuse them even with remote access.
    if address is None and NUMERIC_HOST.fullmatch(host):
        raise ValueError("Numeric target hosts must use canonical IP notation")
    if address is None:
        labels = host.split(".")
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("Target host is invalid")
    local = host == "localhost" or host.endswith(".local")
    if address is not None:
        local = address in {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")}
        if isinstance(address, ipaddress.IPv4Address):
            local = local or any(address in network for network in PRIVATE_NETWORKS)
    if not allow_remote and not local:
        raise ValueError("Remote target requires explicit allow_remote=True")
    return url
