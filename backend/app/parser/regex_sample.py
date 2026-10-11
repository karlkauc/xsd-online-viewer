"""Produce strings that match a (simple) XSD regular expression.

Best effort only: literals, escapes, character classes, the common
``\\p{…}`` categories and blocks, groups, alternation and quantifiers are
understood; anything else (a block this module has no range for, nested
negated subtraction) makes the functions give up, so the caller can fall back
to a type placeholder.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

_ESCAPES = {
    "d": "0",
    "D": "a",
    "w": "a",
    "W": " ",
    "s": " ",
    "S": "a",
    "i": "a",
    "I": "0",  # not a name-start character
    "c": "a",
    "C": " ",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}
# The multi-character escapes that stand for a whole range of characters, so a
# sample can vary them the way it varies ``[0-9]``.
_ESCAPE_MEMBERS = {
    "d": "0123456789",
    "w": "abcdefghijklmnopqrstuvwxyz",
    "S": "abcdefghijklmnopqrstuvwxyz",
    "i": "abcdefghijklmnopqrstuvwxyz",
    "c": "abcdefghijklmnopqrstuvwxyz",
}

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"
# ASCII stand-ins for the Unicode categories and blocks schemas actually use.
_CATEGORIES = {
    "L": _UPPER + _LOWER,
    "Lu": _UPPER,
    "Ll": _LOWER,
    "Lt": _UPPER,
    "N": _DIGITS,
    "Nd": _DIGITS,
    "P": "-.,",
    "Pd": "-",
    "Pc": "_",
    "Po": ".,",
    "Ps": "(",
    "Pe": ")",
    "Z": " ",
    "Zs": " ",
    "S": "+",
    "Sm": "+",
    "Sc": "$",
    "IsBasicLatin": _UPPER + _LOWER + _DIGITS,
}
# Something outside the category, for ``\P{…}``.
_OUTSIDE = {
    "L": "0",
    "Lu": "a",
    "Ll": "A",
    "Lt": "a",
    "N": "a",
    "Nd": "a",
    "P": "a",
    "Pd": "a",
    "Pc": "a",
    "Po": "a",
    "Ps": "a",
    "Pe": "a",
    "Z": "a",
    "Zs": "a",
    "S": "a",
    "Sm": "a",
    "Sc": "a",
}


class _UnsupportedError(Exception):
    pass


# Unicode blocks beyond Basic Latin that turn up in ``\\p{Is…}``; Python has no
# block table of its own.
_BLOCKS = {
    "IsLatin-1Supplement": (0x00A0, 0x00FF),
    "IsLatinExtended-A": (0x0100, 0x017F),
    "IsLatinExtended-B": (0x0180, 0x024F),
    "IsIPAExtensions": (0x0250, 0x02AF),
    "IsGreek": (0x0370, 0x03FF),
    "IsCyrillic": (0x0400, 0x04FF),
    "IsArmenian": (0x0530, 0x058F),
    "IsHebrew": (0x0590, 0x05FF),
    "IsArabic": (0x0600, 0x06FF),
    "IsDevanagari": (0x0900, 0x097F),
    "IsThai": (0x0E00, 0x0E7F),
    "IsGeorgian": (0x10A0, 0x10FF),
    "IsLatinExtendedAdditional": (0x1E00, 0x1EFF),
    "IsGreekExtended": (0x1F00, 0x1FFF),
    "IsGeneralPunctuation": (0x2000, 0x206F),
    "IsCurrencySymbols": (0x20A0, 0x20CF),
    "IsLetterlikeSymbols": (0x2100, 0x214F),
    "IsNumberForms": (0x2150, 0x218F),
    "IsArrows": (0x2190, 0x21FF),
    "IsMathematicalOperators": (0x2200, 0x22FF),
    "IsCJKSymbolsandPunctuation": (0x3000, 0x303F),
    "IsHiragana": (0x3040, 0x309F),
    "IsKatakana": (0x30A0, 0x30FF),
    "IsCJKUnifiedIdeographs": (0x4E00, 0x9FFF),
    "IsHangulSyllables": (0xAC00, 0xD7A3),
}
_CLASS_SIZE = 26


@lru_cache(maxsize=256)
def _unicode_members(name: str, negated: bool) -> str | None:
    """Characters in (or, negated, outside) a category or block the tables above lack."""
    if name in _BLOCKS:
        lo, hi = _BLOCKS[name]
        if negated:
            return "a"
        found = [
            chr(c)
            for c in range(lo, hi + 1)
            if unicodedata.category(chr(c))[0] in "LNPS"
        ][:_CLASS_SIZE]
        return "".join(found) or None
    if not (1 <= len(name) <= 2 and name[0] in "LMNPZSC"):
        return None
    if negated:
        return next(
            (c for c in "a0 -+_" if not unicodedata.category(c).startswith(name)), None
        )
    # Printable members only: a control or format character is nothing to show.
    found = []
    for code in range(0x20, 0x3100):
        if unicodedata.category(chr(code)).startswith(name):
            found.append(chr(code))
            if len(found) == _CLASS_SIZE:
                break
    return "".join(found) or None


# Longest sample worth producing; a pattern that needs more goes unsampled.
_MAX_SAMPLE_CHARS = 200_000


# The parsed pattern: ("lit", text) | ("class", members) | ("seq", [node…]) |
# ("alt", [node…]) | ("rep", node, lo, hi).
_Node = tuple


class _Parser:
    def __init__(self, pattern: str) -> None:
        self.s = pattern
        self.i = 0

    def peek(self) -> str | None:
        return self.s[self.i] if self.i < len(self.s) else None

    def take(self) -> str:
        ch = self.s[self.i]
        self.i += 1
        return ch

    # alternation := branch ('|' branch)*
    def alternation(self) -> _Node:
        branches = [self.branch()]
        while self.peek() == "|":
            self.take()
            branches.append(self.branch())
        return branches[0] if len(branches) == 1 else ("alt", branches)

    def branch(self) -> _Node:
        out: list[_Node] = []
        while (ch := self.peek()) is not None and ch not in "|)":
            out.append(self.piece())
        return ("seq", out)

    def piece(self) -> _Node:
        atom = self.atom()
        lo, hi = self.quantifier()
        return atom if (lo, hi) == (1, 1) else ("rep", atom, lo, hi)

    def quantifier(self) -> tuple[int, int | None]:
        ch = self.peek()
        if ch == "?":
            self.take()
            return 0, 1
        if ch == "*":
            self.take()
            return 0, None
        if ch == "+":
            self.take()
            return 1, None
        if ch == "{":
            self.take()
            digits = ""
            while (c := self.peek()) is not None and c.isdigit():
                digits += self.take()
            if not digits:
                raise _UnsupportedError
            lo = int(digits)
            hi: int | None = lo
            if self.peek() == ",":
                self.take()
                more = ""
                while (c := self.peek()) is not None and c.isdigit():
                    more += self.take()
                hi = int(more) if more else None
            if self.peek() != "}":
                raise _UnsupportedError
            self.take()
            return lo, hi
        return 1, 1

    def atom(self) -> _Node:
        ch = self.take()
        if ch == "(":
            if self.peek() == "?":
                raise _UnsupportedError
            inner = self.alternation()
            if self.peek() != ")":
                raise _UnsupportedError
            self.take()
            return inner
        if ch == "[":
            return self.char_class()
        if ch == "\\":
            return self.escape()
        if ch == ".":
            return ("class", _LOWER)
        # ``^`` and ``$`` are not anchors in XSD regexes (every pattern is
        # implicitly anchored), so they fall through as literal characters.
        if ch in "*+?{":
            raise _UnsupportedError
        return ("lit", ch)

    def category(self, negated: bool) -> str:
        """Members for ``\\p{Name}`` / ``\\P{Name}``, the cursor just past the p."""
        if self.peek() != "{":
            raise _UnsupportedError
        self.take()
        name = ""
        while (c := self.peek()) is not None and c != "}":
            name += self.take()
        if self.peek() != "}":
            raise _UnsupportedError
        self.take()
        table = _OUTSIDE if negated else _CATEGORIES
        if name in table:
            return table[name]
        members = _unicode_members(name, negated)
        if members is None:
            raise _UnsupportedError
        return members

    def escape(self) -> _Node:
        ch = self.take()
        if ch in _ESCAPE_MEMBERS:
            return ("class", _ESCAPE_MEMBERS[ch])
        if ch in _ESCAPES:
            return ("lit", _ESCAPES[ch])
        if ch in "pP":
            return ("class", self.category(ch == "P"))
        return ("lit", ch)  # \. \- \\ \( etc. are literals

    def char_class(self) -> _Node:
        candidates, negated, excluded = self.class_members()
        if negated:
            for candidate in ("a", "0", " ", "x", "-"):
                if candidate not in candidates:
                    return ("lit", candidate)
            raise _UnsupportedError
        members = "".join(dict.fromkeys(m for m in candidates if m not in excluded))
        if not members:
            raise _UnsupportedError
        return ("class", members)

    def class_members(self) -> tuple[list[str], bool, list[str]]:
        """Parse ``[...]`` after the opening bracket; return candidate chars,
        whether the class is negated, and chars removed by subtraction."""
        negated = False
        if self.peek() == "^":
            self.take()
            negated = True
        members: list[str] = []
        excluded: list[str] = []
        first = True
        while True:
            ch = self.peek()
            if ch is None:
                raise _UnsupportedError
            if ch == "]" and not first:
                self.take()
                break
            first = False
            if ch == "-" and self.peek_at(1) == "[":
                self.take()
                self.take()
                sub, sub_negated, _ = self.class_members()
                if sub_negated:
                    raise _UnsupportedError
                excluded.extend(sub)
                continue
            self.take()
            if ch == "\\":
                esc = self.take()
                if esc in "pP":
                    members.extend(self.category(esc == "P"))
                    continue
                if esc in _ESCAPE_MEMBERS and self.peek() != "-":
                    members.extend(_ESCAPE_MEMBERS[esc])
                    continue
                start = _ESCAPES.get(esc, esc)
            else:
                start = ch
            if self.peek() == "-" and self.peek_at(1) not in (None, "]", "["):
                self.take()
                end = self.take()
                if end == "\\":
                    end = self.take()
                lo, hi = ord(start), ord(end)
                members.extend(chr(c) for c in range(lo, min(hi, lo + 25) + 1))
            else:
                members.append(start)
        return members, negated, excluded

    def peek_at(self, offset: int) -> str | None:
        j = self.i + offset
        return self.s[j] if j < len(self.s) else None


@dataclass
class _Style:
    """How one sample resolves the pattern's freedom."""

    # Open or ranged quantifiers repeat up to this many times (within bounds).
    stretch: int = 0
    # Which branch every alternation takes (modulo its branch count).
    branch: int = 0
    # Walk through a class's members instead of repeating the first one.
    rotate: bool = False
    position: int = 0
    # Characters produced by repetitions so far, to stop runaway samples.
    length: int = 0
    # Lengthen just one quantifier: the ``pad_at``-th one met takes ``pad``
    # extra repetitions. Stretching all of them overshoots an exact length
    # (\d*[1-9]\d* at length 6 would go from 3 characters straight to 13).
    pad_at: int = -1
    pad: int = 0
    quantifiers: int = 0


