"""Server profiles: named MPD connections to switch between from the menu.

Pure helpers over the ``mpd_profiles`` list kept in the settings.  A profile
is ``{"name", "host", "port", "password"}``; the empty name stands for the
automatic local connection (MPD_HOST, mpd.conf, the usual sockets).
"""
from __future__ import annotations

from .mpdconn import MpdAddress, autodetect_address

DEFAULT_PORT = 6600


def clean_profiles(raw) -> list[dict]:
    """The usable profiles of a settings value that may be hand-edited:
    anything without a name and a host is dropped, names are unique."""
    profiles, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        host = str(item.get("host") or "").strip()
        if not name or not host or name.lower() in seen:
            continue
        seen.add(name.lower())
        profiles.append({"name": name, "host": host, "port": _port(item.get("port")),
                         "password": str(item.get("password") or "")})
    return profiles


def _port(value) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def find_profile(profiles: list[dict], name: str) -> dict | None:
    wanted = name.strip().lower()
    return next((p for p in profiles if p["name"].lower() == wanted), None)


def with_profile(profiles: list[dict], profile: dict) -> list[dict]:
    """A new list with `profile` added, or replacing the one with its name."""
    others = [p for p in profiles if p["name"].lower() != profile["name"].strip().lower()]
    return clean_profiles([*others, profile])


def without_profile(profiles: list[dict], name: str) -> list[dict]:
    return [p for p in profiles if p["name"].lower() != name.strip().lower()]


def profile_address(profile: dict | None) -> MpdAddress:
    """Where a profile points; None is the automatic local connection."""
    if profile is None:
        return autodetect_address()
    return autodetect_address(profile["host"], profile["port"], profile["password"])
