"""Byte-signature engine used to locate patch sites inside a binary.

The whole point of this module is that we never trust a hard-coded file offset:
game updates move code around, but the instruction sequences we care about
(a comparison followed by a conditional branch, a ``SetParent`` call with fixed
800x600 arguments, ...) survive.  We therefore describe every patch site as a
*byte pattern* with ``??`` wildcards for the parts that legitimately change
between builds, and resolve the real offset at run time.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

__all__ = ["AmbiguousSignature", "PatternError", "Signature", "SignatureNotFound"]


class PatternError(ValueError):
    """The pattern text itself is malformed."""


class SignatureNotFound(LookupError):
    """No occurrence of the signature was found in the binary."""


class AmbiguousSignature(LookupError):
    """More than one occurrence was found; refusing to guess."""


def _parse_token(token: str) -> int | None:
    token = token.strip()
    if token in {"??", "?", "**"}:
        return None
    if len(token) != 2:
        raise PatternError(f"invalid byte token {token!r} (expected two hex digits or '??')")
    try:
        return int(token, 16)
    except ValueError as exc:  # pragma: no cover - defensive
        raise PatternError(f"invalid byte token {token!r}") from exc


@dataclass(frozen=True)
class Signature:
    """A byte pattern where ``??`` matches any single byte."""

    raw: str

    def __post_init__(self) -> None:
        tokens = tuple(self.raw.replace(",", " ").split())
        if not tokens:
            raise PatternError("empty signature")
        values = tuple(_parse_token(t) for t in tokens)
        object.__setattr__(self, "_tokens", tokens)
        object.__setattr__(self, "_values", values)
        anchor_start, anchor = self._longest_concrete_run(values)
        object.__setattr__(self, "_anchor_start", anchor_start)
        object.__setattr__(self, "_anchor", anchor)

    # -- construction helpers -------------------------------------------------
    @classmethod
    def from_bytes(cls, data: bytes) -> Signature:
        return cls(" ".join(f"{b:02X}" for b in data))

    @classmethod
    def join(cls, *parts: Signature | int) -> Signature:
        """Concatenate patterns; an ``int`` part inserts that many wildcards.

        Used to build ``before + gap + after`` where the gap covers the bytes a
        patch rewrites, so one pattern matches the binary in both states.
        """
        if not parts:
            raise PatternError("nothing to join")
        tokens: list[str] = []
        for part in parts:
            if isinstance(part, int):
                if part < 0:
                    raise PatternError("gap length must not be negative")
                tokens.extend(["??"] * part)
            else:
                tokens.extend(part.tokens)
        return cls(" ".join(tokens))

    @staticmethod
    def _longest_concrete_run(values: tuple[int | None, ...]) -> tuple[int, bytes]:
        best_start, best_len, start = 0, 0, None
        for index, value in enumerate((*values, None)):
            if value is None:
                if start is not None and index - start > best_len:
                    best_start, best_len = start, index - start
                start = None
            elif start is None:
                start = index
        if best_len == 0:  # pattern is entirely wildcards
            raise PatternError("signature needs at least one concrete byte")
        anchor = bytes(values[best_start : best_start + best_len])  # type: ignore[arg-type]
        return best_start, anchor

    # -- introspection --------------------------------------------------------
    @property
    def tokens(self) -> tuple[str, ...]:
        return self._tokens  # type: ignore[attr-defined]

    @property
    def values(self) -> tuple[int | None, ...]:
        return self._values  # type: ignore[attr-defined]

    def __len__(self) -> int:
        return len(self.values)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.raw

    # -- matching -------------------------------------------------------------
    def _candidates(self, data: bytes) -> Iterator[int]:
        anchor: bytes = self._anchor  # type: ignore[attr-defined]
        start: int = self._anchor_start  # type: ignore[attr-defined]
        position = data.find(anchor)
        while position != -1:
            candidate = position - start
            if candidate >= 0:
                yield candidate
            position = data.find(anchor, position + 1)

    def matches_at(self, data: bytes, offset: int) -> bool:
        if offset < 0 or offset + len(self) > len(data):
            return False
        return all(
            expected is None or data[offset + index] == expected
            for index, expected in enumerate(self.values)
        )

    def find_all(self, data: bytes) -> list[int]:
        """Return every offset where the pattern matches."""
        return [offset for offset in self._candidates(data) if self.matches_at(data, offset)]

    def find_unique(self, data: bytes, *, what: str = "signature") -> int:
        """Return the single offset where the pattern matches.

        Raises ``SignatureNotFound`` for zero hits and ``AmbiguousSignature``
        for more than one: guessing in either case would corrupt the binary.
        """
        hits = self.find_all(data)
        if not hits:
            raise SignatureNotFound(
                f"{what} not found - the game was probably updated and the pattern "
                f"needs refreshing: {self.raw}"
            )
        if len(hits) > 1:
            rendered = ", ".join(f"0x{hit:X}" for hit in hits[:8])
            raise AmbiguousSignature(
                f"{what} is ambiguous ({len(hits)} hits at {rendered}); refine the pattern"
            )
        return hits[0]