def _render(node: _Node, style: _Style) -> str:
    kind = node[0]
    if kind == "lit":
        return node[1]
    if kind == "class":
        members = node[1]
        if not style.rotate:
            return members[0]
        char = members[style.position % len(members)]
        style.position += 1
        return char
    if kind == "seq":
        return "".join(_render(child, style) for child in node[1])
    if kind == "alt":
        return _render(node[1][style.branch % len(node[1])], style)
    _, atom, lo, hi = node
    count = lo
    if style.stretch > lo:
        count = style.stretch if hi is None else min(hi, style.stretch)
    if style.quantifiers == style.pad_at:
        count = lo + style.pad if hi is None else min(hi, lo + style.pad)
    style.quantifiers += 1
    parts: list[str] = []
    for _ in range(count):
        part = _render(atom, style)
        if not part:
            break  # repeating nothing stays nothing
        style.length += len(part)
        if style.length > _MAX_SAMPLE_CHARS:
            # Nested repetition multiplies: (a+b+)+ stretched to a large
            # minLength would run to gigabytes.
            raise _UnsupportedError
        parts.append(part)
    return "".join(parts)


def _parse(pattern: str) -> _Node | None:
    try:
        parser = _Parser(pattern)
        tree = parser.alternation()
        if parser.peek() is not None:
            return None
        return tree
    except (_UnsupportedError, IndexError, RecursionError):
        return None


