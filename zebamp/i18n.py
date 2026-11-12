"""Translations of the interface.

The text in the code is Spanish (the language Zebamp is written in).
``tr("Reproducir")`` returns it in the language chosen at start-up; anything
without a translation stays in Spanish, so a missing entry never breaks a
window.  Catalogues are plain JSON, ``data/i18n/<language>.json``:
``{"texto en español": "translated text"}``.

The language is fixed for the whole run (`setup()` is called once, before
any window module is imported): tables of labels can then be translated where
they are defined, and changing the language takes effect on the next start.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

SOURCE = "es"
LANGUAGES = {"es": "Español", "en": "English"}
CATALOG_DIR = os.path.join(os.path.dirname(__file__), "data", "i18n")

_language = SOURCE
_catalog: dict[str, str] = {}


def load_catalog(language: str) -> dict[str, str]:
    """The catalogue of `language` ({} for Spanish or when it is unreadable)."""
    if language == SOURCE:
        return {}
    try:
        with open(os.path.join(CATALOG_DIR, f"{language}.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        log.warning("no translation for %r: %s", language, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v}


def pick_language(configured: str, environ=None) -> str:
    """The language to use: the configured one, or for "auto" the system's
    (LC_ALL, LC_MESSAGES, LANG) when Zebamp speaks it, else English."""
    if configured in LANGUAGES:
        return configured
    if configured != "auto":
        return SOURCE
    environ = os.environ if environ is None else environ
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        code = (environ.get(name) or "")[:2].lower()
        if code in LANGUAGES:
            return code
        if code:
            break               # a language we do not have: English
    return "en"


def setup(configured: str = SOURCE) -> str:
    """Choose the language for this run; returns the one in use."""
    global _language, _catalog
    _language = pick_language(configured)
    _catalog = load_catalog(_language)
    return _language


def language() -> str:
    return _language


def number(value: int) -> str:
    """1234567 with the thousands separator of the language in use."""
    return f"{value:,}".replace(",", "." if _language == SOURCE else ",")


def tr(text: str) -> str:
    """`text` (Spanish) in the language in use."""
    return _catalog.get(text, text)
