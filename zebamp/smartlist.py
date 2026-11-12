"""Smart lists: playlists defined by rules instead of by hand.

«Rock, four stars or more, not heard in a month.»  A smart list is plain
data kept in the settings::

    {"name": "…", "match": "all" | "any", "rules": [{"field", "op", "value"}],
     "order": "…", "limit": 0}

and is evaluated against the in-memory library index plus the play
statistics, so it never asks MPD anything.  Everything here is pure: the
editor lives in `ui/smartlist_dialog.py`.
"""
from __future__ import annotations

import random
import time

from .libindex import fold
from .i18n import tr

# index row columns (see libindex.FIELDS)
FILE, TITLE, ARTIST, ALBUM, ALBUMARTIST, GENRE, DURATION, DATE = range(8)
DAY = 86400

TEXT_FIELDS = {"title": (tr("Título"), TITLE), "artist": (tr("Artista"), ARTIST), "album": (tr("Álbum"), ALBUM),
               "albumartist": (tr("Artista del álbum"), ALBUMARTIST), "genre": (tr("Género"), GENRE),
               "file": (tr("Carpeta o archivo"), FILE)}
NUMBER_FIELDS = {"rating": tr("Valoración (estrellas)"), "plays": tr("Veces escuchada"), "year": tr("Año"),
                 "minutes": tr("Duración (minutos)"), "days_since_played": tr("Días sin escucharla")}
FIELDS = {**{k: v[0] for k, v in TEXT_FIELDS.items()}, **NUMBER_FIELDS}

TEXT_OPS = {"contains": tr("contiene"), "not_contains": tr("no contiene"), "is": tr("es"), "is_not": tr("no es"),
            "starts": tr("empieza por")}
NUMBER_OPS = {"ge": tr("al menos"), "le": tr("como mucho"), "eq": tr("exactamente")}

ORDERS = {"artist": tr("Artista y álbum"), "random": tr("Al azar"), "most_played": tr("Más escuchadas primero"),
          "best_rated": tr("Mejor valoradas primero"), "longest_unheard": tr("Las que llevan más sin sonar primero"),
          "recently_played": tr("Escuchadas hace poco primero")}

NEVER_PLAYED_DAYS = 10 ** 6          # "days since played" of a song never played


def ops_for(field: str) -> dict:
    return TEXT_OPS if field in TEXT_FIELDS else NUMBER_OPS


