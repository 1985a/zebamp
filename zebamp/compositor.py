"""What Zebamp needs from the Wayland compositor and Wayland does not offer.

A Wayland application cannot ask where its windows are, move them or take the
focus.  The free-floating skin windows need exactly that for their canvas
(see docs/ARQUITECTURA.md), so each compositor is asked through its own
command-line tool:

* **sway**      ``swaymsg``  (the one Zebamp is developed and tested on)
* **Hyprland**  ``hyprctl``
* anything else: Qt's screen geometry, and the compositor places the canvas.

The parsers are pure functions over the tools' JSON so they can be tested
without the compositor running.
"""
from __future__ import annotations

import json
import os
import subprocess

from PySide6.QtCore import QRect

TOOL_TIMEOUT = 2        # seconds; these run on the GUI thread, on user actions only


def _run_json(command: list[str], default):
    """Parsed JSON printed by `command`, or `default` when it fails."""
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=TOOL_TIMEOUT).stdout
        return json.loads(out or "null") or default
    except (OSError, ValueError, subprocess.SubprocessError):
        return default


def _run(command: list[str]):
    try:
        subprocess.run(command, capture_output=True, timeout=TOOL_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        pass


# ----------------------------------------------------------------- sway
def sway_workspace_rects(workspaces) -> list[QRect]:
    """Visible workspace of each monitor (bars excluded), focused one first."""
    try:
        visible = [w for w in workspaces if w.get("visible")]
        visible.sort(key=lambda w: 0 if w.get("focused") else 1)
        return [QRect(w["rect"]["x"], w["rect"]["y"], w["rect"]["width"], w["rect"]["height"])
                for w in visible]
    except (AttributeError, KeyError, TypeError):
        return []


def sway_find_window(tree, pid: int, title: str) -> dict | None:
    """The floating container of our window in sway's layout tree."""
    todo = [tree] if isinstance(tree, dict) else []
    while todo:
        node = todo.pop()
        if node.get("pid") == pid and node.get("name") == title and node.get("type") == "floating_con":
            return node
        todo += node.get("nodes", []) + node.get("floating_nodes", [])
    return None


class Sway:
    name = "sway"

    def workspace_rects(self) -> list[QRect]:
        return sway_workspace_rects(_run_json(["swaymsg", "-t", "get_workspaces"], []))

    def move_window(self, title: str, x: int, y: int):
        node = sway_find_window(_run_json(["swaymsg", "-t", "get_tree"], {}), os.getpid(), title)
        if node is not None and (node["rect"]["x"], node["rect"]["y"]) != (x, y):
            _run(["swaymsg", f"[con_id={node['id']}] move absolute position {x} {y}"])

    def focus_command(self, title_regex: str) -> list[str]:
        return ["swaymsg", f'[pid={os.getpid()} title="^{title_regex}$"] focus']


# ------------------------------------------------------------- Hyprland
def _four(values) -> list:
    """`values` as exactly four numbers (missing ones are 0)."""
    return [*list(values or []), 0, 0, 0, 0][:4]


def hypr_monitor_rects(monitors) -> list[QRect]:
    """Usable area of each monitor in layout coordinates, focused one first.

    `width`/`height` are physical pixels: divided by the scale (and swapped
    on a rotated monitor) they give the layout size; `reserved` is the space
    bars take on the left, top, right and bottom."""
    rects = []
    try:
        for m in sorted(monitors, key=lambda m: 0 if m.get("focused") else 1):
            scale = float(m.get("scale") or 1) or 1.0
            w, h = m["width"] / scale, m["height"] / scale
            if int(m.get("transform") or 0) % 2:
                w, h = h, w
            left, top, right, bottom = _four(m.get("reserved"))
            rects.append(QRect(int(m["x"] + left), int(m["y"] + top),
                               int(w - left - right), int(h - top - bottom)))
    except (AttributeError, KeyError, TypeError, ValueError):
        return []
    return rects


def hypr_find_client(clients, pid: int, title: str) -> dict | None:
    try:
        return next((c for c in clients if c.get("pid") == pid and c.get("title") == title), None)
    except (AttributeError, TypeError):
        return None


class Hyprland:
    name = "hyprland"

    def workspace_rects(self) -> list[QRect]:
        return hypr_monitor_rects(_run_json(["hyprctl", "-j", "monitors"], []))

    def _client(self, title: str) -> dict | None:
        return hypr_find_client(_run_json(["hyprctl", "-j", "clients"], []), os.getpid(), title)

    def move_window(self, title: str, x: int, y: int):
        client = self._client(title)
        if client is None or not client.get("address"):
            return
        window = f"address:{client['address']}"
        if not client.get("floating"):
            _run(["hyprctl", "dispatch", "setfloating", window])
        if list(client.get("at") or []) != [x, y]:
            _run(["hyprctl", "dispatch", "movewindowpixel", f"exact {x} {y},{window}"])

    def focus_command(self, title_regex: str) -> list[str]:
        return ["hyprctl", "dispatch", "focuswindow", f"title:^{title_regex}$"]


# -------------------------------------------------------------- generic
class Generic:
    """No compositor tool: Qt's geometry, and the canvas stays where the
    compositor puts it (usually the top-left of the monitor it fills)."""
    name = "generic"

    def workspace_rects(self) -> list[QRect]:
        return []

    def move_window(self, title: str, x: int, y: int):
        pass

    def focus_command(self, title_regex: str) -> list[str]:
        return []


def detect(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("SWAYSOCK"):
        return Sway()
    if environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return Hyprland()
    return Generic()


_current = None


def current():
    """The compositor Zebamp is running on (detected once)."""
    global _current
    if _current is None:
        _current = detect()
    return _current