def _branch_count(node: _Node) -> int:
    kind = node[0]
    if kind == "alt":
        return max(len(node[1]), *(_branch_count(child) for child in node[1]))
    if kind == "seq":
        return max((_branch_count(child) for child in node[1]), default=1)
    if kind == "rep":
        return _branch_count(node[1])
    return 1


def sample_from_pattern(pattern: str, stretch: int = 0) -> str | None:
    """Return a string matching ``pattern`` or ``None`` when unsupported.

    By default every quantifier takes its minimum, which gives the shortest
    match -- often the empty string. ``stretch`` repeats open or ranged
    quantifiers up to that many times (within their bounds), which is how a
    caller reaches a ``minLength``.
    """
    tree = _parse(pattern)
    if tree is None:
        return None
    try:
        return _render(tree, _Style(stretch=stretch))
    except _UnsupportedError:
        return None


def _padded_styles(tree: _Node, min_length: int) -> list[_Style]:
    if min_length <= 0:
        return []
    try:
        probe = _Style()
        missing = min_length - len(_render(tree, probe))
    except _UnsupportedError:
        return []
    if missing <= 0:
        return []
    return [
        _Style(rotate=rotate, pad_at=index, pad=missing)
        for index in range(min(probe.quantifiers, 6))
        for rotate in (True, False)
    ]


