"""Forgiving XML reader for Wasabi skin files.

Real-world .wal skins contain plenty of malformed XML (unescaped '&',
duplicate attributes, several root elements per included file, stray
closing tags, attributes without quotes...).  Instead of a strict parser
this module tokenises tags with a regex and builds a tree, tolerating errors
the way Winamp did.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN = re.compile(
    r"<!--.*?-->"                       # comment
    r"|<!\[CDATA\[.*?\]\]>"             # cdata
    r"|<\?.*?\?>"                       # processing instruction
    r"|<!.*?>"                          # doctype
    r"|<\s*(/?)\s*([A-Za-z_][\w:.\-]*)((?:[^<>\"']|\"[^\"]*\"|'[^']*')*?)(/?)\s*>",
    re.S,
)
_ATTR = re.compile(r"([A-Za-z_][\w:.\-]*)\s*(?:=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'>/]+))?")
_ENT = re.compile(r"&(#x[0-9a-fA-F]+|#\d+|amp|lt|gt|quot|apos);")
_ENTMAP = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def unescape(s: str) -> str:
    def rep(m):
        e = m.group(1)
        if e.startswith("#x"):
            try:
                return chr(int(e[2:], 16))
            except ValueError:
                return m.group(0)
        if e.startswith("#"):
            try:
                return chr(int(e[1:]))
            except ValueError:
                return m.group(0)
        return _ENTMAP.get(e, m.group(0))
    return _ENT.sub(rep, s) if "&" in s else s


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    src_dir: str = ""          # folder of the XML file (relative to skin root)
    parent: Node | None = field(default=None, repr=False)

    def get(self, key, default=None):
        return self.attrs.get(key.lower(), default)

    def iter(self, tag=None):
        for c in self.children:
            if tag is None or c.tag == tag:
                yield c
            yield from c.iter(tag)

    def __repr__(self):
        return f"<{self.tag} {self.attrs.get('id', '')} ({len(self.children)})>"


def parse(text: str, src_dir: str = "") -> Node:
    """Parse text into a synthetic <root> node."""
    if text.startswith("﻿"):
        text = text[1:]
    root = Node("root", src_dir=src_dir)
    stack = [root]
    for m in _TOKEN.finditer(text):
        name = m.group(2)
        if name is None:
            continue
        closing, attr_text, selfclose = m.group(1), m.group(3) or "", m.group(4)
        tag = name.lower()
        if closing:
            # pop to the matching tag if it is open, else ignore the stray tag
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].tag == tag:
                    del stack[i:]
                    break
            continue
        attrs = {}
        for am in _ATTR.finditer(attr_text):
            k = am.group(1).lower()
            v = am.group(2)
            if v is None:
                v = "1"
            elif v[:1] in "\"'":
                v = v[1:-1]
            attrs.setdefault(k, unescape(v))
        if attr_text.rstrip().endswith("/"):
            selfclose = "/"
        node = Node(tag, attrs, src_dir=src_dir, parent=stack[-1])
        stack[-1].children.append(node)
        if not selfclose:
            stack.append(node)
    return root
