"""Deterministic citation rules (no LLM): identifiers, source status, draft cross-check.

The rule that matters most is :func:`check_source`. A source the *model*
proposed is never presented as verified: it is ``unverified`` at best, and
``flagged`` (likely fabricated) when it carries no DOI, URL or ISBN. A source
the *user* supplied is ``supplied``; the tool cannot check online that it
exists and says so. There is no "verified" status anywhere in this recipe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Origin = Literal["user", "model"]
Status = Literal["supplied", "unverified", "flagged"]

_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)", re.IGNORECASE)
_URL = re.compile(r"\bhttps?://[^\s\"'<>]+", re.IGNORECASE)
_ISBN_LABELLED = re.compile(r"\bISBN(?:-1[03])?\s*:?\s*([0-9Xx][0-9Xx \-]{8,20}[0-9Xx])", re.I)
_ISBN_BARE = re.compile(r"(?<![\d-])(97[89][\d\-]{10,14}\d)(?![\d-])")
_TRAILING = ".,;:)]}"
_DOI_HOSTS = ("doi.org/", "dx.doi.org/")


def _strip_trailing(text: str) -> str:
    while text and text[-1] in _TRAILING:
        # keep a closing bracket that is part of the DOI, e.g. 10.1002/(SICI)...
        if text[-1] == ")" and text.count("(") >= text.count(")"):
            break
        text = text[:-1]
    return text


def isbn_valid(isbn: str) -> bool:
    """Check an ISBN-10 or ISBN-13 checksum (hyphens and spaces ignored)."""
    digits = re.sub(r"[\s-]", "", isbn).upper()
    if len(digits) == 10 and re.fullmatch(r"\d{9}[\dX]", digits):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
        return total % 11 == 0
    if len(digits) == 13 and digits.isdigit():
        total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(digits))
        return total % 10 == 0
    return False


@dataclass(frozen=True)
class Identifiers:
    """DOIs, URLs and ISBNs found in one reference (normalised for comparison)."""

    dois: frozenset[str] = frozenset()
    urls: frozenset[str] = frozenset()
    isbns: frozenset[str] = frozenset()
    invalid_isbns: frozenset[str] = frozenset()

    @property
    def any(self) -> bool:
        """At least one usable identifier (an ISBN with a wrong checksum does not count)."""
        return bool(self.dois or self.urls or self.isbns)

    def all(self) -> set[str]:
        return set(self.dois) | set(self.urls) | set(self.isbns)


def identifiers(text: str) -> Identifiers:
    """Find the identifiers in a reference. URLs pointing at doi.org count as the DOI."""
    dois = {_strip_trailing(m.group(1)).lower() for m in _DOI.finditer(text)}
    urls: set[str] = set()
    for m in _URL.finditer(text):
        url = _strip_trailing(m.group(0)).rstrip("/")
        if not any(host in url.lower() for host in _DOI_HOSTS):
            urls.add(url)
    valid: set[str] = set()
    invalid: set[str] = set()
    # Springer-style DOIs embed an ISBN ("10.1007/978-3-..."): search the rest only.
    rest = _URL.sub(" ", _DOI.sub(" ", text))
    raw_isbns = [m.group(1) for m in _ISBN_LABELLED.finditer(rest)]
    raw_isbns += [m.group(1) for m in _ISBN_BARE.finditer(rest)]
    for raw in raw_isbns:
        digits = re.sub(r"[\s-]", "", raw).upper()
        (valid if isbn_valid(digits) else invalid).add(digits)
    return Identifiers(frozenset(dois), frozenset(urls), frozenset(valid), frozenset(invalid))


@dataclass
class SourceCheck:
    """The verdict on one reference. ``flags`` are (code, values) pairs for the locale."""

    text: str
    origin: Origin
    status: Status
    flags: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def flag_codes(self) -> list[str]:
        return [code for code, _ in self.flags]

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "origin": self.origin,
            "status": self.status,
            "flags": [{"code": c, "values": v} for c, v in self.flags],
        }


def check_source(text: str, origin: Origin) -> SourceCheck:
    """Classify one reference by who produced it and what identifiers it carries.

    * model-proposed, no DOI/URL/valid ISBN -> ``flagged`` (likely fabricated)
    * model-proposed with an identifier     -> ``unverified`` (check it)
    * user-supplied                         -> ``supplied`` (not checked online)
    """
    ids = identifiers(text)
    check = SourceCheck(text=text, origin=origin, status="supplied")
    if ids.invalid_isbns:
        check.flags.append(("invalid_isbn", sorted(ids.invalid_isbns)))
    if origin == "model":
        check.status = "unverified"
        # Fabricated-citation guard: removing this branch makes
        # tests/recipes/academic/test_citations.py::TestFabricationGuard red.
        if not ids.any:
            check.status = "flagged"
            check.flags.append(("no_identifier", []))
    elif not ids.any:
        check.flags.append(("no_identifier", []))
    return check


def check_formatted(original: str, formatted: str) -> SourceCheck:
    """Check a reference the model formatted from one the user supplied.

    Any identifier in the formatted text that the user did not give was made up
    or recalled by the model, so the entry becomes ``unverified``.
    """
    check = check_source(original, "user")
    check.text = formatted
    before, after = identifiers(original), identifiers(formatted)
    added = sorted(after.all() - before.all())
    if added:
        check.status = "unverified"
        check.flags.append(("identifier_added_by_ai", added))
    dropped = sorted(before.all() - after.all())
    if dropped:
        check.flags.append(("identifier_dropped", dropped))
    return check


_NUMBERING = re.compile(r"^\s*(?:\[\d+\]|\d+[.)]|[-*•])\s+")


def split_references(text: str) -> list[str]:
    """Split a references file: blank-line separated blocks, else one per line.

    Leading numbering (``[1]``, ``1.``, ``-``) is removed; it is re-added for IEEE.
    """
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    blocks = re.split(r"\n\s*\n", text) if re.search(r"\n\s*\n", text) else text.split("\n")
    refs = [" ".join(_NUMBERING.sub("", b).split()) for b in blocks]
    return [r for r in refs if r and not _is_heading(r)]


# --- citations inside a draft -------------------------------------------------

_HEADING_WORDS = (
    "references",
    "reference list",
    "bibliography",
    "works cited",
    "rujukan",
    "senarai rujukan",
    "bibliografi",
)
_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(" + "|".join(_HEADING_WORDS) + r")(?:\*\*)?\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PAREN = re.compile(r"\(([^()]*?\b(?:1[5-9]|20)\d{2}[a-z]?\b[^()]*)\)")
_AUTHOR_YEAR = re.compile(
    r"([A-Z][A-Za-z'’\-]+)(?:\s+(?:et al\.?|dll\.?|&|and|dan)(?:\s+[A-Z][A-Za-z'’\-]+)?)?,?\s+"
    r"((?:1[5-9]|20)\d{2})[a-z]?"
)
_NARRATIVE = re.compile(
    r"\b([A-Z][A-Za-z'’\-]+)(?:\s+(?:et al\.?|dll\.?))?\s+\(((?:1[5-9]|20)\d{2})[a-z]?[,)]"
)
_NUMERIC = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")


def _is_heading(line: str) -> bool:
    return bool(_HEADING.fullmatch(line.strip()))


@dataclass
class DraftCitations:
    """What a deterministic pass found about citations in a draft."""

    in_text: list[str] = field(default_factory=list)
    references: list[SourceCheck] = field(default_factory=list)
    has_reference_list: bool = False
    cited_not_listed: list[str] = field(default_factory=list)
    listed_not_cited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "in_text": self.in_text,
            "has_reference_list": self.has_reference_list,
            "references": [r.to_dict() for r in self.references],
            "cited_not_listed": self.cited_not_listed,
            "listed_not_cited": self.listed_not_cited,
        }


def split_draft(text: str) -> tuple[str, str | None]:
    """(body, reference section or ``None``) using the last references heading."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return text, None
    last = matches[-1]
    return text[: last.start()], text[last.end() :]