def samples_from_pattern(pattern: str, min_length: int = 0, limit: int = 40) -> Iterator[str]:
    """Different strings matching ``pattern``, the most natural-looking first.

    A pattern rarely stands alone: a length, a range or a second pattern
    further up the derivation chain rules some matches out. So this offers
    several -- class members walked through (``AB12`` rather than ``AA00``),
    every alternation branch, and quantifiers at their minimum, once, and
    stretched to ``min_length`` -- and leaves the choice to the caller's
    check. Yields nothing when the pattern is unsupported.
    """
    tree = _parse(pattern)
    if tree is None:
        return
    stretches = [0, 1, 2, 3]
    if min_length > 0:
        stretches[1:1] = [min_length, (min_length + 1) // 2]
    seen: set[str] = set()
    empty_seen = False
    produced = 0
    # First the samples that reach min_length by lengthening a single quantifier.
    for style in _padded_styles(tree, min_length):
        try:
            value = _render(tree, style)
        except _UnsupportedError:
            continue
        if value and value not in seen:
            seen.add(value)
            produced += len(value)
            yield value
    for branch in range(min(_branch_count(tree), 8)):
        for stretch in dict.fromkeys(stretches):
            for rotate in (True, False):
                try:
                    value = _render(tree, _Style(stretch=stretch, branch=branch, rotate=rotate))
                except _UnsupportedError:
                    continue
                if value == "":
                    # An empty match is the least useful one; offer it last.
                    empty_seen = True
                    continue
                if value in seen:
                    continue
                seen.add(value)
                yield value
                produced += len(value)
                # A minLength in the tens of thousands makes every sample that long.
                if len(seen) >= limit or produced > _MAX_SAMPLE_CHARS:
                    return
    if empty_seen:
        yield ""
