"""Produce a string that matches a (simple) XSD regular expression.

Best effort only: literals, escapes, character classes, groups, alternation
and quantifiers are understood; anything else (``\\p{…}`` categories, nested
subtraction, back-references) makes ``sample_from_pattern`` return ``None``
so the caller can fall back to a type placeholder.
"""

from __future__ import annotations

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


class _UnsupportedError(Exception):
    pass


class _Parser:
    def __init__(self, pattern: str, stretch: int = 0) -> None:
        self.s = pattern
        self.i = 0
        self.stretch = stretch

    def peek(self) -> str | None:
        return self.s[self.i] if self.i < len(self.s) else None

    def take(self) -> str:
        ch = self.s[self.i]
        self.i += 1
        return ch

    # alternation := branch ('|' branch)*   — we take the first branch
    def alternation(self) -> str:
        first = self.branch()
        depth = 0
        # Skip the remaining branches at this level.
        while self.peek() == "|":
            self.take()
            while (ch := self.peek()) is not None:
                if ch == "\\":
                    self.take()
                    self.take()
                    continue
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == "|" and depth == 0:
                    break
                self.take()
        return first

    def branch(self) -> str:
        out: list[str] = []
        while (ch := self.peek()) is not None and ch not in "|)":
            out.append(self.piece())
        return "".join(out)

    def piece(self) -> str:
        atom = self.atom()
        lo, hi = self.quantifier()
        count = lo
        if self.stretch > lo:
            count = self.stretch if hi is None else min(hi, self.stretch)
        return atom * count

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

    def atom(self) -> str:
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
            return "a"
        # ``^`` and ``$`` are not anchors in XSD regexes (every pattern is
        # implicitly anchored), so they fall through as literal characters.
        if ch in "*+?{":
            raise _UnsupportedError
        return ch

    def escape(self) -> str:
        ch = self.take()
        if ch in _ESCAPES:
            return _ESCAPES[ch]
        if ch in "pP":
            raise _UnsupportedError
        return ch  # \. \- \\ \( etc. are literals

    def char_class(self) -> str:
        candidates, negated, excluded = self.class_members()
        if negated:
            for candidate in ("a", "0", " ", "x", "-"):
                if candidate not in candidates:
                    return candidate
            raise _UnsupportedError
        for m in candidates:
            if m not in excluded:
                return m
        raise _UnsupportedError

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
                    raise _UnsupportedError
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


def sample_from_pattern(pattern: str, stretch: int = 0) -> str | None:
    """Return a string matching ``pattern`` or ``None`` when unsupported.

    By default every quantifier takes its minimum, which gives the shortest
    match -- often the empty string. ``stretch`` repeats open or ranged
    quantifiers up to that many times (within their bounds), which is how a
    caller reaches a ``minLength``.
    """
    try:
        parser = _Parser(pattern, stretch)
        result = parser.alternation()
        if parser.peek() is not None:
            return None
        return result
    except (_UnsupportedError, IndexError):
        return None