def _numbers(spec: str) -> set[int]:
    out: set[int] = set()
    for part in re.split(r"\s*,\s*", spec):
        bounds = re.split(r"\s*[-–]\s*", part)
        if len(bounds) == 2 and all(b.isdigit() for b in bounds):
            lo, hi = int(bounds[0]), int(bounds[1])
            if 0 < hi - lo < 100 and hi < 1000:
                out.update(range(lo, hi + 1))
                continue
        if part.isdigit() and int(part) < 1000:  # "[2020]" is a year, not a source
            out.add(int(part))
    return out


def analyse_draft(text: str) -> DraftCitations:
    """Cross-check in-text citations against the draft's reference list.

    Handles author–year styles (APA, Harvard: ``(Tan, 2021)``, ``Tan (2021)``)
    and numeric styles (IEEE: ``[3]``). Reference entries are user-supplied.
    """
    body, ref_section = split_draft(text)
    result = DraftCitations(has_reference_list=ref_section is not None)
    entries = split_references(ref_section or "")
    result.references = [check_source(e, "user") for e in entries]

    pairs: list[tuple[str, str]] = []
    for m in _PAREN.finditer(body):
        for chunk in m.group(1).split(";"):
            pairs += [(a, y) for a, y in _AUTHOR_YEAR.findall(chunk)]
    pairs += _NARRATIVE.findall(body)
    numbers: set[int] = set()
    for m in _NUMERIC.finditer(body):
        numbers |= _numbers(m.group(1))

    seen: set[str] = set()
    for author, year in pairs:
        key = f"{author}, {year}"
        if key not in seen:
            seen.add(key)
            result.in_text.append(key)
    result.in_text += [f"[{n}]" for n in sorted(numbers)]

    if not result.has_reference_list:
        return result
    lowered = [e.lower() for e in entries]
    for key in result.in_text:
        if key.startswith("["):
            n = int(key[1:-1])
            if n > len(entries):
                result.cited_not_listed.append(key)
            continue
        author, year = key.split(", ")
        if not any(author.lower() in e and year in e for e in lowered):
            result.cited_not_listed.append(key)
    cited = [(a.lower(), y) for a, y in pairs]
    for i, entry in enumerate(entries, start=1):
        low = entry.lower()
        if numbers:
            if i not in numbers:
                result.listed_not_cited.append(entry)
        elif not any(a in low and y in low for a, y in cited):
            result.listed_not_cited.append(entry)
    return result
