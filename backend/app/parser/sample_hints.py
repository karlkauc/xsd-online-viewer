"""Example values suggested by what an element or attribute is called.

A ``Currency`` reads better as ``EUR`` than as ``string``. The values here
are only ever *offered*: the sample generator checks each one against the
declared type and facets and falls back to its placeholder when none fits,
so a hint can make a sample more plausible but never less valid.
"""

from __future__ import annotations

import re

# Keywords are matched against the name's words (``SystemCountry`` → system,
# country) and against runs of adjacent words (first + name → firstname), so
# ``tel`` does not fire inside ``Hotel``. Earlier rules win.
_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("isin",), ("US0378331005", "DE000BAY0017", "AT0000937503")),
    (("lei",), ("5493001KJTIIGC8Y1R12", "529900T8BM49AURSDO55")),
    (("iban",), ("AT611904300234573201", "DE89370400440532013000")),
    (("bic", "swift", "swiftbic"), ("BKAUATWW", "DEUTDEFF")),
    (("uuid", "guid"), ("123e4567-e89b-12d3-a456-426614174000",)),
    (("currency", "ccy", "waehrung", "währung"), ("EUR", "USD", "CHF")),
    (("country", "nation", "nationality", "land", "staat"), ("AT", "DE", "CH")),
    (("language", "lang", "sprache", "locale"), ("en", "de")),
    (("email", "mail"), ("max.mustermann@example.com", "erika.musterfrau@example.com")),
    (
        ("url", "uri", "website", "homepage", "href", "link"),
        ("https://www.example.com/", "https://www.example.org/"),
    ),
    (("phone", "telephone", "telefon", "tel", "fax", "mobile"), ("+43 1 234567", "+49 30 123456")),
    (("firstname", "givenname", "forename", "vorname"), ("Max", "Erika")),
    (
        ("lastname", "surname", "familyname", "nachname", "familienname"),
        ("Mustermann", "Musterfrau"),
    ),
    (("username", "user", "login", "benutzer"), ("mmustermann", "emusterfrau")),
    (("street", "strasse", "straße", "addressline"), ("Musterstrasse 1", "Beispielweg 2")),
    (("city", "town", "ort", "stadt"), ("Wien", "Berlin")),
    (("zip", "zipcode", "postcode", "postalcode", "plz"), ("1010", "10115")),
    (("version",), ("1.0", "1.1")),
    (("filename", "file"), ("example.xml", "example.pdf")),
    (("mimetype", "contenttype", "mediatype"), ("application/xml", "text/plain")),
    (("title", "titel", "subject", "betreff"), ("Example title", "Another title")),
    (
        ("description", "beschreibung", "comment", "kommentar", "remark", "note", "bemerkung"),
        ("Example text", "Another example text"),
    ),
    (("name", "bezeichnung"), ("Example Name", "Another Name")),
]
_HINTS = {keyword: values for keywords, values in _RULES for keyword in keywords}
# Types whose every lexical value is a URI; only the URL rule makes sense there.
_URI_KEYWORDS = frozenset(("url", "uri", "website", "homepage", "href", "link"))

_WORD = re.compile(r"[A-ZÄÖÜ]+(?![a-zäöüß])|[A-ZÄÖÜ]?[a-zäöüß]+|\d+")


def _words(name: str) -> list[str]:
    return [word.lower() for word in _WORD.findall(name)]


def hinted_values(name: str | None, builtin: str) -> tuple[str, ...]:
    """Plausible values for something called ``name``, best first; empty when the name says nothing."""
    if not name:
        return ()
    words = _words(name)
    # The last words carry the meaning (``FundName`` is a name, not a fund),
    # and a longer run is more specific than a single word.
    for size in (3, 2, 1):
        for start in range(len(words) - size, -1, -1):
            keyword = "".join(words[start : start + size])
            values = _HINTS.get(keyword)
            if values is None:
                continue
            if builtin == "anyURI" and keyword not in _URI_KEYWORDS:
                return ()
            return values
    return ()