# ------------------------------------------------------------ validation
def clean_rule(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    field, op = raw.get("field"), raw.get("op")
    if field not in FIELDS or op not in ops_for(field):
        return None
    if field in TEXT_FIELDS:
        value = str(raw.get("value") or "").strip()
        return {"field": field, "op": op, "value": value} if value else None
    try:
        return {"field": field, "op": op, "value": float(raw.get("value"))}
    except (TypeError, ValueError):
        return None


def clean_smart_list(raw) -> dict | None:
    """A usable smart list from a settings value that may be hand-edited."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    rules = raw.get("rules")
    rules = [r for r in map(clean_rule, rules if isinstance(rules, list) else []) if r]
    if not name or not rules:
        return None
    return {"name": name, "match": "any" if raw.get("match") == "any" else "all", "rules": rules,
            "order": raw.get("order") if raw.get("order") in ORDERS else "artist",
            "limit": _limit(raw.get("limit"))}


def _limit(value) -> int:
    """Most songs a list may hold; 0 (no limit) for anything that is not a count."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def clean_smart_lists(raw) -> list[dict]:
    lists, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        smart = clean_smart_list(item)
        if smart and smart["name"].lower() not in seen:
            seen.add(smart["name"].lower())
            lists.append(smart)
    return lists


def with_smart_list(lists: list[dict], smart: dict, replacing: str = "") -> list[dict]:
    """A new list of smart lists with `smart` added, or in place of the one
    named `replacing` (editing) or sharing its name."""
    gone = {smart["name"].lower(), replacing.lower()} - {""}
    out, placed = [], False
    for item in lists:
        if item["name"].lower() in gone:
            if not placed:
                out.append(smart)
                placed = True
        else:
            out.append(item)
    if not placed:
        out.append(smart)
    return out


def without_smart_list(lists: list[dict], name: str) -> list[dict]:
    return [x for x in lists if x["name"].lower() != name.lower()]


# ------------------------------------------------------------ evaluation
def _year(row) -> int:
    date = str(row[DATE]) if len(row) > DATE else ""
    return int(date[:4]) if date[:4].isdigit() else 0


def _minutes(row) -> float:
    try:
        return float(row[DURATION] or 0) / 60
    except (TypeError, ValueError):
        return 0.0


class _Stats:
    """Read-only view of the play statistics for the evaluator."""

    def __init__(self, ratings: dict, counts: dict, last: dict, now: float):
        self.ratings, self.counts, self.last, self.now = ratings, counts, last, now

    def stars(self, uri: str) -> int:
        return min(5, (self.ratings.get(uri, 0) + 1) // 2)       # stored 0..10

    def days_since_played(self, uri: str) -> float:
        played = self.last.get(uri)
        return (self.now - played) / DAY if played else NEVER_PLAYED_DAYS


def _number_getter(field: str, stats: _Stats):
    return {"rating": lambda row: stats.stars(row[FILE]),
            "plays": lambda row: stats.counts.get(row[FILE], 0),
            "year": _year,
            "minutes": _minutes,
            "days_since_played": lambda row: stats.days_since_played(row[FILE])}[field]


def _test(rule: dict, stats: _Stats):
    """rule -> function(row) -> bool, with the comparison prepared once."""
    field, op, value = rule["field"], rule["op"], rule["value"]
    if field in TEXT_FIELDS:
        column, needle = TEXT_FIELDS[field][1], fold(value)
        checks = {"contains": lambda text: needle in text, "not_contains": lambda text: needle not in text,
                  "is": lambda text: text == needle, "is_not": lambda text: text != needle,
                  "starts": lambda text: text.startswith(needle)}
        check = checks[op]
        return lambda row: check(fold(str(row[column] or "")))
    get = _number_getter(field, stats)
    if op == "ge":
        return lambda row: get(row) >= value
    if op == "le":
        return lambda row: get(row) <= value
    return lambda row: get(row) == value


def _sorted(rows: list, order: str, stats: _Stats) -> list:
    if order == "random":
        rows = list(rows)
        random.shuffle(rows)
        return rows
    keys = {"artist": lambda r: (fold(str(r[ALBUMARTIST] or r[ARTIST])), fold(str(r[ALBUM])), r[FILE]),
            "most_played": lambda r: -stats.counts.get(r[FILE], 0),
            "best_rated": lambda r: -stats.ratings.get(r[FILE], 0),
            "longest_unheard": lambda r: stats.last.get(r[FILE], 0),
            "recently_played": lambda r: -stats.last.get(r[FILE], 0)}
    return sorted(rows, key=keys[order])


def evaluate(smart: dict, rows: list, ratings: dict, counts: dict, last: dict,
             now: float | None = None) -> list:
    """The index rows a smart list selects, ordered and cut to its limit."""
    stats = _Stats(ratings, counts, last, time.time() if now is None else now)
    tests = [_test(rule, stats) for rule in smart["rules"]]
    combine = any if smart["match"] == "any" else all
    chosen = [row for row in rows if combine(test(row) for test in tests)]
    chosen = _sorted(chosen, smart["order"], stats)
    return chosen[:smart["limit"]] if smart["limit"] else chosen


def describe(smart: dict) -> str:
    """One line a person can read: «Género contiene rock y Valoración al menos 4»."""
    def rule_text(rule):
        value = rule["value"]
        if isinstance(value, float):
            value = f"{value:g}"
        return f"{FIELDS[rule['field']]} {ops_for(rule['field'])[rule['op']]} {value}"
    return (tr(" o ") if smart["match"] == "any" else tr(" y ")).join(rule_text(r) for r in smart["rules"])
